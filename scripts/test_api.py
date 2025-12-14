#!/usr/bin/env python3
"""Test script to verify API functionality with real HuggingFace models."""

import requests
import sys
import time

BASE = "http://localhost:8000"


def test_lineage_workflow():
    """Test lineage detection with parent-child models."""
    print("\n" + "=" * 60)
    print("Testing Lineage Detection Workflow")
    print("=" * 60)

    # 1. Reset
    print("\n1. Resetting registry...")
    requests.post(f"{BASE}/reset")
    print("   Done")

    # 2. Ingest GPT-2 (base model)
    print("\n2. Ingesting GPT-2 (base model)...")
    resp = requests.post(f"{BASE}/ingest", json={
        "url": "https://huggingface.co/openai-community/gpt2",
        "artifact_type": "model"
    }, timeout=30)
    data = resp.json()
    gpt2_id = None
    if data.get("success"):
        gpt2_id = data["artifact"]["id"]
        print(f"   SUCCESS: {data['artifact']['name']}")
        print(f"   ID: {gpt2_id[:8]}...")
    else:
        print(f"   Skipped (threshold): {data.get('message', '')[:50]}")

    # 3. Ingest DialoGPT (child of GPT-2)
    print("\n3. Ingesting DialoGPT-small (should link to GPT-2)...")
    resp = requests.post(f"{BASE}/ingest", json={
        "url": "https://huggingface.co/microsoft/DialoGPT-small",
        "artifact_type": "model"
    }, timeout=30)
    data = resp.json()
    dialopt_id = None
    if data.get("success"):
        dialopt_id = data["artifact"]["id"]
        print(f"   SUCCESS: {data['artifact']['name']}")
        print(f"   Message: {data['message']}")
    else:
        print(f"   Skipped (threshold): {data.get('message', '')[:50]}")

    # 4. Check lineage
    if dialopt_id:
        print("\n4. Checking lineage of DialoGPT...")
        resp = requests.get(f"{BASE}/artifacts/model/{dialopt_id}/lineage")
        lineage = resp.json()
        print(f"   Parents: {len(lineage['parents'])}")
        for p in lineage["parents"]:
            print(f"   - {p['name']} ({p['id'][:8]}...)")
        print(f"   Children: {len(lineage['children'])}")

    if gpt2_id:
        print("\n5. Checking lineage of GPT-2...")
        resp = requests.get(f"{BASE}/artifacts/model/{gpt2_id}/lineage")
        lineage = resp.json()
        print(f"   Parents: {len(lineage['parents'])}")
        print(f"   Children: {len(lineage['children'])}")
        for c in lineage["children"]:
            print(f"   - {c['name']} ({c['id'][:8]}...)")

    # 5. Test download parts
    if gpt2_id:
        print("\n6. Testing download parts...")
        for part in ["full", "weights", "config", "dataset"]:
            resp = requests.get(f"{BASE}/artifacts/model/{gpt2_id}/download", params={"part": part})
            data = resp.json()
            files = data.get("files", [])
            print(f"   {part}: {len(files)} file URLs provided")


