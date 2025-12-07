"""Search endpoint for finding artifacts by regex pattern."""

import re
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from src.api.db.database import get_db
from src.api.db import crud
from src.api.models.schemas import (
    ArtifactType,
    ArtifactData,
    ArtifactMetaData,
    SearchResponse,
)

router = APIRouter()

# Maximum regex execution time (for DoS protection)
MAX_REGEX_TIMEOUT_MS = 1000
MAX_RESULTS = 100


def artifact_to_response(artifact) -> ArtifactData:
    """Convert database artifact to response schema."""
    metadata = None
    if artifact.metadata_json:
        metadata = ArtifactMetaData(**artifact.metadata_json)

    return ArtifactData(
        id=artifact.id,
        type=ArtifactType(artifact.type),
        name=artifact.name,
        url=artifact.url,
        download_url=artifact.download_url,
        metadata=metadata,
        size_bytes=artifact.size_bytes,
        created_at=artifact.created_at,
    )


def is_safe_regex(pattern: str) -> bool:
    """
    Check if a regex pattern is safe to execute.

    Rejects patterns known to cause catastrophic backtracking.
    """
    # Reject patterns with nested quantifiers (potential for DoS)
    dangerous_patterns = [
        r"\(\.\*\)\+",  # (.*)+
        r"\(\.\+\)\+",  # (.+)+
        r"\(\.\*\)\*",  # (.*)*
        r"\(\.\+\)\*",  # (.+)*
        r"\(a\+\)\+",   # (a+)+
        r"a\{100,\}",   # Very long repetitions
    ]

    for dangerous in dangerous_patterns:
        if re.search(dangerous, pattern):
            return False

    # Reject very long patterns
    if len(pattern) > 500:
        return False

    return True


@router.get("/artifacts/search", response_model=SearchResponse)
async def search_artifacts(
    query: str = Query(..., description="Regex pattern to search for"),
    artifact_type: Optional[ArtifactType] = None,
    limit: int = Query(default=100, le=MAX_RESULTS),
    db: Session = Depends(get_db),
):
    """
    Search artifacts by name using regex pattern.

    Features:
    - Supports regex patterns for flexible searching
    - Validates patterns to prevent ReDoS attacks
    - Returns 400 for malicious/invalid patterns
    """
    # Validate regex pattern safety
    if not is_safe_regex(query):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or potentially malicious regex pattern",
        )

    # Try to compile the regex
    try:
        pattern = re.compile(query, re.IGNORECASE)
    except re.error as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid regex pattern: {str(e)}",
        )

    # Get all artifacts (filtered by type if specified)
    type_filter = artifact_type.value if artifact_type else None
    all_artifacts = crud.list_artifacts(db, artifact_type=type_filter, limit=1000)

    # Filter by regex match on name - find ALL matches first for accurate total
    matching = [artifact for artifact in all_artifacts if pattern.search(artifact.name)]

    # Apply limit to results, but report true total
    total_matches = len(matching)
    limited_results = matching[:limit]

    return SearchResponse(
        query=query,
        results=[artifact_to_response(a) for a in limited_results],
        total=total_matches,
    )

