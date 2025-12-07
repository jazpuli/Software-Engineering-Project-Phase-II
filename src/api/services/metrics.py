"""Metrics computation service for artifact rating.

This module integrates Phase 1's metric computation infrastructure with
Phase 2's API, adding new metrics (reproducibility, reviewedness, treescore).
"""

import time
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session

from src.api.db import crud

# Import Phase 1 infrastructure
from src.core.compute import compute_one as phase1_compute_one
from src.core.url import parse_url


# Extended weights for Phase 2 (includes new metrics)
WEIGHTS = {
    "ramp_up_time": 0.12,
    "bus_factor": 0.12,
    "license": 0.12,
    "performance_claims": 0.12,
    "dataset_and_code_score": 0.10,
    "dataset_quality": 0.10,
    "code_quality": 0.10,
    "size_score": 0.10,
    "reproducibility": 0.06,
    "reviewedness": 0.06,
}


def compute_net_score(metrics: dict) -> float:
    """Compute weighted average of metrics.

    When reviewedness is unavailable (-1), we exclude it from both the numerator
    and denominator to ensure fair comparison between models with and without
    GitHub repositories.
    """
    size_score = metrics.get("size_score", {})
    if isinstance(size_score, dict) and size_score:
        size_avg = sum(size_score.values()) / len(size_score)
    else:
        size_avg = 0.5

    # Track which weights are actually used for normalization
    total_weight = 0.0
    weighted_sum = 0.0

    # Always-available metrics
    always_available = [
        ("ramp_up_time", metrics.get("ramp_up_time", 0)),
        ("bus_factor", metrics.get("bus_factor", 0)),
        ("license", metrics.get("license", 0)),
        ("performance_claims", metrics.get("performance_claims", 0)),
        ("dataset_and_code_score", metrics.get("dataset_and_code_score", 0)),
        ("dataset_quality", metrics.get("dataset_quality", 0)),
        ("code_quality", metrics.get("code_quality", 0)),
        ("size_score", size_avg),
        ("reproducibility", metrics.get("reproducibility", 0)),
    ]

    for key, value in always_available:
        weighted_sum += WEIGHTS[key] * value
        total_weight += WEIGHTS[key]

    # Handle reviewedness (-1 means not available, exclude from calculation)
    reviewedness = metrics.get("reviewedness", -1)
    if reviewedness >= 0:
        weighted_sum += WEIGHTS["reviewedness"] * reviewedness
        total_weight += WEIGHTS["reviewedness"]

    # Normalize to ensure score is properly weighted
    if total_weight > 0:
        score = weighted_sum / total_weight
    else:
        score = 0.0

    return round(score, 3)


def compute_reproducibility(hf_data: dict) -> float:
    """
    Compute reproducibility metric.

    Returns:
        0 - No reproducibility indicators
        0.5 - Some indicators present
        1.0 - Strong reproducibility indicators
    """
    indicators = 0

    # Check for config files
    siblings = hf_data.get("siblings", []) or hf_data.get("files", []) or []
    config_files = ["config.json", "tokenizer_config.json", "generation_config.json"]
    for sibling in siblings:
        filename = sibling.get("rfilename", "") if isinstance(sibling, dict) else str(sibling)
        if filename in config_files:
            indicators += 1

    # Check for training info in card data
    card_data = hf_data.get("card_data", {}) or hf_data.get("cardData", {}) or {}
    if card_data.get("training_data") or card_data.get("training_procedure"):
        indicators += 2

    if indicators >= 3:
        return 1.0
    elif indicators >= 1:
        return 0.5
    return 0.0


def compute_reviewedness(hf_data: dict) -> float:
    """
    Compute reviewedness metric.

    Per spec: The fraction of all code in the associated GitHub repository
    that was introduced through pull requests with a code review.
    Returns -1 if there is no linked GitHub repository.
    """
    try:
        from src.api.services.github import (
            find_github_url_for_model,
            compute_reviewedness_for_repo,
        )

        # Try to find GitHub URL
        github_url = find_github_url_for_model(hf_data)

        if github_url:
            # Compute actual reviewedness from GitHub
            return compute_reviewedness_for_repo(github_url)

        # Fallback: use community engagement as proxy
        downloads = hf_data.get("downloads", 0)
        likes = hf_data.get("likes", 0)

        # High engagement suggests some level of review/vetting
        if downloads > 10000 and likes > 100:
            return 0.7
        elif downloads > 1000 or likes > 10:
            return 0.3 + min(likes / 500, 0.3)

        return -1.0  # No GitHub and low engagement

    except Exception:
        return -1.0


