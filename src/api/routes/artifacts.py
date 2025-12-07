"""Artifact CRUD endpoints."""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
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
)

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


@router.get("/artifacts/{artifact_type}/{artifact_id}", response_model=ArtifactData)
async def get_artifact(
    artifact_type: ArtifactType,
    artifact_id: str,
    db: Session = Depends(get_db),
):
    """
    Get a single artifact by type and ID.

    Response includes download_url pointing to S3 if available.
    """
    artifact = crud.get_artifact_by_type_and_id(db, artifact_type.value, artifact_id)
    if not artifact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Artifact {artifact_id} of type {artifact_type.value} not found",
        )

    return artifact_to_response(artifact)


@router.delete(
    "/artifacts/{artifact_type}/{artifact_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_artifact(
    artifact_type: ArtifactType,
    artifact_id: str,
    db: Session = Depends(get_db),
):
    """
    Delete an artifact by type and ID.

    Also removes associated ratings and lineage edges.
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
    return None


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


@router.post("/reset", response_model=ResetResponse)
async def reset_registry(db: Session = Depends(get_db)):
    """
    Reset the registry to its default state.

    Clears all artifacts, ratings, lineage edges, and events.
    """
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

