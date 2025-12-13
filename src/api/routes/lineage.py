"""Lineage, cost, and license check endpoints."""

import re
import requests
from typing import Optional, Dict, Any
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
    ArtifactLineageGraph,
    ArtifactLineageNode,
    ArtifactLineageEdge,
    SimpleLicenseCheckRequest,
    ArtifactCostEntry,
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


# ============ SPEC-COMPLIANT ENDPOINTS (BASELINE) ============


def _extract_model_id_from_url(url: str) -> Optional[str]:
    """Extract HuggingFace model ID from URL."""
    if not url or "huggingface.co" not in url:
        return None

    parts = url.rstrip("/").split("/")
    try:
        hf_idx = parts.index("huggingface.co")
        model_parts = parts[hf_idx + 1:]
        return "/".join(model_parts) if model_parts else None
    except ValueError:
        return None


def _fetch_config_json(model_id: str) -> Optional[Dict[str, Any]]:
    """Fetch config.json from HuggingFace model."""
    try:
        url = f"https://huggingface.co/{model_id}/raw/main/config.json"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            return response.json()
    except Exception:
        pass
    return None


def _extract_base_model_from_config(config: Dict[str, Any], model_id: str) -> Optional[str]:
    """Extract base model from config.json."""
    # Check common fields for base model reference
    for field in ["_name_or_path", "model_name_or_path", "base_model"]:
        if field in config:
            value = config[field]
            if isinstance(value, str) and value and "/" in value:
                # It's a HuggingFace model ID
                if value != model_id:  # Not self-reference
                    return value
    return None


def _generate_pseudo_id(name: str) -> str:
    """Generate a pseudo artifact ID for external models."""
    import hashlib
    return hashlib.md5(name.encode()).hexdigest()[:12]


@router.get("/artifact/model/{artifact_id}/lineage", response_model=ArtifactLineageGraph)
async def get_model_lineage_spec(
    artifact_id: str,
    db: Session = Depends(get_db),
):
    """
    Retrieve the lineage graph for this artifact (BASELINE).

    Returns lineage graph extracted from structured metadata with
    nodes and edges format.
    """
    # Verify artifact exists
    artifact = crud.get_artifact(db, artifact_id)
    if not artifact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Artifact {artifact_id} not found",
        )

    # Build nodes and edges from lineage
    nodes = []
    edges = []
    seen_ids = set()

    # Add the main artifact as a node
    nodes.append(ArtifactLineageNode(
        artifact_id=artifact_id,
        name=artifact.name,
        source="config_json",
    ))
    seen_ids.add(artifact_id)

    # Try to extract base model from config.json
    model_id = _extract_model_id_from_url(artifact.url)
    if model_id:
        config = _fetch_config_json(model_id)
        if config:
            base_model_name = _extract_base_model_from_config(config, model_id)
            if base_model_name:
                # Check if base model exists in registry
                all_artifacts = crud.list_artifacts(db, limit=1000)
                base_artifact = None
                for a in all_artifacts:
                    if a.name == base_model_name or base_model_name in (a.url or ""):
                        base_artifact = a
                        break

                if base_artifact:
                    base_id = base_artifact.id
                else:
                    # Create pseudo-ID for external base model
                    base_id = _generate_pseudo_id(base_model_name)

                if base_id not in seen_ids:
                    nodes.append(ArtifactLineageNode(
                        artifact_id=base_id,
                        name=base_model_name.split("/")[-1] if "/" in base_model_name else base_model_name,
                        source="config_json",
                    ))
                    seen_ids.add(base_id)

                # Add edge from base model to this artifact
                edges.append(ArtifactLineageEdge(
                    from_node_artifact_id=base_id,
                    to_node_artifact_id=artifact_id,
                    relationship="base_model",
                ))

    # Also include parents from database
    parents = crud.get_parents(db, artifact_id)
    for parent in parents:
        if parent.id not in seen_ids:
            nodes.append(ArtifactLineageNode(
                artifact_id=parent.id,
                name=parent.name,
                source="config_json",
            ))
            seen_ids.add(parent.id)

        # Add edge from parent to this artifact if not already added
        edge_exists = any(
            e.from_node_artifact_id == parent.id and e.to_node_artifact_id == artifact_id
            for e in edges
        )
        if not edge_exists:
            edges.append(ArtifactLineageEdge(
                from_node_artifact_id=parent.id,
                to_node_artifact_id=artifact_id,
                relationship="base_model",
            ))

    # Get children and add them
    children = crud.get_children(db, artifact_id)
    for child in children:
        if child.id not in seen_ids:
            nodes.append(ArtifactLineageNode(
                artifact_id=child.id,
                name=child.name,
                source="config_json",
            ))
            seen_ids.add(child.id)

        # Add edge from this artifact to child
        edges.append(ArtifactLineageEdge(
            from_node_artifact_id=artifact_id,
            to_node_artifact_id=child.id,
            relationship="derived_model",
        ))

    return ArtifactLineageGraph(nodes=nodes, edges=edges)


@router.post("/artifact/model/{artifact_id}/license-check")
async def check_model_license_spec(
    artifact_id: str,
    request: SimpleLicenseCheckRequest,
    db: Session = Depends(get_db),
) -> bool:
    """
    Assess license compatibility for fine-tune and inference usage (BASELINE).

    Returns true if the licenses are compatible, false otherwise.
    """
    # Get artifact
    artifact = crud.get_artifact(db, artifact_id)
    if not artifact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Artifact {artifact_id} not found",
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

    # If we can't determine licenses, return False
    if not norm_artifact or not norm_github:
        return False

    # Check if licenses are compatible
    compatible_set = LICENSE_COMPATIBILITY.get(norm_artifact, {norm_artifact})
    return norm_github in compatible_set or norm_artifact == norm_github


@router.get("/artifact/{artifact_type}/{artifact_id}/cost")
async def get_artifact_cost_spec(
    artifact_type: ArtifactType,
    artifact_id: str,
    dependency: bool = False,
    db: Session = Depends(get_db),
) -> Dict[str, ArtifactCostEntry]:
    """
    Get the cost of an artifact (BASELINE).

    Returns the total cost in MB. If dependency=true, includes the cost
    of all dependencies.
    """
    # Verify artifact exists
    artifact = crud.get_artifact_by_type_and_id(db, artifact_type.value, artifact_id)
    if not artifact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Artifact {artifact_id} not found",
        )

    # Convert bytes to MB
    own_size_mb = (artifact.size_bytes or 0) / (1024 * 1024)

    result: Dict[str, ArtifactCostEntry] = {}

    if not dependency:
        # Simple case: just the artifact cost
        result[artifact_id] = ArtifactCostEntry(total_cost=own_size_mb)
    else:
        # Include all dependencies
        dependencies = crud.get_all_dependencies(db, artifact_id)

        # Add main artifact with standalone and total
        total_cost = own_size_mb
        for dep in dependencies:
            dep_size_mb = (dep.size_bytes or 0) / (1024 * 1024)
            total_cost += dep_size_mb

        result[artifact_id] = ArtifactCostEntry(
            standalone_cost=own_size_mb,
            total_cost=total_cost,
        )

        # Add each dependency
        for dep in dependencies:
            dep_size_mb = (dep.size_bytes or 0) / (1024 * 1024)
            result[dep.id] = ArtifactCostEntry(
                standalone_cost=dep_size_mb,
                total_cost=dep_size_mb,
            )

    return result

