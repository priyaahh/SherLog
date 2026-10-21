"""
Unit and Integration tests for AI Investigation & Report Endpoints
Covers:
1. Incident status lifecycle:
   - Starts 'open'
   - Transitions to 'investigating' when investigation triggered
   - Transitions to 'investigated' on success (NOT resolved)
   - Transitions back to 'open' on failure
   - Allows human PATCH to 'resolved'
2. Error resilience & Polling 404 handling:
   - 404 from ai-service during polling marks investigation 'failed' and resets incident to 'open'
   - Overall 5-minute timeout prevents investigations hanging indefinitely
   - Startup cleanup marks orphaned 'in_progress' investigations as 'failed' (interrupted)
3. 409 Conflict rejection:
   - POST /investigate rejected with 409 if an investigation is already in progress
4. Log capping at 500 lines:
   - Dispatches at most the last 500 lines to ai-service
   - Records logs_truncated=True, logs_analyzed_count=500, and truncation note
"""

import io
import asyncio
import logging
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch, MagicMock
import pytest
import httpx
from mongomock_motor import AsyncMongoMockClient
from fastapi.testclient import TestClient

from app.main import app
from app.core.database import get_db
from app.services.incident_service import parse_object_id
from app.services.ai_client import AIServiceClient
from app.services.investigation_service import (
    execute_investigation_task,
    cleanup_interrupted_investigations,
    MAX_INVESTIGATION_LOG_LINES
)

client = TestClient(app)

mock_client = AsyncMongoMockClient()
mock_db = mock_client["sherlog_test_db_investigations"]


def override_get_db():
    return mock_db


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
def setup_test_db():
    """Ensure app uses this module's mock_db and clean collections before each test"""
    app.dependency_overrides[get_db] = lambda: mock_db
    async def _clear():
        await mock_db.incidents.delete_many({})
        await mock_db.logs.delete_many({})
        await mock_db.investigations.delete_many({})
        await mock_db.reports.delete_many({})
    asyncio.run(_clear())
    yield


def create_sample_incident_with_logs(line_count: int = 5) -> str:
    """Helper to create an incident and upload sample logs"""
    res = client.post("/api/v1/incidents", json={
        "title": "Auth Service Latency Spike",
        "description": "504 gateway timeout observed under high load",
        "service_name": "auth-service",
        "severity": "critical"
    })
    inc_id = res.json()["id"]

    lines = [f"2026-10-10 20:00:{i:02d} [LOG] Log event number {i}\n" for i in range(1, line_count + 1)]
    log_content = "".join(lines).encode("utf-8")
    files = {"file": ("auth_latency.log", io.BytesIO(log_content), "text/plain")}
    client.post(f"/api/v1/incidents/{inc_id}/logs", files=files)

    return inc_id


# =========================================================================
# Requirement 3: 409 Conflict Rejection
# =========================================================================

def test_trigger_investigation_without_logs():
    """Test POST /incidents/{id}/investigate fails with 400 if no logs uploaded yet"""
    res = client.post("/api/v1/incidents", json={
        "title": "Logless Incident",
        "description": "No logs uploaded",
        "service_name": "worker-service",
        "severity": "medium"
    })
    inc_id = res.json()["id"]

    response = client.post(f"/api/v1/incidents/{inc_id}/investigate")
    assert response.status_code == 400
    assert "No logs have been uploaded" in response.json()["detail"]


def test_trigger_investigation_success_202():
    """Test POST /incidents/{id}/investigate returns 202 Accepted and sets status to investigating"""
    inc_id = create_sample_incident_with_logs()

    with patch("app.services.investigation_service.execute_investigation_task", new_callable=AsyncMock):
        response = client.post(f"/api/v1/incidents/{inc_id}/investigate")

        assert response.status_code == 202
        data = response.json()
        assert "investigation_id" in data
        assert data["incident_id"] == inc_id
        assert data["status"] == "in_progress"
        assert data["logs_truncated"] is False

        # Verify incident status updated to 'investigating'
        inc_res = client.get(f"/api/v1/incidents/{inc_id}")
        assert inc_res.json()["status"] == "investigating"


