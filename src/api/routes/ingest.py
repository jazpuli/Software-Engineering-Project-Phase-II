"""HuggingFace model ingest endpoint."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.api.db.database import get_db
from src.api.db import crud
from src.api.models.schemas import (
    ArtifactType,
    ArtifactData,
    ArtifactMetaData,
    IngestRequest,
    IngestResponse,
    RatingResponse,
    SizeScore,
)
from src.api.services.metrics import compute_all_metrics, passes_quality_threshold
from src.api.services.lineage import create_lineage_for_artifact, detect_parent_models
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


@router.post("/ingest", response_model=IngestResponse)
async def ingest_huggingface_model(
    request: IngestRequest,
    db: Session = Depends(get_db),
):
    """
    Ingest a model from HuggingFace.

    Process:
    1. Fetch model metadata from HuggingFace
    2. Compute trust metrics
    3. Require >= 0.5 on all non-latency metrics to accept
    4. If accepted, create artifact record

    This endpoint handles the Tiny-LLM test case per autograder spec.
    """
    url = request.url
    artifact_type = request.artifact_type

    # Validate URL is a HuggingFace URL
    if "huggingface.co" not in url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="URL must be a HuggingFace model URL",
        )

    # Skip dataset URLs
    if "/datasets/" in url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Dataset URLs are not supported for ingest. Use model URLs.",
        )

    # Extract model name from URL
    parts = url.rstrip("/").split("/")
    model_name = parts[-1]
    if len(parts) >= 2 and parts[-2] != "huggingface.co":
        # Include org name for uniqueness
        model_name = f"{parts[-2]}/{parts[-1]}"

    # Compute metrics for the model
    result = compute_all_metrics(url)
    metrics = result["metrics"]
    latencies = result["latencies"]
    hf_data = result.get("hf_data", {})

    # Check quality threshold
    if not passes_quality_threshold(metrics, threshold=0.5):
        return IngestResponse(
            success=False,
            artifact=None,
            message="Model does not meet minimum quality threshold (>= 0.5 on all metrics)",
            rating=None,
        )

    # Extract size from HuggingFace data
    size_bytes = 0
    # Try safetensors total first
    safetensors = hf_data.get("safetensors", {})
    if safetensors and safetensors.get("total"):
        size_bytes = safetensors.get("total", 0)
    else:
        # Fall back to summing file sizes from siblings
        siblings = hf_data.get("siblings", [])
        for sibling in siblings:
            size_bytes += sibling.get("size", 0)

    # Create artifact in database
    metadata_json = {
        "description": hf_data.get("cardData", {}).get("description", ""),
        "author": hf_data.get("author"),
        "license": hf_data.get("license"),
        "tags": hf_data.get("tags", []),
        "extra": {
            "downloads": hf_data.get("downloads"),
            "likes": hf_data.get("likes"),
            "pipeline_tag": hf_data.get("pipeline_tag"),
        },
    }

    artifact = crud.create_artifact(
        db=db,
        artifact_type=artifact_type.value,
        name=model_name,
        url=url,
        metadata_json=metadata_json,
        size_bytes=size_bytes if size_bytes > 0 else None,
    )

    # Try to upload a reference file to S3 and get download URL
    try:
        s3_key = f"artifacts/{artifact.id}/metadata.json"
        import json
        upload_object(s3_key, json.dumps(metadata_json).encode())
        download_url = get_download_url(s3_key)
        crud.update_artifact_download_url(db, artifact.id, download_url, s3_key)
        artifact = crud.get_artifact(db, artifact.id)  # Refresh
    except Exception:
        # S3 upload optional for MVP
        pass

    # Detect and create lineage relationships BEFORE computing treescore
    linked_parents = []
    try:
        linked_parents = create_lineage_for_artifact(db, artifact.id, model_name, hf_data)
    except Exception:
        pass  # Lineage detection is optional

    # Now compute treescore with actual parent relationships
    from src.api.services.metrics import compute_treescore
    treescore = compute_treescore(db, artifact.id)
    metrics["treescore"] = treescore

    # Store rating in database
    rating = crud.create_rating(
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

    # Build rating response
    rating_response = RatingResponse(
        artifact_id=artifact.id,
        name=artifact.name,
        category=artifact_type.value.upper(),
        net_score=metrics["net_score"],
        ramp_up_time=metrics["ramp_up_time"],
        bus_factor=metrics["bus_factor"],
        license=metrics["license"],
        performance_claims=metrics["performance_claims"],
        dataset_and_code_score=metrics["dataset_and_code_score"],
        dataset_quality=metrics["dataset_quality"],
        code_quality=metrics["code_quality"],
        size_score=SizeScore(**metrics["size_score"]),
        reproducibility=metrics["reproducibility"],
        reviewedness=metrics["reviewedness"],
        treescore=metrics["treescore"],
        net_score_latency=latencies["net_score"],
        ramp_up_time_latency=latencies["ramp_up_time"],
        bus_factor_latency=latencies["bus_factor"],
        license_latency=latencies["license"],
        performance_claims_latency=latencies["performance_claims"],
        dataset_and_code_score_latency=latencies["dataset_and_code_score"],
        dataset_quality_latency=latencies["dataset_quality"],
        code_quality_latency=latencies["code_quality"],
    )

    # Build success message
    message = f"Successfully ingested model: {model_name}"
    if linked_parents:
        message += f" (linked to {len(linked_parents)} parent model(s))"

    return IngestResponse(
        success=True,
        artifact=artifact_to_response(artifact),
        message=message,
        rating=rating_response,
    )

