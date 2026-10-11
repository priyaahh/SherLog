"""
Pydantic schemas and models for Incident management
"""

from enum import Enum
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class SeverityEnum(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class StatusEnum(str, Enum):
    OPEN = "open"
    INVESTIGATING = "investigating"
    INVESTIGATED = "investigated"
    RESOLVED = "resolved"


class IncidentCreate(BaseModel):
    title: str = Field(..., min_length=3, max_length=200, json_schema_extra={"example": "Database Connection Pool Exhaustion"})
    description: str = Field(..., min_length=5, json_schema_extra={"example": "High connection latency observed across auth service"})
    service_name: str = Field(..., min_length=2, max_length=100, json_schema_extra={"example": "auth-service"})
    severity: SeverityEnum = Field(default=SeverityEnum.MEDIUM)


class IncidentUpdate(BaseModel):
    status: StatusEnum = Field(..., json_schema_extra={"example": "investigating"})


class IncidentResponse(BaseModel):
    id: str = Field(..., json_schema_extra={"example": "650000000000000000000001"})
    title: str
    description: str
    service_name: str
    severity: SeverityEnum
    status: StatusEnum
    created_at: datetime
    updated_at: datetime


class IncidentListResponse(BaseModel):
    total: int
    skip: int
    limit: int
    incidents: List[IncidentResponse]