def test_trigger_investigation_rejects_with_409_if_already_in_progress():
    """Requirement 3: Reject POST /investigate with 409 if that incident already has an in_progress investigation"""
    inc_id = create_sample_incident_with_logs()

    # First trigger succeeds
    with patch("app.services.investigation_service.execute_investigation_task", new_callable=AsyncMock):
        res1 = client.post(f"/api/v1/incidents/{inc_id}/investigate")
        assert res1.status_code == 202

        # Second trigger while first is still in_progress must be rejected with 409 Conflict
        res2 = client.post(f"/api/v1/incidents/{inc_id}/investigate")
        assert res2.status_code == 409
        assert "already in progress" in res2.json()["detail"].lower()


# =========================================================================
# Requirement 4: Cap logs sent to ai-service at 500 lines & report truncation
# =========================================================================

def test_log_capping_and_truncation_notice_when_exceeding_500_lines():
    """Requirement 4: Cap at most the last 500 lines and record truncation metadata"""
    # Create incident with 650 lines
    inc_id = create_sample_incident_with_logs(line_count=650)

    with patch("app.services.investigation_service.execute_investigation_task", new_callable=AsyncMock) as mock_task:
        response = client.post(f"/api/v1/incidents/{inc_id}/investigate")

        assert response.status_code == 202
        data = response.json()
        assert data["logs_truncated"] is True
        inv_id = data["investigation_id"]

        # Check background task received only 500 lines (the last 500)
        assert mock_task.called
        kwargs = mock_task.call_args.kwargs
        dispatched_logs = kwargs["logs"]
        assert len(dispatched_logs) == 500
        # First of the 500 dispatched lines corresponds to entry 151 (650 - 500 + 1)
        assert "Log event number 151" in dispatched_logs[0]
        # Last dispatched line corresponds to entry 650
        assert "Log event number 650" in dispatched_logs[-1]

        # Verify investigation document in database records truncation
        inv_status_res = client.get(f"/api/v1/incidents/{inc_id}/investigation")
        assert inv_status_res.status_code == 200
        inv_doc = inv_status_res.json()
        assert inv_doc["logs_truncated"] is True
        assert inv_doc["logs_analyzed_count"] == 500
        assert inv_doc["truncation_note"] is not None
        assert "500" in inv_doc["truncation_note"]
        assert "650" in inv_doc["truncation_note"]


# =========================================================================
# Requirement 1: Incident Status Flow (Never auto-resolved, only 'investigated')
# =========================================================================

@pytest.mark.asyncio
async def test_background_investigation_success_sets_investigated_not_resolved():
    """Requirement 1: After completion, incident is set to 'investigated', NOT 'resolved'. Only humans resolve via PATCH."""
    now = datetime.now(timezone.utc)
    
    # 1. Create incident in mock_db
    inc_res = await mock_db.incidents.insert_one({
        "title": "Auth Service Latency Spike",
        "description": "504 gateway timeout",
        "service_name": "auth-service",
        "severity": "critical",
        "status": "investigating",
        "created_at": now,
        "updated_at": now
    })
    inc_id = str(inc_res.inserted_id)

    # 2. Create in_progress investigation in mock_db
    inv_doc = {
        "incident_id": inc_id,
        "ai_investigation_id": None,
        "status": "in_progress",
        "logs_truncated": False,
        "logs_analyzed_count": 10,
        "truncation_note": None,
        "anomalies": [],
        "relevant_runbooks": [],
        "errors": [],
        "started_at": now,
        "completed_at": None
    }
    inv_res = await mock_db.investigations.insert_one(inv_doc)
    inv_id = str(inv_res.inserted_id)

    # 3. Mock AI Service client
    mock_ai_client = AsyncMock()
    mock_ai_client.trigger_investigation.return_value = "mock-ai-uuid-999"
    mock_ai_client.poll_investigation_result.return_value = {
        "investigation_id": "mock-ai-uuid-999",
        "status": "completed",
        "root_cause": "Database connection pool exhausted due to missing connection release",
        "risk_assessment": {
            "severity": "critical",
            "confidence": 0.95,
            "blast_radius": "Web tier auth dependency"
        },
        "recommendations": [
            "Increase max pool size from 20 to 50",
            "Ensure db.close() in finally block"
        ],
        "anomalies": [{"type": "pool_exhaustion", "count": 12}],
        "relevant_runbooks": [{"id": "rb_001", "title": "DB Pool Recovery Guide"}],
        "errors": []
    }

    # 4. Execute background worker
    await execute_investigation_task(
        incident_id=inc_id,
        investigation_id=inv_id,
        logs=["ERROR Connection pool exhausted"],
        context="Auth service",
        db=mock_db,
        client=mock_ai_client
    )

    # 5. Verify investigation completed
    inv_record = await mock_db.investigations.find_one({"_id": inv_res.inserted_id})
    assert inv_record["status"] == "completed"

    # 6. Verify report created
    report_record = await mock_db.reports.find_one({"incident_id": inc_id})
    assert report_record is not None

    # 7. CRITICAL REQUIREMENT 1: Incident status must be 'investigated', NOT 'resolved'
    inc_record = await mock_db.incidents.find_one({"_id": inc_res.inserted_id})
    assert inc_record is not None
    assert inc_record["status"] == "investigated"

    # 8. Human operator approves and resolves incident via PATCH
    patch_res = client.patch(f"/api/v1/incidents/{inc_id}", json={"status": "resolved"})
    assert patch_res.status_code == 200
    assert patch_res.json()["status"] == "resolved"


