"""Health and observability endpoints."""

import time
from datetime import datetime
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text

from src.api.db.database import get_db, SessionLocal
from src.api.db.crud import get_health_stats
from src.api.models.schemas import (
    HealthResponse,
    HealthComponentsResponse,
    ComponentStatus,
)
from src.api.storage.s3 import check_health as check_s3_health

router = APIRouter()


def get_app_uptime() -> float:
    """Get application uptime in seconds."""
    try:
        from src.api.main import get_app_start_time
        start_time = get_app_start_time()
        if start_time > 0:
            return time.time() - start_time
    except Exception:
        pass
    return 0.0


def check_db_health(db: Session) -> bool:
    """Check database connectivity."""
    try:
        db.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


@router.get("/health", response_model=HealthResponse)
async def get_health(db: Session = Depends(get_db)):
    """
    Get aggregate system health statistics over the last hour.

    Returns:
    - Overall system status
    - Request counts by endpoint
    - Error counts by endpoint
    - Average latency by endpoint
    """
    # Get stats from events table
    stats = get_health_stats(db)

    # Determine overall status
    total_errors = sum(stats["error_counts"].values())
    total_requests = sum(stats["request_counts"].values())

    if total_requests == 0:
        status = "healthy"
    elif total_errors / max(total_requests, 1) > 0.5:
        status = "unhealthy"
    elif total_errors / max(total_requests, 1) > 0.1:
        status = "degraded"
    else:
        status = "healthy"

    return HealthResponse(
        status=status,
        uptime_seconds=get_app_uptime(),
        request_counts=stats["request_counts"],
        error_counts=stats["error_counts"],
        avg_latency_ms=stats["avg_latency_ms"],
        period_seconds=3600,
    )


@router.get("/health/components", response_model=HealthComponentsResponse)
async def get_health_components(db: Session = Depends(get_db)):
    """
    Get per-component health status.

    Components checked:
    - Database (SQLite) connectivity
    - S3 storage connectivity
    - HTTP server (always OK if endpoint reachable)
    """
    now = datetime.utcnow()
    components = []

    # Check database
    db_healthy = check_db_health(db)
    components.append(ComponentStatus(
        name="database",
        status="healthy" if db_healthy else "unhealthy",
        last_check=now,
        message="SQLite connection OK" if db_healthy else "Database connection failed",
    ))

    # Check S3
    s3_healthy = check_s3_health()
    components.append(ComponentStatus(
        name="storage",
        status="healthy" if s3_healthy else "degraded",
        last_check=now,
        message="S3 connection OK" if s3_healthy else "S3 not configured or unreachable",
    ))

    # HTTP server is always healthy if we're responding
    components.append(ComponentStatus(
        name="http_server",
        status="healthy",
        last_check=now,
        message="Server is responding",
    ))

    # Determine overall status
    statuses = [c.status for c in components]
    if "unhealthy" in statuses:
        overall = "unhealthy"
    elif "degraded" in statuses:
        overall = "degraded"
    else:
        overall = "healthy"

    return HealthComponentsResponse(
        components=components,
        overall_status=overall,
    )


@router.get("/tracks")
async def get_tracks():
    """
    Get the list of tracks planned for implementation.

    Returns the tracks that this implementation supports per the ECE 461 spec.
    """
    return {
        "plannedTracks": [
            "Performance track"
        ]
    }

