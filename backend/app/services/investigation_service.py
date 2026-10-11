"""
Investigation and Report service layer orchestrating async AI tasks and persistence
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from bson import ObjectId
from fastapi import BackgroundTasks, HTTPException, status

from app.services.incident_service import parse_object_id, IncidentService
from app.services.ai_client import ai_service_client, AIServiceClient
from app.models.investigation import (
    InvestigationTriggerResponse,
    InvestigationResponse,
    InvestigationStatusEnum
)
from app.models.report import ReportResponse

logger = logging.getLogger(__name__)


def format_investigation(doc: Dict[str, Any]) -> InvestigationResponse:
    """Format MongoDB investigation document into Pydantic schema"""
    return InvestigationResponse(
        id=str(doc["_id"]),
        incident_id=doc["incident_id"],
        ai_investigation_id=doc.get("ai_investigation_id"),
        status=InvestigationStatusEnum(doc["status"]),
        logs_truncated=doc.get("logs_truncated", False),
        logs_analyzed_count=doc.get("logs_analyzed_count", 0),
        truncation_note=doc.get("truncation_note"),
        anomalies=doc.get("anomalies", []),
        relevant_runbooks=doc.get("relevant_runbooks", []),
        errors=doc.get("errors", []),
        started_at=doc["started_at"],
        completed_at=doc.get("completed_at")
    )


def format_report(doc: Dict[str, Any]) -> ReportResponse:
    """Format MongoDB report document into Pydantic schema"""
    return ReportResponse(
        id=str(doc["_id"]),
        incident_id=doc["incident_id"],
        investigation_id=doc["investigation_id"],
        root_cause=doc.get("root_cause", ""),
        risk_assessment=doc.get("risk_assessment", {}),
        recommendations=doc.get("recommendations", []),
        generated_at=doc["generated_at"]
    )


async def execute_investigation_task(
    incident_id: str,
    investigation_id: str,
    logs: List[str],
    context: str,
    db,
    client: Optional[AIServiceClient] = None
):
    """
    Background worker task:
    1. Triggers 6-step multi-agent pipeline in ai-service
    2. Polls for completion
    3. Persists anomalies/runbooks to investigations
    4. Persists RCA report to reports
    5. Updates incident status to 'investigated' (never auto-resolved: only humans resolve via PATCH)
    Handles all network and AI errors gracefully by marking investigation as 'failed' and resetting incident to 'open'
    """
    client = client or ai_service_client
    inv_oid = parse_object_id(investigation_id)

    try:
        logger.info(f"Starting background AI investigation '{investigation_id}' for incident '{incident_id}'...")
        
        # 1. Trigger investigation in ai-service
        ai_inv_id = await client.trigger_investigation(
            incident_id=incident_id,
            logs=logs,
            context=context
        )

        # Update investigation with external AI task ID
        await db.investigations.update_one(
            {"_id": inv_oid},
            {"$set": {"ai_investigation_id": ai_inv_id}}
        )

        # 2. Poll ai-service for completed result
        result = await client.poll_investigation_result(ai_inv_id)

        now = datetime.now(timezone.utc)

        # 3. Save completed investigation state
        anomalies = result.get("anomalies", [])
        runbooks = result.get("relevant_runbooks", [])
        errors = result.get("errors", [])

        await db.investigations.update_one(
            {"_id": inv_oid},
            {"$set": {
                "status": InvestigationStatusEnum.COMPLETED.value,
                "anomalies": anomalies,
                "relevant_runbooks": runbooks,
                "errors": errors,
                "completed_at": now
            }}
        )

        # 4. Save RCA report
        report_doc = {
            "incident_id": incident_id,
            "investigation_id": investigation_id,
            "root_cause": result.get("root_cause", "Root cause identified"),
            "risk_assessment": result.get("risk_assessment", {}),
            "recommendations": result.get("recommendations", []),
            "generated_at": now
        }
        await db.reports.insert_one(report_doc)

        # 5. Mark incident as 'investigated' (never auto-resolve: human engineers review RCA before resolving)
        await db.incidents.update_one(
            {"_id": parse_object_id(incident_id)},
            {"$set": {"status": "investigated", "updated_at": now}}
        )

        logger.info(f"AI investigation '{investigation_id}' completed and report saved. Incident status set to 'investigated'.")

    except Exception as e:
        now = datetime.now(timezone.utc)
        error_msg = str(e)
        logger.error(f"Background investigation '{investigation_id}' failed: {error_msg}")

        # Mark investigation as failed with clear error message instead of crashing
        await db.investigations.update_one(
            {"_id": inv_oid},
            {"$set": {
                "status": InvestigationStatusEnum.FAILED.value,
                "errors": [error_msg],
                "completed_at": now
            }}
        )

        # On failure, reset incident back to 'open'
        await db.incidents.update_one(
            {"_id": parse_object_id(incident_id)},
            {"$set": {"status": "open", "updated_at": now}}
        )



MAX_INVESTIGATION_LOG_LINES = 500


async def cleanup_interrupted_investigations(db) -> int:
    """
    On backend startup, identify any investigations still marked 'in_progress',
    mark them as 'failed' (interrupted), and reset corresponding incidents back to 'open'.
    """
    if db is None:
        return 0

    now = datetime.now(timezone.utc)
    cursor = db.investigations.find({"status": InvestigationStatusEnum.IN_PROGRESS.value})
    interrupted_list = await cursor.to_list(length=None)

    if not interrupted_list:
        return 0

    for inv in interrupted_list:
        inv_id = inv["_id"]
        inc_id = inv.get("incident_id")

        await db.investigations.update_one(
            {"_id": inv_id},
            {"$set": {
                "status": InvestigationStatusEnum.FAILED.value,
                "errors": ["Investigation interrupted: server restarted while investigation was in progress."],
                "completed_at": now
            }}
        )

        if inc_id:
            try:
                await db.incidents.update_one(
                    {"_id": parse_object_id(inc_id), "status": "investigating"},
                    {"$set": {"status": "open", "updated_at": now}}
                )
            except Exception as e:
                logger.warning(f"Failed to reset incident {inc_id} status on startup: {e}")

    logger.info(f"Cleaned up {len(interrupted_list)} interrupted investigation(s) on startup.")
    return len(interrupted_list)


class InvestigationService:

    @staticmethod
    async def trigger_investigation(
        incident_id: str,
        background_tasks: BackgroundTasks,
        db,
        ai_client: Optional[AIServiceClient] = None
    ) -> InvestigationTriggerResponse:
        """
        Validate logs exist, reject if an investigation is already in progress (409),
        cap logs to the last 500 lines, record truncation in investigation doc,
        set incident to 'investigating', and queue background worker task.
        """
        # 1. Verify incident exists
        incident = await IncidentService.get_incident_by_id(incident_id, db)

        # 2. Reject with 409 Conflict if an investigation is already in progress for this incident
        existing_in_progress = await db.investigations.find_one({
            "incident_id": incident_id,
            "status": InvestigationStatusEnum.IN_PROGRESS.value
        })
        if existing_in_progress:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"An investigation is already in progress for incident '{incident_id}'."
            )

        # 3. Check that logs have been uploaded
        log_doc = await db.logs.find_one({"incident_id": incident_id})
        if not log_doc or not log_doc.get("raw_content"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot trigger investigation: No logs have been uploaded for incident '{incident_id}' yet."
            )

        # 4. Cap logs sent to AI service to at most the last 500 lines
        raw_logs = log_doc.get("raw_content", [])
        logs_truncated = len(raw_logs) > MAX_INVESTIGATION_LOG_LINES
        if logs_truncated:
            logs_to_send = raw_logs[-MAX_INVESTIGATION_LOG_LINES:]
            truncation_note = f"Log lines exceeded 500 limit. Capped to most recent {len(logs_to_send)} of {len(raw_logs)} lines."
        else:
            logs_to_send = raw_logs
            truncation_note = None

        now = datetime.now(timezone.utc)

        # 5. Create investigation record with in_progress status and truncation metadata
        inv_doc = {
            "incident_id": incident_id,
            "ai_investigation_id": None,
            "status": InvestigationStatusEnum.IN_PROGRESS.value,
            "logs_truncated": logs_truncated,
            "logs_analyzed_count": len(logs_to_send),
            "truncation_note": truncation_note,
            "anomalies": [],
            "relevant_runbooks": [],
            "errors": [],
            "started_at": now,
            "completed_at": None
        }
        inv_res = await db.investigations.insert_one(inv_doc)
        investigation_id = str(inv_res.inserted_id)

        # 6. Set incident status to 'investigating'
        await db.incidents.update_one(
            {"_id": parse_object_id(incident_id)},
            {"$set": {"status": "investigating", "updated_at": now}}
        )

        # 7. Dispatch background task with capped logs
        context_str = f"Service: {incident.service_name}. Description: {incident.description}"
        background_tasks.add_task(
            execute_investigation_task,
            incident_id=incident_id,
            investigation_id=investigation_id,
            logs=logs_to_send,
            context=context_str,
            db=db,
            client=ai_client
        )

        logger.info(f"Queued background AI investigation '{investigation_id}' for incident '{incident_id}' (logs: {len(logs_to_send)}, truncated: {logs_truncated})")
        return InvestigationTriggerResponse(
            investigation_id=investigation_id,
            incident_id=incident_id,
            status=InvestigationStatusEnum.IN_PROGRESS,
            logs_truncated=logs_truncated,
            message="Investigation started in background. Poll /api/v1/incidents/{id}/investigation for progress."
        )

    @staticmethod
    async def get_investigation_status(incident_id: str, db) -> InvestigationResponse:
        """Get latest investigation status for an incident"""
        await IncidentService.get_incident_by_id(incident_id, db)

        doc = await db.investigations.find_one(
            {"incident_id": incident_id},
            sort=[("started_at", -1)]
        )
        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No investigation found for incident '{incident_id}'"
            )

        return format_investigation(doc)

    @staticmethod
    async def get_report(incident_id: str, db) -> ReportResponse:
        """Get generated RCA report for an incident"""
        await IncidentService.get_incident_by_id(incident_id, db)

        doc = await db.reports.find_one(
            {"incident_id": incident_id},
            sort=[("generated_at", -1)]
        )
        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No report has been generated for incident '{incident_id}' yet."
            )

        return format_report(doc)
