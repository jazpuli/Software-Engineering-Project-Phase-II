"""FastAPI application entry point for Trustworthy Model Registry."""

import os
import time
from pathlib import Path
from contextlib import asynccontextmanager

# Load .env file from project root before other imports
from dotenv import load_dotenv

# Find project root (where .env should be located)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
ENV_FILE = PROJECT_ROOT / ".env"
if ENV_FILE.exists():
    load_dotenv(ENV_FILE)
    print(f"Loaded environment from: {ENV_FILE}")
else:
    # Also try current working directory
    load_dotenv()

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from src.api.db.database import create_tables, get_db
from src.api.routes import artifacts, rating, ingest, search, lineage, health


# Track application start time for uptime calculation
APP_START_TIME: float = 0


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup/shutdown."""
    global APP_START_TIME
    APP_START_TIME = time.time()
    # Create database tables on startup
    create_tables()
    yield
    # Cleanup on shutdown (if needed)


app = FastAPI(
    title="Trustworthy Model Registry",
    description="A registry for ML artifacts with trust metrics and lineage tracking",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS middleware for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request logging and timing middleware
@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    """Log requests and track metrics for health endpoint."""
    from src.api.db.database import SessionLocal
    from src.api.db.models import Event
    from src.api.services.logging import log_request, log_response, log_error

    start_time = time.time()

    # Log incoming request
    body = None
    if request.method in ("POST", "PUT", "PATCH"):
        try:
            body_bytes = await request.body()
            if body_bytes:
                import json
                body = json.loads(body_bytes.decode())
        except Exception:
            body = {"_error": "Could not parse body"}

    log_request(
        method=request.method,
        path=str(request.url.path),
        body=body,
        query_params=dict(request.query_params),
    )

    # Process request
    try:
        response = await call_next(request)
    except Exception as e:
        log_error(request.method, str(request.url.path), str(e))
        raise

    latency_ms = int((time.time() - start_time) * 1000)

    # Log response
    log_response(request.method, str(request.url.path), response.status_code)

    # Record event for health metrics (skip health and log endpoints)
    if not request.url.path.startswith(("/health", "/logs")):
        try:
            db = SessionLocal()
            event = Event(
                endpoint=request.url.path,
                method=request.method,
                status_code=response.status_code,
                latency_ms=latency_ms,
            )
            db.add(event)
            db.commit()
            db.close()
        except Exception:
            pass  # Don't fail requests due to metrics

    return response


# Include routers
# IMPORTANT: search router must come before artifacts router because
# /artifact/byRegEx must match before /artifact/{artifact_type}
app.include_router(search.router, tags=["Search"])
app.include_router(artifacts.router, tags=["Artifacts"])
app.include_router(rating.router, tags=["Rating"])
app.include_router(ingest.router, tags=["Ingest"])
app.include_router(lineage.router, tags=["Lineage"])
app.include_router(health.router, tags=["Health"])

# Mount static files for frontend (create directory if needed)
static_dir = os.path.join(os.path.dirname(__file__), "..", "..", "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
async def root():
    """Root endpoint - redirects to frontend or returns API info."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/static/index.html")


@app.get("/api")
async def api_info():
    """API info endpoint."""
    return {
        "name": "Trustworthy Model Registry",
        "version": "2.0.0",
        "docs": "/docs",
        "health": "/health",
    }


def get_app_start_time() -> float:
    """Get application start time for uptime calculation."""
    return APP_START_TIME


@app.get("/logs")
async def get_logs(lines: int = 100):
    """Get the last N lines of request logs for debugging."""
    from src.api.services.logging import get_log_file_path
    from fastapi.responses import PlainTextResponse

    log_path = get_log_file_path()
    try:
        with open(log_path, "r") as f:
            all_lines = f.readlines()
            last_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines
            return PlainTextResponse("".join(last_lines))
    except FileNotFoundError:
        return PlainTextResponse("No logs yet.")
    except Exception as e:
        return PlainTextResponse(f"Error reading logs: {e}")

