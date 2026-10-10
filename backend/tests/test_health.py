"""
Unit & Integration tests for FastAPI /health endpoint
"""

from unittest.mock import AsyncMock, patch
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_endpoint_healthy():
    """Test GET /health when MongoDB connection is active and responsive"""
    with patch("app.api.health.check_db_health", new_callable=AsyncMock) as mock_check:
        mock_check.return_value = True
        response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "sherlog-backend"
        assert data["database"] == "connected"


def test_health_endpoint_degraded():
    """Test GET /health when MongoDB is unreachable (returns 503 degraded)"""
    with patch("app.api.health.check_db_health", new_callable=AsyncMock) as mock_check:
        mock_check.return_value = False
        response = client.get("/health")
        
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "degraded"
        assert data["service"] == "sherlog-backend"
        assert data["database"] == "disconnected"


def test_api_v1_health_endpoint():
    """Test GET /api/v1/health route alias"""
    with patch("app.api.health.check_db_health", new_callable=AsyncMock) as mock_check:
        mock_check.return_value = True
        response = client.get("/api/v1/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
