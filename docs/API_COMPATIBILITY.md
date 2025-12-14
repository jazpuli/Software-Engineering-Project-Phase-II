# API Compatibility Analysis

Comparison of current implementation against the ECE 461 Fall 2025 OpenAPI Spec (v3.4.7).

## Summary

| Category | Count |
|----------|-------|
| ✅ Fully Compatible | 3 |
| ⚠️ Partially Compatible (path/method differences) | 7 |
| ❌ Not Implemented | 2 |

---

## BASELINE Endpoints

### ✅ Fully Compatible

| Spec Endpoint | Current Implementation | Status |
|---------------|------------------------|--------|
| `GET /health` | `GET /health` | ✅ Compatible |
| `GET /artifacts/{artifact_type}/{id}` | `GET /artifacts/{artifact_type}/{artifact_id}` | ✅ Compatible |
| `DELETE /artifacts/{artifact_type}/{id}` | `DELETE /artifacts/{artifact_type}/{artifact_id}` | ✅ Compatible (NON-BASELINE) |

### ⚠️ Path/Method Differences

| Spec Endpoint | Current Implementation | Issue |
|---------------|------------------------|-------|
| `POST /artifacts` (search/list) | `GET /artifacts` | **Method**: Spec uses POST with body, current uses GET with query params |
| `DELETE /reset` | `POST /reset` | **Method**: Spec uses DELETE, current uses POST |
| `POST /artifact/{artifact_type}` (create) | `POST /artifacts/{artifact_type}` | **Path**: `/artifact/` vs `/artifacts/` |
| `PUT /artifacts/{artifact_type}/{id}` | Not implemented | **Missing**: Update artifact endpoint |
| `GET /artifact/model/{id}/rate` | `GET /artifacts/{artifact_type}/{artifact_id}/rating` | **Path**: Different structure |
| `GET /artifact/{artifact_type}/{id}/cost` | `GET /artifacts/{artifact_type}/{artifact_id}/cost` | **Path**: `/artifact/` vs `/artifacts/` |
| `GET /artifact/model/{id}/lineage` | `GET /artifacts/{artifact_type}/{artifact_id}/lineage` | **Path**: Different structure |
| `POST /artifact/model/{id}/license-check` | `POST /license-check` | **Path**: Missing model/{id} prefix |
| `POST /artifact/byRegEx` | `GET /artifacts/search` | **Method + Path**: POST vs GET, different path |

### ❌ Not Implemented

| Spec Endpoint | Description | Priority |
|---------------|-------------|----------|
| `PUT /artifacts/{artifact_type}/{id}` | Update artifact content | BASELINE |
| `GET /tracks` | Get planned implementation tracks | BASELINE |

---

## Detailed Analysis

### 1. `/artifacts` - List/Search Artifacts

**Spec (BASELINE):**
```
POST /artifacts
Body: [{ "name": "*" }]  // or specific query
Header: X-Authorization required
Response: Array of ArtifactMetadata
```

**Current Implementation:**
```
GET /artifacts?artifact_type=model&limit=100&offset=0
Response: { artifacts: [...], total: number }
```

**Gaps:**
- Method should be POST, not GET
- Should accept array of `ArtifactQuery` objects in body
- Should support `X-Authorization` header
- Should return pagination offset in header

---

### 2. `/reset` - Reset Registry

**Spec (BASELINE):**
```
DELETE /reset
Header: X-Authorization required
```

**Current Implementation:**
```
POST /reset
No authentication required
```

**Gaps:**
- Method should be DELETE, not POST
- Should require `X-Authorization` header

---

### 3. `/artifact/{artifact_type}` - Create Artifact

**Spec (BASELINE):**
```
POST /artifact/{artifact_type}
Body: { "url": "https://..." }
Header: X-Authorization required
Response: Artifact with metadata + data
```

**Current Implementation:**
```
POST /artifacts/{artifact_type}
Body: { "name": "...", "url": "..." }
```

**Gaps:**
- Path uses `/artifacts/` instead of `/artifact/`
- Should require `X-Authorization` header
- Should return `Artifact` schema (metadata + data combined)

---

### 4. `/artifact/model/{id}/rate` - Get Model Rating

**Spec (BASELINE):**
```
GET /artifact/model/{id}/rate
Header: X-Authorization required
Response: ModelRating schema
```

**Current Implementation:**
```
GET /artifacts/{artifact_type}/{artifact_id}/rating
POST /artifacts/{artifact_type}/{artifact_id}/rating (compute new)
```

**Gaps:**
- Path structure different (uses `/artifacts/` and includes type)
- Should be at `/artifact/model/{id}/rate`
- Response schema differences (see below)

**ModelRating Schema Comparison:**

