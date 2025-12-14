"""Tests for artifact CRUD endpoints."""

import pytest
from fastapi.testclient import TestClient


class TestArtifactsCRUD:
    """Test artifact CRUD operations."""

    def test_create_artifact_model(self, client: TestClient, sample_artifact_data):
        """Test creating a model artifact."""
        response = client.post("/artifacts/model", json=sample_artifact_data)
        assert response.status_code == 201

        data = response.json()
        assert data["name"] == sample_artifact_data["name"]
        assert data["url"] == sample_artifact_data["url"]
        assert data["type"] == "model"
        assert "id" in data
        assert "created_at" in data

    def test_create_artifact_with_url_only(self, client: TestClient):
        """Test creating an artifact with just URL (name derived)."""
        response = client.post("/artifacts/model", json={
            "url": "https://huggingface.co/org/my-model"
        })
        assert response.status_code == 201

        data = response.json()
        assert data["name"] == "my-model"  # Derived from URL

    def test_create_artifact_dataset(self, client: TestClient):
        """Test creating a dataset artifact."""
        response = client.post("/artifacts/dataset", json={
            "name": "test-dataset",
            "url": "https://example.com/dataset"
        })
        assert response.status_code == 201
        assert response.json()["type"] == "dataset"

    def test_create_artifact_notebook(self, client: TestClient):
        """Test creating a notebook artifact."""
        response = client.post("/artifacts/notebook", json={
            "name": "test-notebook",
            "url": "https://example.com/notebook"
        })
        assert response.status_code == 201
        assert response.json()["type"] == "notebook"

    def test_list_artifacts_empty(self, client: TestClient):
        """Test listing artifacts when empty."""
        response = client.get("/artifacts")
        assert response.status_code == 200

        data = response.json()
        assert data["artifacts"] == []
        assert data["total"] == 0

    def test_list_artifacts(self, client: TestClient, sample_artifact_data):
        """Test listing artifacts after creating some."""
        # Create artifacts
        client.post("/artifacts/model", json=sample_artifact_data)
        client.post("/artifacts/dataset", json={"name": "ds", "url": "https://a.com/ds"})

        response = client.get("/artifacts")
        assert response.status_code == 200

        data = response.json()
        assert len(data["artifacts"]) == 2
        assert data["total"] == 2

    def test_list_artifacts_filter_by_type(self, client: TestClient, sample_artifact_data):
        """Test filtering artifacts by type."""
        client.post("/artifacts/model", json=sample_artifact_data)
        client.post("/artifacts/dataset", json={"name": "ds", "url": "https://a.com/ds"})

        # Filter by model
        response = client.get("/artifacts?artifact_type=model")
        assert response.status_code == 200
        data = response.json()
        assert len(data["artifacts"]) == 1
        assert data["artifacts"][0]["type"] == "model"

        # Filter by dataset
        response = client.get("/artifacts?artifact_type=dataset")
        data = response.json()
        assert len(data["artifacts"]) == 1
        assert data["artifacts"][0]["type"] == "dataset"

    def test_get_artifact(self, client: TestClient, sample_artifact_data):
        """Test getting a single artifact."""
        # Create artifact
        create_response = client.post("/artifacts/model", json=sample_artifact_data)
        artifact_id = create_response.json()["id"]

        # Get artifact - returns spec-compliant nested format
        response = client.get(f"/artifacts/model/{artifact_id}")
        assert response.status_code == 200

        data = response.json()
        # Spec-compliant format has nested metadata and data
        assert data["metadata"]["id"] == artifact_id
        assert data["metadata"]["name"] == sample_artifact_data["name"]
        assert data["data"]["url"] == sample_artifact_data["url"]

    def test_get_artifact_not_found(self, client: TestClient):
        """Test getting non-existent artifact."""
        response = client.get("/artifacts/model/nonexistent-id")
        assert response.status_code == 404

    def test_get_artifact_wrong_type(self, client: TestClient, sample_artifact_data):
        """Test getting artifact with wrong type."""
        create_response = client.post("/artifacts/model", json=sample_artifact_data)
        artifact_id = create_response.json()["id"]

        # Try to get as dataset
        response = client.get(f"/artifacts/dataset/{artifact_id}")
        assert response.status_code == 404

    def test_delete_artifact(self, client: TestClient, sample_artifact_data):
        """Test deleting an artifact."""
        # Create artifact
        create_response = client.post("/artifacts/model", json=sample_artifact_data)
        artifact_id = create_response.json()["id"]

        # Delete artifact (API returns 200 per OpenAPI spec)
        response = client.delete(f"/artifacts/model/{artifact_id}")
        assert response.status_code == 200

        # Verify deletion
        get_response = client.get(f"/artifacts/model/{artifact_id}")
        assert get_response.status_code == 404

    def test_delete_artifact_not_found(self, client: TestClient):
        """Test deleting non-existent artifact."""
        response = client.delete("/artifacts/model/nonexistent-id")
        assert response.status_code == 404

    def test_download_artifact(self, client: TestClient, sample_artifact_data):
        """Test download endpoint."""
        # Create artifact
        create_response = client.post("/artifacts/model", json=sample_artifact_data)
        artifact_id = create_response.json()["id"]

        # Get download info
        response = client.get(f"/artifacts/model/{artifact_id}/download?part=full")
        assert response.status_code == 200

        data = response.json()
        assert "artifact" in data
        assert data["part"] == "full"

    def test_download_artifact_invalid_part(self, client: TestClient, sample_artifact_data):
        """Test download with invalid part parameter."""
        create_response = client.post("/artifacts/model", json=sample_artifact_data)
        artifact_id = create_response.json()["id"]

        response = client.get(f"/artifacts/model/{artifact_id}/download?part=invalid")
        assert response.status_code == 400

    def test_download_artifact_weights(self, client: TestClient):
        """Test download with weights part."""
        create_response = client.post("/artifacts/model", json={
            "name": "test/model",
            "url": "https://huggingface.co/test/model"
        })
        artifact_id = create_response.json()["id"]

        response = client.get(f"/artifacts/model/{artifact_id}/download?part=weights")
        assert response.status_code == 200
        data = response.json()
        assert data["part"] == "weights"
        assert "files" in data

    def test_download_artifact_config(self, client: TestClient):
        """Test download with config part."""
        create_response = client.post("/artifacts/model", json={
            "name": "test/model",
            "url": "https://huggingface.co/test/model"
        })
        artifact_id = create_response.json()["id"]

        response = client.get(f"/artifacts/model/{artifact_id}/download?part=config")
        assert response.status_code == 200
        data = response.json()
        assert data["part"] == "config"
        assert "files" in data


class TestReset:
    """Test reset endpoint."""

    def test_reset_registry(self, client: TestClient, sample_artifact_data):
        """Test resetting the registry."""
        # Create some artifacts
        client.post("/artifacts/model", json=sample_artifact_data)
        client.post("/artifacts/dataset", json={"name": "ds", "url": "https://a.com/ds"})

        # Verify artifacts exist
        list_response = client.get("/artifacts")
        assert list_response.json()["total"] == 2

        # Reset
        response = client.post("/reset")
        assert response.status_code == 200
        assert response.json()["success"] is True

        # Verify artifacts are gone
        list_response = client.get("/artifacts")
        assert list_response.json()["total"] == 0

