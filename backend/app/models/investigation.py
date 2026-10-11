"""
Pydantic schemas and models for Investigations
"""

from enum import Enum
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class InvestigationStatusEnum(str, Enum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class InvestigationTriggerResponse(BaseModel):
    investigation_id: str = Field(..., json_schema_extra={"example": "650000000000000000000003"})
    incident_id: str = Field(..., json_schema_extra={"example": "650000000000000000000001"})
    status: InvestigationStatusEnum = Field(default=InvestigationStatusEnum.IN_PROGRESS)
    logs_truncated: bool = Field(default=False, description="True if input logs exceeded 500 lines and were capped")
    message: str = Field(default="Investigation initiated in background.")


class InvestigationResponse(BaseModel):
    id: str = Field(..., json_schema_extra={"example": "650000000000000000000003"})
    incident_id: str = Field(..., json_schema_extra={"example": "650000000000000000000001"})
    ai_investigation_id: Optional[str] = None
    status: InvestigationStatusEnum
    logs_truncated: bool = Field(default=False, description="True if input logs exceeded 500 lines and were capped")
    logs_analyzed_count: int = Field(default=0, description="Total number of log lines dispatched to AI service")
    truncation_note: Optional[str] = Field(default=None, description="Explanation when logs are capped to last 500 lines")
    anomalies: List[Dict[str, Any]] = []
    relevant_runbooks: List[Dict[str, Any]] = []
    errors: List[str] = []
    started_at: datetime
    completed_at: Optional[datetime] = None
