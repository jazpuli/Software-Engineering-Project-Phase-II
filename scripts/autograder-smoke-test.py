#!/usr/bin/env python3
"""
Autograder smoke test script.

Validates API behavior against rubric expectations by running through
all critical endpoints and checking responses.
"""

import sys
import time
import requests

BASE_URL = "http://localhost:8000"


def log(message: str, status: str = "INFO"):
    """Print formatted log message."""
    colors = {
        "INFO": "\033[94m",
        "PASS": "\033[92m",
        "FAIL": "\033[91m",
        "WARN": "\033[93m",
    }
    reset = "\033[0m"
    print(f"{colors.get(status, '')}{status}{reset}: {message}")


def check(condition: bool, message: str) -> bool:
    """Check condition and log result."""
    if condition:
        log(message, "PASS")
        return True
    else:
        log(message, "FAIL")
        return False


def run_tests():
    """Run all smoke tests."""
    results = []

    # Test 1: Reset registry
    log("Testing POST /reset...")
    resp = requests.post(f"{BASE_URL}/reset")
    results.append(check(
        resp.status_code == 200 and resp.json().get("success"),
        "Reset registry"
    ))

    # Test 2: Create artifact
    log("Testing POST /artifacts/model...")
    resp = requests.post(f"{BASE_URL}/artifacts/model", json={
        "name": "test-model",
        "url": "https://huggingface.co/test/model"
    })
    results.append(check(resp.status_code == 201, "Create artifact returns 201"))
    artifact = resp.json()
    artifact_id = artifact.get("id")
    results.append(check(artifact_id is not None, "Artifact has ID"))
    results.append(check(artifact.get("type") == "model", "Artifact type is correct"))

    # Test 3: List artifacts
    log("Testing GET /artifacts...")
    resp = requests.get(f"{BASE_URL}/artifacts")
    results.append(check(resp.status_code == 200, "List artifacts returns 200"))
    results.append(check(len(resp.json().get("artifacts", [])) == 1, "List contains 1 artifact"))

    # Test 4: Get artifact
    log("Testing GET /artifacts/model/{id}...")
    resp = requests.get(f"{BASE_URL}/artifacts/model/{artifact_id}")
    results.append(check(resp.status_code == 200, "Get artifact returns 200"))
    results.append(check(resp.json().get("name") == "test-model", "Artifact name matches"))

    # Test 5: Rate artifact
    log("Testing POST /artifacts/model/{id}/rating...")
    resp = requests.post(f"{BASE_URL}/artifacts/model/{artifact_id}/rating")
    results.append(check(resp.status_code == 200, "Rate artifact returns 200"))
    rating = resp.json()
    results.append(check("net_score" in rating, "Rating has net_score"))
    results.append(check("reproducibility" in rating, "Rating has reproducibility"))
    results.append(check("reviewedness" in rating, "Rating has reviewedness"))
    results.append(check("treescore" in rating, "Rating has treescore"))
    results.append(check("size_score" in rating, "Rating has size_score"))

    # Test 6: Search
    log("Testing GET /artifacts/search...")
    resp = requests.get(f"{BASE_URL}/artifacts/search", params={"query": "test"})
    results.append(check(resp.status_code == 200, "Search returns 200"))
    results.append(check(len(resp.json().get("results", [])) >= 1, "Search finds artifact"))

    # Test 7: Invalid regex search
    log("Testing GET /artifacts/search with invalid regex...")
    resp = requests.get(f"{BASE_URL}/artifacts/search", params={"query": "[invalid"})
    results.append(check(resp.status_code == 400, "Invalid regex returns 400"))

    # Test 8: Lineage
    log("Testing GET /artifacts/model/{id}/lineage...")
    resp = requests.get(f"{BASE_URL}/artifacts/model/{artifact_id}/lineage")
    results.append(check(resp.status_code == 200, "Lineage returns 200"))
    results.append(check("parents" in resp.json(), "Lineage has parents"))
    results.append(check("children" in resp.json(), "Lineage has children"))

    # Test 9: Cost
    log("Testing GET /artifacts/model/{id}/cost...")
    resp = requests.get(f"{BASE_URL}/artifacts/model/{artifact_id}/cost")
    results.append(check(resp.status_code == 200, "Cost returns 200"))
    results.append(check("total_size_bytes" in resp.json(), "Cost has total_size_bytes"))

    # Test 10: Download
    log("Testing GET /artifacts/model/{id}/download...")
    resp = requests.get(f"{BASE_URL}/artifacts/model/{artifact_id}/download", params={"part": "full"})
    results.append(check(resp.status_code == 200, "Download returns 200"))
    results.append(check("artifact" in resp.json(), "Download has artifact info"))

    # Test 11: Health
    log("Testing GET /health...")
    resp = requests.get(f"{BASE_URL}/health")
    results.append(check(resp.status_code == 200, "Health returns 200"))
    results.append(check("status" in resp.json(), "Health has status"))
    results.append(check("request_counts" in resp.json(), "Health has request_counts"))

    # Test 12: Health components
    log("Testing GET /health/components...")
    resp = requests.get(f"{BASE_URL}/health/components")
    results.append(check(resp.status_code == 200, "Health components returns 200"))
    results.append(check("components" in resp.json(), "Has components list"))

    # Test 13: License check
    log("Testing POST /license-check...")
    resp = requests.post(f"{BASE_URL}/license-check", json={
        "artifact_id": artifact_id,
        "github_url": "https://github.com/test/repo"
    })
    results.append(check(resp.status_code == 200, "License check returns 200"))
    results.append(check("compatible" in resp.json(), "License check has compatible field"))

    # Test 14: Delete artifact
    log("Testing DELETE /artifacts/model/{id}...")
    resp = requests.delete(f"{BASE_URL}/artifacts/model/{artifact_id}")
    results.append(check(resp.status_code == 204, "Delete returns 204"))

    # Test 15: Verify deletion
    log("Testing GET deleted artifact...")
    resp = requests.get(f"{BASE_URL}/artifacts/model/{artifact_id}")
    results.append(check(resp.status_code == 404, "Deleted artifact returns 404"))

    # Test 16: Ingest (if HuggingFace is reachable)
    log("Testing POST /ingest (may be skipped if HF unreachable)...")
    try:
        resp = requests.post(f"{BASE_URL}/ingest", json={
            "url": "https://huggingface.co/google/gemma-3-270m",
            "artifact_type": "model"
        }, timeout=30)
        results.append(check(resp.status_code == 200, "Ingest returns 200"))
        if resp.status_code == 200:
            data = resp.json()
            # Success can be True (accepted) or False (quality rejection)
            results.append(check("success" in data, "Ingest has success field"))
    except requests.exceptions.Timeout:
        log("Ingest test skipped (timeout)", "WARN")

    # Summary
    print("\n" + "=" * 50)
    passed = sum(results)
    total = len(results)
    print(f"Results: {passed}/{total} tests passed")

    if passed == total:
        log("All tests passed!", "PASS")
        return 0
    else:
        log(f"{total - passed} tests failed", "FAIL")
        return 1


def main():
    """Main entry point."""
    print("=" * 50)
    print("Autograder Smoke Test")
    print("=" * 50)
    print(f"Target: {BASE_URL}")
    print()

    # Check server is running
    try:
        resp = requests.get(f"{BASE_URL}/", timeout=5)
        if resp.status_code != 200:
            log("Server not responding correctly", "FAIL")
            sys.exit(1)
    except requests.exceptions.ConnectionError:
        log(f"Cannot connect to {BASE_URL}. Is the server running?", "FAIL")
        sys.exit(1)

    log("Server is running", "PASS")
    print()

    sys.exit(run_tests())


if __name__ == "__main__":
    main()

