"""CRUD operations for database models."""

from typing import Optional, List
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func

from src.api.db.models import Artifact, Rating, LineageEdge, Event


# ============ Artifact CRUD ============

def create_artifact(
    db: Session,
    artifact_type: str,
    name: str,
    url: str,
    download_url: Optional[str] = None,
    s3_key: Optional[str] = None,
    metadata_json: Optional[dict] = None,
    size_bytes: Optional[int] = None,
) -> Artifact:
    """Create a new artifact."""
    artifact = Artifact(
        type=artifact_type,
        name=name,
        url=url,
        download_url=download_url,
        s3_key=s3_key,
        metadata_json=metadata_json,
        size_bytes=size_bytes,
    )
    db.add(artifact)
    db.commit()
    db.refresh(artifact)
    return artifact


def get_artifact(db: Session, artifact_id: str) -> Optional[Artifact]:
    """Get an artifact by ID."""
    return db.query(Artifact).filter(Artifact.id == artifact_id).first()


def get_artifact_by_type_and_id(
    db: Session, artifact_type: str, artifact_id: str
) -> Optional[Artifact]:
    """Get an artifact by type and ID."""
    return db.query(Artifact).filter(
        Artifact.id == artifact_id,
        Artifact.type == artifact_type,
    ).first()


def list_artifacts(
    db: Session,
    artifact_type: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> List[Artifact]:
    """List artifacts with optional type filter."""
    query = db.query(Artifact)
    if artifact_type:
        query = query.filter(Artifact.type == artifact_type)
    return query.order_by(Artifact.created_at.desc()).offset(offset).limit(limit).all()


def count_artifacts(db: Session, artifact_type: Optional[str] = None) -> int:
    """Count total artifacts."""
    query = db.query(func.count(Artifact.id))
    if artifact_type:
        query = query.filter(Artifact.type == artifact_type)
    return query.scalar()


def delete_artifact(db: Session, artifact_id: str) -> bool:
    """Delete an artifact by ID."""
    artifact = get_artifact(db, artifact_id)
    if artifact:
        db.delete(artifact)
        db.commit()
        return True
    return False


def search_artifacts(db: Session, pattern: str, limit: int = 100) -> List[Artifact]:
    """Search artifacts by name using SQL LIKE (for regex, use Python filtering)."""
    # For SQLite, we use LIKE; for more complex regex, filter in Python
    like_pattern = f"%{pattern}%"
    return db.query(Artifact).filter(
        Artifact.name.like(like_pattern)
    ).limit(limit).all()


def update_artifact_download_url(
    db: Session, artifact_id: str, download_url: str, s3_key: str
) -> Optional[Artifact]:
    """Update artifact's download URL and S3 key."""
    artifact = get_artifact(db, artifact_id)
    if artifact:
        artifact.download_url = download_url
        artifact.s3_key = s3_key
        db.commit()
        db.refresh(artifact)
    return artifact


# ============ Rating CRUD ============

def create_rating(
    db: Session,
    artifact_id: str,
    net_score: float,
    ramp_up_time: float,
    bus_factor: float,
    license_score: float,
    performance_claims: float,
    dataset_and_code_score: float,
    dataset_quality: float,
    code_quality: float,
    size_score: dict,
    reproducibility: float = 0.0,
    reviewedness: float = -1.0,
    treescore: float = 0.0,
    latencies: Optional[dict] = None,
) -> Rating:
    """Create a rating for an artifact."""
    latencies = latencies or {}
    rating = Rating(
        artifact_id=artifact_id,
        net_score=net_score,
        ramp_up_time=ramp_up_time,
        bus_factor=bus_factor,
        license=license_score,
        performance_claims=performance_claims,
        dataset_and_code_score=dataset_and_code_score,
        dataset_quality=dataset_quality,
        code_quality=code_quality,
        size_score=size_score,
        reproducibility=reproducibility,
        reviewedness=reviewedness,
        treescore=treescore,
        net_score_latency=latencies.get("net_score", 0),
        ramp_up_time_latency=latencies.get("ramp_up_time", 0),
        bus_factor_latency=latencies.get("bus_factor", 0),
        license_latency=latencies.get("license", 0),
        performance_claims_latency=latencies.get("performance_claims", 0),
        dataset_and_code_score_latency=latencies.get("dataset_and_code_score", 0),
        dataset_quality_latency=latencies.get("dataset_quality", 0),
        code_quality_latency=latencies.get("code_quality", 0),
    )
    db.add(rating)
    db.commit()
    db.refresh(rating)
    return rating


def get_latest_rating(db: Session, artifact_id: str) -> Optional[Rating]:
    """Get the most recent rating for an artifact."""
    return db.query(Rating).filter(
        Rating.artifact_id == artifact_id
    ).order_by(Rating.created_at.desc()).first()


def get_ratings_for_artifact(db: Session, artifact_id: str) -> List[Rating]:
    """Get all ratings for an artifact."""
    return db.query(Rating).filter(
        Rating.artifact_id == artifact_id
    ).order_by(Rating.created_at.desc()).all()


# ============ Lineage CRUD ============

def add_lineage_edge(db: Session, parent_id: str, child_id: str) -> LineageEdge:
    """Add a parent-child lineage relationship."""
    edge = LineageEdge(parent_id=parent_id, child_id=child_id)
    db.add(edge)
    db.commit()
    db.refresh(edge)
    return edge


def get_parents(db: Session, artifact_id: str) -> List[Artifact]:
    """Get all parent artifacts of an artifact."""
    edges = db.query(LineageEdge).filter(LineageEdge.child_id == artifact_id).all()
    parent_ids = [edge.parent_id for edge in edges]
    return db.query(Artifact).filter(Artifact.id.in_(parent_ids)).all()


def get_children(db: Session, artifact_id: str) -> List[Artifact]:
    """Get all child artifacts of an artifact."""
    edges = db.query(LineageEdge).filter(LineageEdge.parent_id == artifact_id).all()
    child_ids = [edge.child_id for edge in edges]
    return db.query(Artifact).filter(Artifact.id.in_(child_ids)).all()


def get_all_dependencies(db: Session, artifact_id: str, visited: Optional[set] = None) -> List[Artifact]:
    """Recursively get all dependencies (parents and their parents) of an artifact."""
    if visited is None:
        visited = set()

    if artifact_id in visited:
        return []
    visited.add(artifact_id)

    parents = get_parents(db, artifact_id)
    all_deps = list(parents)

    for parent in parents:
        all_deps.extend(get_all_dependencies(db, parent.id, visited))

    return all_deps


# ============ Event CRUD (for health metrics) ============

def record_event(
    db: Session,
    endpoint: str,
    method: str,
    status_code: int,
    latency_ms: int,
) -> Event:
    """Record a request event for health metrics."""
    event = Event(
        endpoint=endpoint,
        method=method,
        status_code=status_code,
        latency_ms=latency_ms,
    )
    db.add(event)
    db.commit()
    return event


def get_events_since(db: Session, since: datetime) -> List[Event]:
    """Get all events since a given timestamp."""
    return db.query(Event).filter(Event.timestamp >= since).all()


def get_events_last_hour(db: Session) -> List[Event]:
    """Get events from the last hour."""
    one_hour_ago = datetime.utcnow() - timedelta(hours=1)
    return get_events_since(db, one_hour_ago)


def cleanup_old_events(db: Session, older_than_hours: int = 24):
    """Delete events older than specified hours."""
    cutoff = datetime.utcnow() - timedelta(hours=older_than_hours)
    db.query(Event).filter(Event.timestamp < cutoff).delete()
    db.commit()


def get_health_stats(db: Session) -> dict:
    """Get aggregated health statistics from events in the last hour."""
    events = get_events_last_hour(db)

    request_counts: dict = {}
    error_counts: dict = {}
    latencies: dict = {}

    for event in events:
        key = f"{event.method} {event.endpoint}"

        # Count requests
        request_counts[key] = request_counts.get(key, 0) + 1

        # Count errors (4xx and 5xx)
        if event.status_code >= 400:
            error_counts[key] = error_counts.get(key, 0) + 1

        # Track latencies for averaging
        if key not in latencies:
            latencies[key] = []
        latencies[key].append(event.latency_ms)

    # Compute average latencies
    avg_latency_ms = {
        key: sum(vals) / len(vals) if vals else 0.0
        for key, vals in latencies.items()
    }

    return {
        "request_counts": request_counts,
        "error_counts": error_counts,
        "avg_latency_ms": avg_latency_ms,
    }

