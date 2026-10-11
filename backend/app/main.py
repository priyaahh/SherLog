"""
Main FastAPI Application Entry Point for SherLog Backend
"""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import connect_to_mongo, close_mongo_connection, db_manager
from app.services.investigation_service import cleanup_interrupted_investigations
from app.api.health import router as health_router
from app.api.incidents import router as incidents_router
from app.api.logs import router as logs_router
from app.api.investigations import router as investigations_router
from app.api.reports import router as reports_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application Lifespan Context Manager
    Handles startup (DB connection and cleanup of interrupted tasks) and shutdown (cleanup) events
    """
    logger.info("Initializing SherLog Backend application...")
    await connect_to_mongo()
    if db_manager.db is not None:
        await cleanup_interrupted_investigations(db_manager.db)
    yield
    logger.info("Shutting down SherLog Backend application...")
    await close_mongo_connection()


app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan
)

# CORS middleware configuration for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API Routers
app.include_router(health_router, prefix=settings.API_V1_STR, tags=["Health"])
app.include_router(health_router, tags=["Health"])  # Root /health shortcut
app.include_router(incidents_router, prefix=settings.API_V1_STR, tags=["Incidents"])
app.include_router(logs_router, prefix=settings.API_V1_STR, tags=["Logs"])
app.include_router(investigations_router, prefix=settings.API_V1_STR, tags=["Investigations"])
app.include_router(reports_router, prefix=settings.API_V1_STR, tags=["Reports"])
