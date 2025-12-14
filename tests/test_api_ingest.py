"""Tests for artifact ingest endpoint."""

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient


class TestIngest:
    """Test artifact ingest for models, datasets, and code."""

    def test_ingest_model_success(self, client: TestClient):
        """Test successful model ingest with mocked external calls."""
        with patch('src.api.services.metrics._fetch_hf_data_for_phase2') as mock_hf:
            mock_hf.return_value = {
                "cardData": {"description": "A test model"},
                "siblings": [
                    {"rfilename": "config.json"},
                    {"rfilename": "model.safetensors"},
                    {"rfilename": "tokenizer_config.json"},
                ],
                "license": "mit",
                "downloads": 100000,
                "likes": 500,
                "author": "test-org",
                "tags": ["transformers"],
            }

            response = client.post("/ingest", json={
                "url": "https://huggingface.co/test/model",
                "artifact_type": "model"
            })

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["artifact"] is not None

    def test_ingest_dataset_success(self, client: TestClient):
        """Test successful dataset ingest."""
        with patch('src.api.routes.ingest._fetch_hf_dataset_metadata') as mock_ds:
            mock_ds.return_value = {
                "description": "A test dataset",
                "license": "apache-2.0",
                "downloads": 1000,
                "author": "test-org",
            }

            response = client.post("/ingest", json={
                "url": "https://huggingface.co/datasets/test/dataset",
                "artifact_type": "dataset"
            })

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["artifact"] is not None
            assert data["artifact"]["type"] == "dataset"

    def test_ingest_code_success(self, client: TestClient):
        """Test successful code/GitHub ingest."""
        with patch('src.api.routes.ingest._fetch_github_metadata') as mock_gh:
            mock_gh.return_value = {
                "description": "A test repository",
                "owner": {"login": "test-org"},
                "license": {"spdx_id": "MIT"},
                "stargazers_count": 100,
                "forks_count": 20,
                "language": "Python",
                "size": 1024,
            }

            response = client.post("/ingest", json={
                "url": "https://github.com/test-org/repo",
                "artifact_type": "code"
            })

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["artifact"] is not None
            assert data["artifact"]["type"] == "code"

    def test_ingest_model_low_quality_still_accepted(self, client: TestClient):
        """Test model ingest with low scores is still accepted (lenient policy)."""
        with patch('src.api.services.metrics._fetch_hf_data_for_phase2') as mock_hf, \
             patch('src.api.services.metrics.phase1_compute_one') as mock_phase1:
            # Low quality model data
            mock_hf.return_value = {
                "cardData": {},
                "siblings": [],
                "license": None,
                "downloads": 0,
                "likes": 0,
            }
            # Phase 1 returns low scores - but implementation is lenient
            mock_phase1.return_value = {
                "ramp_up_time": 0.1,
                "bus_factor": 0.1,
                "license": 0.0,
                "performance_claims": 0.1,
                "dataset_and_code_score": 0.0,
                "dataset_quality": 0.0,
                "code_quality": 0.1,
                "size_score": {"raspberry_pi": 0.5, "jetson_nano": 0.5, "desktop_pc": 0.5, "aws_server": 0.5},
            }

            response = client.post("/ingest", json={
                "url": "https://huggingface.co/test/unlicensed-model",
                "artifact_type": "model"
            })

            # Implementation is lenient - accepts models even with low scores
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True

    def test_ingest_auto_detects_type(self, client: TestClient):
        """Test that ingest auto-detects artifact type from URL."""
        with patch('src.api.routes.ingest._fetch_hf_dataset_metadata') as mock_ds:
            mock_ds.return_value = {"description": "Dataset"}

            # Send as model but URL is dataset - should detect as dataset
            response = client.post("/ingest", json={
                "url": "https://huggingface.co/datasets/test/data",
                "artifact_type": "model"  # Wrong type, should be auto-corrected
            })

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            # Should be detected as dataset regardless of requested type
            assert data["artifact"]["type"] == "dataset"

    def test_ingest_extracts_name_from_url(self, client: TestClient):
        """Test that name is correctly extracted from URL."""
        with patch('src.api.routes.ingest._fetch_github_metadata') as mock_gh:
            mock_gh.return_value = {"description": "Test"}

            response = client.post("/ingest", json={
                "url": "https://github.com/openai/transformers",
                "artifact_type": "code"
            })

            assert response.status_code == 200
            data = response.json()
            assert "openai/transformers" in data["artifact"]["name"]
