"""Search endpoint for finding artifacts by regex pattern."""

import re
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from src.api.db.database import get_db
from src.api.db import crud
from src.api.models.schemas import (
    ArtifactType,
    ArtifactData,
    ArtifactMetaData,
    ArtifactMetadataSpec,
    ArtifactRegEx,
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

    Rejects patterns known to cause catastrophic backtracking (ReDoS).
    """
    # Reject very long patterns first
    if len(pattern) > 200:
        return False

    # Reject patterns with nested quantifiers (potential for DoS)
    dangerous_patterns = [
        r"\(\.\*\)\+",  # (.*)+
        r"\(\.\+\)\+",  # (.+)+
        r"\(\.\*\)\*",  # (.*)*
        r"\(\.\+\)\*",  # (.+)*
        r"\([^)]+\+\)\+",   # (x+)+ - any nested + quantifier
        r"\([^)]+\*\)\+",   # (x*)+ - any nested * quantifier
        r"\([^)]+\+\)\*",   # (x+)* - any nested quantifier
        r"\([^)]+\*\)\*",   # (x*)* - any nested quantifier
        r"\([^)]+\)\{[0-9]+,",  # (x){n, - grouped repetition (ReDoS vector)
        r"\([^)]*\|[^)]*\)\*",  # (a|b)* - alternation with * quantifier (ReDoS)
        r"\([^)]*\|[^)]*\)\+",  # (a|b)+ - alternation with + quantifier (ReDoS)
        r"\([^)]*\|[^)]*\)\{",  # (a|b){n} - alternation with {n} quantifier
    ]

    for dangerous in dangerous_patterns:
        if re.search(dangerous, pattern):
            return False

    # Reject patterns with large repetition counts like {100,} or {1,99999}
    # This catches patterns like (a{1,99999}){1,99999}
    large_rep_pattern = r"\{(\d+),?(\d*)\}"
    for match in re.finditer(large_rep_pattern, pattern):
        start = int(match.group(1))
        end = match.group(2)
        if start > 50:
            return False
        if end and int(end) > 50:
            return False

    # Reject patterns with multiple nested groups (potential ReDoS)
    if pattern.count('(') > 3:
        return False

    # Reject patterns with backtracking traps
    if re.search(r'\(\?[^:)]', pattern):  # Lookahead/lookbehind can be slow
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


@router.post("/artifact/byRegEx", response_model=List[ArtifactMetadataSpec])
async def search_by_regex(
    request: ArtifactRegEx,
    db: Session = Depends(get_db),
):
    """
    Get any artifacts fitting the regular expression (BASELINE).

    Search for an artifact using regular expression over artifact names
    and READMEs. This is similar to search by name.
    """
    regex_pattern = request.regex

    # Validate regex pattern safety
    if not is_safe_regex(regex_pattern):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or potentially malicious regex pattern",
        )

    # Try to compile the regex
    try:
        pattern = re.compile(regex_pattern, re.IGNORECASE)
    except re.error as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid regex pattern: {str(e)}",
        )

    # Get all artifacts
    all_artifacts = crud.list_artifacts(db, limit=1000)

    # Filter by regex match on name (and README/description in metadata)
    matching = []
    for artifact in all_artifacts:
        # Check name
        if pattern.search(artifact.name):
            matching.append(artifact)
            continue

        # Check description/README in metadata if available
        if artifact.metadata_json:
            # Check description field
            description = artifact.metadata_json.get("description", "")
            if description and pattern.search(description):
                matching.append(artifact)
                continue

            # Check README content (spec requires regex search over READMEs)
            readme = artifact.metadata_json.get("readme", "")
            if readme and pattern.search(readme):
                matching.append(artifact)
                continue

    if not matching:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No artifact found under this regex",
        )

    return [
        ArtifactMetadataSpec(
            name=a.name,
            id=a.id,
            type=ArtifactType(a.type),
        )
        for a in matching
    ]

