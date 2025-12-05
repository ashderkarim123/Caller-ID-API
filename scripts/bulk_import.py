#!/usr/bin/env python3
"""Bulk import caller IDs from CSV via the FastAPI endpoint."""

from __future__ import annotations

import argparse
import asyncio
import csv
from pathlib import Path
from typing import Any, Dict, List

import httpx


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bulk add caller IDs to the rotation API")
    parser.add_argument("csv_path", type=Path, help="CSV file with caller_id,carrier,area_code")
    parser.add_argument(
        "--api",
        default="http://127.0.0.1:8000",
        help="Base URL of the API (default: http://127.0.0.1:8000)",
    )
    parser.add_argument("--token", required=True, help="Admin token for /add-number")
    parser.add_argument("--concurrency", type=int, default=20, help="Concurrent requests")
    return parser.parse_args()


def load_rows(csv_path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with csv_path.open("r", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            rows.append(
                {
                    "caller_id": row.get("caller_id") or row.get("CallerID"),
                    "carrier": row.get("carrier"),
                    "area_code": row.get("area_code"),
                    "daily_limit": int(row["daily_limit"]) if row.get("daily_limit") else None,
                    "hourly_limit": int(row["hourly_limit"]) if row.get("hourly_limit") else None,
                }
            )
    return rows


async def submit_row(client: httpx.AsyncClient, token: str, payload: Dict[str, Any]) -> None:
    headers = {"X-Admin-Token": token}
    response = await client.post("/add-number", json=payload, headers=headers, timeout=20)
    response.raise_for_status()


async def run_import(args: argparse.Namespace) -> None:
    rows = load_rows(args.csv_path)
    total = len(rows)
    print(f"Importing {total} caller IDs ...")
    semaphore = asyncio.Semaphore(args.concurrency)

    async with httpx.AsyncClient(base_url=args.api) as client:

        async def bounded_submit(payload: Dict[str, Any]) -> None:
            async with semaphore:
                try:
                    await submit_row(client, args.token, payload)
                    print(f"OK {payload['caller_id']}")
                except httpx.HTTPError as exc:  # pragma: no cover - CLI feedback
                    print(f"Failed {payload['caller_id']}: {exc}")

        await asyncio.gather(*(bounded_submit(row) for row in rows))


def main() -> None:
    args = parse_args()
    asyncio.run(run_import(args))


if __name__ == "__main__":
    main()
