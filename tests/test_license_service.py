"""Tests for the license service."""

import pytest
from unittest.mock import patch, MagicMock

from src.api.services.license import (
    normalize_license,
    detect_license_from_content,
    check_compatibility,
    fetch_github_license,
    LICENSE_COMPATIBILITY,
)


class TestNormalizeLicense:
    """Tests for license normalization."""

    def test_normalize_none(self):
        """Test normalizing None."""
        assert normalize_license(None) is None

    def test_normalize_empty_string(self):
        """Test normalizing empty string."""
        assert normalize_license("") is None

    def test_normalize_mit_variants(self):
        """Test normalizing MIT license variants."""
        assert normalize_license("mit") == "mit"
        assert normalize_license("MIT") == "mit"
        assert normalize_license("MIT License") == "mit"
        assert normalize_license("expat") == "mit"

    def test_normalize_apache_variants(self):
        """Test normalizing Apache license variants."""
        assert normalize_license("apache-2.0") == "apache-2.0"
        assert normalize_license("Apache 2.0") == "apache-2.0"
        assert normalize_license("Apache License 2.0") == "apache-2.0"
        assert normalize_license("Apache License, Version 2.0") == "apache-2.0"

    def test_normalize_bsd_variants(self):
        """Test normalizing BSD license variants."""
        assert normalize_license("bsd-2-clause") == "bsd-2-clause"
        assert normalize_license("bsd 2-clause") == "bsd-2-clause"
        assert normalize_license("simplified bsd") == "bsd-2-clause"
        assert normalize_license("bsd-3-clause") == "bsd-3-clause"
        assert normalize_license("new bsd") == "bsd-3-clause"

    def test_normalize_gpl_variants(self):
        """Test normalizing GPL license variants."""
        assert normalize_license("gpl-2.0") == "gpl-2.0"
        assert normalize_license("GPL 2.0") == "gpl-2.0"
        assert normalize_license("GNU GPL v2") == "gpl-2.0"
        assert normalize_license("gpl-3.0") == "gpl-3.0"
        assert normalize_license("GNU General Public License v3.0") == "gpl-3.0"

    def test_normalize_lgpl_variants(self):
        """Test normalizing LGPL license variants."""
        assert normalize_license("lgpl-2.1") == "lgpl-2.1"
        assert normalize_license("lgpl-3.0") == "lgpl-3.0"

    def test_normalize_public_domain(self):
        """Test normalizing public domain licenses."""
        assert normalize_license("unlicense") == "unlicense"
        assert normalize_license("public domain") == "unlicense"
        assert normalize_license("cc0-1.0") == "cc0-1.0"

    def test_normalize_creative_commons(self):
        """Test normalizing Creative Commons licenses."""
        assert normalize_license("cc-by-4.0") == "cc-by-4.0"
        assert normalize_license("cc by 4.0") == "cc-by-4.0"
        assert normalize_license("cc-by-sa-4.0") == "cc-by-sa-4.0"

    def test_normalize_other_licenses(self):
        """Test normalizing other licenses."""
        assert normalize_license("isc") == "isc"
        assert normalize_license("ISC License") == "isc"
        assert normalize_license("mpl-2.0") == "mpl-2.0"

    def test_normalize_unknown_returns_lowercase(self):
        """Test that unknown licenses are returned as lowercase."""
        assert normalize_license("Some Unknown License") == "some unknown license"


class TestDetectLicenseFromContent:
    """Tests for license detection from content."""

    def test_detect_mit_from_content(self):
        """Test detecting MIT license from content."""
        content = "MIT License\nPermission is hereby granted, free of charge..."
        assert detect_license_from_content(content) == "mit"

    def test_detect_mit_from_permission_grant(self):
        """Test detecting MIT license from permission grant text."""
        content = "Permission is hereby granted, free of charge, to any person..."
        assert detect_license_from_content(content) == "mit"

    def test_detect_bsd_2_clause(self):
        """Test detecting BSD 2-Clause license."""
        content = "BSD 2-Clause License\nRedistribution and use in source and binary forms..."
        assert detect_license_from_content(content) == "bsd-2-clause"

    def test_detect_bsd_3_clause(self):
        """Test detecting BSD 3-Clause license."""
        content = "BSD 3-Clause License\nRedistribution and use in source and binary forms..."
        assert detect_license_from_content(content) == "bsd-3-clause"

    def test_detect_unlicense(self):
        """Test detecting Unlicense."""
        content = "This is free and unencumbered software released into the public domain."
        assert detect_license_from_content(content) == "unlicense"

    def test_detect_gpl_v3(self):
        """Test detecting GPL v3."""
        content = "GNU General Public License\nVersion 3, 29 June 2007..."
        assert detect_license_from_content(content) == "gpl-3.0"

    def test_detect_gpl_v2(self):
        """Test detecting GPL v2."""
        content = "GNU General Public License\nVersion 2, June 1991..."
        assert detect_license_from_content(content) == "gpl-2.0"

    def test_detect_lgpl_v3(self):
        """Test detecting LGPL v3."""
        content = "GNU Lesser General Public License\nVersion 3, 29 June 2007..."
        assert detect_license_from_content(content) == "lgpl-3.0"

    def test_detect_lgpl_v21(self):
        """Test detecting LGPL v2.1."""
        content = "GNU Lesser General Public License\nVersion 2.1, February 1999..."
        assert detect_license_from_content(content) == "lgpl-2.1"

    def test_detect_no_match(self):
        """Test when no license is detected."""
        content = "Some random text that doesn't match any license."
        assert detect_license_from_content(content) is None


