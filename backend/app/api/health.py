"""
Health Check Router for FastAPI Backend
"""

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from app.core.database import check_db_health

router = APIRouter()


@router.get(
    "/health",
    summary="Service & Database Health Status",
    response_description="Returns HTTP status and MongoDB connectivity state"
)
async def health_check():
    """
    Check operational status of FastAPI server and MongoDB connection
    """
    db_healthy = await check_db_health()
    overall_status = "healthy" if db_healthy else "degraded"
    
    http_status_code = (
        status.HTTP_200_OK if db_healthy else status.HTTP_503_SERVICE_UNAVAILABLE
    )
    
    return JSONResponse(
        status_code=http_status_code,
        content={
            "status": overall_status,
            "service": "sherlog-backend",
            "database": "connected" if db_healthy else "disconnected"
        }
    )
