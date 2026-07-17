from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def now() -> datetime:
    return datetime.now(UTC)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class Asset(Base, TimestampMixin):
    __tablename__ = "assets"
    __table_args__ = (UniqueConstraint("workspace_id", "id", name="uq_asset_workspace_id"),)

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(80), index=True)
    kind: Mapped[str] = mapped_column(String(30))
    name: Mapped[str] = mapped_column(String(200))
    engine: Mapped[str] = mapped_column(String(80), default="mock")
    status: Mapped[str] = mapped_column(String(30), default="ready")
    source_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)


class EngineDeployment(Base, TimestampMixin):
    __tablename__ = "engine_deployments"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(80), index=True)
    name: Mapped[str] = mapped_column(String(160))
    engine_kind: Mapped[str] = mapped_column(String(50))
    target_kind: Mapped[str] = mapped_column(String(50))
    current_revision_id: Mapped[str | None] = mapped_column(String(80), nullable=True)

    revisions: Mapped[list[DeploymentRevision]] = relationship(back_populates="deployment", cascade="all, delete-orphan")
    observations: Mapped[list[DeploymentObservation]] = relationship(back_populates="deployment", cascade="all, delete-orphan")


class DeploymentRevision(Base, TimestampMixin):
    __tablename__ = "deployment_revisions"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    deployment_id: Mapped[str] = mapped_column(ForeignKey("engine_deployments.id"), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    adapter_type: Mapped[str] = mapped_column(String(100))
    config_json: Mapped[dict] = mapped_column(JSON, default=dict)
    image_digest: Mapped[str | None] = mapped_column(String(255), nullable=True)
    model_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    capabilities_json: Mapped[dict] = mapped_column(JSON, default=dict)

    deployment: Mapped[EngineDeployment] = relationship(back_populates="revisions")


class DeploymentObservation(Base):
    __tablename__ = "deployment_observations"

    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=lambda: new_id("obs"))
    deployment_id: Mapped[str] = mapped_column(ForeignKey("engine_deployments.id"), index=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    healthy: Mapped[bool] = mapped_column(Boolean, default=False)
    warm: Mapped[bool] = mapped_column(Boolean, default=False)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    details_json: Mapped[dict] = mapped_column(JSON, default=dict)

    deployment: Mapped[EngineDeployment] = relationship(back_populates="observations")


class RealtimeSession(Base, TimestampMixin):
    __tablename__ = "realtime_sessions"

    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=lambda: new_id("rt"))
    workspace_id: Mapped[str] = mapped_column(String(80), index=True)
    state: Mapped[str] = mapped_column(String(30), default="creating")
    state_version: Mapped[int] = mapped_column(Integer, default=1)
    credential_epoch: Mapped[int] = mapped_column(Integer, default=1)
    engine_deployment_id: Mapped[str] = mapped_column(String(80), default="mock-realtime")
    transcript_json: Mapped[list] = mapped_column(JSON, default=list)
    subtitle_seq: Mapped[int] = mapped_column(Integer, default=0)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class VideoJob(Base, TimestampMixin):
    __tablename__ = "video_jobs"

    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=lambda: new_id("job"))
    workspace_id: Mapped[str] = mapped_column(String(80), index=True)
    state: Mapped[str] = mapped_column(String(40), default="queued", index=True)
    desired_state: Mapped[str] = mapped_column(String(20), default="run")
    state_version: Mapped[int] = mapped_column(Integer, default=1)
    stage: Mapped[str] = mapped_column(String(40), default="validating")
    progress: Mapped[int | None] = mapped_column(Integer, nullable=True)
    script: Mapped[str] = mapped_column(Text)
    script_hash: Mapped[str] = mapped_column(String(64))
    avatar_version_id: Mapped[str] = mapped_column(String(80))
    voice_enrollment_id: Mapped[str] = mapped_column(String(80))
    engine_deployment_id: Mapped[str] = mapped_column(String(80))
    output_spec_json: Mapped[dict] = mapped_column(JSON, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_details_json: Mapped[dict] = mapped_column(JSON, default=dict)
    artifact_id: Mapped[str | None] = mapped_column(String(80), nullable=True)

    attempts: Mapped[list[JobAttempt]] = relationship(back_populates="job", cascade="all, delete-orphan")


class JobAttempt(Base, TimestampMixin):
    __tablename__ = "job_attempts"

    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=lambda: new_id("attempt"))
    job_id: Mapped[str] = mapped_column(ForeignKey("video_jobs.id"), index=True)
    sequence: Mapped[int] = mapped_column(Integer, default=1)
    state: Mapped[str] = mapped_column(String(40), default="pending")
    fencing_token: Mapped[int] = mapped_column(Integer, default=0)
    row_version: Mapped[int] = mapped_column(Integer, default=1)
    lease_owner: Mapped[str | None] = mapped_column(String(120), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    execution_plan_json: Mapped[dict] = mapped_column(JSON, default=dict)
    remote_operation_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    termination_reason: Mapped[str | None] = mapped_column(String(160), nullable=True)

    job: Mapped[VideoJob] = relationship(back_populates="attempts")


class JobEvent(Base):
    __tablename__ = "job_events"

    cursor: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[str] = mapped_column(String(80), index=True)
    job_id: Mapped[str] = mapped_column(String(80), index=True)
    event_type: Mapped[str] = mapped_column(String(80))
    state_version: Mapped[int] = mapped_column(Integer)
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (UniqueConstraint("workspace_id", "endpoint", "key", name="uq_idempotency_scope"),)

    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=lambda: new_id("idem"))
    workspace_id: Mapped[str] = mapped_column(String(80), index=True)
    endpoint: Mapped[str] = mapped_column(String(120))
    key: Mapped[str] = mapped_column(String(200))
    request_hash: Mapped[str] = mapped_column(String(64))
    response_json: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class OutboxEvent(Base):
    __tablename__ = "outbox_events"

    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=lambda: new_id("outbox"))
    aggregate_type: Mapped[str] = mapped_column(String(50))
    aggregate_id: Mapped[str] = mapped_column(String(80), index=True)
    event_type: Mapped[str] = mapped_column(String(80))
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Artifact(Base, TimestampMixin):
    __tablename__ = "artifacts"

    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=lambda: new_id("artifact"))
    workspace_id: Mapped[str] = mapped_column(String(80), index=True)
    job_id: Mapped[str] = mapped_column(String(80), index=True)
    attempt_id: Mapped[str] = mapped_column(String(80))
    fencing_token: Mapped[int] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String(30), default="staging")
    path: Mapped[str] = mapped_column(String(500))
    sha256: Mapped[str] = mapped_column(String(64))
    media_type: Mapped[str] = mapped_column(String(100), default="video/mp4")
    size_bytes: Mapped[int] = mapped_column(Integer)
    manifest_json: Mapped[dict] = mapped_column(JSON, default=dict)

