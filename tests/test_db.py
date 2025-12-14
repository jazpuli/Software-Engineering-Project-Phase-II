"""Tests for database CRUD operations."""

import pytest
from datetime import datetime, timedelta

from src.api.db import crud
from src.api.db.models import Artifact, Rating, LineageEdge, Event


class TestArtifactCRUD:
    """Test artifact CRUD operations."""

    def test_create_artifact(self, db_session):
        """Test creating an artifact."""
        artifact = crud.create_artifact(
            db_session,
            artifact_type="model",
            name="test-model",
            url="https://example.com/model",
        )

        assert artifact.id is not None
        assert artifact.type == "model"
        assert artifact.name == "test-model"
        assert artifact.url == "https://example.com/model"
        assert artifact.created_at is not None

    def test_get_artifact(self, db_session):
        """Test getting an artifact."""
        created = crud.create_artifact(
            db_session, "model", "test", "https://a.com/m"
        )

        fetched = crud.get_artifact(db_session, created.id)
        assert fetched is not None
        assert fetched.id == created.id

    def test_get_artifact_not_found(self, db_session):
        """Test getting non-existent artifact."""
        result = crud.get_artifact(db_session, "nonexistent")
        assert result is None

    def test_list_artifacts(self, db_session):
        """Test listing artifacts."""
        crud.create_artifact(db_session, "model", "m1", "https://a.com/1")
        crud.create_artifact(db_session, "model", "m2", "https://a.com/2")
        crud.create_artifact(db_session, "dataset", "d1", "https://a.com/3")

        # List all
        all_artifacts = crud.list_artifacts(db_session)
        assert len(all_artifacts) == 3

        # Filter by type
        models = crud.list_artifacts(db_session, artifact_type="model")
        assert len(models) == 2

    def test_delete_artifact(self, db_session):
        """Test deleting an artifact."""
        artifact = crud.create_artifact(db_session, "model", "test", "https://a.com/m")

        result = crud.delete_artifact(db_session, artifact.id)
        assert result is True

        # Verify deletion
        assert crud.get_artifact(db_session, artifact.id) is None

    def test_search_artifacts(self, db_session):
        """Test searching artifacts."""
        crud.create_artifact(db_session, "model", "bert-base", "https://a.com/1")
        crud.create_artifact(db_session, "model", "gpt2", "https://a.com/2")
        crud.create_artifact(db_session, "model", "bert-large", "https://a.com/3")

        results = crud.search_artifacts(db_session, "bert")
        assert len(results) == 2


class TestRatingCRUD:
    """Test rating CRUD operations."""

    def test_create_rating(self, db_session):
        """Test creating a rating."""
        artifact = crud.create_artifact(db_session, "model", "test", "https://a.com/m")

        rating = crud.create_rating(
            db_session,
            artifact_id=artifact.id,
            net_score=0.75,
            ramp_up_time=0.8,
            bus_factor=0.7,
            license_score=1.0,
            performance_claims=0.6,
            dataset_and_code_score=0.5,
            dataset_quality=0.5,
            code_quality=0.5,
            size_score={"raspberry_pi": 0.5, "jetson_nano": 0.5, "desktop_pc": 0.5, "aws_server": 0.5},
        )

        assert rating.id is not None
        assert rating.artifact_id == artifact.id
        assert rating.net_score == 0.75

    def test_get_latest_rating(self, db_session):
        """Test getting latest rating."""
        artifact = crud.create_artifact(db_session, "model", "test", "https://a.com/m")

        # Create multiple ratings
        size_score = {"raspberry_pi": 0.5, "jetson_nano": 0.5, "desktop_pc": 0.5, "aws_server": 0.5}
        crud.create_rating(
            db_session, artifact.id, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, size_score
        )
        crud.create_rating(
            db_session, artifact.id, 0.8, 0.8, 0.8, 0.8, 0.8, 0.8, 0.8, 0.8, size_score
        )

        latest = crud.get_latest_rating(db_session, artifact.id)
        assert latest is not None
        assert latest.net_score == 0.8  # Most recent


class TestLineageCRUD:
    """Test lineage CRUD operations."""

    def test_add_lineage_edge(self, db_session):
        """Test adding a lineage edge."""
        parent = crud.create_artifact(db_session, "model", "parent", "https://a.com/p")
        child = crud.create_artifact(db_session, "model", "child", "https://a.com/c")

        edge = crud.add_lineage_edge(db_session, parent.id, child.id)
        assert edge.parent_id == parent.id
        assert edge.child_id == child.id

    def test_get_parents(self, db_session):
        """Test getting parents."""
        parent1 = crud.create_artifact(db_session, "model", "p1", "https://a.com/1")
        parent2 = crud.create_artifact(db_session, "model", "p2", "https://a.com/2")
        child = crud.create_artifact(db_session, "model", "child", "https://a.com/c")

        crud.add_lineage_edge(db_session, parent1.id, child.id)
        crud.add_lineage_edge(db_session, parent2.id, child.id)

        parents = crud.get_parents(db_session, child.id)
        assert len(parents) == 2

    def test_get_children(self, db_session):
        """Test getting children."""
        parent = crud.create_artifact(db_session, "model", "parent", "https://a.com/p")
        child1 = crud.create_artifact(db_session, "model", "c1", "https://a.com/1")
        child2 = crud.create_artifact(db_session, "model", "c2", "https://a.com/2")

        crud.add_lineage_edge(db_session, parent.id, child1.id)
        crud.add_lineage_edge(db_session, parent.id, child2.id)

        children = crud.get_children(db_session, parent.id)
        assert len(children) == 2

    def test_get_all_dependencies(self, db_session):
        """Test getting all dependencies recursively."""
        grandparent = crud.create_artifact(db_session, "model", "gp", "https://a.com/gp")
        parent = crud.create_artifact(db_session, "model", "p", "https://a.com/p")
        child = crud.create_artifact(db_session, "model", "c", "https://a.com/c")

        crud.add_lineage_edge(db_session, grandparent.id, parent.id)
        crud.add_lineage_edge(db_session, parent.id, child.id)

        deps = crud.get_all_dependencies(db_session, child.id)
        assert len(deps) == 2


class TestEventCRUD:
    """Test event CRUD operations."""

    def test_record_event(self, db_session):
        """Test recording an event."""
        event = crud.record_event(
            db_session,
            endpoint="/artifacts",
            method="GET",
            status_code=200,
            latency_ms=50,
        )

        assert event.id is not None
        assert event.endpoint == "/artifacts"
        assert event.latency_ms == 50

    def test_get_events_last_hour(self, db_session):
        """Test getting events from last hour."""
        # Record events
        crud.record_event(db_session, "/artifacts", "GET", 200, 50)
        crud.record_event(db_session, "/artifacts", "POST", 201, 100)

        events = crud.get_events_last_hour(db_session)
        assert len(events) == 2

    def test_get_health_stats(self, db_session):
        """Test getting health statistics."""
        # Record various events
        crud.record_event(db_session, "/artifacts", "GET", 200, 50)
        crud.record_event(db_session, "/artifacts", "GET", 200, 60)
        crud.record_event(db_session, "/artifacts", "POST", 201, 100)
        crud.record_event(db_session, "/artifacts", "GET", 500, 200)

        stats = crud.get_health_stats(db_session)

        assert "request_counts" in stats
        assert "error_counts" in stats
        assert "avg_latency_ms" in stats

        # Check counts
        assert stats["request_counts"].get("GET /artifacts", 0) == 3
        assert stats["error_counts"].get("GET /artifacts", 0) == 1

