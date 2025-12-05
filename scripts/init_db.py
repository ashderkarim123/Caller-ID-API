#!/usr/bin/env python3
"""
Database initialization script
Creates tables and optionally adds sample data
"""
import asyncio
import sys
import os
import logging

# Add parent directory to path to import app modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy.ext.asyncio import create_async_engine
from app.models import Base, CallerID
from app.config import settings
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def init_database(add_sample_data: bool = False):
    """Initialize database tables"""
    logger.info("Initializing database...")
    
    # Create async engine
    engine = create_async_engine(
        settings.database_url,
        echo=True,
        pool_size=10
    )
    
    try:
        # Create all tables
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        
        logger.info("Database tables created successfully")
        
        # Add sample data if requested
        if add_sample_data:
            await add_sample_caller_ids(engine)
    
    except Exception as e:
        logger.error(f"Error initializing database: {e}", exc_info=True)
        raise
    finally:
        await engine.dispose()


async def add_sample_caller_ids(engine):
    """Add sample caller-IDs for testing"""
    logger.info("Adding sample caller-IDs...")
    
    async_session = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False
    )
    
    sample_caller_ids = [
        CallerID(caller_id="2125551001", carrier="AT&T", area_code="212", hourly_limit=100, daily_limit=500, is_active=1),
        CallerID(caller_id="2125551002", carrier="Verizon", area_code="212", hourly_limit=100, daily_limit=500, is_active=1),
        CallerID(caller_id="2135552001", carrier="T-Mobile", area_code="213", hourly_limit=150, daily_limit=750, is_active=1),
        CallerID(caller_id="2135552002", carrier="Sprint", area_code="213", hourly_limit=150, daily_limit=750, is_active=1),
        CallerID(caller_id="3105553001", carrier="AT&T", area_code="310", hourly_limit=200, daily_limit=1000, is_active=1),
        CallerID(caller_id="3105553002", carrier="Verizon", area_code="310", hourly_limit=200, daily_limit=1000, is_active=1),
        CallerID(caller_id="4155554001", carrier="T-Mobile", area_code="415", hourly_limit=100, daily_limit=500, is_active=1),
        CallerID(caller_id="4155554002", carrier="Sprint", area_code="415", hourly_limit=100, daily_limit=500, is_active=1),
        CallerID(caller_id="7025555001", carrier="AT&T", area_code="702", hourly_limit=150, daily_limit=750, is_active=1),
        CallerID(caller_id="7025555002", carrier="Verizon", area_code="702", hourly_limit=150, daily_limit=750, is_active=1),
    ]
    
    async with async_session() as session:
        try:
            session.add_all(sample_caller_ids)
            await session.commit()
            logger.info(f"Added {len(sample_caller_ids)} sample caller-IDs")
        except Exception as e:
            await session.rollback()
            logger.error(f"Error adding sample data: {e}")


async def drop_all_tables():
    """Drop all database tables (use with caution!)"""
    logger.warning("Dropping all database tables...")
    
    engine = create_async_engine(
        settings.database_url,
        echo=True
    )
    
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        
        logger.info("All tables dropped successfully")
    
    except Exception as e:
        logger.error(f"Error dropping tables: {e}", exc_info=True)
        raise
    finally:
        await engine.dispose()


async def reset_database(add_sample_data: bool = False):
    """Drop and recreate all tables"""
    logger.warning("Resetting database (dropping and recreating tables)...")
    await drop_all_tables()
    await init_database(add_sample_data)
    logger.info("Database reset complete")


def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Database initialization script')
    parser.add_argument('--reset', action='store_true',
                        help='Drop and recreate all tables')
    parser.add_argument('--sample-data', action='store_true',
                        help='Add sample caller-IDs')
    parser.add_argument('--drop', action='store_true',
                        help='Drop all tables (use with caution!)')
    
    args = parser.parse_args()
    
    try:
        if args.drop:
            confirm = input("Are you sure you want to drop all tables? (yes/no): ")
            if confirm.lower() == 'yes':
                asyncio.run(drop_all_tables())
            else:
                logger.info("Operation cancelled")
        elif args.reset:
            confirm = input("Are you sure you want to reset the database? (yes/no): ")
            if confirm.lower() == 'yes':
                asyncio.run(reset_database(args.sample_data))
            else:
                logger.info("Operation cancelled")
        else:
            asyncio.run(init_database(args.sample_data))
    
    except KeyboardInterrupt:
        logger.info("Operation cancelled by user")
    except Exception as e:
        logger.error(f"Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
