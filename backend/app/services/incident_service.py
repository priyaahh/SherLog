"""
Incident service handling database operations for Incident entity
"""

import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import HTTPException, status

from app.models.incident import (
    IncidentCreate,
    IncidentUpdate,
    IncidentResponse,
    IncidentListResponse,
    StatusEnum,
    SeverityEnum
)

logger = logging.getLogger(__name__)


def parse_object_id(id_str: str) -> ObjectId:
    """Validate and convert string to MongoDB ObjectId"""
    if not ObjectId.is_valid(id_str):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid ObjectId format: '{id_str}'"
        )
    return ObjectId(id_str)


def format_incident(doc: Dict[str, Any]) -> IncidentResponse:
    """Format MongoDB document into IncidentResponse Pydantic schema"""
    return IncidentResponse(
        id=str(doc["_id"]),
        title=doc["title"],
        description=doc["description"],
        service_name=doc["service_name"],
        severity=doc["severity"],
        status=doc["status"],
        created_at=doc["created_at"],
        updated_at=doc["updated_at"]
    )


class IncidentService:

    @staticmethod
    async def create_incident(payload: IncidentCreate, db) -> IncidentResponse:
        """Create a new incident record in database"""
        now = datetime.now(timezone.utc)
        doc = {
            "title": payload.title,
            "description": payload.description,
            "service_name": payload.service_name,
            "severity": payload.severity.value,
            "status": StatusEnum.OPEN.value,
            "created_at": now,
            "updated_at": now
        }
        result = await db.incidents.insert_one(doc)
        doc["_id"] = result.inserted_id
        logger.info(f"Created incident '{doc['title']}' with ID: {result.inserted_id}")
        return format_incident(doc)

    @staticmethod
    async def get_incidents(
        db,
        skip: int = 0,
        limit: int = 20,
        status_filter: Optional[str] = None,
        severity_filter: Optional[str] = None
    ) -> IncidentListResponse:
        """List incidents with pagination and optional filtering"""
        query: Dict[str, Any] = {}
        
        if status_filter:
            query["status"] = status_filter
        if severity_filter:
            query["severity"] = severity_filter
            
        total = await db.incidents.count_documents(query)
        cursor = db.incidents.find(query).sort("created_at", -1).skip(skip).limit(limit)
        
        incidents = []
        async for doc in cursor:
            incidents.append(format_incident(doc))
            
        return IncidentListResponse(
            total=total,
            skip=skip,
            limit=limit,
            incidents=incidents
        )

    @staticmethod
    async def get_incident_by_id(incident_id: str, db) -> IncidentResponse:
        """Get incident details by ID"""
        oid = parse_object_id(incident_id)
        doc = await db.incidents.find_one({"_id": oid})
        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Incident with ID '{incident_id}' not found"
            )
        return format_incident(doc)

    @staticmethod
    async def update_incident_status(incident_id: str, payload: IncidentUpdate, db) -> IncidentResponse:
        """Update incident status"""
        oid = parse_object_id(incident_id)
        now = datetime.now(timezone.utc)
        
        result = await db.incidents.find_one_and_update(
            {"_id": oid},
            {"$set": {"status": payload.status.value, "updated_at": now}},
            return_document=True
        )
        
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Incident with ID '{incident_id}' not found"
            )
            
        logger.info(f"Updated status of incident '{incident_id}' to '{payload.status.value}'")
        return format_incident(result)
