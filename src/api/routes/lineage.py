"""Lineage, cost, and license check endpoints."""

import re
import requests
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.api.db.database import get_db
from src.api.db import crud
from src.api.models.schemas import (
    ArtifactType,
    LineageNode,
    LineageResponse,
    CostResponse,
    LicenseCheckRequest,
    LicenseCheckResponse,
)

router = APIRouter()


@router.get("/artifacts/{artifact_type}/{artifact_id}/lineage", response_model=LineageResponse)
async def get_artifact_lineage(
    artifact_type: ArtifactType,
    artifact_id: str,
    db: Session = Depends(get_db),
):
    """
    Get lineage graph (parents and children) for an artifact.

    Returns parent artifacts this artifact was derived from,
    and child artifacts derived from this artifact.
    """
    # Verify artifact exists
    artifact = crud.get_artifact(db, artifact_id)
    if not artifact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Artifact {artifact_id} not found",
        )

    # Get parents and children
    parents = crud.get_parents(db, artifact_id)
    children = crud.get_children(db, artifact_id)

    return LineageResponse(
        artifact_id=artifact_id,
        parents=[
            LineageNode(
                id=p.id,
                name=p.name,
                type=ArtifactType(p.type),
            )
            for p in parents
        ],
        children=[
            LineageNode(
                id=c.id,
                name=c.name,
                type=ArtifactType(c.type),
            )
            for c in children
        ],
    )


@router.post("/artifacts/{artifact_type}/{artifact_id}/lineage")
async def add_lineage_edge(
    artifact_type: ArtifactType,
    artifact_id: str,
    parent_id: str,
    db: Session = Depends(get_db),
):
    """
    Add a parent-child lineage relationship.

    The artifact specified by artifact_id becomes a child of parent_id.
    """
    # Verify both artifacts exist
    child = crud.get_artifact(db, artifact_id)
    if not child:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Child artifact {artifact_id} not found",
        )

    parent = crud.get_artifact(db, parent_id)
    if not parent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Parent artifact {parent_id} not found",
        )

    # Prevent self-referencing
    if artifact_id == parent_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Artifact cannot be its own parent",
        )

    # Add edge
    edge = crud.add_lineage_edge(db, parent_id=parent_id, child_id=artifact_id)

    return {
        "success": True,
        "parent_id": parent_id,
        "child_id": artifact_id,
        "message": f"Added lineage: {parent.name} -> {child.name}",
    }


@router.get("/artifacts/{artifact_type}/{artifact_id}/cost", response_model=CostResponse)
async def get_artifact_cost(
    artifact_type: ArtifactType,
    artifact_id: str,
    db: Session = Depends(get_db),
):
    """
    Get size cost of an artifact including all dependencies.

    Recursively sums sizes of the artifact and all parent artifacts,
    avoiding double-counting in case of diamond dependencies.
    """
    # Verify artifact exists
    artifact = crud.get_artifact(db, artifact_id)
    if not artifact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Artifact {artifact_id} not found",
        )

    own_size = artifact.size_bytes or 0

    # Get all dependencies recursively (avoids duplicates via visited set)
    dependencies = crud.get_all_dependencies(db, artifact_id)

    # Sum dependency sizes
    dep_size = sum(d.size_bytes or 0 for d in dependencies)

    return CostResponse(
        artifact_id=artifact_id,
        own_size_bytes=own_size,
        dependencies_size_bytes=dep_size,
        total_size_bytes=own_size + dep_size,
    )


# License compatibility mapping (simplified)
LICENSE_COMPATIBILITY = {
    # Permissive licenses are compatible with most
    "mit": {"mit", "apache-2.0", "bsd-2-clause", "bsd-3-clause", "isc", "unlicense"},
    "apache-2.0": {"mit", "apache-2.0", "bsd-2-clause", "bsd-3-clause", "isc", "unlicense"},
    "bsd-2-clause": {"mit", "apache-2.0", "bsd-2-clause", "bsd-3-clause", "isc", "unlicense"},
    "bsd-3-clause": {"mit", "apache-2.0", "bsd-2-clause", "bsd-3-clause", "isc", "unlicense"},
    # Copyleft licenses have restrictions
    "gpl-2.0": {"gpl-2.0", "gpl-3.0"},
    "gpl-3.0": {"gpl-3.0"},
    "agpl-3.0": {"agpl-3.0"},
    "lgpl-2.1": {"lgpl-2.1", "lgpl-3.0", "gpl-2.0", "gpl-3.0"},
    "lgpl-3.0": {"lgpl-3.0", "gpl-3.0"},
}


