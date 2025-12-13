"""Artifact CRUD endpoints."""

from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from src.api.db.database import get_db, reset_database
from src.api.db import crud
from src.api.models.schemas import (
    ArtifactType,
    ArtifactCreateRequest,
    ArtifactData,
    ArtifactMetaData,
    ArtifactListResponse,
    ResetResponse,
    Artifact,
    ArtifactMetadataSpec,
    ArtifactDataSpec,
    ArtifactQuery,
    ArtifactUploadRequest,
    SizeScore,
)
from src.api.services.metrics import compute_all_metrics, passes_quality_threshold, compute_treescore
from src.api.services.lineage import create_lineage_for_artifact
from src.api.storage.s3 import upload_object, get_download_url

router = APIRouter()


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


def artifact_to_spec_response(artifact) -> Artifact:
    """Convert database artifact to spec-compliant Artifact response.

    Returns the nested {metadata: {...}, data: {...}} format required by the OpenAPI spec.
    """
    return Artifact(
        metadata=ArtifactMetadataSpec(
            name=artifact.name,
            id=artifact.id,
            type=ArtifactType(artifact.type),
        ),
        data=ArtifactDataSpec(
            url=artifact.url,
            download_url=artifact.download_url,
        ),
    )


@router.post(
    "/artifacts/{artifact_type}",
    response_model=ArtifactData,
    status_code=status.HTTP_201_CREATED,
    responses={202: {"description": "Artifact creation accepted (async processing)"}},
)
async def create_artifact(
    artifact_type: ArtifactType,
    request: ArtifactCreateRequest,
    db: Session = Depends(get_db),
):
    """
    Create a new artifact.

    Accepts name + url in request body. Version is not required in metadata.
    Returns 201 on success, 202 if async processing is needed.
    """
    # Extract name from request or derive from URL
    name = request.name
    if not name:
        # Derive name from URL (last path segment)
        name = request.url.rstrip("/").split("/")[-1]

    # Create artifact in database
    artifact = crud.create_artifact(
        db=db,
        artifact_type=artifact_type.value,
        name=name,
        url=request.url,
        metadata_json=request.metadata,
    )

    return artifact_to_response(artifact)


# ============ SPEC-COMPLIANT UPLOAD ENDPOINT (BASELINE) ============


def _extract_name_from_url(url: str) -> str:
    """Extract artifact name from URL."""
    import re
    url = url.rstrip("/")

    # Remove tree/main, blob/main, etc. from GitHub URLs
    url = re.sub(r'/tree/[^/]+/?$', '', url)
    url = re.sub(r'/blob/[^/]+/?$', '', url)

    # GitHub: owner/repo -> use just repo name
    gh_match = re.search(r"github\.com/([^/]+)/([^/]+)", url)
    if gh_match:
        owner, repo = gh_match.groups()
        repo = repo.rstrip(".git")
        return repo  # Just the repo name, not owner/repo

    # HuggingFace datasets: datasets/org/name
    if "huggingface.co/datasets/" in url.lower():
        match = re.search(r"huggingface\.co/datasets/([^/]+(?:/[^/]+)?)", url)
        if match:
            parts = match.group(1).split("/")
            return parts[-1] if parts else "unknown"

    # HuggingFace models: org/name
    parts = url.split("/")
    if len(parts) >= 2:
        # Return just the model name, not org/name
        return parts[-1]

    return parts[-1] if parts else "unknown"


def _fetch_github_metadata(url: str) -> dict:
    """Fetch metadata from GitHub API."""
    import re
    import requests

    # Extract owner/repo
    match = re.search(r"github\.com/([^/]+)/([^/]+)", url)
    if not match:
        return {}

    owner, repo = match.groups()
    repo = repo.rstrip(".git")

    try:
        response = requests.get(
            f"https://api.github.com/repos/{owner}/{repo}",
            timeout=10,
            headers={"Accept": "application/vnd.github.v3+json"}
        )
        if response.status_code == 200:
            return response.json()
    except Exception:
        pass

    return {}