@pytest.mark.asyncio
async def test_background_investigation_failure_resets_incident_to_open():
    """Requirement 1: On failure, incident is set back to 'open'."""
    now = datetime.now(timezone.utc)
    
    inc_res = await mock_db.incidents.insert_one({
        "title": "Auth Service Failure",
        "description": "500 error",
        "service_name": "auth-service",
        "severity": "high",
        "status": "investigating",
        "created_at": now,
        "updated_at": now
    })
    inc_id = str(inc_res.inserted_id)

    inv_doc = {
        "incident_id": inc_id,
        "ai_investigation_id": None,
        "status": "in_progress",
        "logs_truncated": False,
        "logs_analyzed_count": 1,
        "truncation_note": None,
        "errors": [],
        "started_at": now,
        "completed_at": None
    }
    inv_res = await mock_db.investigations.insert_one(inv_doc)
    inv_id = str(inv_res.inserted_id)

    mock_ai_client = AsyncMock()
    mock_ai_client.trigger_investigation.side_effect = ConnectionError("AI Service unreachable at http://localhost:5000")

    await execute_investigation_task(
        incident_id=inc_id,
        investigation_id=inv_id,
        logs=["ERROR Connection refused"],
        context="Auth service",
        db=mock_db,
        client=mock_ai_client
    )

    # Investigation marked failed
    inv_record = await mock_db.investigations.find_one({"_id": inv_res.inserted_id})
    assert inv_record["status"] == "failed"
    assert "unreachable" in inv_record["errors"][0].lower()

    # CRITICAL REQUIREMENT 1: Incident reset to 'open' on failure
    inc_record = await mock_db.incidents.find_one({"_id": inc_res.inserted_id})
    assert inc_record["status"] == "open"


# =========================================================================
# Requirement 2: Polling 404, Timeout & Server Startup Cleanup
# =========================================================================

