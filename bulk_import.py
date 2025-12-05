#!/usr/bin/env python3
"""
Bulk import script for caller-IDs from CSV file

Usage:
    python bulk_import.py caller_ids.csv

CSV Format:
    caller_id,carrier,area_code,daily_limit,hourly_limit,meta_json
    5551234567,Verizon,555,1000,100,{"state":"CA","type":"mobile"}
"""
import asyncio
import csv
import json
import sys
import os
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import AsyncSessionLocal, init_db
from app.models import CallerID
from app.config import settings

async def import_caller_ids(csv_file: str):
    """Import caller-IDs from CSV file"""
    print(f"Starting bulk import from {csv_file}...")
    
    # Initialize database
    await init_db()
    
    imported = 0
    skipped = 0
    errors = 0
    
    async with AsyncSessionLocal() as db:
        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            
            for row_num, row in enumerate(reader, start=2):  # Start at 2 (header is row 1)
                try:
                    # Extract fields
                    caller_id = row.get('caller_id', '').strip()
                    if not caller_id:
                        print(f"Row {row_num}: Skipping - no caller_id")
                        skipped += 1
                        continue
                    
                    # Check if already exists
                    from sqlalchemy import select
                    existing = await db.execute(
                        select(CallerID).where(CallerID.caller_id == caller_id)
                    )
                    if existing.scalar_one_or_none():
                        print(f"Row {row_num}: Skipping {caller_id} - already exists")
                        skipped += 1
                        continue
                    
                    # Parse optional fields
                    carrier = row.get('carrier', '').strip() or None
                    area_code = row.get('area_code', '').strip() or None
                    
                    # Extract area code from caller_id if not provided
                    if not area_code:
                        digits = ''.join(filter(str.isdigit, caller_id))
                        if len(digits) >= 3:
                            area_code = digits[:3]
                    
                    daily_limit = int(row.get('daily_limit', settings.DEFAULT_DAILY_LIMIT))
                    hourly_limit = int(row.get('hourly_limit', settings.DEFAULT_HOURLY_LIMIT))
                    
                    # Parse meta JSON if provided
                    meta = None
                    if row.get('meta_json'):
                        try:
                            meta = json.loads(row['meta_json'])
                        except json.JSONDecodeError:
                            print(f"Row {row_num}: Warning - invalid JSON in meta_json, ignoring")
                    
                    # Create caller-ID
                    caller_id_obj = CallerID(
                        caller_id=caller_id,
                        carrier=carrier,
                        area_code=area_code,
                        daily_limit=daily_limit,
                        hourly_limit=hourly_limit,
                        meta=meta
                    )
                    
                    db.add(caller_id_obj)
                    imported += 1
                    
                    if imported % 100 == 0:
                        await db.commit()
                        print(f"Imported {imported} caller-IDs...")
                    
                except Exception as e:
                    print(f"Row {row_num}: Error - {e}")
                    errors += 1
                    continue
            
            # Final commit
            await db.commit()
    
    print(f"\nImport complete!")
    print(f"  Imported: {imported}")
    print(f"  Skipped: {skipped}")
    print(f"  Errors: {errors}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python bulk_import.py <csv_file>")
        sys.exit(1)
    
    csv_file = sys.argv[1]
    if not os.path.exists(csv_file):
        print(f"Error: File {csv_file} not found")
        sys.exit(1)
    
    asyncio.run(import_caller_ids(csv_file))