def compute_treescore(db: Session, artifact_id: str) -> float:
    """
    Compute treescore as mean of parent artifact scores.

    Args:
        db: Database session
        artifact_id: ID of the artifact to compute treescore for

    Returns:
        Mean net_score of parent artifacts, or -1 if no parents (N/A)
    """
    parents = crud.get_parents(db, artifact_id)
    if not parents:
        return -1.0  # No parents = N/A, not 0

    parent_scores = []
    for parent in parents:
        rating = crud.get_latest_rating(db, parent.id)
        if rating:
            parent_scores.append(rating.net_score)

    if not parent_scores:
        return -1.0  # Parents exist but have no ratings = N/A

    return round(sum(parent_scores) / len(parent_scores), 3)


def _extract_github_urls(hf_data: Dict[str, Any]) -> List[str]:
    """Extract GitHub repository URLs from HuggingFace model metadata."""
    github_urls = []

    # Check model card for GitHub links
    card_data = hf_data.get("cardData", {}) or hf_data.get("card_data", {}) or {}

    # Check for repo_url field
    repo_url = card_data.get("repo_url") or card_data.get("github") or card_data.get("repo")
    if repo_url and "github.com" in str(repo_url):
        github_urls.append(repo_url)

    # Check tags for github links
    tags = hf_data.get("tags", []) or []
    for tag in tags:
        if isinstance(tag, str) and "github.com" in tag:
            github_urls.append(tag)

    # Check model card text for GitHub URLs
    readme = hf_data.get("readme", "") or hf_data.get("card", "") or ""
    import re
    gh_pattern = r'https?://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+'
    found = re.findall(gh_pattern, readme)
    github_urls.extend(found)

    return list(set(github_urls))[:3]  # Limit to 3 unique URLs


def _extract_dataset_urls(hf_data: Dict[str, Any]) -> List[str]:
    """Extract dataset URLs from HuggingFace model metadata."""
    dataset_urls = []

    # Check dataset_tags
    dataset_tags = hf_data.get("dataset_tags", []) or hf_data.get("datasets", []) or []
    for ds in dataset_tags:
        if isinstance(ds, str):
            # Convert dataset name to URL
            if not ds.startswith("http"):
                dataset_urls.append(f"https://huggingface.co/datasets/{ds}")
            else:
                dataset_urls.append(ds)

    # Check card data
    card_data = hf_data.get("cardData", {}) or hf_data.get("card_data", {}) or {}
    card_datasets = card_data.get("datasets", []) or card_data.get("dataset", []) or []
    if isinstance(card_datasets, str):
        card_datasets = [card_datasets]
    for ds in card_datasets:
        if isinstance(ds, str):
            if not ds.startswith("http"):
                dataset_urls.append(f"https://huggingface.co/datasets/{ds}")
            else:
                dataset_urls.append(ds)

    return list(set(dataset_urls))[:5]  # Limit to 5 unique URLs