@pytest.mark.asyncio
async def test_polling_404_marks_investigation_failed_and_resets_incident_to_open():
    """Requirement 2: Handle a 404 from ai-service when polling (e.g. it restarted): mark failed with clear message"""
    now = datetime.now(timezone.utc)

    inc_res = await mock_db.incidents.insert_one({
        "title": "Payment Service Failure",
        "description": "Timeout",
        "service_name": "payment-service",
        "severity": "high",
        "status": "investigating",
        "created_at": now,
        "updated_at": now
    })
    inc_id = str(inc_res.inserted_id)

    inv_doc = {
        "incident_id": inc_id,
        "ai_investigation_id": None,
        "status": "in_progress",
        "logs_truncated": False,
        "logs_analyzed_count": 5,
        "truncation_note": None,
        "errors": [],
        "started_at": now,
        "completed_at": None
    }
    inv_res = await mock_db.investigations.insert_one(inv_doc)
    inv_id = str(inv_res.inserted_id)

    # Mock client where trigger succeeds but polling returns 404 (service restarted)
    mock_ai_client = AsyncMock()
    mock_ai_client.trigger_investigation.return_value = "ai-inv-lost-state"
    mock_ai_client.poll_investigation_result.side_effect = RuntimeError(
        "AI service lost investigation state for 'ai-inv-lost-state' (404 Not Found) - AI service may have restarted."
    )

    await execute_investigation_task(
        incident_id=inc_id,
        investigation_id=inv_id,
        logs=["ERROR 504 Gateway Timeout"],
        context="Payment",
        db=mock_db,
        client=mock_ai_client
    )

    # Investigation marked failed with 404 explanation
    inv_record = await mock_db.investigations.find_one({"_id": inv_res.inserted_id})
    assert inv_record["status"] == "failed"
    assert "404 not found" in inv_record["errors"][0].lower()
    assert "restarted" in inv_record["errors"][0].lower()

    # Incident reset to 'open'
    inc_record = await mock_db.incidents.find_one({"_id": inc_res.inserted_id})
    assert inc_record["status"] == "open"


@pytest.mark.asyncio
async def test_ai_client_poll_raises_clear_error_on_404():
    """Requirement 2: AIServiceClient.poll_investigation_result raises clear 404 message when state is lost"""
    client_instance = AIServiceClient("http://fake-ai-service:5000")

    mock_resp = MagicMock()
    mock_resp.status_code = 404

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        with pytest.raises(RuntimeError) as exc_info:
            await client_instance.poll_investigation_result("lost-task-123", max_polls=2, poll_interval=0.01)

        err_str = str(exc_info.value)
        assert "404 Not Found" in err_str
        assert "AI service may have restarted" in err_str


@pytest.mark.asyncio
async def test_startup_cleanup_marks_in_progress_investigations_as_failed():
    """Requirement 2: On backend startup, mark any investigations still 'in_progress' as 'failed' (interrupted) and reset incidents to 'open'"""
    now = datetime.now(timezone.utc)

    # Create 2 orphaned in-progress investigations and 1 already completed investigation
    inc1 = await mock_db.incidents.insert_one({
        "title": "Orphan 1",
        "description": "desc",
        "service_name": "srv1",
        "severity": "low",
        "status": "investigating",
        "created_at": now,
        "updated_at": now
    })
    inc2 = await mock_db.incidents.insert_one({
        "title": "Orphan 2",
        "description": "desc",
        "service_name": "srv2",
        "severity": "medium",
        "status": "investigating",
        "created_at": now,
        "updated_at": now
    })
    inc_completed = await mock_db.incidents.insert_one({
        "title": "Completed",
        "description": "desc",
        "service_name": "srv3",
        "severity": "high",
        "status": "investigated",
        "created_at": now,
        "updated_at": now
    })

    inv1 = await mock_db.investigations.insert_one({
        "incident_id": str(inc1.inserted_id),
        "status": "in_progress",
        "started_at": now
    })
    inv2 = await mock_db.investigations.insert_one({
        "incident_id": str(inc2.inserted_id),
        "status": "in_progress",
        "started_at": now
    })
    inv_done = await mock_db.investigations.insert_one({
        "incident_id": str(inc_completed.inserted_id),
        "status": "completed",
        "started_at": now,
        "completed_at": now
    })

    # Run startup cleanup helper
    cleaned_count = await cleanup_interrupted_investigations(mock_db)
    assert cleaned_count == 2

    # Verify both in_progress investigations were marked as failed with clear message
    res_inv1 = await mock_db.investigations.find_one({"_id": inv1.inserted_id})
    assert res_inv1["status"] == "failed"
    assert "server restarted" in res_inv1["errors"][0].lower()
    assert res_inv1["completed_at"] is not None

    res_inv2 = await mock_db.investigations.find_one({"_id": inv2.inserted_id})
    assert res_inv2["status"] == "failed"

    # Completed investigation untouched
    res_inv_done = await mock_db.investigations.find_one({"_id": inv_done.inserted_id})
    assert res_inv_done["status"] == "completed"

    # Verify orphaned incidents reset to 'open'
    res_inc1 = await mock_db.incidents.find_one({"_id": inc1.inserted_id})
    assert res_inc1["status"] == "open"

    res_inc2 = await mock_db.incidents.find_one({"_id": inc2.inserted_id})
    assert res_inc2["status"] == "open"

    # Completed incident remains 'investigated'
    res_inc_completed = await mock_db.incidents.find_one({"_id": inc_completed.inserted_id})
    assert res_inc_completed["status"] == "investigated"


