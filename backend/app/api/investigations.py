"""
Investigation API Router
"""

from fastapi import APIRouter, status, BackgroundTasks, Depends
from app.core.database import get_db
from app.models.investigation import (
    InvestigationTriggerResponse,
    InvestigationResponse
)
from app.services.investigation_service import InvestigationService

router = APIRouter()


@router.post(
    "/incidents/{incident_id}/investigate",
    response_model=InvestigationTriggerResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger asynchronous AI root cause investigation"
)
async def trigger_incident_investigation(
    incident_id: str,
    background_tasks: BackgroundTasks,
    db=Depends(get_db)
):
    """
    Trigger 6-step multi-agent incident investigation in the background.
    Requires logs to be uploaded first. Returns 202 Accepted immediately.
    """
    return await InvestigationService.trigger_investigation(
        incident_id=incident_id,
        background_tasks=background_tasks,
        db=db
    )


@router.get(
    "/incidents/{incident_id}/investigation",
    response_model=InvestigationResponse,
    status_code=status.HTTP_200_OK,
    summary="Poll investigation status and progress"
)
async def get_incident_investigation(
    incident_id: str,
    db=Depends(get_db)
):
    """
    Poll status of ongoing or completed AI root cause analysis investigation
    """
    return await InvestigationService.get_investigation_status(
        incident_id=incident_id,
        db=db
    )
