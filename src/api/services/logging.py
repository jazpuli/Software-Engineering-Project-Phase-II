"""Request logging service for debugging, monitoring, and audit trails.

Security: Provides non-repudiation by logging all API requests with
client identification (IP, User-Agent) and correlation IDs.
"""

import os
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Configure logging
LOG_DIR = Path(os.environ.get("LOG_DIR", "/tmp/api_logs"))
LOG_DIR.mkdir(parents=True, exist_ok=True)

# Create a dedicated logger for requests
request_logger = logging.getLogger("api.requests")
request_logger.setLevel(logging.DEBUG)

# File handler - logs all requests to a file (JSON format for CloudWatch)
log_file = LOG_DIR / "requests.log"
file_handler = logging.FileHandler(log_file)
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s | %(levelname)s | %(message)s'
))
request_logger.addHandler(file_handler)

# Also log to console
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter('%(asctime)s | %(message)s'))
request_logger.addHandler(console_handler)


def generate_request_id() -> str:
    """Generate a unique request ID for correlation."""
    return str(uuid.uuid4())[:8]


def log_request(
    method: str,
    path: str,
    body: dict = None,
    query_params: dict = None,
    client_ip: Optional[str] = None,
    user_agent: Optional[str] = None,
    request_id: Optional[str] = None,
):
    """
    Log an incoming request with client identification.
    
    Security (STRIDE - Repudiation): Captures client IP and User-Agent
    for audit trails and incident investigation.
    """
    if request_id is None:
        request_id = generate_request_id()
    
    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "request_id": request_id,
        "method": method,
        "path": path,
        "client_ip": client_ip or "unknown",
        "user_agent": user_agent or "unknown",
        "body": body,
        "query_params": query_params,
    }
    
    # Log human-readable format with security-relevant info
    request_logger.info(
        f"REQUEST: {method} {path} | id={request_id} | ip={client_ip or 'unknown'} | "
        f"ua={user_agent[:50] if user_agent else 'unknown'}... | body={json.dumps(body) if body else 'None'}"
    )
    
    # Also log structured JSON for CloudWatch/SIEM ingestion
    request_logger.debug(f"REQUEST_JSON: {json.dumps(log_entry)}")


def log_response(
    method: str,
    path: str,
    status_code: int,
    body: dict = None,
    request_id: Optional[str] = None,
    latency_ms: Optional[int] = None,
):
    """Log an outgoing response with timing information."""
    latency_str = f" | latency={latency_ms}ms" if latency_ms else ""
    request_logger.info(
        f"RESPONSE: {method} {path} | id={request_id or 'unknown'} | "
        f"status={status_code}{latency_str} | body={json.dumps(body)[:500] if body else 'None'}"
    )


def log_error(
    method: str,
    path: str,
    error: str,
    request_id: Optional[str] = None,
    client_ip: Optional[str] = None,
):
    """
    Log an error with full context for incident investigation.
    
    Security: Detailed errors are logged server-side only.
    Clients receive generic error messages.
    """
    request_logger.error(
        f"ERROR: {method} {path} | id={request_id or 'unknown'} | "
        f"ip={client_ip or 'unknown'} | {error}"
    )


def get_log_file_path() -> str:
    """Get the path to the log file."""
    return str(log_file)