def test_get_investigation_and_report_endpoints():
    """Test GET endpoints for investigation status and reports"""
    inc_id = create_sample_incident_with_logs()

    # 1. 404 before investigation starts
    res_inv = client.get(f"/api/v1/incidents/{inc_id}/investigation")
    assert res_inv.status_code == 404

    res_rep = client.get(f"/api/v1/incidents/{inc_id}/report")
    assert res_rep.status_code == 404

    # 2. Trigger investigation with mocked background task
    with patch("app.services.investigation_service.execute_investigation_task", new_callable=AsyncMock):
        client.post(f"/api/v1/incidents/{inc_id}/investigate")

    # 3. GET /investigation returns 200
    res_inv_after = client.get(f"/api/v1/incidents/{inc_id}/investigation")
    assert res_inv_after.status_code == 200
    assert res_inv_after.json()["incident_id"] == inc_id
    assert res_inv_after.json()["status"] == "in_progress"
    assert res_inv_after.json()["logs_truncated"] is False


# =========================================================================
# Requirement: Non-2xx and non-JSON response error sanitization & logging
# =========================================================================

@pytest.mark.asyncio
async def test_ai_service_non_2xx_html_response_truncation_and_logging(caplog):
    """
    When AI service returns a non-2xx response with HTML:
    - Truncate the error stored on the investigation to ~200 characters
    - Strip HTML tags
    - Log the full body server-side only
    """
    now = datetime.now(timezone.utc)
    inc_res = await mock_db.incidents.insert_one({
        "title": "Gateway Crash Incident",
        "description": "502 Gateway Error",
        "service_name": "api-gateway",
        "severity": "critical",
        "status": "investigating",
        "created_at": now,
        "updated_at": now
    })
    inc_id = str(inc_res.inserted_id)

    inv_doc = {
        "incident_id": inc_id,
        "ai_investigation_id": None,
        "status": "in_progress",
        "logs_truncated": False,
        "logs_analyzed_count": 10,
        "truncation_note": None,
        "anomalies": [],
        "relevant_runbooks": [],
        "errors": [],
        "started_at": now,
        "completed_at": None
    }
    inv_res = await mock_db.investigations.insert_one(inv_doc)
    inv_id = str(inv_res.inserted_id)

    # 1,200 character HTML error body from proxy / crash
    long_html_body = (
        "<!DOCTYPE html><html><head><title>502 Bad Gateway Crash</title></head><body>"
        "<h1>502 Bad Gateway</h1><p>"
        + "Detailed stack trace and internal error message from proxy that goes on and on: " * 15
        + "</p></body></html>"
    )

    mock_resp = MagicMock()
    mock_resp.status_code = 502
    mock_resp.text = long_html_body
    mock_resp.is_error = True

    client_instance = AIServiceClient("http://fake-ai-service:5000")

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        with caplog.at_level(logging.ERROR):
            await execute_investigation_task(
                incident_id=inc_id,
                investigation_id=inv_id,
                logs=["ERROR 502 upstream failed"],
                context="api-gateway",
                db=mock_db,
                client=client_instance
            )

    # 1. Investigation marked as failed
    inv_record = await mock_db.investigations.find_one({"_id": inv_res.inserted_id})
    assert inv_record["status"] == "failed"
    assert len(inv_record["errors"]) == 1

    error_stored = inv_record["errors"][0]

    # 2. Error stored on investigation is truncated to ~200 characters
    assert len(error_stored) <= 200

    # 3. HTML tags stripped from the stored error
    assert "<html" not in error_stored.lower()
    assert "<body>" not in error_stored.lower()
    assert "<h1>" not in error_stored.lower()
    assert "<" not in error_stored
    assert ">" not in error_stored
    assert "502" in error_stored

    # 4. Full body is logged server-side only
    assert long_html_body in caplog.text

    # 5. Incident reset to 'open'
    inc_record = await mock_db.incidents.find_one({"_id": inc_res.inserted_id})
    assert inc_record["status"] == "open"


