"""
Logs API Router for Log Upload and Retrieval
"""

from fastapi import APIRouter, status, UploadFile, File, Depends
from app.core.database import db_manager, get_db
from app.models.log import LogResponse
from app.services.log_service import LogService

router = APIRouter()


@router.post(
    "/incidents/{incident_id}/logs",
    response_model=LogResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload log file for an incident"
)
async def upload_log(
    incident_id: str,
    file: UploadFile = File(..., description="Log file (.log, .txt, .json, max 5MB)"),
    db=Depends(get_db)
):
    """
    Upload log file for an incident.
    Validates file extension, 5 MB file size limit, and non-empty content.
    """
    return await LogService.upload_log_file(incident_id, file, db)


@router.get(
    "/incidents/{incident_id}/logs",
    response_model=LogResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve logs for an incident"
)
async def get_incident_logs(
    incident_id: str,
    db=Depends(get_db)
):
    """Retrieve uploaded log file record for an incident"""
    return await LogService.get_logs_by_incident(incident_id, db)
