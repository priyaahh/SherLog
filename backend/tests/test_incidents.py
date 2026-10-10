"""
Unit and Integration tests for Incidents API (/api/v1/incidents)
Uses mongomock_motor to ensure zero interaction with production/real databases.
"""

import pytest
from mongomock_motor import AsyncMongoMockClient
from fastapi.testclient import TestClient
from app.main import app
from app.core.database import get_db

client = TestClient(app)

mock_client = AsyncMongoMockClient()
mock_db = mock_client["sherlog_test_db_incidents"]


def override_get_db():
    return mock_db


app.dependency_overrides[get_db] = override_get_db


def test_create_incident():
    """Test POST /api/v1/incidents creates a valid incident"""
    payload = {
        "title": "Database Connection Leak",
        "description": "High latency on auth-service DB pool",
        "service_name": "auth-service",
        "severity": "high"
    }
    response = client.post("/api/v1/incidents", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert data["title"] == payload["title"]
    assert data["status"] == "open"
    assert data["severity"] == "high"


def test_get_incident_by_id():
    """Test GET /api/v1/incidents/{id} fetches incident details"""
    payload = {
        "title": "Kafka Consumer Lag",
        "description": "Payment stream lag > 10,000 events",
        "service_name": "payment-service",
        "severity": "critical"
    }
    create_res = client.post("/api/v1/incidents", json=payload)
    inc_id = create_res.json()["id"]

    get_res = client.get(f"/api/v1/incidents/{inc_id}")
    assert get_res.status_code == 200
    data = get_res.json()
    assert data["id"] == inc_id
    assert data["service_name"] == "payment-service"


def test_get_incident_invalid_objectid():
    """Test GET /api/v1/incidents/{id} returns 400 Bad Request for malformed ObjectId"""
    response = client.get("/api/v1/incidents/invalid-object-id-123")
    assert response.status_code == 400
    assert "Invalid ObjectId format" in response.json()["detail"]


def test_get_incident_not_found():
    """Test GET /api/v1/incidents/{id} returns 404 for valid but non-existent ObjectId"""
    non_existent_id = "650000000000000000000099"
    response = client.get(f"/api/v1/incidents/{non_existent_id}")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"]


def test_list_incidents_with_pagination_and_filter():
    """Test GET /api/v1/incidents filtering by status/severity & pagination"""
    client.post("/api/v1/incidents", json={
        "title": "Unique Filter Incident 1", "description": "Desc 1", "service_name": "filter-srv1", "severity": "low"
    })
    client.post("/api/v1/incidents", json={
        "title": "Unique Filter Incident 2", "description": "Desc 2", "service_name": "filter-srv2", "severity": "critical"
    })

    # Test list all
    res = client.get("/api/v1/incidents")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] >= 2

    # Test severity filter
    res_filtered = client.get("/api/v1/incidents?severity=critical")
    assert res_filtered.status_code == 200
    data_filtered = res_filtered.json()
    assert data_filtered["total"] >= 1
    assert data_filtered["incidents"][0]["severity"] == "critical"


def test_patch_incident_status():
    """Test PATCH /api/v1/incidents/{id} updates status"""
    create_res = client.post("/api/v1/incidents", json={
        "title": "Nginx 502 Bad Gateway",
        "description": "Ingress returning 502 errors",
        "service_name": "ingress-service",
        "severity": "medium"
    })
    inc_id = create_res.json()["id"]

    patch_res = client.patch(f"/api/v1/incidents/{inc_id}", json={"status": "investigating"})
    assert patch_res.status_code == 200
    data = patch_res.json()
    assert data["status"] == "investigating"