def _fetch_hf_dataset_metadata(url: str) -> dict:
    """Fetch metadata from HuggingFace dataset API."""
    import re
    import requests

    # Extract dataset name
    match = re.search(r"huggingface\.co/datasets/([^/]+(?:/[^/]+)?)", url)
    if not match:
        return {}

    dataset_name = match.group(1)

    try:
        response = requests.get(
            f"https://huggingface.co/api/datasets/{dataset_name}",
            timeout=10
        )
        if response.status_code == 200:
            return response.json()
    except Exception:
        pass

    return {}


@router.post(
    "/artifact/{artifact_type}",
    response_model=Artifact,
    status_code=status.HTTP_201_CREATED,
    responses={
        202: {"description": "Artifact ingest accepted but rating deferred"},
        409: {"description": "Artifact exists already"},
        424: {"description": "Artifact not registered due to disqualified rating"},
    },
)
async def upload_artifact_spec(
    artifact_type: ArtifactType,
    request: ArtifactUploadRequest,
    db: Session = Depends(get_db),
):
    """
    Register a new artifact (BASELINE).

    This is the spec-compliant endpoint that accepts:
    - Request body: {"url": "...", "name": "..."} (name is optional)
    - Returns nested {metadata: {...}, data: {...}} format

    For models: computes metrics and creates rating.
    For datasets/code: creates artifact with metadata from source.
    """
    import json

    url = request.url

    # Extract name from request or URL
    name = request.name if request.name else _extract_name_from_url(url)

    # Prepare metadata based on artifact type
    metadata_json = {}
    size_bytes = 0
    metrics = None
    latencies = None
    hf_data = {}

    if artifact_type == ArtifactType.MODEL:
        # HuggingFace model - compute metrics
        try:
            result = compute_all_metrics(url)
            metrics = result["metrics"]
            latencies = result["latencies"]
            hf_data = result.get("hf_data", {})

            # Check quality threshold
            if not passes_quality_threshold(metrics, threshold=0.5):
                raise HTTPException(
                    status_code=status.HTTP_424_FAILED_DEPENDENCY,
                    detail=f"Model does not meet quality threshold. net_score={metrics.get('net_score', 0):.2f}",
                )

            metadata_json = {
                "description": hf_data.get("cardData", {}).get("description", "") if hf_data else "",
                "author": hf_data.get("author") if hf_data else None,
                "license": hf_data.get("license") if hf_data else None,
                "tags": hf_data.get("tags", []) if hf_data else [],
                "extra": {
                    "downloads": hf_data.get("downloads") if hf_data else None,
                    "likes": hf_data.get("likes") if hf_data else None,
                    "pipeline_tag": hf_data.get("pipeline_tag") if hf_data else None,
                },
            }

            # Extract size
            if hf_data:
                safetensors = hf_data.get("safetensors", {})
                if safetensors and safetensors.get("total"):
                    size_bytes = safetensors.get("total", 0)
                else:
                    siblings = hf_data.get("siblings", [])
                    for sibling in siblings:
                        size_bytes += sibling.get("size", 0)

        except HTTPException:
            raise
        except Exception as e:
            # Continue with basic metadata on error
            pass

    elif artifact_type == ArtifactType.DATASET:
        # Fetch dataset metadata
        if "huggingface.co" in url.lower():
            hf_data = _fetch_hf_dataset_metadata(url)
            metadata_json = {
                "description": hf_data.get("description", ""),
                "author": hf_data.get("author"),
                "license": hf_data.get("license"),
                "tags": hf_data.get("tags", []),
                "extra": {
                    "downloads": hf_data.get("downloads"),
                    "likes": hf_data.get("likes"),
                },
            }
        else:
            # External dataset (e.g., Kaggle) - basic metadata
            metadata_json = {"source": "external"}

    elif artifact_type == ArtifactType.CODE:
        # Fetch GitHub metadata
        gh_data = _fetch_github_metadata(url)
        metadata_json = {
            "description": gh_data.get("description", ""),
            "author": gh_data.get("owner", {}).get("login") if gh_data.get("owner") else None,
            "license": gh_data.get("license", {}).get("spdx_id") if gh_data.get("license") else None,
            "tags": gh_data.get("topics", []),
            "extra": {
                "stars": gh_data.get("stargazers_count"),
                "forks": gh_data.get("forks_count"),
                "language": gh_data.get("language"),
            },
        }
        size_bytes = gh_data.get("size", 0) * 1024  # GitHub reports size in KB

    # Create artifact in database
    artifact = crud.create_artifact(
        db=db,
        artifact_type=artifact_type.value,
        name=name,
        url=url,
        metadata_json=metadata_json,
        size_bytes=size_bytes if size_bytes > 0 else None,
    )

    # Try to upload to S3 and get download URL
    try:
        s3_key = f"artifacts/{artifact.id}/metadata.json"
        upload_object(s3_key, json.dumps(metadata_json).encode())
        download_url = get_download_url(s3_key)
        crud.update_artifact_download_url(db, artifact.id, download_url, s3_key)
        artifact = crud.get_artifact(db, artifact.id)
    except Exception:
        # Fallback: generate a self-hosted download URL
        # This ensures download_url is always available per the spec
        fallback_download_url = f"/artifacts/{artifact_type.value}/{artifact.id}/download"
        crud.update_artifact_download_url(db, artifact.id, fallback_download_url, None)
        artifact = crud.get_artifact(db, artifact.id)

    # For models, create lineage and rating
    if artifact_type == ArtifactType.MODEL and metrics:
        # Create lineage
        try:
            create_lineage_for_artifact(db, artifact.id, name, hf_data)
        except Exception:
            pass

        # Compute treescore
        treescore = compute_treescore(db, artifact.id)
        metrics["treescore"] = treescore

        # Store rating
        crud.create_rating(
            db=db,
            artifact_id=artifact.id,
            net_score=metrics["net_score"],
            ramp_up_time=metrics["ramp_up_time"],
            bus_factor=metrics["bus_factor"],
            license_score=metrics["license"],
            performance_claims=metrics["performance_claims"],
            dataset_and_code_score=metrics["dataset_and_code_score"],
            dataset_quality=metrics["dataset_quality"],
            code_quality=metrics["code_quality"],
            size_score=metrics["size_score"],
            reproducibility=metrics["reproducibility"],
            reviewedness=metrics["reviewedness"],
            treescore=treescore,
            latencies=latencies,
        )

    # Return spec-compliant response
    return artifact_to_spec_response(artifact)


