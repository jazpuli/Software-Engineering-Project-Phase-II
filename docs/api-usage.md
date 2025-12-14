# API Usage Guide

This guide covers common usage patterns for the Trustworthy Model Registry API.

## Quick Start

The API is available at the root URL. Full OpenAPI documentation is at `/docs`.

## Authentication

Currently, the MVP does not require authentication. For production, implement OAuth2 or API keys.

## Endpoints

### Artifacts

#### Create Artifact

```bash
curl -X POST "http://localhost:8000/artifacts/model" \
  -H "Content-Type: application/json" \
  -d '{"name": "my-model", "url": "https://huggingface.co/org/model"}'
```

Response (201):
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "type": "model",
  "name": "my-model",
  "url": "https://huggingface.co/org/model",
  "download_url": null,
  "created_at": "2024-01-15T10:30:00Z"
}
```

#### List Artifacts

```bash
curl "http://localhost:8000/artifacts"
curl "http://localhost:8000/artifacts?artifact_type=model&limit=10"
```

#### Get Artifact

```bash
curl "http://localhost:8000/artifacts/model/{artifact_id}"
```

#### Delete Artifact

```bash
curl -X DELETE "http://localhost:8000/artifacts/model/{artifact_id}"
```

### Rating

#### Rate an Artifact

```bash
curl -X POST "http://localhost:8000/artifacts/model/{artifact_id}/rating"
```

Response:
```json
{
  "artifact_id": "...",
  "net_score": 0.75,
  "ramp_up_time": 0.8,
  "bus_factor": 0.7,
  "license": 1.0,
  "reproducibility": 0.5,
  "reviewedness": 0.6,
  "treescore": 0.0,
  "size_score": {
    "raspberry_pi": 0.5,
    "jetson_nano": 0.6,
    "desktop_pc": 0.9,
    "aws_server": 1.0
  }
}
```

### Search

```bash
curl "http://localhost:8000/artifacts/search?query=bert"
curl "http://localhost:8000/artifacts/search?query=model-v[12]"
```

### Ingest from HuggingFace

```bash
curl -X POST "http://localhost:8000/ingest" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://huggingface.co/google/gemma-3-270m", "artifact_type": "model"}'
```

### Lineage

#### Get Lineage

```bash
curl "http://localhost:8000/artifacts/{artifact_id}/lineage"
```

#### Add Lineage Edge

```bash
curl -X POST "http://localhost:8000/artifacts/{child_id}/lineage?parent_id={parent_id}"
```

### Cost

```bash
curl "http://localhost:8000/artifacts/{artifact_id}/cost"
```

### License Check

```bash
curl -X POST "http://localhost:8000/license-check" \
  -H "Content-Type: application/json" \
  -d '{"artifact_id": "...", "github_url": "https://github.com/owner/repo"}'
```

### Health

```bash
# Aggregate health stats
curl "http://localhost:8000/health"

# Component status
curl "http://localhost:8000/health/components"
```

### Reset

```bash
curl -X POST "http://localhost:8000/reset"
```

## Error Handling

All errors return JSON with a `detail` field:

```json
{
  "detail": "Artifact not found"
}
```

Common status codes:
- 200: Success
- 201: Created
- 204: No Content (successful delete)
- 400: Bad Request
- 404: Not Found
- 500: Internal Server Error

## Python Client Example

```python
import requests

BASE_URL = "http://localhost:8000"

# Create artifact
response = requests.post(f"{BASE_URL}/artifacts/model", json={
    "name": "my-model",
    "url": "https://huggingface.co/org/model"
})
artifact = response.json()

# Rate artifact
rating = requests.post(
    f"{BASE_URL}/artifacts/model/{artifact['id']}/rating"
).json()

print(f"Net Score: {rating['net_score']}")
```

## JavaScript Client Example

```javascript
const BASE_URL = 'http://localhost:8000';

// Create artifact
const artifact = await fetch(`${BASE_URL}/artifacts/model`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    name: 'my-model',
    url: 'https://huggingface.co/org/model'
  })
}).then(r => r.json());

// Rate artifact
const rating = await fetch(
  `${BASE_URL}/artifacts/model/${artifact.id}/rating`,
  { method: 'POST' }
).then(r => r.json());

console.log(`Net Score: ${rating.net_score}`);
```