@pytest.mark.asyncio
async def test_ai_service_non_json_response_truncation_and_logging(caplog):
    """
    When AI service returns a non-JSON response (e.g. HTML on 202 or plain text):
    - Truncate the error stored on the investigation to ~200 characters
    - Strip HTML tags
    - Log the full body server-side only
    """
    now = datetime.now(timezone.utc)
    inc_res = await mock_db.incidents.insert_one({
        "title": "Non-JSON Response Incident",
        "description": "Malformed response",
        "service_name": "worker",
        "severity": "medium",
        "status": "investigating",
        "created_at": now,
        "updated_at": now
    })
    inc_id = str(inc_res.inserted_id)

    inv_doc = {
        "incident_id": inc_id,
        "ai_investigation_id": None,
        "status": "in_progress",
        "logs_truncated": False,
        "logs_analyzed_count": 5,
        "truncation_note": None,
        "anomalies": [],
        "relevant_runbooks": [],
        "errors": [],
        "started_at": now,
        "completed_at": None
    }
    inv_res = await mock_db.investigations.insert_one(inv_doc)
    inv_id = str(inv_res.inserted_id)

    non_json_html = (
        "<html><body><h1>Unexpected Cloudflare Challenge</h1><p>"
        + "Verification required before proceeding to the requested service. " * 12
        + "</p></body></html>"
    )

    mock_resp = MagicMock()
    mock_resp.status_code = 202
    mock_resp.text = non_json_html
    mock_resp.json.side_effect = ValueError("Invalid JSON")

    client_instance = AIServiceClient("http://fake-ai-service:5000")

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        with caplog.at_level(logging.ERROR):
            await execute_investigation_task(
                incident_id=inc_id,
                investigation_id=inv_id,
                logs=["ERROR worker disconnected"],
                context="worker",
                db=mock_db,
                client=client_instance
            )

    inv_record = await mock_db.investigations.find_one({"_id": inv_res.inserted_id})
    assert inv_record["status"] == "failed"

    error_stored = inv_record["errors"][0]
    assert len(error_stored) <= 200
    assert "<" not in error_stored
    assert ">" not in error_stored
    assert "non-json" in error_stored.lower()
    assert non_json_html in caplog.text


@pytest.mark.asyncio
async def test_execute_investigation_empty_exception_stores_unknown_failure():
    """When an exception has an empty message, store 'Unknown failure'"""
    now = datetime.now(timezone.utc)
    inc_res = await mock_db.incidents.insert_one({
        "title": "Blank Error Test",
        "description": "Blank error",
        "service_name": "worker",
        "severity": "low",
        "status": "investigating",
        "created_at": now,
        "updated_at": now
    })
    inc_id = str(inc_res.inserted_id)

    inv_res = await mock_db.investigations.insert_one({
        "incident_id": inc_id,
        "status": "in_progress",
        "started_at": now,
        "errors": []
    })
    inv_id = str(inv_res.inserted_id)

    mock_client_instance = AsyncMock()
    mock_client_instance.trigger_investigation.side_effect = Exception("")

    await execute_investigation_task(
        incident_id=inc_id,
        investigation_id=inv_id,
        logs=["ERROR something went wrong"],
        context="worker",
        db=mock_db,
        client=mock_client_instance
    )

    inv_record = await mock_db.investigations.find_one({"_id": inv_res.inserted_id})
    assert inv_record["status"] == "failed"
    assert len(inv_record["errors"]) == 1
    assert inv_record["errors"][0] == "Unknown failure"


