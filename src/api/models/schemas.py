"""Pydantic models for API request/response schemas."""

from datetime import datetime
from typing import Optional, Dict, Any, List
from enum import Enum
from pydantic import BaseModel, Field


class ArtifactType(str, Enum):
    """Supported artifact types."""
    MODEL = "model"
    DATASET = "dataset"
    CODE = "code"
    NOTEBOOK = "notebook"  # Legacy, keeping for backwards compatibility


class ArtifactCreateRequest(BaseModel):
    """Request body for creating an artifact."""
    name: Optional[str] = None
    url: str = Field(..., description="Source URL of the artifact")
    metadata: Optional[Dict[str, Any]] = None


class ArtifactMetaData(BaseModel):
    """Metadata for an artifact (version not required per spec v3.4.7)."""
    description: Optional[str] = None
    version: Optional[str] = None  # Not required per spec
    author: Optional[str] = None
    license: Optional[str] = None
    tags: Optional[List[str]] = None
    extra: Optional[Dict[str, Any]] = None


class ArtifactData(BaseModel):
    """Full artifact data returned by API."""
    id: str
    type: ArtifactType
    name: str
    url: str
    download_url: Optional[str] = None  # Required per spec v3.4.7
    metadata: Optional[ArtifactMetaData] = None
    size_bytes: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True


class ArtifactListResponse(BaseModel):
    """Response for listing artifacts."""
    artifacts: List[ArtifactData]
    total: int


class SizeScore(BaseModel):
    """Size scores for different hardware targets."""
    raspberry_pi: float = 0.0
    jetson_nano: float = 0.0
    desktop_pc: float = 0.0
    aws_server: float = 0.0


class RatingResponse(BaseModel):
    """Response from rating an artifact."""
    artifact_id: str
    name: str
    category: str
    net_score: float
    ramp_up_time: float
    bus_factor: float
    license: float
    performance_claims: float
    dataset_and_code_score: float
    dataset_quality: float
    code_quality: float
    size_score: SizeScore
    reproducibility: float  # 0, 0.5, or 1
    reviewedness: float  # -1 or fraction
    treescore: float  # Mean of parent scores
    # Latency fields
    net_score_latency: int
    ramp_up_time_latency: int
    bus_factor_latency: int
    license_latency: int
    performance_claims_latency: int
    dataset_and_code_score_latency: int
    dataset_quality_latency: int
    code_quality_latency: int


class IngestRequest(BaseModel):
    """Request body for ingesting a HuggingFace model."""
    url: str = Field(..., description="HuggingFace model URL")
    artifact_type: ArtifactType = ArtifactType.MODEL


class IngestResponse(BaseModel):
    """Response from ingest endpoint."""
    success: bool
    artifact: Optional[ArtifactData] = None
    message: str
    rating: Optional[RatingResponse] = None


class SearchResponse(BaseModel):
    """Response from search endpoint."""
    query: str
    results: List[ArtifactData]
    total: int


class LineageNode(BaseModel):
    """A node in the lineage graph."""
    id: str
    name: str
    type: ArtifactType


class LineageResponse(BaseModel):
    """Response from lineage endpoint."""
    artifact_id: str
    parents: List[LineageNode]
    children: List[LineageNode]


class CostResponse(BaseModel):
    """Response from cost endpoint."""
    artifact_id: str
    own_size_bytes: int
    dependencies_size_bytes: int
    total_size_bytes: int


class LicenseCheckRequest(BaseModel):
    """Request body for license check."""
    artifact_id: str
    github_url: str


class LicenseCheckResponse(BaseModel):
    """Response from license check endpoint."""
    compatible: bool
    artifact_license: Optional[str] = None
    github_license: Optional[str] = None
    message: str


class ComponentStatus(BaseModel):
    """Status of a system component."""
    name: str
    status: str  # "healthy", "degraded", "unhealthy"
    last_check: datetime
    message: Optional[str] = None