class TestCheckCompatibility:
    """Tests for license compatibility checking."""

    def test_same_license_compatible(self):
        """Test that same license is compatible."""
        is_compat, msg = check_compatibility("mit", "mit")
        assert is_compat is True
        assert "match" in msg.lower()

    def test_mit_apache_compatible(self):
        """Test MIT and Apache-2.0 are compatible."""
        is_compat, msg = check_compatibility("mit", "apache-2.0")
        assert is_compat is True

    def test_unknown_artifact_license(self):
        """Test unknown artifact license returns False."""
        is_compat, msg = check_compatibility(None, "mit")
        assert is_compat is False
        assert "unknown" in msg.lower()

    def test_unknown_target_license(self):
        """Test unknown target license returns False."""
        is_compat, msg = check_compatibility("mit", None)
        assert is_compat is False
        assert "unknown" in msg.lower()

    def test_gpl_mit_incompatible(self):
        """Test GPL and MIT are not directly compatible."""
        is_compat, msg = check_compatibility("gpl-3.0", "mit")
        assert is_compat is False

    def test_permissive_licenses_compatible(self):
        """Test permissive licenses are compatible with each other."""
        permissive = ["mit", "apache-2.0", "bsd-2-clause", "bsd-3-clause", "isc"]
        for lic1 in permissive:
            for lic2 in permissive:
                is_compat, _ = check_compatibility(lic1, lic2)
                assert is_compat is True, f"{lic1} should be compatible with {lic2}"

    def test_reverse_compatibility(self):
        """Test reverse compatibility check."""
        # Apache-2.0 includes MIT in its compatible set
        is_compat, msg = check_compatibility("apache-2.0", "mit")
        assert is_compat is True


class TestFetchGitHubLicense:
    """Tests for fetching GitHub license."""

    def test_invalid_url(self):
        """Test invalid URL returns None."""
        assert fetch_github_license("not a github url") is None

    @patch("src.api.services.license.requests.get")
    def test_api_success(self, mock_get):
        """Test successful API response."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "license": {"spdx_id": "MIT", "key": "mit"}
        }
        mock_get.return_value = mock_response

        result = fetch_github_license("https://github.com/owner/repo")
        assert result == "MIT"

    @patch("src.api.services.license.requests.get")
    def test_api_failure_fallback(self, mock_get):
        """Test fallback to raw LICENSE file on API failure."""
        # First call fails (API), subsequent calls return license content
        responses = [
            MagicMock(status_code=404),  # API call
            MagicMock(status_code=404),  # main/LICENSE
            MagicMock(status_code=404),  # main/LICENSE.md
            MagicMock(status_code=404),  # main/LICENSE.txt
            MagicMock(status_code=404),  # master/LICENSE
            MagicMock(status_code=200, text="MIT License\nPermission is hereby granted..."),
        ]
        mock_get.side_effect = responses

        result = fetch_github_license("https://github.com/owner/repo")
        assert result == "mit"

    @patch("src.api.services.license.requests.get")
    def test_request_exception(self, mock_get):
        """Test handling of request exceptions."""
        import requests
        mock_get.side_effect = requests.RequestException("Connection error")

        result = fetch_github_license("https://github.com/owner/repo")
        assert result is None


class TestLicenseCompatibilityMap:
    """Tests for the license compatibility map."""

    def test_permissive_licenses_exist(self):
        """Test that permissive licenses are in the map."""
        assert "mit" in LICENSE_COMPATIBILITY
        assert "apache-2.0" in LICENSE_COMPATIBILITY
        assert "bsd-2-clause" in LICENSE_COMPATIBILITY
        assert "bsd-3-clause" in LICENSE_COMPATIBILITY

    def test_copyleft_licenses_exist(self):
        """Test that copyleft licenses are in the map."""
        assert "gpl-2.0" in LICENSE_COMPATIBILITY
        assert "gpl-3.0" in LICENSE_COMPATIBILITY
        assert "lgpl-2.1" in LICENSE_COMPATIBILITY

    def test_creative_commons_exist(self):
        """Test that Creative Commons licenses are in the map."""
        assert "cc-by-4.0" in LICENSE_COMPATIBILITY
        assert "cc-by-sa-4.0" in LICENSE_COMPATIBILITY
