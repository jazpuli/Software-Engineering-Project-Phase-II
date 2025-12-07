"""Pydantic models for API request/response schemas."""

from datetime import datetime
from typing import Optional, Dict, Any, List
from enum import Enum
from pydantic import BaseModel, Field


class ArtifactType(str, Enum):
    """Supported artifact types."""
    MODEL = "model"
    DATASET = "dataset"
    NOTEBOOK = "notebook"


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