class HealthResponse(BaseModel):
    """Aggregate health statistics."""
    status: str  # "healthy", "degraded", "unhealthy"
    uptime_seconds: float
    request_counts: Dict[str, int]
    error_counts: Dict[str, int]
    avg_latency_ms: Dict[str, float]
    period_seconds: int = 3600  # Last hour


class HealthComponentsResponse(BaseModel):
    """Per-component health status."""
    components: List[ComponentStatus]
    overall_status: str


class ResetResponse(BaseModel):
    """Response from reset endpoint."""
    success: bool
    message: str


# ============ SPEC-COMPLIANT SCHEMAS (ECE 461 v3.4.7) ============


class ArtifactMetadataSpec(BaseModel):
    """Artifact metadata per OpenAPI spec."""
    name: str
    id: str
    type: ArtifactType


class ArtifactQuery(BaseModel):
    """Query for searching artifacts."""
    name: str = Field(..., description="Artifact name or '*' for all")
    types: Optional[List[ArtifactType]] = Field(
        None, description="Optional list of artifact types to filter results"
    )


class ArtifactDataSpec(BaseModel):
    """Artifact data source per OpenAPI spec."""
    url: str = Field(..., description="Artifact source url used during ingest")
    download_url: Optional[str] = Field(
        None, description="Direct download link served by your server"
    )


class Artifact(BaseModel):
    """Artifact envelope containing metadata and ingest details."""
    metadata: ArtifactMetadataSpec
    data: ArtifactDataSpec


class ArtifactRegEx(BaseModel):
    """Request body for regex search."""
    regex: str = Field(
        ..., description="A regular expression over artifact names and READMEs"
    )


class ModelRating(BaseModel):
    """Model rating per OpenAPI spec (BASELINE)."""
    name: str
    category: str
    net_score: float
    net_score_latency: float
    ramp_up_time: float
    ramp_up_time_latency: float
    bus_factor: float
    bus_factor_latency: float
    performance_claims: float
    performance_claims_latency: float
    license: float
    license_latency: float
    dataset_and_code_score: float
    dataset_and_code_score_latency: float
    dataset_quality: float
    dataset_quality_latency: float
    code_quality: float
    code_quality_latency: float
    reproducibility: float
    reproducibility_latency: float
    reviewedness: float
    reviewedness_latency: float
    tree_score: float
    tree_score_latency: float
    size_score: SizeScore
    size_score_latency: float


class ArtifactLineageNode(BaseModel):
    """A single node in an artifact lineage graph."""
    artifact_id: str
    name: str
    source: Optional[str] = Field(None, description="Provenance for how the node was discovered")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Optional metadata for lineage")


class ArtifactLineageEdge(BaseModel):
    """Directed relationship between two lineage nodes."""
    from_node_artifact_id: str
    to_node_artifact_id: str
    relationship: str = Field(..., description="Qualitative description of the edge")


class ArtifactLineageGraph(BaseModel):
    """Complete lineage graph for an artifact."""
    nodes: List[ArtifactLineageNode]
    edges: List[ArtifactLineageEdge]


class SimpleLicenseCheckRequest(BaseModel):
    """Request payload for artifact license compatibility analysis."""
    github_url: str = Field(..., description="GitHub repository url to evaluate")


class ArtifactCostEntry(BaseModel):
    """Cost entry for a single artifact."""
    standalone_cost: Optional[float] = Field(
        None, description="Standalone cost excluding dependencies (required when dependency=true)"
    )
    total_cost: float = Field(..., description="Total cost of the artifact")


class ArtifactUploadRequest(BaseModel):
    """Request body for uploading an artifact (spec-compliant).

    Per OpenAPI spec, only url is required. Name is optional but
    the autograder sends it, so we accept both.
    """
    url: str = Field(..., description="Artifact source url used during ingest")
    name: Optional[str] = Field(None, description="Optional artifact name")
