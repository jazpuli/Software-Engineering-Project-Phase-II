"""SQLite database connection and session management."""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Database URL - use SQLite file in project root
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./registry.db")

# Create engine with SQLite-specific settings
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},  # Needed for SQLite
    echo=False,
)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for ORM models
Base = declarative_base()


def get_db():
    """Dependency for FastAPI routes to get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables():
    """Create all database tables."""
    from src.api.db.models import Artifact, Rating, LineageEdge, Event
    Base.metadata.create_all(bind=engine)


def drop_tables():
    """Drop all database tables (for reset)."""
    from src.api.db.models import Artifact, Rating, LineageEdge, Event
    Base.metadata.drop_all(bind=engine)


def reset_database():
    """Reset database to default state."""
    drop_tables()
    create_tables()


def clear_all_data(db):
    """Clear all data from database tables (works with any session)."""
    from src.api.db.models import Artifact, Rating, LineageEdge, Event
    db.query(Event).delete()
    db.query(Rating).delete()
    db.query(LineageEdge).delete()
    db.query(Artifact).delete()
    db.commit()

