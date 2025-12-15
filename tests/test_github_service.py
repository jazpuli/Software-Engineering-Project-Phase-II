"""Tests for the GitHub service."""

import pytest
from unittest.mock import patch, MagicMock

from src.api.services.github import (
    get_github_headers,
    extract_repo_info,
    get_repo_info,
    get_pull_requests,
    get_pr_reviews,
    get_commits,
    compute_reviewedness_for_repo,
    find_github_url_for_model,
)


class TestGetGitHubHeaders:
    """Tests for GitHub headers generation."""

    def test_headers_without_token(self):
        """Test headers without token."""
        with patch.dict("os.environ", {}, clear=True):
            # Need to reload module to pick up new env
            headers = get_github_headers()
            assert "Accept" in headers
            assert "User-Agent" in headers

    @patch.dict("os.environ", {"GITHUB_TOKEN": "test-token"})
    def test_headers_with_token(self):
        """Test headers with token."""
        # Reload the module to pick up the token
        import importlib
        import src.api.services.github as github_module
        importlib.reload(github_module)

        headers = github_module.get_github_headers()
        assert "Accept" in headers
        assert "User-Agent" in headers


class TestExtractRepoInfo:
    """Tests for extracting repo info from URL."""

    def test_standard_github_url(self):
        """Test standard GitHub URL."""
        result = extract_repo_info("https://github.com/owner/repo")
        assert result == ("owner", "repo")

    def test_github_url_with_git_suffix(self):
        """Test GitHub URL with .git suffix."""
        result = extract_repo_info("https://github.com/owner/repo.git")
        assert result == ("owner", "repo")

    def test_github_url_with_trailing_slash(self):
        """Test GitHub URL with trailing slash."""
        result = extract_repo_info("https://github.com/owner/repo/")
        assert result == ("owner", "repo")

    def test_github_ssh_url(self):
        """Test GitHub SSH URL."""
        result = extract_repo_info("git@github.com:owner/repo.git")
        assert result == ("owner", "repo")

    def test_invalid_url(self):
        """Test invalid URL returns None."""
        assert extract_repo_info("https://gitlab.com/owner/repo") is None
        assert extract_repo_info("not a url") is None


class TestGetRepoInfo:
    """Tests for getting repo info from GitHub API."""

    @patch("src.api.services.github.requests.get")
    def test_successful_request(self, mock_get):
        """Test successful API request."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"name": "repo", "full_name": "owner/repo"}
        mock_get.return_value = mock_response

        result = get_repo_info("owner", "repo")
        assert result == {"name": "repo", "full_name": "owner/repo"}

    @patch("src.api.services.github.requests.get")
    def test_failed_request(self, mock_get):
        """Test failed API request."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        result = get_repo_info("owner", "nonexistent")
        assert result is None

    @patch("src.api.services.github.requests.get")
    def test_exception_handling(self, mock_get):
        """Test exception handling."""
        mock_get.side_effect = Exception("Connection error")
        result = get_repo_info("owner", "repo")
        assert result is None


class TestGetPullRequests:
    """Tests for getting pull requests."""

    @patch("src.api.services.github.requests.get")
    def test_successful_request(self, mock_get):
        """Test successful API request."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{"number": 1}, {"number": 2}]
        mock_get.return_value = mock_response

        result = get_pull_requests("owner", "repo")
        assert len(result) == 2

    @patch("src.api.services.github.requests.get")
    def test_failed_request(self, mock_get):
        """Test failed API request returns empty list."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        result = get_pull_requests("owner", "repo")
        assert result == []


class TestGetPRReviews:
    """Tests for getting PR reviews."""

    @patch("src.api.services.github.requests.get")
    def test_successful_request(self, mock_get):
        """Test successful API request."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{"state": "APPROVED"}]
        mock_get.return_value = mock_response

        result = get_pr_reviews("owner", "repo", 1)
        assert len(result) == 1

    @patch("src.api.services.github.requests.get")
    def test_failed_request(self, mock_get):
        """Test failed API request returns empty list."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        result = get_pr_reviews("owner", "repo", 1)
        assert result == []


class TestGetCommits:
    """Tests for getting commits."""

    @patch("src.api.services.github.requests.get")
    def test_successful_request(self, mock_get):
        """Test successful API request."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{"sha": "abc123"}]
        mock_get.return_value = mock_response

        result = get_commits("owner", "repo")
        assert len(result) == 1

    @patch("src.api.services.github.requests.get")
    def test_failed_request(self, mock_get):
        """Test failed API request returns empty list."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        result = get_commits("owner", "repo")
        assert result == []


