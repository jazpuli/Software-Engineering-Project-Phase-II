"""Ingest endpoint for HuggingFace models, datasets, and GitHub code."""

import re
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
from src.api.services.lineage import create_lineage_for_artifact
from src.api.storage.s3 import upload_object, get_download_url
from src.api.services.logging import log_request, log_error

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


def _detect_artifact_type(url: str, requested_type: ArtifactType) -> ArtifactType:
    """Detect or validate artifact type based on URL."""
    url_lower = url.lower()

    # HuggingFace dataset URL
    if "huggingface.co/datasets/" in url_lower:
        return ArtifactType.DATASET

    # GitHub URL (code)
    if "github.com" in url_lower:
        return ArtifactType.CODE

    # HuggingFace model URL
    if "huggingface.co" in url_lower:
        return ArtifactType.MODEL

    # Default to requested type
    return requested_type


def _extract_name_from_url(url: str) -> str:
    """Extract artifact name from URL."""
    url = url.rstrip("/")

    # GitHub: owner/repo
    gh_match = re.search(r"github\.com/([^/]+/[^/]+)", url)
    if gh_match:
        return gh_match.group(1)

    # HuggingFace: org/name or datasets/org/name
    parts = url.split("/")
    if len(parts) >= 2:
        if "datasets" in parts:
            # e.g., huggingface.co/datasets/org/name
            idx = parts.index("datasets")
            if idx + 2 < len(parts):
                return f"{parts[idx + 1]}/{parts[idx + 2]}"
            elif idx + 1 < len(parts):
                return parts[idx + 1]
        else:
            # e.g., huggingface.co/org/name
            return f"{parts[-2]}/{parts[-1]}" if parts[-2] not in ("huggingface.co", "www.huggingface.co") else parts[-1]

    return parts[-1] if parts else "unknown"


def _fetch_github_metadata(url: str) -> dict:
    """Fetch metadata from GitHub API."""
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


@router.post("/ingest", response_model=IngestResponse)
async def ingest_artifact(
    request: IngestRequest,
    db: Session = Depends(get_db),
):
    """
    Ingest an artifact from HuggingFace (model/dataset) or GitHub (code).

    Supports:
    - HuggingFace models: https://huggingface.co/org/model
    - HuggingFace datasets: https://huggingface.co/datasets/org/dataset
    - GitHub code: https://github.com/owner/repo

    Process:
    1. Detect artifact type from URL
    2. Fetch metadata from source
    3. Compute trust metrics (for models)
    4. Create artifact record
    """
    url = request.url
    requested_type = request.artifact_type

    # Detect actual artifact type from URL
    artifact_type = _detect_artifact_type(url, requested_type)

    # Extract name from URL
    name = _extract_name_from_url(url)

    # Fetch metadata based on type
    metadata_json = {}
    size_bytes = 0
    hf_data = {}

    if artifact_type == ArtifactType.DATASET:
        # HuggingFace dataset
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

    elif artifact_type == ArtifactType.CODE:
        # GitHub code repository
        gh_data = _fetch_github_metadata(url)
        metadata_json = {
            "description": gh_data.get("description", ""),
            "author": gh_data.get("owner", {}).get("login"),
            "license": gh_data.get("license", {}).get("spdx_id") if gh_data.get("license") else None,
            "tags": gh_data.get("topics", []),
            "extra": {
                "stars": gh_data.get("stargazers_count"),
                "forks": gh_data.get("forks_count"),
                "language": gh_data.get("language"),
            },
        }
        size_bytes = gh_data.get("size", 0) * 1024  # GitHub reports size in KB

    else:
        # HuggingFace model - use full metrics computation
        try:
            result = compute_all_metrics(url)
            metrics = result["metrics"]
            latencies = result["latencies"]
            hf_data = result.get("hf_data", {})

            # Check quality threshold for models
            if not passes_quality_threshold(metrics, threshold=0.5):
                return IngestResponse(
                    success=False,
                    artifact=None,
                    message=f"Model does not meet minimum quality threshold. net_score={metrics.get('net_score', 0):.2f}, license={metrics.get('license', 0)}",
                    rating=None,
                )

            # Fetch README content for regex search
            readme_content = ""
            try:
                import requests
                readme_url = f"https://huggingface.co/{name}/raw/main/README.md"
                readme_resp = requests.get(readme_url, timeout=10)
                if readme_resp.status_code == 200:
                    readme_content = readme_resp.text[:10000]  # Limit size
            except Exception:
                pass

            metadata_json = {
                "description": hf_data.get("cardData", {}).get("description", "") if hf_data else "",
                "readme": readme_content,  # Store README for regex search
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

        except Exception as e:
            log_error("POST", "/ingest", f"Metrics computation failed: {e}")
            # Continue with basic metadata
            pass

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
        import json
        s3_key = f"artifacts/{artifact.id}/metadata.json"
        upload_object(s3_key, json.dumps(metadata_json).encode())
        download_url = get_download_url(s3_key)
        crud.update_artifact_download_url(db, artifact.id, download_url, s3_key)
        artifact = crud.get_artifact(db, artifact.id)
    except Exception:
        pass  # S3 upload optional

    # For models, create lineage and rating
    rating_response = None
    if artifact_type == ArtifactType.MODEL and 'metrics' in dir() and metrics:
        # Detect and create lineage
        try:
            create_lineage_for_artifact(db, artifact.id, name, hf_data)
        except Exception:
            pass

        # Compute treescore
        from src.api.services.metrics import compute_treescore
        treescore = compute_treescore(db, artifact.id)
        metrics["treescore"] = treescore

        # Store rating
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

    return IngestResponse(
        success=True,
        artifact=artifact_to_response(artifact),
        message=f"Successfully ingested {artifact_type.value}: {name}",
        rating=rating_response,
    )
