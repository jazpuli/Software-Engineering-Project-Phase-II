"""SQLAlchemy ORM models for database tables."""

import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, Float, DateTime, Text, ForeignKey, JSON
from sqlalchemy.orm import relationship
from src.api.db.database import Base


def generate_uuid() -> str:
    """Generate a new UUID string."""
    return str(uuid.uuid4())


class Artifact(Base):
    """Artifact table for storing model/dataset/notebook metadata."""
    __tablename__ = "artifacts"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    type = Column(String(50), nullable=False, index=True)  # model, dataset, notebook
    name = Column(String(255), nullable=False, index=True)
    url = Column(Text, nullable=False)
    download_url = Column(Text, nullable=True)  # S3 URL
    s3_key = Column(String(255), nullable=True)  # S3 object key
    metadata_json = Column(JSON, nullable=True)
    size_bytes = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    ratings = relationship("Rating", back_populates="artifact", cascade="all, delete-orphan")
    parent_edges = relationship(
        "LineageEdge",
        foreign_keys="LineageEdge.child_id",
        back_populates="child",
        cascade="all, delete-orphan",
    )
    child_edges = relationship(
        "LineageEdge",
        foreign_keys="LineageEdge.parent_id",
        back_populates="parent",
        cascade="all, delete-orphan",
    )


class Rating(Base):
    """Rating table for storing artifact metric scores."""
    __tablename__ = "ratings"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    artifact_id = Column(String(36), ForeignKey("artifacts.id", ondelete="CASCADE"), nullable=False, index=True)

    # Core metrics
    net_score = Column(Float, nullable=False)
    ramp_up_time = Column(Float, nullable=False)
    bus_factor = Column(Float, nullable=False)
    license = Column(Float, nullable=False)
    performance_claims = Column(Float, nullable=False)
    dataset_and_code_score = Column(Float, nullable=False)
    dataset_quality = Column(Float, nullable=False)
    code_quality = Column(Float, nullable=False)

    # Size scores (stored as JSON)
    size_score = Column(JSON, nullable=False)

    # New metrics
    reproducibility = Column(Float, default=0.0)  # 0, 0.5, or 1
    reviewedness = Column(Float, default=-1.0)  # -1 or fraction
    treescore = Column(Float, default=0.0)  # Mean of parent scores

    # Latency metrics
    net_score_latency = Column(Integer, nullable=True)
    ramp_up_time_latency = Column(Integer, nullable=True)
    bus_factor_latency = Column(Integer, nullable=True)
    license_latency = Column(Integer, nullable=True)
    performance_claims_latency = Column(Integer, nullable=True)
    dataset_and_code_score_latency = Column(Integer, nullable=True)
    dataset_quality_latency = Column(Integer, nullable=True)
    code_quality_latency = Column(Integer, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationship
    artifact = relationship("Artifact", back_populates="ratings")


class LineageEdge(Base):
    """Lineage edges for parent-child relationships between artifacts."""
    __tablename__ = "lineage_edges"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    parent_id = Column(String(36), ForeignKey("artifacts.id", ondelete="CASCADE"), nullable=False, index=True)
    child_id = Column(String(36), ForeignKey("artifacts.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    parent = relationship("Artifact", foreign_keys=[parent_id], back_populates="child_edges")
    child = relationship("Artifact", foreign_keys=[child_id], back_populates="parent_edges")


class Event(Base):
    """Event table for tracking request metrics (health endpoint)."""
    __tablename__ = "events"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    endpoint = Column(String(255), nullable=False, index=True)
    method = Column(String(10), nullable=False)
    status_code = Column(Integer, nullable=False)
    latency_ms = Column(Integer, nullable=False)

