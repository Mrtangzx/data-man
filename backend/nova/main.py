from __future__ import annotations

import asyncio
import json
import secrets
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

from fastapi import Depends, FastAPI, File, Header, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from .adapters.mock import MockExecutionTargetAdapter
from .config import get_settings
from .db import SessionLocal, get_db, init_db
from .errors import NovaError, NotFoundError
from .models import (
    Artifact,
    Asset,
    DeploymentObservation,
    DeploymentRevision,
    EngineDeployment,
    JobEvent,
    RealtimeSession,
    VideoJob,
    new_id,
    now,
)
from .schemas import (
    AssetOut,
    ComputePlan,
    EngineDeploymentOut,
    HealthResponse,
    LlmActiveProviderIn,
    LlmProviderUpdate,
    LlmProvidersOut,
    LlmTestOut,
    JobListOut,
    PreflightCheck,
    PreflightResponse,
    ProbeResponse,
    RealtimeSessionCreate,
    RealtimeSessionOut,
    RealtimeTurnIn,
    RealtimeTurnOut,
    SystemSummary,
    VideoJobCreate,
    VideoJobOut,
)
from .services.bootstrap import seed_defaults
from .services.jobs import (
    TERMINAL_JOB_STATES,
    LocalDispatcher,
    create_video_job,
    emit_event,
    ensure_sample_video,
    serialize_job,
)
from .services.llm import (
    chat_completion,
    get_active_provider_id,
    get_provider,
    list_providers,
    save_provider,
    set_active_provider,
)


settings = get_settings()
dispatcher = LocalDispatcher()


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    with SessionLocal() as db:
        seed_defaults(db)
    ensure_sample_video()
    dispatcher.start()
    yield
    dispatcher.stop()


