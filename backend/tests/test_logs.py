"""
Unit and Integration tests for Log Upload API (/api/v1/incidents/{id}/logs)
Uses mongomock_motor to ensure zero interaction with production/real databases.
"""

import io
import asyncio
import pytest
from mongomock_motor import AsyncMongoMockClient
from fastapi.testclient import TestClient
from app.main import app
from app.core.database import get_db

client = TestClient(app)

mock_client = AsyncMongoMockClient()
mock_db = mock_client["sherlog_test_db_logs"]


def override_get_db():
    return mock_db


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
def clear_test_db():
    """Clear test database collections before each test"""
    async def _clear():
        await mock_db.incidents.delete_many({})
        await mock_db.logs.delete_many({})
    asyncio.run(_clear())


def create_sample_incident() -> str:
    """Helper to create an incident and return its ID"""
    res = client.post("/api/v1/incidents", json={
        "title": "JVM OutOfMemoryError",
        "description": "Auth service heap memory limit exceeded",
        "service_name": "auth-service",
        "severity": "critical"
    })
    return res.json()["id"]


def test_upload_valid_log_file():
    """Test POST /api/v1/incidents/{id}/logs uploads and parses log lines successfully"""
    inc_id = create_sample_incident()

    log_content = (
        "2026-10-10 13:00:00 [ERROR] Connection pool exhausted\n"
        "2026-10-10 13:00:01 [WARN] Retrying connection attempt 1\n"
        "2026-10-10 13:00:05 [FATAL] Timeout waiting for DB connection\n"
    ).encode("utf-8")

    files = {"file": ("syslog.log", io.BytesIO(log_content), "text/plain")}
    response = client.post(f"/api/v1/incidents/{inc_id}/logs", files=files)

    assert response.status_code == 201
    data = response.json()
    assert data["incident_id"] == inc_id
    assert data["filename"] == "syslog.log"
    assert data["total_entries"] == 3
    assert len(data["raw_content"]) == 3

    # Check incident status remains 'open' (only changes to 'investigating' when AI investigation starts)
    inc_res = client.get(f"/api/v1/incidents/{inc_id}")
    assert inc_res.json()["status"] == "open"


def test_upload_log_invalid_extension():
    """Test upload fails with 400 when file extension is not allowed (.exe / .pdf)"""
    inc_id = create_sample_incident()
    files = {"file": ("malicious_script.exe", io.BytesIO(b"binary data"), "application/octet-stream")}

    response = client.post(f"/api/v1/incidents/{inc_id}/logs", files=files)
    assert response.status_code == 400
    assert "Only .log, .txt, and .json files are allowed" in response.json()["detail"]


def test_upload_empty_log_file():
    """Test upload fails with 400 when log file is empty (0 bytes)"""
    inc_id = create_sample_incident()
    files = {"file": ("empty.log", io.BytesIO(b""), "text/plain")}

    response = client.post(f"/api/v1/incidents/{inc_id}/logs", files=files)
    assert response.status_code == 400
    assert "File is empty" in response.json()["detail"]


def test_upload_log_exceeds_size_limit():
    """Test upload fails with 400 when file size exceeds 5 MB cap"""
    inc_id = create_sample_incident()
    # Create 5.1 MB buffer
    large_content = b"A" * (5 * 1024 * 1024 + 100)
    files = {"file": ("huge_log.log", io.BytesIO(large_content), "text/plain")}

    response = client.post(f"/api/v1/incidents/{inc_id}/logs", files=files)
    assert response.status_code == 400
    assert "exceeds maximum allowed limit of 5 MB" in response.json()["detail"]


def test_get_incident_logs():
    """Test GET /api/v1/incidents/{id}/logs retrieves uploaded logs"""
    inc_id = create_sample_incident()

    log_content = "2026-10-10 13:00:00 [ERROR] OutOfMemoryError in auth container".encode("utf-8")
    files = {"file": ("auth.log", io.BytesIO(log_content), "text/plain")}
    client.post(f"/api/v1/incidents/{inc_id}/logs", files=files)

    get_res = client.get(f"/api/v1/incidents/{inc_id}/logs")
    assert get_res.status_code == 200
    data = get_res.json()
    assert data["incident_id"] == inc_id
    assert data["filename"] == "auth.log"
    assert data["total_entries"] == 1


def test_get_logs_non_existent_incident():
    """Test GET /api/v1/incidents/{id}/logs returns 404 if incident does not exist"""
    response = client.get("/api/v1/incidents/650000000000000000000099/logs")
    assert response.status_code == 404
