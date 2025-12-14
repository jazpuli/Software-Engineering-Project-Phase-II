#!/usr/bin/env python3
"""Run the Trustworthy Model Registry server."""

import os
import uvicorn


def main():
    """Start the FastAPI server."""
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    reload = os.environ.get("RELOAD", "false").lower() == "true"

    print(f"Starting Trustworthy Model Registry on http://{host}:{port}")
    print(f"API Documentation: http://{host}:{port}/docs")
    print(f"Health Check: http://{host}:{port}/health")

    uvicorn.run(
        "src.api.main:app",
        host=host,
        port=port,
        reload=reload,
    )


if __name__ == "__main__":
    main()

