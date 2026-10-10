"""
Async MongoDB database management using Motor driver
"""

import logging
from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings

logger = logging.getLogger(__name__)


class Database:
    client: AsyncIOMotorClient = None
    db = None


db_manager = Database()


async def connect_to_mongo():
    """Establish async connection pool to MongoDB"""
    try:
        logger.info(f"Connecting to MongoDB at {settings.MONGODB_URL}...")
        db_manager.client = AsyncIOMotorClient(
            settings.MONGODB_URL,
            serverSelectionTimeoutMS=3000
        )
        db_manager.db = db_manager.client[settings.DATABASE_NAME]
        logger.info(f"Connected to MongoDB database: {settings.DATABASE_NAME}")
    except Exception as e:
        logger.error(f"Failed to connect to MongoDB: {e}")
        db_manager.client = None
        db_manager.db = None


async def close_mongo_connection():
    """Gracefully close MongoDB connection pool"""
    if db_manager.client:
        logger.info("Closing MongoDB connection pool...")
        db_manager.client.close()
        logger.info("MongoDB connection closed.")


async def check_db_health() -> bool:
    """Check if MongoDB server is responsive via ping command"""
    if db_manager.client is None:
        return False
    try:
        await db_manager.client.admin.command('ping')
        return True
    except Exception as e:
        logger.warning(f"MongoDB health ping failed: {e}")
        return False
