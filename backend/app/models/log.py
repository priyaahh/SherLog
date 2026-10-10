"""
Pydantic schemas and models for Log records
"""

from datetime import datetime
from typing import List
from pydantic import BaseModel, Field


class LogResponse(BaseModel):
    id: str = Field(..., json_schema_extra={"example": "650000000000000000000002"})
    incident_id: str = Field(..., json_schema_extra={"example": "650000000000000000000001"})
    filename: str = Field(..., json_schema_extra={"example": "auth_service_syslog.log"})
    total_entries: int = Field(..., json_schema_extra={"example": 120})
    raw_content: List[str] = Field(..., description="List of log entry lines")
    uploaded_at: datetime
