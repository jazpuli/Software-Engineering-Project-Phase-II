"""Rating endpoint for computing artifact trust metrics."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.api.db.database import get_db
from src.api.db import crud
from src.api.models.schemas import ArtifactType, RatingResponse, ModelRating, SizeScore
from src.api.services.metrics import compute_all_metrics

router = APIRouter()


@router.post(
    "/artifacts/{artifact_type}/{artifact_id}/rating",
    response_model=RatingResponse,
    responses={
        200: {"description": "Rating computed successfully"},
        202: {"description": "Rating computation accepted (async processing)"},
    },
)
async def rate_artifact(
    artifact_type: ArtifactType,
    artifact_id: str,
    db: Session = Depends(get_db),
):
    """
    Compute and return trust metrics for an artifact.

    Computes all metrics including:
    - Core metrics: ramp_up_time, bus_factor, license, performance_claims, etc.
    - New metrics: reproducibility, reviewedness, treescore
    - Size scores for different hardware targets

    Returns 200 for synchronous computation (MVP), 202 allowed per spec for async.
    """
    # Get artifact from database
    artifact = crud.get_artifact_by_type_and_id(db, artifact_type.value, artifact_id)
    if not artifact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Artifact {artifact_id} of type {artifact_type.value} not found",
        )

    # Compute metrics
    result = compute_all_metrics(artifact.url, db=db, artifact_id=artifact_id)
    metrics = result["metrics"]
    latencies = result["latencies"]

    # Store rating in database
    rating = crud.create_rating(
        db=db,
        artifact_id=artifact_id,
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
        treescore=metrics["treescore"],
        latencies=latencies,
    )

    # Build response
    return RatingResponse(
        artifact_id=artifact_id,
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


@router.get(
    "/artifacts/{artifact_type}/{artifact_id}/rating",
    response_model=RatingResponse,
)
async def get_latest_rating(
    artifact_type: ArtifactType,
    artifact_id: str,
    db: Session = Depends(get_db),
):
    """
    Get the most recent rating for an artifact.

    Returns cached rating if available, without recomputing metrics.
    """
    # Get artifact from database
    artifact = crud.get_artifact_by_type_and_id(db, artifact_type.value, artifact_id)
    if not artifact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Artifact {artifact_id} of type {artifact_type.value} not found",
        )

    # Get latest rating
    rating = crud.get_latest_rating(db, artifact_id)
    if not rating:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No rating found for artifact {artifact_id}. POST to rate first.",
        )

    return RatingResponse(
        artifact_id=artifact_id,
        name=artifact.name,
        category=artifact_type.value.upper(),
        net_score=rating.net_score,
        ramp_up_time=rating.ramp_up_time,
        bus_factor=rating.bus_factor,
        license=rating.license,
        performance_claims=rating.performance_claims,
        dataset_and_code_score=rating.dataset_and_code_score,
        dataset_quality=rating.dataset_quality,
        code_quality=rating.code_quality,
        size_score=SizeScore(**rating.size_score),
        reproducibility=rating.reproducibility,
        reviewedness=rating.reviewedness,
        treescore=rating.treescore,
        net_score_latency=rating.net_score_latency or 0,
        ramp_up_time_latency=rating.ramp_up_time_latency or 0,
        bus_factor_latency=rating.bus_factor_latency or 0,
        license_latency=rating.license_latency or 0,
        performance_claims_latency=rating.performance_claims_latency or 0,
        dataset_and_code_score_latency=rating.dataset_and_code_score_latency or 0,
        dataset_quality_latency=rating.dataset_quality_latency or 0,
        code_quality_latency=rating.code_quality_latency or 0,
    )


@router.get("/artifact/model/{artifact_id}/rate", response_model=ModelRating)
async def get_model_rating_spec(
    artifact_id: str,
    db: Session = Depends(get_db),
):
    """
    Get ratings for this model artifact (BASELINE).

    Returns the rating for a model. Only use this if each metric was
    computed successfully.
    """
    # Get artifact from database (must be a model type)
    artifact = crud.get_artifact_by_type_and_id(db, "model", artifact_id)
    if not artifact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Model artifact {artifact_id} not found",
        )

    # Get latest rating
    rating = crud.get_latest_rating(db, artifact_id)
    if not rating:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No rating found for artifact {artifact_id}",
        )

    return ModelRating(
        name=artifact.name,
        category="MODEL",
        net_score=rating.net_score,
        net_score_latency=rating.net_score_latency or 0.001,
        ramp_up_time=rating.ramp_up_time,
        ramp_up_time_latency=rating.ramp_up_time_latency or 0.001,
        bus_factor=rating.bus_factor,
        bus_factor_latency=rating.bus_factor_latency or 0.001,
        performance_claims=rating.performance_claims,
        performance_claims_latency=rating.performance_claims_latency or 0.001,
        license=rating.license,
        license_latency=rating.license_latency or 0.001,
        dataset_and_code_score=rating.dataset_and_code_score,
        dataset_and_code_score_latency=rating.dataset_and_code_score_latency or 0.001,
        dataset_quality=rating.dataset_quality,
        dataset_quality_latency=rating.dataset_quality_latency or 0.001,
        code_quality=rating.code_quality,
        code_quality_latency=rating.code_quality_latency or 0.001,
        reproducibility=rating.reproducibility,
        reproducibility_latency=rating.reproducibility_latency or 0.001,
        reviewedness=rating.reviewedness,
        reviewedness_latency=rating.reviewedness_latency or 0.001,
        tree_score=rating.treescore,
        tree_score_latency=rating.tree_score_latency or 0.001,
        size_score=SizeScore(**rating.size_score),
        size_score_latency=rating.size_score_latency or 0.001,
    )

