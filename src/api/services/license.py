"""License compatibility checking service."""

import re
import requests
from typing import Optional, Tuple


# License compatibility mapping (simplified)
# Maps license -> set of compatible licenses
LICENSE_COMPATIBILITY = {
    # Permissive licenses are broadly compatible
    "mit": {"mit", "apache-2.0", "bsd-2-clause", "bsd-3-clause", "isc", "unlicense", "cc0-1.0"},
    "apache-2.0": {"mit", "apache-2.0", "bsd-2-clause", "bsd-3-clause", "isc", "unlicense"},
    "bsd-2-clause": {"mit", "apache-2.0", "bsd-2-clause", "bsd-3-clause", "isc", "unlicense"},
    "bsd-3-clause": {"mit", "apache-2.0", "bsd-2-clause", "bsd-3-clause", "isc", "unlicense"},
    "isc": {"mit", "apache-2.0", "bsd-2-clause", "bsd-3-clause", "isc", "unlicense"},
    "unlicense": {"mit", "apache-2.0", "bsd-2-clause", "bsd-3-clause", "isc", "unlicense", "cc0-1.0"},
    "cc0-1.0": {"mit", "apache-2.0", "bsd-2-clause", "bsd-3-clause", "isc", "unlicense", "cc0-1.0"},

    # Copyleft licenses have restrictions
    "gpl-2.0": {"gpl-2.0", "gpl-3.0"},
    "gpl-3.0": {"gpl-3.0"},
    "agpl-3.0": {"agpl-3.0"},
    "lgpl-2.1": {"lgpl-2.1", "lgpl-3.0", "gpl-2.0", "gpl-3.0"},
    "lgpl-3.0": {"lgpl-3.0", "gpl-3.0"},

    # Creative Commons
    "cc-by-4.0": {"cc-by-4.0", "cc-by-sa-4.0"},
    "cc-by-sa-4.0": {"cc-by-sa-4.0"},
}


def normalize_license(license_str: Optional[str]) -> Optional[str]:
    """
    Normalize license string to a standard identifier.

    Args:
        license_str: Raw license string

    Returns:
        Normalized license identifier or None
    """
    if not license_str:
        return None

    license_lower = license_str.lower().strip()

    # Common mappings from various formats
    mappings = {
        # MIT variants
        "mit license": "mit",
        "mit": "mit",
        "expat": "mit",

        # Apache variants
        "apache 2.0": "apache-2.0",
        "apache-2.0": "apache-2.0",
        "apache license 2.0": "apache-2.0",
        "apache license, version 2.0": "apache-2.0",

        # BSD variants
        "bsd-2-clause": "bsd-2-clause",
        "bsd 2-clause": "bsd-2-clause",
        "simplified bsd": "bsd-2-clause",
        "bsd-3-clause": "bsd-3-clause",
        "bsd 3-clause": "bsd-3-clause",
        "new bsd": "bsd-3-clause",
        "modified bsd": "bsd-3-clause",

        # GPL variants
        "gpl-2.0": "gpl-2.0",
        "gpl 2.0": "gpl-2.0",
        "gnu gpl v2": "gpl-2.0",
        "gpl-3.0": "gpl-3.0",
        "gpl 3.0": "gpl-3.0",
        "gnu gpl v3": "gpl-3.0",
        "gnu general public license v3.0": "gpl-3.0",

        # AGPL
        "agpl-3.0": "agpl-3.0",
        "gnu agpl v3": "agpl-3.0",

        # LGPL variants
        "lgpl-2.1": "lgpl-2.1",
        "gnu lgpl v2.1": "lgpl-2.1",
        "lgpl-3.0": "lgpl-3.0",
        "gnu lgpl v3": "lgpl-3.0",

        # Public domain
        "unlicense": "unlicense",
        "public domain": "unlicense",
        "cc0-1.0": "cc0-1.0",
        "cc0 1.0": "cc0-1.0",

        # Creative Commons
        "cc-by-4.0": "cc-by-4.0",
        "cc by 4.0": "cc-by-4.0",
        "cc-by-sa-4.0": "cc-by-sa-4.0",
        "cc by-sa 4.0": "cc-by-sa-4.0",

        # Other
        "isc": "isc",
        "isc license": "isc",
        "mpl-2.0": "mpl-2.0",
        "mozilla public license 2.0": "mpl-2.0",
    }

    return mappings.get(license_lower, license_lower)