class TestComputeReviewednessForRepo:
    """Tests for computing reviewedness metric."""

    def test_invalid_url(self):
        """Test invalid URL returns -1."""
        result = compute_reviewedness_for_repo("not a github url")
        assert result == -1.0

    @patch("src.api.services.github.get_repo_info")
    def test_repo_not_found(self, mock_repo_info):
        """Test repo not found returns -1."""
        mock_repo_info.return_value = None
        result = compute_reviewedness_for_repo("https://github.com/owner/repo")
        assert result == -1.0

    @patch("src.api.services.github.get_repo_info")
    @patch("src.api.services.github.get_pull_requests")
    @patch("src.api.services.github.get_commits")
    def test_no_prs_with_commits(self, mock_commits, mock_prs, mock_repo_info):
        """Test repo with no PRs but has commits returns 0.1."""
        mock_repo_info.return_value = {"name": "repo"}
        mock_prs.return_value = []
        mock_commits.return_value = [{"sha": "abc"}]

        result = compute_reviewedness_for_repo("https://github.com/owner/repo")
        assert result == 0.1

    @patch("src.api.services.github.get_repo_info")
    @patch("src.api.services.github.get_pull_requests")
    @patch("src.api.services.github.get_commits")
    def test_no_prs_no_commits(self, mock_commits, mock_prs, mock_repo_info):
        """Test repo with no PRs and no commits returns -1."""
        mock_repo_info.return_value = {"name": "repo"}
        mock_prs.return_value = []
        mock_commits.return_value = []

        result = compute_reviewedness_for_repo("https://github.com/owner/repo")
        assert result == -1.0

    @patch("src.api.services.github.get_repo_info")
    @patch("src.api.services.github.get_pull_requests")
    @patch("src.api.services.github.get_pr_reviews")
    def test_all_prs_reviewed(self, mock_reviews, mock_prs, mock_repo_info):
        """Test all merged PRs reviewed returns 1.0."""
        mock_repo_info.return_value = {"name": "repo"}
        mock_prs.return_value = [
            {"number": 1, "merged_at": "2023-01-01"},
            {"number": 2, "merged_at": "2023-01-02"},
        ]
        mock_reviews.return_value = [{"state": "APPROVED"}]

        result = compute_reviewedness_for_repo("https://github.com/owner/repo")
        assert result == 1.0

    @patch("src.api.services.github.get_repo_info")
    @patch("src.api.services.github.get_pull_requests")
    @patch("src.api.services.github.get_pr_reviews")
    def test_half_prs_reviewed(self, mock_reviews, mock_prs, mock_repo_info):
        """Test half merged PRs reviewed returns 0.5."""
        mock_repo_info.return_value = {"name": "repo"}
        mock_prs.return_value = [
            {"number": 1, "merged_at": "2023-01-01"},
            {"number": 2, "merged_at": "2023-01-02"},
        ]
        # First PR has review, second doesn't
        mock_reviews.side_effect = [
            [{"state": "APPROVED"}],
            [],
        ]

        result = compute_reviewedness_for_repo("https://github.com/owner/repo")
        assert result == 0.5

    @patch("src.api.services.github.get_repo_info")
    @patch("src.api.services.github.get_pull_requests")
    def test_unmerged_prs(self, mock_prs, mock_repo_info):
        """Test PRs without merged_at are not counted."""
        mock_repo_info.return_value = {"name": "repo"}
        mock_prs.return_value = [
            {"number": 1, "merged_at": None},  # Not merged
            {"number": 2},  # No merged_at field
        ]

        result = compute_reviewedness_for_repo("https://github.com/owner/repo")
        assert result == 0.2  # PRs exist but none merged


class TestFindGitHubUrlForModel:
    """Tests for finding GitHub URL from HuggingFace data."""

    def test_github_in_card_data(self):
        """Test finding GitHub URL in card data."""
        hf_data = {"cardData": {"github": "https://github.com/owner/repo"}}
        result = find_github_url_for_model(hf_data)
        assert result == "https://github.com/owner/repo"

    def test_repo_url_in_card_data(self):
        """Test finding repo_url in card data."""
        hf_data = {"cardData": {"repo_url": "https://github.com/owner/repo"}}
        result = find_github_url_for_model(hf_data)
        assert result == "https://github.com/owner/repo"

    def test_repository_in_card_data(self):
        """Test finding repository in card data."""
        hf_data = {"cardData": {"repository": "https://github.com/owner/repo"}}
        result = find_github_url_for_model(hf_data)
        assert result == "https://github.com/owner/repo"

    def test_github_in_card_text(self):
        """Test finding GitHub URL in card text."""
        hf_data = {"card": "Check out our code at https://github.com/owner/repo for more info"}
        result = find_github_url_for_model(hf_data)
        assert result == "https://github.com/owner/repo"

    def test_github_in_tags(self):
        """Test finding GitHub URL in tags."""
        hf_data = {"tags": ["nlp", "https://github.com/owner/repo"]}
        result = find_github_url_for_model(hf_data)
        assert result == "https://github.com/owner/repo"

    def test_no_github_url(self):
        """Test when no GitHub URL is found."""
        hf_data = {"cardData": {"something": "else"}}
        result = find_github_url_for_model(hf_data)
        assert result is None

    def test_empty_data(self):
        """Test with empty data."""
        result = find_github_url_for_model({})
        assert result is None

    def test_null_card_data(self):
        """Test with null card data."""
        hf_data = {"cardData": None}
        result = find_github_url_for_model(hf_data)
        assert result is None