@router.get("/artifacts", response_model=ArtifactListResponse)
async def list_artifacts(
    artifact_type: Optional[ArtifactType] = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    """
    List all artifacts with optional type filter.

    Supports pagination via limit and offset parameters.
    """
    type_filter = artifact_type.value if artifact_type else None
    artifacts = crud.list_artifacts(db, artifact_type=type_filter, limit=limit, offset=offset)
    total = crud.count_artifacts(db, artifact_type=type_filter)

    return ArtifactListResponse(
        artifacts=[artifact_to_response(a) for a in artifacts],
        total=total,
    )


@router.post("/artifacts", response_model=List[ArtifactMetadataSpec])
async def query_artifacts(
    queries: List[ArtifactQuery],
    response: Response,
    offset: Optional[str] = Query(None, description="Pagination offset"),
    db: Session = Depends(get_db),
):
    """
    Get artifacts from the registry (BASELINE).

    Search for artifacts satisfying the indicated query.
    If you want to enumerate all artifacts, provide an array with a single
    artifact_query whose name is "*".

    The response is paginated; the response header includes the offset to
    use in the next query.
    """
    results = []
    offset_int = int(offset) if offset else 0
    limit = 100

    for query in queries:
        if query.name == "*":
            # Enumerate all artifacts
            type_filters = [t.value for t in query.types] if query.types else None
            if type_filters:
                for type_filter in type_filters:
                    artifacts = crud.list_artifacts(
                        db, artifact_type=type_filter, limit=limit, offset=offset_int
                    )
                    for a in artifacts:
                        results.append(ArtifactMetadataSpec(
                            name=a.name,
                            id=a.id,
                            type=ArtifactType(a.type),
                        ))
            else:
                artifacts = crud.list_artifacts(db, limit=limit, offset=offset_int)
                for a in artifacts:
                    results.append(ArtifactMetadataSpec(
                        name=a.name,
                        id=a.id,
                        type=ArtifactType(a.type),
                    ))
        else:
            # Search by name
            artifacts = crud.search_artifacts_by_name(db, query.name)
            for a in artifacts:
                if query.types and ArtifactType(a.type) not in query.types:
                    continue
                results.append(ArtifactMetadataSpec(
                    name=a.name,
                    id=a.id,
                    type=ArtifactType(a.type),
                ))

    # Set pagination offset in response header
    next_offset = str(offset_int + len(results))
    response.headers["offset"] = next_offset

    return results


@router.get("/artifacts/{artifact_type}/{artifact_id}", response_model=Artifact)
async def get_artifact(
    artifact_type: ArtifactType,
    artifact_id: str,
    db: Session = Depends(get_db),
):
    """
    Get a single artifact by type and ID (BASELINE).

    Returns the spec-compliant nested {metadata: {...}, data: {...}} format.
    Response includes download_url pointing to S3 if available.
    """
    artifact = crud.get_artifact_by_type_and_id(db, artifact_type.value, artifact_id)
    if not artifact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Artifact {artifact_id} of type {artifact_type.value} not found",
        )

    return artifact_to_spec_response(artifact)


