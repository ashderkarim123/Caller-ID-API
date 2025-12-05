#!/usr/bin/env python3
"""
Bulk import script for caller-IDs from CSV file
Supports both direct database import and API import
"""
import asyncio
import csv
import sys
import os
import argparse
from typing import List, Dict
import logging

# Add parent directory to path to import app modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.models import CallerID
from app.config import settings
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def extract_area_code(phone_number: str) -> str:
    """Extract area code from phone number"""
    import re
    cleaned = re.sub(r'\D', '', phone_number)
    
    if len(cleaned) == 10:
        return cleaned[:3]
    elif len(cleaned) == 11 and cleaned.startswith('1'):
        return cleaned[1:4]
    elif len(cleaned) >= 3:
        return cleaned[:3]
    
    return '000'


async def bulk_import_to_db(csv_file: str, batch_size: int = 1000):
    """
    Import caller-IDs directly to database in batches
    CSV format: caller_id,carrier,area_code,hourly_limit,daily_limit
    """
    logger.info(f"Starting bulk import from {csv_file}")
    
    # Create database engine
    engine = create_async_engine(
        settings.database_url,
        echo=False,
        pool_size=10,
        max_overflow=20
    )
    
    async_session = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False
    )
    
    try:
        # Read CSV file
        caller_ids = []
        with open(csv_file, 'r') as f:
            reader = csv.DictReader(f)
            
            for row in reader:
                caller_id = row.get('caller_id', '').strip()
                if not caller_id:
                    continue
                
                # Extract or use provided area code
                area_code = row.get('area_code', '').strip()
                if not area_code:
                    area_code = extract_area_code(caller_id)
                
                caller_id_obj = CallerID(
                    caller_id=caller_id,
                    carrier=row.get('carrier', '').strip() or None,
                    area_code=area_code,
                    hourly_limit=int(row.get('hourly_limit', settings.DEFAULT_HOURLY_LIMIT)),
                    daily_limit=int(row.get('daily_limit', settings.DEFAULT_DAILY_LIMIT)),
                    is_active=1,
                    meta={'imported_at': datetime.utcnow().isoformat()}
                )
                
                caller_ids.append(caller_id_obj)
        
        logger.info(f"Read {len(caller_ids)} caller-IDs from CSV")
        
        if not caller_ids:
            logger.warning("No caller-IDs found in CSV file")
            return
        
        # Insert in batches
        total_inserted = 0
        total_skipped = 0
        
        for i in range(0, len(caller_ids), batch_size):
            batch = caller_ids[i:i + batch_size]
            
            async with async_session() as session:
                try:
                    session.add_all(batch)
                    await session.commit()
                    total_inserted += len(batch)
                    logger.info(f"Inserted batch {i // batch_size + 1}: {len(batch)} caller-IDs (Total: {total_inserted}/{len(caller_ids)})")
                except Exception as e:
                    await session.rollback()
                    logger.error(f"Error inserting batch: {e}")
                    
                    # Try inserting one by one to skip duplicates
                    for cid_obj in batch:
                        try:
                            async with async_session() as retry_session:
                                retry_session.add(cid_obj)
                                await retry_session.commit()
                                total_inserted += 1
                        except Exception as retry_e:
                            total_skipped += 1
                            logger.warning(f"Skipped duplicate or invalid caller-ID: {cid_obj.caller_id}")
        
        logger.info(f"Bulk import completed: {total_inserted} inserted, {total_skipped} skipped")
    
    except FileNotFoundError:
        logger.error(f"CSV file not found: {csv_file}")
    except Exception as e:
        logger.error(f"Error during bulk import: {e}", exc_info=True)
    finally:
        await engine.dispose()