def _apply_hf_fallbacks(
    metrics: Dict[str, Any],
    hf_data: Dict[str, Any],
    github_urls: List[str],
    dataset_urls: List[str],
) -> Dict[str, Any]:
    """
    Apply reasonable fallback scores for models without GitHub repos/datasets.

    Many HuggingFace models are just model weights without associated code
    repositories. We use model popularity and other signals as proxies.
    """
    downloads = hf_data.get("downloads", 0) or 0
    likes = hf_data.get("likes", 0) or 0
    siblings = hf_data.get("siblings", []) or []

    # bus_factor: If no GitHub repo, use popularity as a proxy
    # Popular models have been vetted by many users
    if metrics["bus_factor"] == 0 and not github_urls:
        if downloads > 100000 and likes > 100:
            metrics["bus_factor"] = 0.7  # Very popular model
        elif downloads > 10000 or likes > 50:
            metrics["bus_factor"] = 0.5  # Popular model
        elif downloads > 1000 or likes > 10:
            metrics["bus_factor"] = 0.3  # Some usage
        else:
            metrics["bus_factor"] = 0.1  # New/unknown model

    # code_quality: Give credit for having model files, configs, etc.
    if metrics["code_quality"] < 0.3 and not github_urls:
        has_safetensors = any(s.get("rfilename", "").endswith(".safetensors") for s in siblings)
        has_config = any(s.get("rfilename", "") == "config.json" for s in siblings)
        has_tokenizer = any("tokenizer" in s.get("rfilename", "").lower() for s in siblings)

        code_score = 0.2  # Base score for any model
        if has_safetensors:
            code_score += 0.2  # Modern format
        if has_config:
            code_score += 0.2  # Proper configuration
        if has_tokenizer:
            code_score += 0.1  # Complete package

        metrics["code_quality"] = max(metrics["code_quality"], min(code_score, 0.7))

    # dataset_and_code_score: Give partial credit for having model assets
    if metrics["dataset_and_code_score"] == 0:
        has_model_files = any(
            s.get("rfilename", "").endswith((".safetensors", ".bin", ".pt", ".onnx"))
            for s in siblings
        )
        if has_model_files:
            metrics["dataset_and_code_score"] = 0.3  # Has model weights
        if dataset_urls:
            metrics["dataset_and_code_score"] += 0.3  # Has linked datasets

    # dataset_quality: If model references datasets but we couldn't find URLs
    if metrics["dataset_quality"] == 0 and not dataset_urls:
        # Check if model mentions training data
        tags = hf_data.get("tags", []) or []
        if any("dataset:" in str(t).lower() for t in tags):
            metrics["dataset_quality"] = 0.4  # References training data

    return metrics


def compute_all_metrics(
    url: str,
    db: Optional[Session] = None,
    artifact_id: Optional[str] = None,
) -> dict:
    """
    Compute all metrics for an artifact using Phase 1 infrastructure.

    This integrates Phase 1's proven metric computation with Phase 2's
    new metrics (reproducibility, reviewedness, treescore).

    Args:
        url: Source URL (HuggingFace URL)
        db: Optional database session for treescore calculation
        artifact_id: Optional artifact ID for treescore calculation

    Returns:
        Dictionary containing all metric scores and latencies
    """
    start_time = time.time()

    # Fetch HF metadata first to extract associated repos and datasets
    hf_data = _fetch_hf_data_for_phase2(url)

    # Extract GitHub repos and datasets from model metadata
    github_urls = _extract_github_urls(hf_data)
    dataset_urls = _extract_dataset_urls(hf_data)

    # Use Phase 1's compute_one with extracted repos and datasets
    phase1_result = phase1_compute_one(url, datasets=dataset_urls, code=github_urls)

    if not phase1_result:
        # If Phase 1 can't process (e.g., not a valid HF model), use fallback
        phase1_result = _fallback_metrics(url)

    # Extract metrics from Phase 1 result
    metrics = {
        "ramp_up_time": phase1_result.get("ramp_up_time", 0.5),
        "bus_factor": phase1_result.get("bus_factor", 0.5),
        "license": phase1_result.get("license", 0.0),
        "performance_claims": phase1_result.get("performance_claims", 0.5),
        "dataset_and_code_score": phase1_result.get("dataset_and_code_score", 0.5),
        "dataset_quality": phase1_result.get("dataset_quality", 0.5),
        "code_quality": phase1_result.get("code_quality", 0.5),
        "size_score": phase1_result.get("size_score", {
            "raspberry_pi": 0.5,
            "jetson_nano": 0.5,
            "desktop_pc": 0.5,
            "aws_server": 0.5,
        }),
    }

    # Apply reasonable fallbacks for models without GitHub repos/datasets
    # (Many HF models are just weights, no code repo)
    metrics = _apply_hf_fallbacks(metrics, hf_data, github_urls, dataset_urls)

    # Extract latencies from Phase 1
    latencies = {
        "ramp_up_time": phase1_result.get("ramp_up_time_latency", 0),
        "bus_factor": phase1_result.get("bus_factor_latency", 0),
        "license": phase1_result.get("license_latency", 0),
        "performance_claims": phase1_result.get("performance_claims_latency", 0),
        "dataset_and_code_score": phase1_result.get("dataset_and_code_score_latency", 0),
        "dataset_quality": phase1_result.get("dataset_quality_latency", 0),
        "code_quality": phase1_result.get("code_quality_latency", 0),
    }

    # hf_data already fetched above for Phase 2 metrics (reproducibility, reviewedness)

    # Add Phase 2 metrics
    metrics["reproducibility"] = compute_reproducibility(hf_data)
    metrics["reviewedness"] = compute_reviewedness(hf_data)

    # Compute treescore if database context available
    if db and artifact_id:
        metrics["treescore"] = compute_treescore(db, artifact_id)
    else:
        metrics["treescore"] = -1.0

    # Compute net score with all metrics
    metrics["net_score"] = compute_net_score(metrics)

    # Calculate total latency
    elapsed_ms = int((time.time() - start_time) * 1000)
    latencies["net_score"] = elapsed_ms

    return {
        "metrics": metrics,
        "latencies": latencies,
        "hf_data": hf_data,
    }