@router.delete(
    "/artifacts/{artifact_type}/{artifact_id}",
    status_code=status.HTTP_200_OK,
)
async def delete_artifact(
    artifact_type: ArtifactType,
    artifact_id: str,
    db: Session = Depends(get_db),
):
    """
    Delete an artifact by type and ID (NON-BASELINE).

    Also removes associated ratings and lineage edges.
    Returns 200 on success per OpenAPI spec.
    """
    artifact = crud.get_artifact_by_type_and_id(db, artifact_type.value, artifact_id)
    if not artifact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Artifact {artifact_id} of type {artifact_type.value} not found",
        )

    # Delete from S3 if applicable
    if artifact.s3_key:
        try:
            from src.api.storage.s3 import delete_object
            delete_object(artifact.s3_key)
        except Exception:
            pass  # Continue even if S3 delete fails

    crud.delete_artifact(db, artifact_id)
    return {"message": "Artifact deleted"}


@router.put(
    "/artifacts/{artifact_type}/{artifact_id}",
    response_model=Artifact,
    responses={
        200: {"description": "Artifact is updated"},
        202: {"description": "Artifact update accepted (async processing)"},
    },
)
async def update_artifact(
    artifact_type: ArtifactType,
    artifact_id: str,
    request: Artifact,
    db: Session = Depends(get_db),
):
    """
    Update an existing artifact (BASELINE).

    The name and id in the request must match the path parameters.
    The artifact source (from artifact data) will replace the previous contents.
    """
    # Verify artifact exists
    artifact = crud.get_artifact_by_type_and_id(db, artifact_type.value, artifact_id)
    if not artifact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Artifact {artifact_id} of type {artifact_type.value} not found",
        )

    # Validate that the ID in the request matches
    if request.metadata.id != artifact_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Artifact ID in request body must match path parameter",
        )

    # Update the artifact
    crud.update_artifact(
        db=db,
        artifact_id=artifact_id,
        url=request.data.url if request.data else None,
        name=request.metadata.name,
        metadata_json=None,  # Can be extended to update metadata
    )

    # Return updated artifact in spec-compliant format
    updated_artifact = crud.get_artifact(db, artifact_id)
    return artifact_to_spec_response(updated_artifact)


