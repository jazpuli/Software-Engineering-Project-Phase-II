"""Request logging service for debugging and monitoring."""

import os
import json
import logging
from datetime import datetime
from pathlib import Path

# Configure logging
LOG_DIR = Path(os.environ.get("LOG_DIR", "/tmp/api_logs"))
LOG_DIR.mkdir(parents=True, exist_ok=True)

# Create a dedicated logger for requests
request_logger = logging.getLogger("api.requests")
request_logger.setLevel(logging.DEBUG)

# File handler - logs all requests to a file
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


def log_request(method: str, path: str, body: dict = None, query_params: dict = None):
    """Log an incoming request."""
    log_entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "method": method,
        "path": path,
        "body": body,
        "query_params": query_params,
    }
    request_logger.info(f"REQUEST: {method} {path} | body={json.dumps(body) if body else 'None'}")


def log_response(method: str, path: str, status_code: int, body: dict = None):
    """Log an outgoing response."""
    request_logger.info(f"RESPONSE: {method} {path} | status={status_code} | body={json.dumps(body)[:500] if body else 'None'}")


def log_error(method: str, path: str, error: str):
    """Log an error."""
    request_logger.error(f"ERROR: {method} {path} | {error}")


def get_log_file_path() -> str:
    """Get the path to the log file."""
    return str(log_file)

