#!/usr/bin/env python3
"""Bulk import caller IDs from CSV via API or direct DB."""

from __future__ import annotations

import argparse
import asyncio
import csv
import os
import sys
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy.exc import IntegrityError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db import AsyncSessionMaker  # noqa: E402
from app.models import CallerID  # noqa: E402
from app.utils import extract_area_code, normalize_phone  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bulk import caller IDs")
    parser.add_argument("--csv", required=True, help="Path to CSV file")
    parser.add_argument("--api-url", default="http://127.0.0.1:8000", help="FastAPI base URL")
    parser.add_argument("--admin-token", help="Admin token for /add-number")
    parser.add_argument("--concurrency", type=int, default=20, help="Concurrent API workers")
    parser.add_argument(
        "--mode",
        choices=["api", "db"],
        default="api",
        help="Send records via FastAPI (api) or directly into Postgres (db)",
    )
    parser.add_argument("--batch", type=int, default=1000, help="DB insert batch size")
    return parser.parse_args()


def read_rows(csv_path: str) -> list[dict[str, Any]]:
    with open(csv_path, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = [row for row in reader]
    return rows


async def import_via_api(rows: list[dict[str, Any]], args: argparse.Namespace) -> None:
    headers = {"X-Admin-Token": args.admin_token or os.getenv("ADMIN_TOKEN", "")}
    if not headers["X-Admin-Token"]:
        raise RuntimeError("Admin token required for API mode")
    sem = asyncio.Semaphore(args.concurrency)

    async with httpx.AsyncClient(base_url=args.api_url, timeout=None) as client:

        async def worker(row: dict[str, Any]) -> None:
            async with sem:
                payload = build_payload(row)
                response = await client.post("/add-number", json=payload, headers=headers)
                if response.status_code >= 400:
                    print(f"Failed to import {payload['caller_id']}: {response.text}")

        await asyncio.gather(*(worker(row) for row in rows))


async def import_via_db(rows: list[dict[str, Any]], args: argparse.Namespace) -> None:
    async with AsyncSessionMaker() as session:
        batch: list[CallerID] = []
        for row in rows:
            payload = build_payload(row)
            caller = CallerID(
                caller_id=payload["caller_id"],
                carrier=payload.get("carrier"),
                area_code=payload.get("area_code"),
                daily_limit=payload.get("daily_limit") or 500,
                hourly_limit=payload.get("hourly_limit") or 50,
                meta=payload.get("meta"),
            )
            batch.append(caller)
            if len(batch) >= args.batch:
                await _flush_batch(session, batch)
                batch.clear()
        if batch:
            await _flush_batch(session, batch)


def build_payload(row: dict[str, Any]) -> dict[str, Any]:
    caller_id = normalize_phone(row.get("caller_id", ""))
    if not caller_id:
        raise ValueError("caller_id column is required")
    area_code = row.get("area_code") or extract_area_code(caller_id)
    payload: dict[str, Any] = {
        "caller_id": caller_id,
        "carrier": row.get("carrier") or None,
        "area_code": area_code,
        "daily_limit": int(row.get("daily_limit", 500) or 500),
        "hourly_limit": int(row.get("hourly_limit", 50) or 50),
        "meta": {"source": "bulk-import"},
    }
    return payload


async def _flush_batch(session, batch: list[CallerID]) -> None:
    session.add_all(batch)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        for record in batch:
            session.add(record)
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                print(f"Skipped existing caller ID {record.caller_id}")


async def main() -> None:
    args = parse_args()
    rows = read_rows(args.csv)
    if args.mode == "api":
        await import_via_api(rows, args)
    else:
        await import_via_db(rows, args)


if __name__ == "__main__":
    asyncio.run(main())
