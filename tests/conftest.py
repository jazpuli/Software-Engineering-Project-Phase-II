"""Pytest configuration and fixtures for both Phase 1 and Phase 2 tests."""

import os
import sys

# Phase 1 setup: Add src to path for imports
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

import pytest


# ============ Phase 2 API Fixtures ============

@pytest.fixture
def db_session():
    """Create a database session for testing CRUD operations directly."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from src.api.db.database import Base
    from src.api.db.models import Artifact, Rating, LineageEdge, Event

    # Use in-memory SQLite for test isolation
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestSession()

    yield session

    session.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    from fastapi.testclient import TestClient
    from src.api.main import app
    from src.api.db.database import create_tables, reset_database

    # Reset database for clean test state
    reset_database()

    with TestClient(app) as test_client:
        yield test_client

    # Cleanup after test
    reset_database()


@pytest.fixture
def sample_artifact_data():
    """Sample artifact data for testing."""
    return {
        "name": "test-model",
        "url": "https://huggingface.co/test-org/test-model",
    }


@pytest.fixture
def sample_huggingface_url():
    """Sample HuggingFace URL for ingest testing."""
    return "https://huggingface.co/google/gemma-3-270m"
