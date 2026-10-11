"""
Pydantic schemas and models for Root Cause Analysis (RCA) Reports
"""

from datetime import datetime
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class RiskAssessment(BaseModel):
    severity: Optional[str] = Field(default="medium", json_schema_extra={"example": "high"})
    confidence: Optional[float] = Field(default=0.9, json_schema_extra={"example": 0.95})
    blast_radius: Optional[str] = Field(default="isolated", json_schema_extra={"example": "10+ systems"})
    attack_pattern: Optional[str] = Field(default="N/A", json_schema_extra={"example": "T1059"})


class ReportResponse(BaseModel):
    id: str = Field(..., json_schema_extra={"example": "650000000000000000000004"})
    incident_id: str = Field(..., json_schema_extra={"example": "650000000000000000000001"})
    investigation_id: str = Field(..., json_schema_extra={"example": "650000000000000000000003"})
    root_cause: str = Field(..., json_schema_extra={"example": "Unauthorized connection pool exhaustion due to leaked DB handles"})
    risk_assessment: Dict[str, Any] = Field(default_factory=dict)
    recommendations: List[str] = Field(default_factory=list)
    generated_at: datetime