app = FastAPI(
    title="NOVA C2 Control Plane",
    version="0.1.0",
    description="Stable control-plane API. The dev profile is deterministic Mock and is not model-quality evidence.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    request.state.request_id = request.headers.get("X-Request-ID") or new_id("req")
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    return response


@app.exception_handler(NovaError)
async def nova_error_handler(request: Request, error: NovaError):
    return JSONResponse(
        status_code=error.status_code,
        content={
            "code": error.code,
            "message": error.message,
            "retryable": error.retryable,
            "details": error.details,
            "request_id": getattr(request.state, "request_id", new_id("req")),
        },
    )


def _deployment_out(db: Session, deployment: EngineDeployment) -> EngineDeploymentOut:
    revision = db.get(DeploymentRevision, deployment.current_revision_id)
    if revision is None:
        raise NotFoundError("DeploymentRevision")
    observation = db.scalar(
        select(DeploymentObservation)
        .where(DeploymentObservation.deployment_id == deployment.id)
        .order_by(DeploymentObservation.observed_at.desc())
        .limit(1)
    )
    active_provider = get_provider()
    realtime_is_real = deployment.engine_kind == "realtime" and bool(active_provider.api_key.strip())
    revision_capabilities = revision.capabilities_json
    if realtime_is_real:
        revision_capabilities = {
            **revision_capabilities,
            "mock": False,
            "real_language": True,
            "model": active_provider.model,
        }
    return EngineDeploymentOut(
        id=deployment.id,
        name="真实语言实时引擎" if realtime_is_real else deployment.name,
        engine_kind=deployment.engine_kind,
        target_kind="openai_compatible" if realtime_is_real else deployment.target_kind,
        revision={
            "id": revision.id,
            "revision": revision.revision,
            "adapter_type": "llm.openai_compatible.v1" if realtime_is_real else revision.adapter_type,
            "image_digest": revision.image_digest,
            "model_hash": revision.model_hash,
            "capabilities": revision_capabilities,
        },
        observation=(
            {
                "observed_at": observation.observed_at,
                "healthy": observation.healthy,
                "warm": observation.warm,
                "latency_ms": observation.latency_ms,
                "details": observation.details_json,
            }
            if observation
            else None
        ),
    )


def _session_out(session: RealtimeSession) -> RealtimeSessionOut:
    provider_id = next(
        (item.get("provider_id") for item in (session.transcript_json or []) if item.get("role") == "meta"),
        get_active_provider_id(),
    )
    provider = get_provider(provider_id)
    return RealtimeSessionOut(
        session_id=session.id,
        state=session.state,
        state_version=session.state_version,
        credential_epoch=session.credential_epoch,
        credential=secrets.token_urlsafe(24),
        engine_type="llm",
        client_config={
            "transport": "control-plane-llm",
            "supports_text": True,
            "supports_microphone": True,
            "supports_interrupt": True,
            "supports_subtitles": True,
            "provider": provider.base_url,
            "provider_id": provider.id,
            "model": provider.model,
            "real_language": True,
        },
    )


def _llm_reply(session: RealtimeSession) -> str:
    provider_id = next(
        (item.get("provider_id") for item in (session.transcript_json or []) if item.get("role") == "meta"),
        get_active_provider_id(),
    )
    provider = get_provider(provider_id)
    messages = [{"role": "system", "content": settings.llm_system_prompt}]
    for item in (session.transcript_json or [])[-20:]:
        role = item.get("role")
        text_value = item.get("text")
        if role in {"user", "assistant"} and isinstance(text_value, str) and text_value.strip():
            messages.append({"role": role, "content": text_value})

    return chat_completion(provider, messages)


@app.get("/healthz", response_model=HealthResponse)
def health(db: Session = Depends(get_db)) -> HealthResponse:
    db.execute(text("SELECT 1"))
    return HealthResponse(
        status="ok",
        profile=settings.profile,
        version=app.version,
        database="ok",
        dispatcher="running" if dispatcher._thread and dispatcher._thread.is_alive() else "starting",
    )


@app.get("/api/v1/system/summary", response_model=SystemSummary)
def system_summary(db: Session = Depends(get_db)) -> SystemSummary:
    assets = int(db.scalar(select(func.count()).select_from(Asset).where(Asset.status == "ready")) or 0)
    healthy = int(
        db.scalar(select(func.count()).select_from(DeploymentObservation).where(DeploymentObservation.healthy.is_(True))) or 0
    )
    active = int(
        db.scalar(select(func.count()).select_from(VideoJob).where(VideoJob.state.in_(("queued", "running", "reconciling"))))
        or 0
    )
    return SystemSummary(
        profile=settings.profile,
        mock_mode=settings.profile in {"dev", "lite"},
        assets_ready=assets,
        deployments_healthy=healthy,
        active_jobs=active,
        upstream_gate_resolved=False,
    )


@app.get("/api/v1/system/compute-plan", response_model=ComputePlan)
def compute_plan() -> ComputePlan:
    """Expose the selected low-cost policy without exposing provider credentials."""
    rate = settings.compute_gpu_rate_usd_per_second
    return ComputePlan(
        mode=settings.compute_mode,
        provider=settings.compute_provider,
        gpu=settings.compute_gpu,
        local_gpu_required=False,
        scale_to_zero=True,
        rate_usd_per_second=rate,
        rate_usd_per_hour=round(rate * 3600, 4),
        monthly_credit_usd=settings.compute_monthly_credit_usd,
        free_quota_label=settings.compute_free_quota_label,
        # The product gate allows at most 10 GPU minutes for one output minute.
        estimated_gpu_cost_per_output_minute_usd=round(rate * 600, 4),
        estimate_assumption="魔搭社区免费额度内 GPU 费用为 0；额度、排队与实例时长以账户页面为准。",
        checked_at=settings.compute_cost_checked_at,
        source_url="https://www.modelscope.cn/learn/434367",
        status="configured" if settings.profile not in {"dev", "lite"} else "recommended",
        next_action="在魔搭 Notebook 领取免费 A10 24GB，运行 deploy/modelscope/NOVA-ModelScope-A10.ipynb 完成真实成片纵切。",
    )


@app.get("/api/v1/llm/providers", response_model=LlmProvidersOut)
def get_llm_providers() -> dict:
    return list_providers()


@app.put("/api/v1/llm/providers/{provider_id}", response_model=dict)
def update_llm_provider(provider_id: str, payload: LlmProviderUpdate) -> dict:
    return save_provider(provider_id, payload.name, payload.base_url, payload.model, payload.api_key, payload.active)


@app.put("/api/v1/llm/active", response_model=dict)
def update_active_llm_provider(payload: LlmActiveProviderIn) -> dict:
    return set_active_provider(payload.provider_id)


@app.post("/api/v1/llm/providers/{provider_id}/test", response_model=LlmTestOut)
def test_llm_provider(provider_id: str) -> LlmTestOut:
    provider = get_provider(provider_id)
    reply = chat_completion(
        provider,
        [
            {"role": "system", "content": "你是连接测试助手，只回复：连接成功。"},
            {"role": "user", "content": "请测试当前语言模型连接。"},
        ],
    )
    return LlmTestOut(provider_id=provider.id, model=provider.model, reply=reply)


@app.get("/api/v1/assets", response_model=list[AssetOut])
def list_assets(db: Session = Depends(get_db)) -> list[Asset]:
    return list(
        db.scalars(select(Asset).where(Asset.workspace_id == settings.workspace_id).order_by(Asset.created_at.desc()))
    )


@app.get("/api/v1/assets/{asset_id}/content")
def get_asset_content(asset_id: str, db: Session = Depends(get_db)):
    asset = db.get(Asset, asset_id)
    if not asset or asset.workspace_id != settings.workspace_id:
        raise NotFoundError("Asset")
    raw_path = asset.metadata_json.get("path")
    if not raw_path:
        raise NotFoundError("Asset file")
    path = Path(raw_path).resolve()
    upload_root = (settings.storage_dir / "uploads").resolve()
    if not path.is_relative_to(upload_root) or not path.is_file():
        raise NotFoundError("Asset file")
    return FileResponse(path, media_type=asset.content_type or "application/octet-stream", filename=asset.source_name)


@app.post("/api/v1/assets/preflight", response_model=PreflightResponse, status_code=201)
async def preflight_asset(
    kind: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> PreflightResponse:
    if kind not in {"avatar", "voice"}:
        raise NovaError("NOVA-ASSET-1101", "kind must be avatar or voice.", 422)
    content = await file.read(25 * 1024 * 1024 + 1)
    if not content:
        raise NovaError("NOVA-ASSET-1102", "The uploaded file is empty.", 422)
    if len(content) > 25 * 1024 * 1024:
        raise NovaError("NOVA-ASSET-1103", "The file exceeds the 25 MB development limit.", 413)

    allowed_prefixes = ("image/", "video/") if kind == "avatar" else ("audio/", "video/")
    media_ok = bool(file.content_type and file.content_type.startswith(allowed_prefixes))
    asset_id = new_id(kind)
    suffix = Path(file.filename or "upload.bin").suffix[:12]
    upload_dir = settings.storage_dir / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    target = upload_dir / f"{asset_id}{suffix}"
    target.write_bytes(content)
    asset = Asset(
        id=asset_id,
        workspace_id=settings.workspace_id,
        kind=kind,
        name=Path(file.filename or f"{kind} material").stem[:200],
        engine="unassigned",
        status="ready" if media_ok else "needs_review",
        source_name=file.filename,
        content_type=file.content_type,
        size_bytes=len(content),
        metadata_json={"path": str(target), "mock_preflight": True, "quality_evidence": False},
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    checks = [
        PreflightCheck(key="size", label="文件大小", status="pass", message="文件大小在开发环境限制内。"),
        PreflightCheck(
            key="media_type",
            label="媒体类型",
            status="pass" if media_ok else "warning",
            message="媒体类型符合预期。" if media_ok else "浏览器未提供可确认的媒体类型，需要真实引擎复检。",
        ),
        PreflightCheck(
            key="engine",
            label="引擎兼容性",
            status="warning",
            message="当前只完成协议预检，接入固定版本模型后执行真实兼容性检查。",
        ),
    ]
    return PreflightResponse(
        asset=AssetOut.model_validate(asset),
        overall="warning",
        checks=checks,
        compatible_deployments=["mock-realtime", "mock-render"],
    )


@app.get("/api/v1/engine-deployments", response_model=list[EngineDeploymentOut])
def list_deployments(db: Session = Depends(get_db)) -> list[EngineDeploymentOut]:
    deployments = db.scalars(
        select(EngineDeployment)
        .where(EngineDeployment.workspace_id == settings.workspace_id)
        .order_by(EngineDeployment.engine_kind, EngineDeployment.name)
    )
    return [_deployment_out(db, deployment) for deployment in deployments]


@app.post("/api/v1/engine-deployments/{deployment_id}/probe", response_model=ProbeResponse)
def probe_deployment(deployment_id: str, db: Session = Depends(get_db)) -> ProbeResponse:
    deployment = db.get(EngineDeployment, deployment_id)
    if not deployment or deployment.workspace_id != settings.workspace_id:
        raise NotFoundError("EngineDeployment")
    adapter = MockExecutionTargetAdapter()
    result = adapter.health_check()
    revision = db.get(DeploymentRevision, deployment.current_revision_id)
    observation = DeploymentObservation(
        deployment_id=deployment.id,
        healthy=bool(result["healthy"]),
        warm=bool(result["warm"]),
        latency_ms=int(result["latency_ms"]),
        details_json=result,
    )
    db.add(observation)
    db.commit()
    return ProbeResponse(
        deployment_id=deployment.id,
        healthy=observation.healthy,
        warm=observation.warm,
        latency_ms=observation.latency_ms or 0,
        capabilities=revision.capabilities_json if revision else {},
        checked_at=observation.observed_at,
    )


@app.post("/api/v1/realtime/sessions", response_model=RealtimeSessionOut, status_code=201)
def create_realtime_session(payload: RealtimeSessionCreate, db: Session = Depends(get_db)) -> RealtimeSessionOut:
    provider_id = payload.provider_id or get_active_provider_id()
    provider = get_provider(provider_id)
    if not provider.api_key.strip():
        raise NovaError(
            "NOVA-RT-2501",
            f"供应商“{provider.name}”尚未配置 API key，无法启动实时交流。",
            503,
            details={"fix": "打开系统设置，填写 API key 后保存。"},
        )
    deployment = db.get(EngineDeployment, payload.deployment_id)
    if not deployment or deployment.engine_kind != "realtime":
        raise NotFoundError("Realtime EngineDeployment")
    session = RealtimeSession(
        workspace_id=settings.workspace_id,
        state="connected",
        state_version=2,
        engine_deployment_id=payload.deployment_id,
        transcript_json=[{"role": "meta", "provider_id": provider.id}],
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return _session_out(session)


@app.post("/api/v1/realtime/sessions/{session_id}/credentials/refresh", response_model=RealtimeSessionOut)
def refresh_realtime_credentials(session_id: str, db: Session = Depends(get_db)) -> RealtimeSessionOut:
    session = db.get(RealtimeSession, session_id)
    if not session or session.workspace_id != settings.workspace_id:
        raise NotFoundError("RealtimeSession")
    if session.state == "ended":
        raise NovaError("NOVA-RT-2409", "The realtime session has ended.", 409)
    session.credential_epoch += 1
    session.state_version += 1
    db.commit()
    return _session_out(session)


@app.post("/api/v1/realtime/sessions/{session_id}/turns", response_model=RealtimeTurnOut)
def send_realtime_turn(
    session_id: str,
    payload: RealtimeTurnIn,
    db: Session = Depends(get_db),
) -> RealtimeTurnOut:
    session = db.get(RealtimeSession, session_id)
    if not session or session.workspace_id != settings.workspace_id:
        raise NotFoundError("RealtimeSession")
    if session.state not in {"connected", "speaking", "listening"}:
        raise NovaError("NOVA-RT-2409", "The realtime session is not connected.", 409)
    sequence = sum(1 for item in (session.transcript_json or []) if item.get("role") == "user") + 1
    session.transcript_json = [
        *(session.transcript_json or []),
        {"sequence": sequence, "role": "user", "text": payload.text, "at": now().isoformat()},
    ]
    assistant_text = _llm_reply(session)
    transcript = [
        *session.transcript_json,
        {"sequence": sequence, "role": "assistant", "text": assistant_text, "at": now().isoformat()},
    ]
    session.transcript_json = transcript
    session.subtitle_seq += 1
    session.state = "speaking"
    session.state_version += 1
    db.commit()
    return RealtimeTurnOut(
        turn_id=new_id("turn"),
        sequence=sequence,
        user_text=payload.text,
        assistant_text=assistant_text,
        state=session.state,
    )


@app.post("/api/v1/realtime/sessions/{session_id}/interrupt")
def interrupt_realtime_session(session_id: str, db: Session = Depends(get_db)) -> dict:
    session = db.get(RealtimeSession, session_id)
    if not session or session.workspace_id != settings.workspace_id:
        raise NotFoundError("RealtimeSession")
    session.state = "connected"
    session.state_version += 1
    db.commit()
    return {"acknowledged": True, "state": session.state, "state_version": session.state_version}


@app.delete("/api/v1/realtime/sessions/{session_id}")
def close_realtime_session(session_id: str, db: Session = Depends(get_db)) -> dict:
    session = db.get(RealtimeSession, session_id)
    if not session or session.workspace_id != settings.workspace_id:
        raise NotFoundError("RealtimeSession")
    session.state = "ended"
    session.state_version += 1
    session.ended_at = datetime.now(UTC)
    db.commit()
    return {"session_id": session.id, "state": session.state, "state_version": session.state_version}


@app.post("/api/v1/video-jobs", response_model=VideoJobOut, status_code=202)
def submit_video_job(
    payload: VideoJobCreate,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
) -> VideoJobOut:
    if not idempotency_key or len(idempotency_key) > 200:
        raise NovaError("NOVA-JOB-3003", "A valid Idempotency-Key header is required.", 400)
    result, _ = create_video_job(db, settings.workspace_id, idempotency_key, payload)
    return result


@app.get("/api/v1/video-jobs", response_model=JobListOut)
def list_video_jobs(db: Session = Depends(get_db)) -> JobListOut:
    jobs = db.scalars(
        select(VideoJob).where(VideoJob.workspace_id == settings.workspace_id).order_by(VideoJob.created_at.desc()).limit(100)
    )
    return JobListOut(items=[serialize_job(db, job) for job in jobs])


@app.get("/api/v1/video-jobs/{job_id}", response_model=VideoJobOut)
def get_video_job(job_id: str, db: Session = Depends(get_db)) -> VideoJobOut:
    job = db.get(VideoJob, job_id)
    if not job or job.workspace_id != settings.workspace_id:
        raise NotFoundError("VideoJob")
    return serialize_job(db, job)


@app.post("/api/v1/video-jobs/{job_id}/cancel", response_model=VideoJobOut)
def cancel_video_job(job_id: str, db: Session = Depends(get_db)) -> VideoJobOut:
    job = db.get(VideoJob, job_id)
    if not job or job.workspace_id != settings.workspace_id:
        raise NotFoundError("VideoJob")
    if job.state in TERMINAL_JOB_STATES:
        return serialize_job(db, job)
    job.desired_state = "cancel"
    job.state_version += 1
    emit_event(db, job, "job.cancel_requested")
    db.commit()
    return serialize_job(db, job)


@app.get("/api/v1/video-jobs/{job_id}/events")
async def stream_job_events(
    job_id: str,
    request: Request,
    after: int = 0,
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
):
    cursor = after
    if last_event_id and last_event_id.isdigit():
        cursor = max(cursor, int(last_event_id))
    with SessionLocal() as db:
        job = db.get(VideoJob, job_id)
        if not job or job.workspace_id != settings.workspace_id:
            raise NotFoundError("VideoJob")

    async def event_source():
        nonlocal cursor
        idle_ticks = 0
        while not await request.is_disconnected():
            with SessionLocal() as db:
                events = list(
                    db.scalars(
                        select(JobEvent)
                        .where(JobEvent.job_id == job_id, JobEvent.cursor > cursor)
                        .order_by(JobEvent.cursor)
                        .limit(100)
                    )
                )
                job = db.get(VideoJob, job_id)
                for event in events:
                    cursor = event.cursor
                    snapshot = serialize_job(db, job).model_dump(mode="json") if job else None
                    data = {
                        **event.payload_json,
                        "event_cursor": event.cursor,
                        "state_version": event.state_version,
                        "snapshot": snapshot,
                    }
                    yield f"id: {event.cursor}\nevent: {event.event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
                if events:
                    idle_ticks = 0
                else:
                    idle_ticks += 1
                if job and job.state in TERMINAL_JOB_STATES and not events:
                    break
            if idle_ticks and idle_ticks % 15 == 0:
                yield ": heartbeat\n\n"
            await asyncio.sleep(0.2)

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/v1/artifacts/{artifact_id}/download")
def download_artifact(artifact_id: str, db: Session = Depends(get_db)):
    artifact = db.get(Artifact, artifact_id)
    if not artifact or artifact.workspace_id != settings.workspace_id or artifact.state != "published":
        raise NotFoundError("Artifact")
    path = Path(artifact.path)
    if not path.is_file():
        raise NotFoundError("Artifact file")
    return FileResponse(path, media_type=artifact.media_type, filename=f"nova-{artifact.job_id}.mp4")
