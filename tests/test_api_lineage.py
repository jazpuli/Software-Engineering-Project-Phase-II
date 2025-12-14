"""Tests for lineage and cost endpoints."""

import pytest
from fastapi.testclient import TestClient


class TestLineage:
    """Test lineage functionality."""

    def test_get_lineage_empty(self, client: TestClient, sample_artifact_data):
        """Test getting lineage for artifact with no relationships."""
        create_response = client.post("/artifacts/model", json=sample_artifact_data)
        artifact_id = create_response.json()["id"]

        response = client.get(f"/artifacts/model/{artifact_id}/lineage")
        assert response.status_code == 200

        data = response.json()
        assert data["artifact_id"] == artifact_id
        assert data["parents"] == []
        assert data["children"] == []

    def test_add_lineage_edge(self, client: TestClient):
        """Test adding a lineage relationship."""
        # Create parent and child
        parent = client.post("/artifacts/model", json={"name": "parent", "url": "https://a.com/p"}).json()
        child = client.post("/artifacts/model", json={"name": "child", "url": "https://a.com/c"}).json()

        # Add lineage edge
        response = client.post(f"/artifacts/model/{child['id']}/lineage?parent_id={parent['id']}")
        assert response.status_code == 200
        assert response.json()["success"] is True

        # Verify lineage
        lineage = client.get(f"/artifacts/model/{child['id']}/lineage").json()
        assert len(lineage["parents"]) == 1
        assert lineage["parents"][0]["id"] == parent["id"]

        # Check parent's children
        parent_lineage = client.get(f"/artifacts/model/{parent['id']}/lineage").json()
        assert len(parent_lineage["children"]) == 1
        assert parent_lineage["children"][0]["id"] == child["id"]

    def test_lineage_self_reference_rejected(self, client: TestClient, sample_artifact_data):
        """Test that self-referencing is rejected."""
        artifact = client.post("/artifacts/model", json=sample_artifact_data).json()

        response = client.post(f"/artifacts/model/{artifact['id']}/lineage?parent_id={artifact['id']}")
        assert response.status_code == 400

    def test_lineage_nonexistent_artifact(self, client: TestClient):
        """Test lineage for non-existent artifact."""
        response = client.get("/artifacts/model/nonexistent-id/lineage")
        assert response.status_code == 404


class TestCost:
    """Test cost calculation."""

    def test_get_cost_no_dependencies(self, client: TestClient, sample_artifact_data):
        """Test cost for artifact with no dependencies."""
        create_response = client.post("/artifacts/model", json=sample_artifact_data)
        artifact_id = create_response.json()["id"]

        response = client.get(f"/artifacts/model/{artifact_id}/cost")
        assert response.status_code == 200

        data = response.json()
        assert data["artifact_id"] == artifact_id
        assert data["own_size_bytes"] == 0  # Size not set
        assert data["dependencies_size_bytes"] == 0
        assert data["total_size_bytes"] == 0

    def test_get_cost_with_dependencies(self, client: TestClient, db_session):
        """Test cost including dependencies."""
        from src.api.db import crud

        # Create artifacts with sizes
        parent = crud.create_artifact(db_session, "model", "parent", "https://a.com/p", size_bytes=1000)
        child = crud.create_artifact(db_session, "model", "child", "https://a.com/c", size_bytes=500)

        # Add lineage
        crud.add_lineage_edge(db_session, parent.id, child.id)

        # Get cost
        response = client.get(f"/artifacts/model/{child.id}/cost")
        assert response.status_code == 200

        data = response.json()
        assert data["own_size_bytes"] == 500
        assert data["dependencies_size_bytes"] == 1000
        assert data["total_size_bytes"] == 1500

    def test_cost_nonexistent_artifact(self, client: TestClient):
        """Test cost for non-existent artifact."""
        response = client.get("/artifacts/model/nonexistent-id/cost")
        assert response.status_code == 404


class TestLicenseCheck:
    """Test license compatibility checking."""

    def test_license_check_missing_artifact(self, client: TestClient):
        """Test license check for non-existent artifact."""
        response = client.post("/license-check", json={
            "artifact_id": "nonexistent",
            "github_url": "https://github.com/owner/repo"
        })
        assert response.status_code == 404

    def test_license_check_artifact_no_license(self, client: TestClient, sample_artifact_data):
        """Test license check when artifact has no license."""
        artifact = client.post("/artifacts/model", json=sample_artifact_data).json()

        response = client.post("/license-check", json={
            "artifact_id": artifact["id"],
            "github_url": "https://github.com/owner/repo"
        })
        assert response.status_code == 200

        data = response.json()
        assert data["compatible"] is False
        assert "Could not determine" in data["message"]

