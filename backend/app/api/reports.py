"""
Reports API Router
"""

from fastapi import APIRouter, status, Depends
from app.core.database import get_db
from app.models.report import ReportResponse
from app.services.investigation_service import InvestigationService

router = APIRouter()


@router.get(
    "/incidents/{incident_id}/report",
    response_model=ReportResponse,
    status_code=status.HTTP_200_OK,
    summary="Get completed Root Cause Analysis (RCA) report"
)
async def get_incident_report(
    incident_id: str,
    db=Depends(get_db)
):
    """
    Retrieve generated Root Cause Analysis report with risk assessment and remediation recommendations
    """
    return await InvestigationService.get_report(
        incident_id=incident_id,
        db=db
    )