def normalize_license(license_str: Optional[str]) -> Optional[str]:
    """Normalize license string for comparison."""
    if not license_str:
        return None

    # Common mappings
    license_lower = license_str.lower().strip()

    # Handle various formats
    mappings = {
        "mit license": "mit",
        "mit": "mit",
        "apache 2.0": "apache-2.0",
        "apache-2.0": "apache-2.0",
        "apache license 2.0": "apache-2.0",
        "bsd-2-clause": "bsd-2-clause",
        "bsd-3-clause": "bsd-3-clause",
        "gpl-2.0": "gpl-2.0",
        "gpl-3.0": "gpl-3.0",
        "gnu gpl v3": "gpl-3.0",
        "agpl-3.0": "agpl-3.0",
        "lgpl-2.1": "lgpl-2.1",
        "lgpl-3.0": "lgpl-3.0",
        "unlicense": "unlicense",
        "cc0-1.0": "unlicense",
    }

    return mappings.get(license_lower, license_lower)


def fetch_github_license(github_url: str) -> Optional[str]:
    """Fetch license from GitHub repository."""
    # Extract owner/repo from URL
    match = re.search(r"github\.com/([^/]+)/([^/]+)", github_url)
    if not match:
        return None

    owner, repo = match.groups()
    repo = repo.rstrip(".git")

    try:
        # Use GitHub API to get license
        api_url = f"https://api.github.com/repos/{owner}/{repo}/license"
        response = requests.get(api_url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            return data.get("license", {}).get("spdx_id")
    except Exception:
        pass

    # Fallback: try to fetch LICENSE file directly
    try:
        raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/main/LICENSE"
        response = requests.get(raw_url, timeout=10)
        if response.status_code == 200:
            content = response.text.lower()
            if "mit license" in content:
                return "MIT"
            elif "apache" in content and "2.0" in content:
                return "Apache-2.0"
            elif "gnu general public license" in content:
                if "version 3" in content:
                    return "GPL-3.0"
                return "GPL-2.0"
    except Exception:
        pass

    return None


@router.post("/license-check", response_model=LicenseCheckResponse)
async def check_license_compatibility(
    request: LicenseCheckRequest,
    db: Session = Depends(get_db),
):
    """
    Check license compatibility between an artifact and a GitHub repository.

    Fetches the license from the GitHub repo and compares it with
    the artifact's license to determine compatibility.
    """
    # Get artifact
    artifact = crud.get_artifact(db, request.artifact_id)
    if not artifact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Artifact {request.artifact_id} not found",
        )

    # Get artifact license from metadata
    artifact_license = None
    if artifact.metadata_json:
        artifact_license = artifact.metadata_json.get("license")

    # Fetch GitHub license
    github_license = fetch_github_license(request.github_url)

    # Normalize licenses
    norm_artifact = normalize_license(artifact_license)
    norm_github = normalize_license(github_license)

    # Check compatibility
    if not norm_artifact or not norm_github:
        return LicenseCheckResponse(
            compatible=False,
            artifact_license=artifact_license,
            github_license=github_license,
            message="Could not determine one or both licenses",
        )

    # Check if licenses are compatible
    compatible_set = LICENSE_COMPATIBILITY.get(norm_artifact, {norm_artifact})
    is_compatible = norm_github in compatible_set or norm_artifact == norm_github

    return LicenseCheckResponse(
        compatible=is_compatible,
        artifact_license=artifact_license,
        github_license=github_license,
        message="Licenses are compatible" if is_compatible else "Licenses may be incompatible",
    )

