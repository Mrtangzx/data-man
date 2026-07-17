from __future__ import annotations

import hashlib
import json
import shutil
import socket
import subprocess
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..adapters.mock import MockExecutionTargetAdapter
from ..config import get_settings
from ..db import SessionLocal
from ..errors import CapabilityMismatchError, IdempotencyConflictError, NotFoundError
from ..models import Artifact, IdempotencyRecord, JobAttempt, JobEvent, OutboxEvent, VideoJob
from ..schemas import VideoJobCreate, VideoJobOut
from ..state_machine import transition_attempt, transition_job


TERMINAL_JOB_STATES = {"succeeded", "failed", "cancelled"}
STAGES: tuple[tuple[str, int], ...] = (
    ("validating", 8),
    ("preprocessing", 22),
    ("synthesizing", 45),
    ("rendering", 72),
    ("encoding", 90),
    ("uploading", 97),
)


def canonical_request_hash(payload: VideoJobCreate) -> str:
    canonical = json.dumps(payload.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def latest_cursor(db: Session, job_id: str) -> int:
    return int(db.scalar(select(func.max(JobEvent.cursor)).where(JobEvent.job_id == job_id)) or 0)


def emit_event(db: Session, job: VideoJob, event_type: str, payload: dict | None = None) -> JobEvent:
    event = JobEvent(
        workspace_id=job.workspace_id,
        job_id=job.id,
        event_type=event_type,
        state_version=job.state_version,
        payload_json={
            "job_id": job.id,
            "state": job.state,
            "stage": job.stage,
            "progress": job.progress,
            **(payload or {}),
        },
    )
    db.add(event)
    db.flush()
    return event


def serialize_job(db: Session, job: VideoJob) -> VideoJobOut:
    error = None
    if job.error_code:
        error = {"code": job.error_code, **job.error_details_json}
    return VideoJobOut(
        id=job.id,
        state=job.state,
        desired_state=job.desired_state,
        state_version=job.state_version,
        stage=job.stage,
        progress=job.progress,
        script=job.script,
        avatar_version_id=job.avatar_version_id,
        voice_enrollment_id=job.voice_enrollment_id,
        engine_deployment_id=job.engine_deployment_id,
        output=job.output_spec_json,
        artifact_id=job.artifact_id,
        download_url=f"/api/v1/artifacts/{job.artifact_id}/download" if job.artifact_id else None,
        error=error,
        event_cursor=latest_cursor(db, job.id),
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


def create_video_job(db: Session, workspace_id: str, key: str, payload: VideoJobCreate) -> tuple[VideoJobOut, bool]:
    request_hash = canonical_request_hash(payload)
    existing = db.scalar(
        select(IdempotencyRecord).where(
            IdempotencyRecord.workspace_id == workspace_id,
            IdempotencyRecord.endpoint == "POST:/api/v1/video-jobs",
            IdempotencyRecord.key == key,
        )
    )
    if existing:
        if existing.request_hash != request_hash:
            raise IdempotencyConflictError()
        job = db.get(VideoJob, existing.response_json["job_id"])
        if not job:
            raise NotFoundError("VideoJob referenced by the idempotency record")
        return serialize_job(db, job), True

    plan = {
        "script_hash": hashlib.sha256(payload.script.encode()).hexdigest(),
        "avatar_version_id": payload.avatar_version_id,
        "voice_enrollment_id": payload.voice_enrollment_id,
        "engine_deployment_id": payload.engine_deployment_id,
        "deployment_revision_id": f"{payload.engine_deployment_id}-r1",
        "output": payload.output.model_dump(),
        "capability_snapshot": MockExecutionTargetAdapter().discover_capabilities().as_dict(),
    }
    errors = MockExecutionTargetAdapter().validate_execution_plan(plan)
    if errors:
        raise CapabilityMismatchError(errors)

    job = VideoJob(
        workspace_id=workspace_id,
        script=payload.script,
        script_hash=plan["script_hash"],
        avatar_version_id=payload.avatar_version_id,
        voice_enrollment_id=payload.voice_enrollment_id,
        engine_deployment_id=payload.engine_deployment_id,
        output_spec_json=payload.output.model_dump(),
        state="queued",
        stage="validating",
        progress=0,
    )
    db.add(job)
    db.flush()
    attempt = JobAttempt(job_id=job.id, sequence=1, state="pending", execution_plan_json=plan)
    outbox = OutboxEvent(
        aggregate_type="VideoJob",
        aggregate_id=job.id,
        event_type="video_job.requested",
        payload_json={"job_id": job.id},
    )
    db.add_all([attempt, outbox])
    emit_event(db, job, "job.queued")
    response = {"job_id": job.id}
    db.add(
        IdempotencyRecord(
            workspace_id=workspace_id,
            endpoint="POST:/api/v1/video-jobs",
            key=key,
            request_hash=request_hash,
            response_json=response,
        )
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return create_video_job(db, workspace_id, key, payload)
    db.refresh(job)
    return serialize_job(db, job), False


def ensure_sample_video() -> Path:
    settings = get_settings()
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    sample = settings.storage_dir / "mock-output.mp4"
    if sample.exists() and sample.stat().st_size > 1000:
        return sample
    bundled = Path(__file__).resolve().parent.parent / "fixtures" / "mock-output.mp4"
    if bundled.is_file() and bundled.stat().st_size > 1000:
        shutil.copyfile(bundled, sample)
        return sample
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        sample.write_bytes(b"NOVA MOCK MP4 REQUIRES THE DOCKER PROFILE WITH FFMPEG")
        return sample
    command = [
        ffmpeg,
        "-y",
        "-f",
        "lavfi",
        "-i",
        "testsrc2=size=1280x720:rate=25:duration=3",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=330:sample_rate=48000:duration=3",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-shortest",
        "-movflags",
        "+faststart",
        str(sample),
    ]
    subprocess.run(command, check=True, capture_output=True, timeout=60)
    return sample


class LocalDispatcher:
    def __init__(self, poll_seconds: float = 0.25, stage_seconds: float = 0.35) -> None:
        self.poll_seconds = poll_seconds
        self.stage_seconds = stage_seconds
        self.worker_id = f"local-{socket.gethostname()}-{id(self)}"
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="nova-local-dispatcher", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)
        self._thread = None

    def _run(self) -> None:
        while not self._stop.is_set():
            claimed = self._claim_next()
            if claimed:
                self._execute(*claimed)
            else:
                self._stop.wait(self.poll_seconds)

    def _claim_next(self) -> tuple[str, str, int] | None:
        with SessionLocal() as db:
            job = db.scalar(select(VideoJob).where(VideoJob.state == "queued").order_by(VideoJob.created_at).limit(1))
            if not job:
                return None
            attempt = db.scalar(select(JobAttempt).where(JobAttempt.job_id == job.id).order_by(JobAttempt.sequence.desc()))
            if not attempt or attempt.state != "pending":
                return None
            attempt.state = transition_attempt(attempt.state, "leased")
            attempt.fencing_token += 1
            attempt.row_version += 1
            attempt.lease_owner = self.worker_id
            attempt.lease_expires_at = datetime.now(UTC) + timedelta(seconds=30)
            job.state = transition_job(job.state, "running")
            job.state_version += 1
            emit_event(db, job, "job.leased", {"attempt_id": attempt.id, "fencing_token": attempt.fencing_token})
            outbox = db.scalar(select(OutboxEvent).where(OutboxEvent.aggregate_id == job.id, OutboxEvent.published_at.is_(None)))
            if outbox:
                outbox.published_at = datetime.now(UTC)
            db.commit()
            return job.id, attempt.id, attempt.fencing_token

    def _execute(self, job_id: str, attempt_id: str, fencing_token: int) -> None:
        for stage, progress in STAGES:
            if self._stop.is_set():
                return
            with SessionLocal() as db:
                job = db.get(VideoJob, job_id)
                attempt = db.get(JobAttempt, attempt_id)
                if not job or not attempt or attempt.fencing_token != fencing_token:
                    return
                if job.desired_state == "cancel":
                    attempt.state = "cancelled"
                    attempt.termination_reason = "cancelled_by_user"
                    job.state = "cancelled"
                    job.stage = "cancelled"
                    job.progress = None
                    job.state_version += 1
                    emit_event(db, job, "job.cancelled")
                    db.commit()
                    return
                if attempt.state == "leased":
                    attempt.state = transition_attempt(attempt.state, "running")
                attempt.lease_expires_at = datetime.now(UTC) + timedelta(seconds=30)
                job.stage = stage
                job.progress = progress
                job.state_version += 1
                emit_event(db, job, "job.progress")
                db.commit()
            time.sleep(self.stage_seconds)

        sample = ensure_sample_video()
        content = sample.read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        with SessionLocal() as db:
            job = db.get(VideoJob, job_id)
            attempt = db.get(JobAttempt, attempt_id)
            if not job or not attempt or attempt.fencing_token != fencing_token or job.state != "running":
                return
            artifact = Artifact(
                workspace_id=job.workspace_id,
                job_id=job.id,
                attempt_id=attempt.id,
                fencing_token=fencing_token,
                state="published",
                path=str(sample),
                sha256=digest,
                media_type="video/mp4",
                size_bytes=len(content),
                manifest_json={
                    "mock": True,
                    "quality_evidence": False,
                    "width": job.output_spec_json["width"],
                    "height": job.output_spec_json["height"],
                    "fps": job.output_spec_json["fps"],
                    "motion_profile": job.output_spec_json.get("motion_profile", "natural"),
                },
            )
            db.add(artifact)
            db.flush()
            attempt.state = transition_attempt(attempt.state, "succeeded")
            attempt.row_version += 1
            job.state = transition_job(job.state, "succeeded")
            job.stage = "completed"
            job.progress = 100
            job.artifact_id = artifact.id
            job.state_version += 1
            emit_event(db, job, "job.succeeded", {"artifact_id": artifact.id})
            db.commit()