| Spec Field | Current Field | Status |
|------------|---------------|--------|
| `name` | `name` | ✅ |
| `category` | `category` | ✅ |
| `net_score` | `net_score` | ✅ |
| `net_score_latency` | `net_score_latency` | ✅ |
| `ramp_up_time` | `ramp_up_time` | ✅ |
| `ramp_up_time_latency` | `ramp_up_time_latency` | ✅ |
| `bus_factor` | `bus_factor` | ✅ |
| `bus_factor_latency` | `bus_factor_latency` | ✅ |
| `performance_claims` | `performance_claims` | ✅ |
| `performance_claims_latency` | `performance_claims_latency` | ✅ |
| `license` | `license` | ✅ |
| `license_latency` | `license_latency` | ✅ |
| `dataset_and_code_score` | `dataset_and_code_score` | ✅ |
| `dataset_and_code_score_latency` | `dataset_and_code_score_latency` | ✅ |
| `dataset_quality` | `dataset_quality` | ✅ |
| `dataset_quality_latency` | `dataset_quality_latency` | ✅ |
| `code_quality` | `code_quality` | ✅ |
| `code_quality_latency` | `code_quality_latency` | ✅ |
| `reproducibility` | `reproducibility` | ✅ |
| `reproducibility_latency` | Missing | ❌ |
| `reviewedness` | `reviewedness` | ✅ |
| `reviewedness_latency` | Missing | ❌ |
| `tree_score` | `treescore` | ⚠️ Name difference |
| `tree_score_latency` | Missing | ❌ |
| `size_score` (object) | `size_score` (object) | ✅ |
| `size_score_latency` | Missing | ❌ |

---

### 5. `/artifact/{artifact_type}/{id}/cost` - Get Artifact Cost

**Spec (BASELINE):**
```
GET /artifact/{artifact_type}/{id}/cost?dependency=false
Response: { "{id}": { "total_cost": number, "standalone_cost"?: number } }
```

**Current Implementation:**
```
GET /artifacts/{artifact_type}/{artifact_id}/cost
Response: { artifact_id, own_size_bytes, dependencies_size_bytes, total_size_bytes }
```

**Gaps:**
- Path uses `/artifacts/` instead of `/artifact/`
- Response schema different (should use artifact ID as key)
- `dependency` query parameter not implemented
- Cost values should be in MB, not bytes

---

### 6. `/artifact/model/{id}/lineage` - Get Lineage Graph

**Spec (BASELINE):**
```
GET /artifact/model/{id}/lineage
Response: { nodes: [...], edges: [...] }
```

**Current Implementation:**
```
GET /artifacts/{artifact_type}/{artifact_id}/lineage
Response: { artifact_id, parents: [...], children: [...] }
```

**Gaps:**
- Path uses `/artifacts/` instead of `/artifact/`
- Response schema different (should be graph with nodes/edges)

---

### 7. `/artifact/model/{id}/license-check` - License Compatibility

**Spec (BASELINE):**
```
POST /artifact/model/{id}/license-check
Body: { "github_url": "https://github.com/..." }
Response: boolean
```

**Current Implementation:**
```
POST /license-check
Body: { "artifact_id": "...", "github_url": "..." }
Response: { compatible, artifact_license, github_license, message }
```

**Gaps:**
- Path should include `/artifact/model/{id}/`
- Should extract artifact_id from path, not body
- Response should be just boolean (true/false)

---

### 8. `/artifact/byRegEx` - Search by Regex

**Spec (BASELINE):**
```
POST /artifact/byRegEx
Body: { "regex": ".*bert.*" }
Response: Array of ArtifactMetadata
```

**Current Implementation:**
```
GET /artifacts/search?query=bert
Response: { query, results: [...], total }
```

**Gaps:**
- Method should be POST, not GET
- Path should be `/artifact/byRegEx`
- Should accept regex in body, not query param
- Response should be array of ArtifactMetadata only

---

### 9. `/tracks` - Get Planned Tracks

**Spec (BASELINE):**
```
GET /tracks
Response: { "plannedTracks": ["Performance track", ...] }
```

**Current Implementation:** Not implemented

**Required Implementation:**
```python
@router.get("/tracks")
async def get_tracks():
    return {
        "plannedTracks": [
            "Performance track",
            # Add other tracks as applicable
        ]
    }
```

---

## NON-BASELINE Endpoints (Optional)

| Endpoint | Status | Notes |
|----------|--------|-------|
| `GET /health/components` | ✅ Implemented | Compatible |
| `PUT /authenticate` | ❌ Not implemented | Return 501 if not supporting auth |
| `GET /artifact/byName/{name}` | ❌ Not implemented | Optional |
| `GET /artifact/{type}/{id}/audit` | ❌ Not implemented | Optional |

---

## Recommended Fixes (Priority Order)

### High Priority (BASELINE)

1. **Add `/tracks` endpoint** - Simple implementation needed
2. **Add `PUT /artifacts/{type}/{id}`** - Update artifact endpoint
3. **Fix `/reset` method** - Change from POST to DELETE
4. **Fix `/artifacts` search** - Change from GET to POST with body

### Medium Priority (Path Alignment)

5. **Align paths** - Change `/artifacts/` to `/artifact/` for single-resource endpoints
6. **Fix rating response** - Add missing latency fields
7. **Fix cost response** - Return spec-compliant schema

### Low Priority (Schema Refinement)

8. **Add `X-Authorization` header support** - Even if just passthrough
9. **Fix lineage response** - Use nodes/edges format
10. **Fix license-check path** - Include artifact ID in path

---

## Authentication Notes

The spec allows returning HTTP 501 "Not implemented" for `/authenticate` if authentication is not supported. Current implementation does not require authentication, which is acceptable for baseline.

If not implementing authentication:
- `/authenticate` should return 501
- Other endpoints should ignore `X-Authorization` header