def main():
    print("=" * 60)
    print("Testing Trustworthy Model Registry API")
    print("=" * 60)

    # Test 1: Check server is running
    print("\n1. Checking server health...")
    try:
        resp = requests.get(f"{BASE}/health", timeout=5)
        print(f"   Status: {resp.status_code}")
        health = resp.json()
        print(f"   System: {health['status']}")
    except requests.exceptions.ConnectionError:
        print("   ERROR: Server not responding!")
        print("   Start it with: python run.py")
        sys.exit(1)

    # Test 2: Reset registry for clean test
    print("\n2. Resetting registry...")
    resp = requests.post(f"{BASE}/reset")
    print(f"   Status: {resp.status_code} - {resp.json()['message']}")

    # Test 3: Create a manual artifact
    print("\n3. Creating manual artifact...")
    resp = requests.post(f"{BASE}/artifacts/model", json={
        "name": "test-local-model",
        "url": "https://example.com/model"
    })
    print(f"   Status: {resp.status_code}")
    if resp.status_code == 201:
        artifact = resp.json()
        print(f"   Created: {artifact['name']} (ID: {artifact['id'][:8]}...)")
        manual_id = artifact["id"]
    else:
        manual_id = None

    # Test 4: Ingest from HuggingFace - try multiple models
    print("\n4. Ingesting from HuggingFace...")
    print("   (This may take a few seconds...)")

    # Try multiple models until one passes
    models_to_try = [
        "openai-community/gpt2",
        "distilbert/distilbert-base-uncased",
        "google/flan-t5-small",
        "TinyLlama/TinyLlama-1.1B-Chat-v1.0",
    ]

    ingested_id = None
    for model in models_to_try:
        print(f"   Trying: {model}")
        try:
            resp = requests.post(f"{BASE}/ingest", json={
                "url": f"https://huggingface.co/{model}",
                "artifact_type": "model"
            }, timeout=30)
            data = resp.json()
            if data.get("success"):
                print(f"   SUCCESS: {data['artifact']['name']}")
                print(f"   Net Score: {data['rating']['net_score']}")
                print(f"   License: {data['rating']['license']}")
                print(f"   Reproducibility: {data['rating']['reproducibility']}")
                print(f"   Reviewedness: {data['rating']['reviewedness']}")
                ingested_id = data["artifact"]["id"]
                break
            else:
                print(f"   Rejected (below threshold)")
        except requests.exceptions.Timeout:
            print(f"   Timeout")
        except Exception as e:
            print(f"   Error: {e}")

    tinyllama_id = ingested_id

    # Test 5: List all artifacts
    print("\n5. Listing artifacts...")
    resp = requests.get(f"{BASE}/artifacts")
    artifacts = resp.json()
    print(f"   Total: {artifacts['total']} artifacts")
    for a in artifacts["artifacts"]:
        print(f"   - {a['name']} ({a['type']})")

    # Test 6: Search
    print('\n6. Searching for "Llama"...')
    resp = requests.get(f"{BASE}/artifacts/search", params={"query": "Llama"})
    results = resp.json()
    print(f"   Found: {results['total']} results")
    for r in results["results"]:
        print(f"   - {r['name']}")

    # Test 7: Rate the manual artifact
    if manual_id:
        print("\n7. Rating manual artifact...")
        resp = requests.post(f"{BASE}/artifacts/model/{manual_id}/rating")
        if resp.status_code == 200:
            rating = resp.json()
            print(f"   Net Score: {rating['net_score']}")
            print(f"   Reproducibility: {rating['reproducibility']}")
            print(f"   Bus Factor: {rating['bus_factor']}")

    # Test 8: Get lineage
    if tinyllama_id:
        print("\n8. Getting lineage for TinyLlama...")
        resp = requests.get(f"{BASE}/artifacts/model/{tinyllama_id}/lineage")
        if resp.status_code == 200:
            lineage = resp.json()
            print(f"   Parents: {len(lineage['parents'])}")
            print(f"   Children: {len(lineage['children'])}")

    # Test 9: Get cost
    if tinyllama_id:
        print("\n9. Getting storage cost...")
        resp = requests.get(f"{BASE}/artifacts/model/{tinyllama_id}/cost")
        if resp.status_code == 200:
            cost = resp.json()
            print(f"   Own size: {cost['own_size_bytes']} bytes")
            print(f"   Total: {cost['total_size_bytes']} bytes")

    # Test 10: Check health components
    print("\n10. Checking component health...")
    resp = requests.get(f"{BASE}/health/components")
    components = resp.json()
    print(f"   Overall: {components['overall_status']}")
    for c in components["components"]:
        icon = "✓" if c["status"] == "healthy" else "!" if c["status"] == "degraded" else "✗"
        print(f"   {icon} {c['name']}: {c['status']}")

    print("\n" + "=" * 60)
    print("Basic tests complete!")
    print("=" * 60)

    # Run lineage tests
    test_lineage_workflow()

    print("\n" + "=" * 60)
    print("All tests complete!")
    print("Visit: http://localhost:8000/static/index.html")
    print("=" * 60)


if __name__ == "__main__":
    main()

