from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ErrorEnvelope(BaseModel):
    code: str
    message: str
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)
    request_id: str


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    profile: str
    version: str
    database: str
    dispatcher: str


class AssetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    kind: str
    name: str
    engine: str
    status: str
    source_name: str | None = None
    content_type: str | None = None
    size_bytes: int | None = None
    metadata_json: dict[str, Any]
    created_at: datetime


class PreflightCheck(BaseModel):
    key: str
    label: str
    status: Literal["pass", "warning", "blocked"]
    message: str


class PreflightResponse(BaseModel):
    asset: AssetOut
    overall: Literal["valid", "warning", "blocked"]
    checks: list[PreflightCheck]
    compatible_deployments: list[str]


class DeploymentRevisionOut(BaseModel):
    id: str
    revision: int
    adapter_type: str
    image_digest: str | None
    model_hash: str | None
    capabilities: dict[str, Any]


class DeploymentObservationOut(BaseModel):
    observed_at: datetime
    healthy: bool
    warm: bool
    latency_ms: int | None
    details: dict[str, Any]


class EngineDeploymentOut(BaseModel):
    id: str
    name: str
    engine_kind: str
    target_kind: str
    revision: DeploymentRevisionOut
    observation: DeploymentObservationOut | None


class ProbeResponse(BaseModel):
    deployment_id: str
    healthy: bool
    warm: bool
    latency_ms: int
    capabilities: dict[str, Any]
    checked_at: datetime


class RealtimeSessionCreate(BaseModel):
    deployment_id: str = "mock-realtime"
    avatar_version_id: str = "avatar_sample_v1"
    voice_enrollment_id: str = "voice_sample_v1"


class RealtimeSessionOut(BaseModel):
    session_id: str
    state: str
    state_version: int
    credential_epoch: int
    credential: str
    expires_in_seconds: int = 300
    engine_type: str
    client_config: dict[str, Any]


class RealtimeTurnIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)

    @field_validator("text")
    @classmethod
    def text_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("text must contain a visible character")
        return value


class RealtimeTurnOut(BaseModel):
    turn_id: str
    sequence: int
    user_text: str
    assistant_text: str
    state: str


class OutputSpec(BaseModel):
    width: int = Field(default=1280, ge=640, le=1920)
    height: int = Field(default=720, ge=360, le=1080)
    fps: int = Field(default=25, ge=20, le=30)
    container: Literal["mp4"] = "mp4"
    motion_profile: Literal["steady", "natural", "expressive"] = "natural"


class VideoJobCreate(BaseModel):
    script: str = Field(min_length=1, max_length=10000)
    avatar_version_id: str = "avatar_sample_v1"
    voice_enrollment_id: str = "voice_sample_v1"
    engine_deployment_id: str = "mock-render"
    output: OutputSpec = Field(default_factory=OutputSpec)

    @field_validator("script")
    @classmethod
    def script_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value or all(not character.isalnum() for character in value):
            raise ValueError("script must contain letters or numbers")
        return value


class VideoJobOut(BaseModel):
    id: str
    state: str
    desired_state: str
    state_version: int
    stage: str
    progress: int | None
    script: str
    avatar_version_id: str
    voice_enrollment_id: str
    engine_deployment_id: str
    output: dict[str, Any]
    artifact_id: str | None
    download_url: str | None
    error: dict[str, Any] | None
    event_cursor: int
    created_at: datetime
    updated_at: datetime


class JobListOut(BaseModel):
    items: list[VideoJobOut]


class SystemSummary(BaseModel):
    profile: str
    mock_mode: bool
    assets_ready: int
    deployments_healthy: int
    active_jobs: int
    upstream_gate_resolved: bool


class ComputePlan(BaseModel):
    mode: str
    provider: str
    gpu: str
    local_gpu_required: bool
    scale_to_zero: bool
    rate_usd_per_second: float
    rate_usd_per_hour: float
    monthly_credit_usd: float
    free_quota_label: str
    estimated_gpu_cost_per_output_minute_usd: float
    estimate_assumption: str
    checked_at: str
    source_url: str
    status: Literal["recommended", "configured"]
    next_action: str
