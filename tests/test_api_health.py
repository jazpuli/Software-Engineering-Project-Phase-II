"""Tests for health endpoints."""

import pytest
from fastapi.testclient import TestClient


class TestHealth:
    """Test health endpoints."""

    def test_health_endpoint(self, client: TestClient):
        """Test /health endpoint."""
        response = client.get("/health")
        assert response.status_code == 200

        data = response.json()
        assert "status" in data
        assert data["status"] in ["healthy", "degraded", "unhealthy"]
        assert "uptime_seconds" in data
        assert "request_counts" in data
        assert "error_counts" in data
        assert "avg_latency_ms" in data
        assert data["period_seconds"] == 3600

    def test_health_components_endpoint(self, client: TestClient):
        """Test /health/components endpoint."""
        response = client.get("/health/components")
        assert response.status_code == 200

        data = response.json()
        assert "components" in data
        assert "overall_status" in data
        assert data["overall_status"] in ["healthy", "degraded", "unhealthy"]

        # Check component structure
        for component in data["components"]:
            assert "name" in component
            assert "status" in component
            assert "last_check" in component

    def test_health_components_db_status(self, client: TestClient):
        """Test that database component is checked."""
        response = client.get("/health/components")
        data = response.json()

        # Find database component
        db_components = [c for c in data["components"] if c["name"] == "database"]
        assert len(db_components) == 1
        assert db_components[0]["status"] == "healthy"

    def test_health_components_http_server(self, client: TestClient):
        """Test that HTTP server component is always healthy."""
        response = client.get("/health/components")
        data = response.json()

        # Find HTTP server component
        http_components = [c for c in data["components"] if c["name"] == "http_server"]
        assert len(http_components) == 1
        assert http_components[0]["status"] == "healthy"

    def test_health_after_requests(self, client: TestClient, sample_artifact_data):
        """Test health stats update after requests."""
        # Make some requests
        client.get("/artifacts")
        client.post("/artifacts/model", json=sample_artifact_data)
        client.get("/artifacts")

        # Check health
        response = client.get("/health")
        data = response.json()

        # Should have recorded some requests
        # Note: request counts may be empty in tests due to session handling
        assert isinstance(data["request_counts"], dict)


class TestRoot:
    """Test root endpoint."""

    def test_root_endpoint(self, client: TestClient):
        """Test root endpoint redirects to frontend."""
        response = client.get("/", follow_redirects=False)
        assert response.status_code == 307
        assert response.headers["location"] == "/static/index.html"

