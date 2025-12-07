"""Tests for rating endpoint."""

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient


class TestRating:
    """Test rating functionality."""

    @patch('src.api.services.metrics.fetch_huggingface_metadata')
    def test_rate_artifact(self, mock_fetch, client: TestClient, sample_artifact_data):
        """Test rating an artifact."""
        # Mock HuggingFace API response
        mock_fetch.return_value = {
            "cardData": {"description": "A test model"},
            "siblings": [{"rfilename": "model.safetensors"}],
            "license": "mit",
            "downloads": 1000,
            "likes": 50,
        }

        # Create artifact
        create_response = client.post("/artifacts/model", json=sample_artifact_data)
        artifact = create_response.json()

        # Rate artifact
        response = client.post(f"/artifacts/model/{artifact['id']}/rating")
        assert response.status_code == 200

        data = response.json()
        assert data["artifact_id"] == artifact["id"]
        assert "net_score" in data
        assert "ramp_up_time" in data
        assert "bus_factor" in data
        assert "license" in data
        assert "reproducibility" in data
        assert "reviewedness" in data
        assert "treescore" in data
        assert "size_score" in data

        # Check latencies
        assert "net_score_latency" in data
        assert isinstance(data["net_score_latency"], int)

    @patch('src.api.services.metrics.fetch_huggingface_metadata')
    def test_get_rating(self, mock_fetch, client: TestClient, sample_artifact_data):
        """Test getting existing rating."""
        mock_fetch.return_value = {"license": "mit"}

        # Create and rate artifact
        create_response = client.post("/artifacts/model", json=sample_artifact_data)
        artifact = create_response.json()
        client.post(f"/artifacts/model/{artifact['id']}/rating")

        # Get rating
        response = client.get(f"/artifacts/model/{artifact['id']}/rating")
        assert response.status_code == 200
        assert response.json()["artifact_id"] == artifact["id"]

    def test_get_rating_not_rated(self, client: TestClient, sample_artifact_data):
        """Test getting rating for unrated artifact."""
        create_response = client.post("/artifacts/model", json=sample_artifact_data)
        artifact = create_response.json()

        response = client.get(f"/artifacts/model/{artifact['id']}/rating")
        assert response.status_code == 404

    def test_rate_nonexistent_artifact(self, client: TestClient):
        """Test rating non-existent artifact."""
        response = client.post("/artifacts/model/nonexistent-id/rating")
        assert response.status_code == 404


class TestMetricsComputation:
    """Test metric computation logic."""

    def test_net_score_calculation(self):
        """Test net score weighted average calculation."""
        from src.api.services.metrics import compute_net_score

        metrics = {
            "ramp_up_time": 1.0,
            "bus_factor": 1.0,
            "license": 1.0,
            "performance_claims": 1.0,
            "dataset_and_code_score": 1.0,
            "dataset_quality": 1.0,
            "code_quality": 1.0,
            "size_score": {
                "raspberry_pi": 1.0,
                "jetson_nano": 1.0,
                "desktop_pc": 1.0,
                "aws_server": 1.0,
            },
            "reproducibility": 1.0,
            "reviewedness": 1.0,
        }

        score = compute_net_score(metrics)
        assert 0.9 <= score <= 1.0  # Should be close to 1.0

    def test_net_score_with_negative_reviewedness(self):
        """Test net score ignores -1 reviewedness."""
        from src.api.services.metrics import compute_net_score

        metrics = {
            "ramp_up_time": 0.5,
            "bus_factor": 0.5,
            "license": 0.5,
            "performance_claims": 0.5,
            "dataset_and_code_score": 0.5,
            "dataset_quality": 0.5,
            "code_quality": 0.5,
            "size_score": {
                "raspberry_pi": 0.5,
                "jetson_nano": 0.5,
                "desktop_pc": 0.5,
                "aws_server": 0.5,
            },
            "reproducibility": 0.5,
            "reviewedness": -1.0,  # Not available
        }

        score = compute_net_score(metrics)
        assert 0.4 <= score <= 0.6  # Should be around 0.5

    def test_quality_threshold(self):
        """Test quality threshold checking."""
        from src.api.services.metrics import passes_quality_threshold

        # Passing metrics
        good_metrics = {
            "ramp_up_time": 0.6,
            "bus_factor": 0.6,
            "license": 0.6,
            "performance_claims": 0.6,
            "dataset_and_code_score": 0.6,
            "dataset_quality": 0.6,
            "code_quality": 0.6,
            "reproducibility": 0.5,
            "net_score": 0.6,
            "size_score": {
                "raspberry_pi": 0.6,
                "jetson_nano": 0.6,
                "desktop_pc": 0.6,
                "aws_server": 0.6,
            },
        }
        assert passes_quality_threshold(good_metrics) is True

        # Failing metrics - need 2+ critical failures to reject
        # Critical: bus_factor, license, performance_claims, code_quality
        bad_metrics = dict(good_metrics)
        bad_metrics["license"] = 0.3
        bad_metrics["bus_factor"] = 0.3  # 2 critical failures = rejection
        assert passes_quality_threshold(bad_metrics) is False

