"""Tests for search endpoint."""

import pytest
from fastapi.testclient import TestClient


class TestSearch:
    """Test search functionality."""

    def test_search_by_name(self, client: TestClient):
        """Test searching artifacts by name."""
        # Create artifacts with different names
        client.post("/artifacts/model", json={"name": "bert-base", "url": "https://a.com/1"})
        client.post("/artifacts/model", json={"name": "gpt2-small", "url": "https://a.com/2"})
        client.post("/artifacts/model", json={"name": "bert-large", "url": "https://a.com/3"})

        # Search for "bert"
        response = client.get("/artifacts/search?query=bert")
        assert response.status_code == 200

        data = response.json()
        assert data["query"] == "bert"
        assert len(data["results"]) == 2
        assert all("bert" in r["name"].lower() for r in data["results"])

    def test_search_regex_pattern(self, client: TestClient):
        """Test search with regex pattern."""
        client.post("/artifacts/model", json={"name": "model-v1", "url": "https://a.com/1"})
        client.post("/artifacts/model", json={"name": "model-v2", "url": "https://a.com/2"})
        client.post("/artifacts/model", json={"name": "dataset-v1", "url": "https://a.com/3"})

        # Search with regex
        response = client.get("/artifacts/search?query=model-v[12]")
        assert response.status_code == 200

        data = response.json()
        assert len(data["results"]) == 2

    def test_search_case_insensitive(self, client: TestClient):
        """Test search is case insensitive."""
        client.post("/artifacts/model", json={"name": "BERT-Base", "url": "https://a.com/1"})

        response = client.get("/artifacts/search?query=bert")
        assert response.status_code == 200
        assert len(response.json()["results"]) == 1

    def test_search_no_results(self, client: TestClient):
        """Test search with no matching results."""
        client.post("/artifacts/model", json={"name": "test-model", "url": "https://a.com/1"})

        response = client.get("/artifacts/search?query=nonexistent")
        assert response.status_code == 200

        data = response.json()
        assert len(data["results"]) == 0
        assert data["total"] == 0

    def test_search_invalid_regex(self, client: TestClient):
        """Test search with invalid regex pattern."""
        response = client.get("/artifacts/search?query=[invalid")
        assert response.status_code == 400

    def test_search_with_type_filter(self, client: TestClient):
        """Test search with artifact type filter."""
        client.post("/artifacts/model", json={"name": "test-model", "url": "https://a.com/1"})
        client.post("/artifacts/dataset", json={"name": "test-dataset", "url": "https://a.com/2"})

        response = client.get("/artifacts/search?query=test&artifact_type=model")
        assert response.status_code == 200

        data = response.json()
        assert len(data["results"]) == 1
        assert data["results"][0]["type"] == "model"

    def test_search_limit(self, client: TestClient):
        """Test search result limit returns correct total."""
        # Create many artifacts
        for i in range(10):
            client.post("/artifacts/model", json={"name": f"model-{i}", "url": f"https://a.com/{i}"})

        response = client.get("/artifacts/search?query=model&limit=5")
        assert response.status_code == 200
        data = response.json()
        # Results should be limited to 5
        assert len(data["results"]) == 5
        # But total should report all 10 matches
        assert data["total"] == 10