async def bulk_import_via_api(csv_file: str, api_url: str, admin_token: str):
    """
    Import caller-IDs via API endpoint
    Slower but more reliable for production systems
    """
    import httpx
    
    logger.info(f"Starting API-based bulk import from {csv_file}")
    
    try:
        # Read CSV file
        caller_ids = []
        with open(csv_file, 'r') as f:
            reader = csv.DictReader(f)
            
            for row in reader:
                caller_id = row.get('caller_id', '').strip()
                if not caller_id:
                    continue
                
                area_code = row.get('area_code', '').strip()
                if not area_code:
                    area_code = extract_area_code(caller_id)
                
                caller_ids.append({
                    'caller_id': caller_id,
                    'carrier': row.get('carrier', '').strip() or None,
                    'area_code': area_code,
                    'hourly_limit': int(row.get('hourly_limit', settings.DEFAULT_HOURLY_LIMIT)),
                    'daily_limit': int(row.get('daily_limit', settings.DEFAULT_DAILY_LIMIT))
                })
        
        logger.info(f"Read {len(caller_ids)} caller-IDs from CSV")
        
        if not caller_ids:
            logger.warning("No caller-IDs found in CSV file")
            return
        
        # Import via API
        total_success = 0
        total_failed = 0
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            for idx, cid_data in enumerate(caller_ids, 1):
                try:
                    response = await client.post(
                        f"{api_url}/add-number",
                        params=cid_data,
                        headers={'Authorization': f'Bearer {admin_token}'}
                    )
                    
                    if response.status_code == 200:
                        total_success += 1
                        if idx % 100 == 0:
                            logger.info(f"Progress: {idx}/{len(caller_ids)} ({total_success} success, {total_failed} failed)")
                    else:
                        total_failed += 1
                        logger.warning(f"Failed to add {cid_data['caller_id']}: {response.text}")
                
                except Exception as e:
                    total_failed += 1
                    logger.error(f"Error adding {cid_data['caller_id']}: {e}")
                
                # Rate limiting - don't overwhelm the API
                if idx % 10 == 0:
                    await asyncio.sleep(0.1)
        
        logger.info(f"API import completed: {total_success} success, {total_failed} failed")
    
    except FileNotFoundError:
        logger.error(f"CSV file not found: {csv_file}")
    except Exception as e:
        logger.error(f"Error during API import: {e}", exc_info=True)


def generate_sample_csv(output_file: str, count: int = 100):
    """Generate a sample CSV file with random caller-IDs"""
    import random
    
    logger.info(f"Generating sample CSV with {count} caller-IDs")
    
    area_codes = ['212', '213', '214', '215', '216', '217', '218', '219', '220', '224',
                  '225', '227', '228', '229', '231', '234', '239', '240', '248', '251']
    
    carriers = ['AT&T', 'Verizon', 'T-Mobile', 'Sprint', 'US Cellular', 'Cricket', 'Metro PCS']
    
    with open(output_file, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['caller_id', 'carrier', 'area_code', 'hourly_limit', 'daily_limit'])
        writer.writeheader()
        
        for i in range(count):
            area_code = random.choice(area_codes)
            number = f"{area_code}{random.randint(2000000, 9999999)}"
            
            writer.writerow({
                'caller_id': number,
                'carrier': random.choice(carriers),
                'area_code': area_code,
                'hourly_limit': random.choice([50, 100, 150, 200]),
                'daily_limit': random.choice([300, 500, 1000, 1500])
            })
    
    logger.info(f"Sample CSV generated: {output_file}")


def main():
    """Main function"""
    parser = argparse.ArgumentParser(description='Bulk import caller-IDs from CSV')
    parser.add_argument('--csv', type=str, help='Path to CSV file')
    parser.add_argument('--method', type=str, choices=['db', 'api'], default='db',
                        help='Import method: db (direct) or api (via API endpoint)')
    parser.add_argument('--api-url', type=str, default='http://localhost:8000',
                        help='API URL (for api method)')
    parser.add_argument('--admin-token', type=str,
                        help='Admin token (for api method)')
    parser.add_argument('--batch-size', type=int, default=1000,
                        help='Batch size for database import')
    parser.add_argument('--generate-sample', type=str,
                        help='Generate sample CSV file with given filename')
    parser.add_argument('--sample-count', type=int, default=100,
                        help='Number of sample records to generate')
    
    args = parser.parse_args()
    
    # Generate sample CSV if requested
    if args.generate_sample:
        generate_sample_csv(args.generate_sample, args.sample_count)
        return
    
    # Validate required arguments
    if not args.csv:
        parser.error("--csv is required (or use --generate-sample)")
    
    if not os.path.exists(args.csv):
        logger.error(f"CSV file not found: {args.csv}")
        sys.exit(1)
    
    # Run import
    if args.method == 'db':
        asyncio.run(bulk_import_to_db(args.csv, args.batch_size))
    elif args.method == 'api':
        if not args.admin_token:
            parser.error("--admin-token is required for API import")
        asyncio.run(bulk_import_via_api(args.csv, args.api_url, args.admin_token))


if __name__ == '__main__':
    main()