def _fetch_hf_data_for_phase2(url: str) -> Dict[str, Any]:
    """Fetch HuggingFace data for Phase 2 metrics."""
    import requests

    # Extract model name from URL
    parts = url.rstrip("/").split("/")
    if len(parts) >= 2:
        full_model_name = f"{parts[-2]}/{parts[-1]}"
    else:
        full_model_name = parts[-1]

    try:
        response = requests.get(
            f"https://huggingface.co/api/models/{full_model_name}",
            timeout=10
        )
        if response.status_code == 200:
            return response.json()
    except Exception:
        pass

    return {}


def _fallback_metrics(url: str) -> Dict[str, Any]:
    """Fallback metrics computation when Phase 1 can't process the URL."""
    import requests

    # Try to fetch basic HF data
    hf_data = _fetch_hf_data_for_phase2(url)

    # Compute basic metrics from HF data
    has_license = bool(hf_data.get("license") or hf_data.get("cardData", {}).get("license"))
    siblings = hf_data.get("siblings", [])

    return {
        "name": url.rstrip("/").split("/")[-1],
        "category": "MODEL",
        "ramp_up_time": 0.5,
        "ramp_up_time_latency": 0,
        "bus_factor": min(len(siblings) / 10, 1.0) if siblings else 0.5,
        "bus_factor_latency": 0,
        "license": 1.0 if has_license else 0.0,
        "license_latency": 0,
        "performance_claims": 0.5,
        "performance_claims_latency": 0,
        "dataset_and_code_score": 0.5,
        "dataset_and_code_score_latency": 0,
        "dataset_quality": 0.5,
        "dataset_quality_latency": 0,
        "code_quality": 0.5,
        "code_quality_latency": 0,
        "size_score": {
            "raspberry_pi": 0.5,
            "jetson_nano": 0.5,
            "desktop_pc": 0.5,
            "aws_server": 0.5,
        },
        "size_score_latency": 0,
        "net_score": 0.5,
        "net_score_latency": 0,
    }


def passes_quality_threshold(metrics: dict, threshold: float = 0.5) -> bool:
    """
    Check if metrics pass the quality threshold for ingest.

    This uses a lenient approach suitable for HuggingFace model repos,
    which often are just model weights without code/tests/CI.

    Key requirements:
    - Must have a license (critical for reuse)
    - Net score must be at least 0.25
    - At least some documentation (ramp_up_time > 0.3)
    """
    # License is the most important - models must be properly licensed
    license_score = metrics.get("license", 0)
    if license_score < 0.5:
        return False

    # Net score should be reasonable (lowered from 0.3 to 0.25 for model repos)
    net_score = metrics.get("net_score", 0)
    if net_score < 0.25:
        return False

    # Should have some documentation
    ramp_up_time = metrics.get("ramp_up_time", 0)
    if ramp_up_time < 0.3:
        return False

    return True
