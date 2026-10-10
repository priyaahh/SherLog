"""
Incidents API Router
"""

from typing import Optional
from fastapi import APIRouter, status, Query, Depends
from app.core.database import db_manager, get_db
from app.models.incident import (
    IncidentCreate,
    IncidentUpdate,
    IncidentResponse,
    IncidentListResponse,
    StatusEnum,
    SeverityEnum
)
from app.services.incident_service import IncidentService

router = APIRouter()


@router.post(
    "/incidents",
    response_model=IncidentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new incident"
)
async def create_incident(
    payload: IncidentCreate,
    db=Depends(get_db)
):
    """Create a new IT incident record"""
    return await IncidentService.create_incident(payload, db)


@router.get(
    "/incidents",
    response_model=IncidentListResponse,
    status_code=status.HTTP_200_OK,
    summary="List incidents with pagination and filtering"
)
async def list_incidents(
    skip: int = Query(0, ge=0, description="Number of items to skip"),
    limit: int = Query(20, ge=1, le=100, description="Max items to return"),
    status_filter: Optional[StatusEnum] = Query(None, alias="status", description="Filter by incident status"),
    severity_filter: Optional[SeverityEnum] = Query(None, alias="severity", description="Filter by severity level"),
    db=Depends(get_db)
):
    """List incidents with pagination, status filter, and severity filter"""
    status_val = status_filter.value if status_filter else None
    severity_val = severity_filter.value if severity_filter else None
    
    return await IncidentService.get_incidents(
        db=db,
        skip=skip,
        limit=limit,
        status_filter=status_val,
        severity_filter=severity_val
    )


@router.get(
    "/incidents/{incident_id}",
    response_model=IncidentResponse,
    status_code=status.HTTP_200_OK,
    summary="Get incident details by ID"
)
async def get_incident(
    incident_id: str,
    db=Depends(get_db)
):
    """Get single incident record by ID"""
    return await IncidentService.get_incident_by_id(incident_id, db)


@router.patch(
    "/incidents/{incident_id}",
    response_model=IncidentResponse,
    status_code=status.HTTP_200_OK,
    summary="Update incident status"
)
async def update_incident_status(
    incident_id: str,
    payload: IncidentUpdate,
    db=Depends(get_db)
):
    """Update incident status (open -> investigating -> resolved)"""
    return await IncidentService.update_incident_status(incident_id, payload, db)
