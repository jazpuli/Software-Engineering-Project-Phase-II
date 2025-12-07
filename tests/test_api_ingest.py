"""Tests for HuggingFace ingest endpoint."""

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient


class TestIngest:
    """Test HuggingFace model ingest."""

    @patch('src.api.services.metrics.fetch_huggingface_metadata')
    @patch('src.api.routes.ingest.upload_object')
    @patch('src.api.routes.ingest.get_download_url')
    def test_ingest_success(self, mock_download_url, mock_upload, mock_fetch, client: TestClient):
        """Test successful model ingest."""
        # Mock HuggingFace metadata with good scores that pass all thresholds
        mock_fetch.return_value = {
            "cardData": {
                "description": "A well-documented model for testing purposes",
                "long_description": "This is a comprehensive description " * 50,  # Long = good ramp_up
                "training_data": "some dataset",
                "training_procedure": "Fine-tuned with care",
            },
            "siblings": [
                {"rfilename": "config.json"},
                {"rfilename": "model.safetensors"},
                {"rfilename": "tokenizer_config.json"},
                {"rfilename": "generation_config.json"},
                {"rfilename": "modeling.py"},  # Python file for code score
                {"rfilename": "train.py"},
                {"rfilename": "utils.py"},
            ] + [{"rfilename": f"file{i}.txt"} for i in range(10)],  # Many files for bus_factor
            "license": "mit",
            "downloads": 50000,
            "likes": 200,
            "author": "test-org",
            "tags": ["transformers", "pytorch"],
            "pipeline_tag": "text-generation",
            "dataset_tags": ["dataset1", "dataset2", "dataset3"],  # For dataset scores
            "eval_results": [{"task": "test", "metric": "accuracy", "value": 0.95}] * 5,  # For performance_claims
        }
        mock_upload.return_value = "artifacts/test/metadata.json"
        mock_download_url.return_value = "https://s3.example.com/test"

        response = client.post("/ingest", json={
            "url": "https://huggingface.co/test/model",
            "artifact_type": "model"
        })

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["artifact"] is not None
        assert data["rating"] is not None
        assert "test/model" in data["artifact"]["name"]

    @patch('src.api.services.metrics.fetch_huggingface_metadata')
    def test_ingest_quality_rejection(self, mock_fetch, client: TestClient):
        """Test ingest rejection due to low quality scores."""
        # Mock HuggingFace metadata with poor scores
        mock_fetch.return_value = {
            "cardData": {},  # No documentation
            "siblings": [],  # No files
            "license": None,  # No license
            "downloads": 0,
            "likes": 0,
        }

        response = client.post("/ingest", json={
            "url": "https://huggingface.co/test/bad-model",
            "artifact_type": "model"
        })

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "quality threshold" in data["message"].lower()
        assert data["artifact"] is None

    def test_ingest_invalid_url(self, client: TestClient):
        """Test ingest with non-HuggingFace URL."""
        response = client.post("/ingest", json={
            "url": "https://example.com/model",
            "artifact_type": "model"
        })
        assert response.status_code == 400
        assert "HuggingFace" in response.json()["detail"]

    def test_ingest_dataset_url_rejected(self, client: TestClient):
        """Test ingest rejects dataset URLs."""
        response = client.post("/ingest", json={
            "url": "https://huggingface.co/datasets/test/dataset",
            "artifact_type": "model"
        })
        assert response.status_code == 400
        assert "Dataset" in response.json()["detail"]

