"""Tests for rating endpoint."""

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient


class TestRating:
    """Test rating functionality."""

    @patch('src.api.routes.rating.compute_all_metrics')
    def test_rate_artifact(self, mock_compute, client: TestClient, sample_artifact_data):
        """Test rating an artifact."""
        # Mock compute_all_metrics response
        mock_compute.return_value = {
            "metrics": {
                "net_score": 0.75,
                "ramp_up_time": 0.8,
                "bus_factor": 0.7,
                "license": 1.0,
                "performance_claims": 0.6,
                "dataset_and_code_score": 0.5,
                "dataset_quality": 0.5,
                "code_quality": 0.6,
                "size_score": {"raspberry_pi": 0.5, "jetson_nano": 0.5, "desktop_pc": 0.8, "aws_server": 1.0},
                "reproducibility": 0.7,
                "reviewedness": 0.5,
                "treescore": 0.6,
            },
            "latencies": {
                "net_score": 100,
                "ramp_up_time": 50,
                "bus_factor": 60,
                "license": 30,
                "performance_claims": 40,
                "dataset_and_code_score": 80,
                "dataset_quality": 70,
                "code_quality": 90,
            },
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
        assert isinstance(data["net_score_latency"], (int, float))

    @patch('src.api.routes.rating.compute_all_metrics')
    def test_get_rating(self, mock_compute, client: TestClient, sample_artifact_data):
        """Test getting existing rating."""
        mock_compute.return_value = {
            "metrics": {
                "net_score": 0.75,
                "ramp_up_time": 0.8,
                "bus_factor": 0.7,
                "license": 1.0,
                "performance_claims": 0.6,
                "dataset_and_code_score": 0.5,
                "dataset_quality": 0.5,
                "code_quality": 0.6,
                "size_score": {"raspberry_pi": 0.5, "jetson_nano": 0.5, "desktop_pc": 0.8, "aws_server": 1.0},
                "reproducibility": 0.7,
                "reviewedness": 0.5,
                "treescore": 0.6,
            },
            "latencies": {
                "net_score": 100, "ramp_up_time": 50, "bus_factor": 60, "license": 30,
                "performance_claims": 40, "dataset_and_code_score": 80, "dataset_quality": 70, "code_quality": 90,
            },
        }

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

        # Passing metrics - any net_score above 0.1 passes
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

        # Even low individual scores pass if net_score is reasonable
        # (implementation is lenient to avoid blocking legitimate models)
        low_metrics = dict(good_metrics)
        low_metrics["license"] = 0.3
        low_metrics["bus_factor"] = 0.3
        low_metrics["net_score"] = 0.5  # Still above 0.1 threshold
        assert passes_quality_threshold(low_metrics) is True

        # Only reject when net_score is near zero (indicates broken model)
        bad_metrics = {"net_score": 0.05}
        assert passes_quality_threshold(bad_metrics) is False

