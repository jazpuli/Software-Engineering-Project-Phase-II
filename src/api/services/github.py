"""GitHub integration for reviewedness metric."""

import os
import re
import requests
from typing import Optional, Tuple, Dict, Any

# GitHub API base URL
GITHUB_API = "https://api.github.com"

# Get token from environment (optional, for higher rate limits)
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")


def get_github_headers() -> Dict[str, str]:
    """Get headers for GitHub API requests."""
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "TrustworthyModelRegistry/2.0",
    }
    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"
    return headers


def extract_repo_info(url: str) -> Optional[Tuple[str, str]]:
    """
    Extract owner and repo from a GitHub URL.

    Returns:
        Tuple of (owner, repo) or None if not a valid GitHub URL
    """
    patterns = [
        r"github\.com/([^/]+)/([^/]+)",
        r"github\.com:([^/]+)/([^/]+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            owner, repo = match.groups()
            repo = repo.rstrip(".git").rstrip("/")
            return owner, repo

    return None


def get_repo_info(owner: str, repo: str) -> Optional[Dict[str, Any]]:
    """Get repository information from GitHub API."""
    try:
        url = f"{GITHUB_API}/repos/{owner}/{repo}"
        response = requests.get(url, headers=get_github_headers(), timeout=10)
        if response.status_code == 200:
            return response.json()
    except Exception:
        pass
    return None


def get_pull_requests(owner: str, repo: str, state: str = "all", per_page: int = 100) -> list:
    """
    Get pull requests for a repository.

    Args:
        owner: Repository owner
        repo: Repository name
        state: PR state (open, closed, all)
        per_page: Number of PRs to fetch

    Returns:
        List of pull request data
    """
    try:
        url = f"{GITHUB_API}/repos/{owner}/{repo}/pulls"
        params = {"state": state, "per_page": per_page}
        response = requests.get(url, headers=get_github_headers(), params=params, timeout=15)
        if response.status_code == 200:
            return response.json()
    except Exception:
        pass
    return []


def get_pr_reviews(owner: str, repo: str, pr_number: int) -> list:
    """Get reviews for a specific pull request."""
    try:
        url = f"{GITHUB_API}/repos/{owner}/{repo}/pulls/{pr_number}/reviews"
        response = requests.get(url, headers=get_github_headers(), timeout=10)
        if response.status_code == 200:
            return response.json()
    except Exception:
        pass
    return []


def get_commits(owner: str, repo: str, per_page: int = 100) -> list:
    """Get recent commits for a repository."""
    try:
        url = f"{GITHUB_API}/repos/{owner}/{repo}/commits"
        params = {"per_page": per_page}
        response = requests.get(url, headers=get_github_headers(), params=params, timeout=15)
        if response.status_code == 200:
            return response.json()
    except Exception:
        pass
    return []


def compute_reviewedness_for_repo(github_url: str) -> float:
    """
    Compute the reviewedness metric for a GitHub repository.

    The metric is the fraction of code introduced through pull requests
    that received at least one code review.

    Args:
        github_url: GitHub repository URL

    Returns:
        -1 if no GitHub repo or cannot analyze
        0-1 fraction of reviewed code
    """
    # Extract repo info
    repo_info = extract_repo_info(github_url)
    if not repo_info:
        return -1.0

    owner, repo = repo_info

    # Get repository info
    repo_data = get_repo_info(owner, repo)
    if not repo_data:
        return -1.0

    # Get pull requests
    prs = get_pull_requests(owner, repo, state="closed", per_page=50)

    if not prs:
        # No PRs means all code was direct commits (not reviewed)
        # But give some credit if repo exists and has commits
        commits = get_commits(owner, repo, per_page=10)
        if commits:
            return 0.1  # Some code exists but no PR workflow
        return -1.0

    # Count PRs with reviews
    reviewed_prs = 0
    total_merged_prs = 0

    for pr in prs:
        # Only count merged PRs
        if not pr.get("merged_at"):
            continue

        total_merged_prs += 1
        pr_number = pr.get("number")

        # Check if PR has reviews
        reviews = get_pr_reviews(owner, repo, pr_number)

        # Count as reviewed if has at least one approved or commented review
        has_review = any(
            r.get("state") in ("APPROVED", "CHANGES_REQUESTED", "COMMENTED")
            for r in reviews
        )

        if has_review:
            reviewed_prs += 1

        # Limit API calls
        if total_merged_prs >= 20:
            break

    if total_merged_prs == 0:
        # PRs exist but none are merged
        return 0.2

    # Calculate fraction
    reviewedness = reviewed_prs / total_merged_prs
    return round(reviewedness, 3)


def find_github_url_for_model(hf_data: Dict[str, Any]) -> Optional[str]:
    """
    Find associated GitHub URL for a HuggingFace model.

    Args:
        hf_data: HuggingFace API response data

    Returns:
        GitHub URL if found, None otherwise
    """
    # Check model card for GitHub links
    card_data = hf_data.get("cardData", {}) or {}

    # Check explicit GitHub field
    if "github" in card_data:
        return card_data["github"]

    # Check repo URL
    repo_url = card_data.get("repo_url") or card_data.get("repository")
    if repo_url and "github.com" in repo_url:
        return repo_url

    # Check model card text for GitHub links
    card_text = hf_data.get("card", "") or ""
    github_pattern = r"https?://github\.com/[a-zA-Z0-9_-]+/[a-zA-Z0-9_-]+"
    matches = re.findall(github_pattern, card_text)
    if matches:
        return matches[0]

    # Check tags
    tags = hf_data.get("tags", []) or []
    for tag in tags:
        if "github.com" in tag:
            return tag

    # Check siblings for .git files or references
    siblings = hf_data.get("siblings", []) or []
    for sibling in siblings:
        filename = sibling.get("rfilename", "")
        if ".git" in filename or "github" in filename.lower():
            # This might be a git submodule reference
            pass

    return None