def fetch_github_license(github_url: str) -> Optional[str]:
    """
    Fetch license information from a GitHub repository.

    Args:
        github_url: GitHub repository URL

    Returns:
        License SPDX identifier or None
    """
    # Extract owner/repo from URL
    match = re.search(r"github\.com/([^/]+)/([^/]+)", github_url)
    if not match:
        return None

    owner, repo = match.groups()
    repo = repo.rstrip(".git")

    # Try GitHub API first
    try:
        api_url = f"https://api.github.com/repos/{owner}/{repo}/license"
        response = requests.get(api_url, timeout=10, headers={
            "Accept": "application/vnd.github.v3+json"
        })
        if response.status_code == 200:
            data = response.json()
            license_info = data.get("license", {})
            return license_info.get("spdx_id") or license_info.get("key")
    except requests.RequestException:
        pass

    # Fallback: Try to detect from LICENSE file content
    try:
        for branch in ["main", "master"]:
            for filename in ["LICENSE", "LICENSE.md", "LICENSE.txt"]:
                raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{filename}"
                response = requests.get(raw_url, timeout=10)
                if response.status_code == 200:
                    return detect_license_from_content(response.text)
    except requests.RequestException:
        pass

    return None


def detect_license_from_content(content: str) -> Optional[str]:
    """
    Detect license type from LICENSE file content.

    Args:
        content: Content of LICENSE file

    Returns:
        Detected license identifier or None
    """
    content_lower = content.lower()

    # Simple content-based detection
    patterns = [
        ("mit license", "mit"),
        ("permission is hereby granted, free of charge", "mit"),
        ("apache license", "apache-2.0"),
        ("version 2.0", None),  # Marker for Apache
        ("gnu general public license", None),  # Need to check version
        ("gnu lesser general public license", None),
        ("bsd 2-clause", "bsd-2-clause"),
        ("bsd 3-clause", "bsd-3-clause"),
        ("this is free and unencumbered software", "unlicense"),
    ]

    detected = None
    for pattern, license_id in patterns:
        if pattern in content_lower:
            if license_id:
                detected = license_id
                break

    # Check GPL version
    if "gnu general public license" in content_lower:
        if "version 3" in content_lower:
            detected = "gpl-3.0"
        elif "version 2" in content_lower:
            detected = "gpl-2.0"

    # Check LGPL version
    if "gnu lesser general public license" in content_lower:
        if "version 3" in content_lower:
            detected = "lgpl-3.0"
        elif "version 2.1" in content_lower:
            detected = "lgpl-2.1"

    return detected


def check_compatibility(
    artifact_license: Optional[str],
    target_license: Optional[str]
) -> Tuple[bool, str]:
    """
    Check if two licenses are compatible.

    Args:
        artifact_license: License of the artifact
        target_license: License to check compatibility with

    Returns:
        Tuple of (is_compatible, message)
    """
    # Normalize both licenses
    norm_artifact = normalize_license(artifact_license)
    norm_target = normalize_license(target_license)

    if not norm_artifact:
        return False, "Artifact license unknown"

    if not norm_target:
        return False, "Target license unknown"

    # Same license is always compatible
    if norm_artifact == norm_target:
        return True, f"Licenses match: {norm_artifact}"

    # Check compatibility map
    compatible_set = LICENSE_COMPATIBILITY.get(norm_artifact, set())

    if norm_target in compatible_set:
        return True, f"{norm_artifact} is compatible with {norm_target}"

    # Check reverse compatibility
    reverse_compatible = LICENSE_COMPATIBILITY.get(norm_target, set())
    if norm_artifact in reverse_compatible:
        return True, f"{norm_target} is compatible with {norm_artifact}"

    return False, f"{norm_artifact} may not be compatible with {norm_target}"