@router.get("/artifacts/{artifact_type}/{artifact_id}/download")
async def download_artifact(
    artifact_type: ArtifactType,
    artifact_id: str,
    part: str = "full",
    db: Session = Depends(get_db),
):
    """
    Get download information for an artifact.

    Returns artifact metadata with download_url.

    Supported 'part' values:
    - 'full': Complete artifact package
    - 'weights': Model weights only (.safetensors, .bin, .pt files)
    - 'config': Configuration files only (config.json, tokenizer_config.json, etc.)
    - 'dataset': Associated datasets only
    """
    artifact = crud.get_artifact_by_type_and_id(db, artifact_type.value, artifact_id)
    if not artifact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Artifact {artifact_id} of type {artifact_type.value} not found",
        )

    # Validate part parameter
    valid_parts = ["full", "weights", "config", "dataset"]
    if part not in valid_parts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid part '{part}'. Supported: {', '.join(valid_parts)}",
        )

    response = artifact_to_response(artifact)

    # Build download info based on part
    download_info = {
        "artifact": response.model_dump(),
        "part": part,
        "download_url": artifact.download_url,
        "files": [],
    }

    # For HuggingFace models, provide specific file URLs
    if "huggingface.co" in artifact.url:
        model_id = artifact.name
        base_url = f"https://huggingface.co/{model_id}/resolve/main"

        if part == "full":
            download_info["description"] = "Complete model package including all files"
            download_info["huggingface_url"] = f"https://huggingface.co/{model_id}"

        elif part == "weights":
            download_info["description"] = "Model weights only"
            download_info["files"] = [
                {"name": "model.safetensors", "url": f"{base_url}/model.safetensors"},
                {"name": "pytorch_model.bin", "url": f"{base_url}/pytorch_model.bin"},
            ]
            download_info["note"] = "File availability depends on model. Try each URL."

        elif part == "config":
            download_info["description"] = "Configuration files only"
            download_info["files"] = [
                {"name": "config.json", "url": f"{base_url}/config.json"},
                {"name": "tokenizer_config.json", "url": f"{base_url}/tokenizer_config.json"},
                {"name": "generation_config.json", "url": f"{base_url}/generation_config.json"},
                {"name": "special_tokens_map.json", "url": f"{base_url}/special_tokens_map.json"},
            ]

        elif part == "dataset":
            download_info["description"] = "Associated datasets"
            # Check metadata for dataset info
            metadata = artifact.metadata_json or {}
            extra = metadata.get("extra", {})
            if "dataset_tags" in metadata:
                download_info["datasets"] = metadata.get("dataset_tags", [])
            else:
                download_info["datasets"] = []
                download_info["note"] = "No associated datasets found for this model"

    return download_info


async def _do_reset(db: Session) -> ResetResponse:
    """Internal reset logic."""
    try:
        from src.api.db.database import clear_all_data
        clear_all_data(db)
        return ResetResponse(
            success=True,
            message="Registry reset to default state successfully",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reset registry: {str(e)}",
        )


@router.post("/reset", response_model=ResetResponse)
async def reset_registry_post(db: Session = Depends(get_db)):
    """
    Reset the registry to its default state (BASELINE).

    Clears all artifacts, ratings, lineage edges, and events.
    """
    return await _do_reset(db)


@router.delete("/reset", response_model=ResetResponse)
async def reset_registry_delete(db: Session = Depends(get_db)):
    """
    Reset the registry to its default state (BASELINE).

    Clears all artifacts, ratings, lineage edges, and events.
    """
    return await _do_reset(db)