@pytest.mark.asyncio
async def test_execute_investigation_exception_stores_type_and_message():
    """When an exception has a message, store f'{type(e).__name__}: {str(e)}'"""
    now = datetime.now(timezone.utc)
    inc_res = await mock_db.incidents.insert_one({
        "title": "Typed Error Test",
        "description": "Typed error",
        "service_name": "worker",
        "severity": "medium",
        "status": "investigating",
        "created_at": now,
        "updated_at": now
    })
    inc_id = str(inc_res.inserted_id)

    inv_res = await mock_db.investigations.insert_one({
        "incident_id": inc_id,
        "status": "in_progress",
        "started_at": now,
        "errors": []
    })
    inv_id = str(inv_res.inserted_id)

    mock_client_instance = AsyncMock()
    mock_client_instance.trigger_investigation.side_effect = ValueError("Invalid payload signature")

    await execute_investigation_task(
        incident_id=inc_id,
        investigation_id=inv_id,
        logs=["ERROR signature mismatch"],
        context="worker",
        db=mock_db,
        client=mock_client_instance
    )

    inv_record = await mock_db.investigations.find_one({"_id": inv_res.inserted_id})
    assert inv_record["status"] == "failed"
    assert len(inv_record["errors"]) == 1
    assert inv_record["errors"][0] == "ValueError: Invalid payload signature"


@pytest.mark.asyncio
async def test_execute_investigation_incident_status_update_failure_does_not_prevent_report(caplog):
    """
    When incident status update to 'investigated' fails, the report is still saved,
    the investigation completes, and an ERROR is logged with the incident_id.
    """
    now = datetime.now(timezone.utc)
    inc_res = await mock_db.incidents.insert_one({
        "title": "Incident Update Failure Test",
        "description": "Report should survive incident update failure",
        "service_name": "order-service",
        "severity": "critical",
        "status": "investigating",
        "created_at": now,
        "updated_at": now
    })
    inc_id = str(inc_res.inserted_id)

    inv_res = await mock_db.investigations.insert_one({
        "incident_id": inc_id,
        "status": "in_progress",
        "started_at": now,
        "errors": []
    })
    inv_id = str(inv_res.inserted_id)

    mock_ai_client = AsyncMock()
    mock_ai_client.trigger_investigation.return_value = "ai-inv-resilient"
    mock_ai_client.poll_investigation_result.return_value = {
        "investigation_id": "ai-inv-resilient",
        "status": "completed",
        "root_cause": "Deadlock in order placement",
        "risk_assessment": {"severity": "critical"},
        "recommendations": ["Optimize lock order"],
        "anomalies": [],
        "relevant_runbooks": [],
        "errors": []
    }

    # Simulate database failure only on incidents.update_one
    mock_incidents_col = MagicMock()
    mock_incidents_col.update_one = AsyncMock(
        side_effect=RuntimeError("Simulated DB connection drop on incidents collection")
    )

    class DBProxy:
        def __init__(self, real_db, incidents_col):
            self._real_db = real_db
            self.incidents = incidents_col

        def __getattr__(self, name):
            return getattr(self._real_db, name)

        def __getitem__(self, name):
            if name == "incidents":
                return self.incidents
            return self._real_db[name]

    proxy_db = DBProxy(mock_db, mock_incidents_col)

    with caplog.at_level(logging.ERROR):
        await execute_investigation_task(
            incident_id=inc_id,
            investigation_id=inv_id,
            logs=["ERROR Deadlock detected"],
            context="order-service",
            db=proxy_db,
            client=mock_ai_client
        )

    # 1. Report MUST still be saved
    report = await mock_db.reports.find_one({"incident_id": inc_id})
    assert report is not None
    assert report["root_cause"] == "Deadlock in order placement"

    # 2. Investigation status is COMPLETED
    inv_record = await mock_db.investigations.find_one({"_id": inv_res.inserted_id})
    assert inv_record["status"] == "completed"

    # 3. Logged as ERROR with incident_id
    assert inc_id in caplog.text
    assert "Failed to update incident" in caplog.text

