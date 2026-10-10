"""
Async MongoDB database management using Motor driver
"""

import logging
from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings

from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def get_mongo_host(url: str) -> str:
    """Extract host info from MongoDB connection string without credentials"""
    try:
        parsed = urlparse(url)
        host = parsed.hostname or "localhost"
        port = f":{parsed.port}" if parsed.port else ""
        return f"{host}{port}"
    except Exception:
        return "configured-host"


class Database:
    client: AsyncIOMotorClient = None
    db = None


db_manager = Database()


async def connect_to_mongo():
    """Establish async connection pool to MongoDB"""
    try:
        host_info = get_mongo_host(settings.MONGODB_URL)
        logger.info(f"Connecting to MongoDB host '{host_info}'...")
        db_manager.client = AsyncIOMotorClient(
            settings.MONGODB_URL,
            serverSelectionTimeoutMS=3000
        )
        db_manager.db = db_manager.client[settings.DATABASE_NAME]
        logger.info(f"Connected to MongoDB database '{settings.DATABASE_NAME}'")
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


def get_db():
    """Dependency to retrieve active MongoDB database instance"""
    return db_manager.db
