"""
Main FastAPI Application Entry Point for SherLog Backend
"""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import connect_to_mongo, close_mongo_connection
from app.api.health import router as health_router
from app.api.incidents import router as incidents_router
from app.api.logs import router as logs_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application Lifespan Context Manager
    Handles startup (DB connection) and shutdown (cleanup) events
    """
    logger.info("Initializing SherLog Backend application...")
    await connect_to_mongo()
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
