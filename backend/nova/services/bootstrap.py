from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Asset, DeploymentObservation, DeploymentRevision, EngineDeployment


MOCK_RENDER_CAPABILITIES = {
    "inputs": ["text", "avatar_version", "voice_enrollment", "motion_profile"],
    "outputs": ["video/mp4"],
    "resolutions": ["1280x720", "1920x1080"],
    "supports_progress": True,
    "supports_cancel": True,
    "supports_idempotency": True,
    "supports_client_reference_lookup": True,
    "concurrency_limit": 1,
    "motion_profiles": ["steady", "natural", "expressive"],
    "mock": True,
    "quality_evidence": False,
}


def seed_defaults(db: Session) -> None:
    workspace_id = get_settings().workspace_id
    if not db.scalar(select(Asset).where(Asset.id == "avatar_sample_v1")):
        db.add_all(
            [
                Asset(
                    id="avatar_sample_v1",
                    workspace_id=workspace_id,
                    kind="avatar",
                    name="NOVA 示例形象",
                    engine="mock",
                    status="ready",
                    source_name="licensed-synthetic-fixture",
                    content_type="image/svg+xml",
                    size_bytes=0,
                    metadata_json={"mock": True, "consent": "synthetic-fixture", "quality_evidence": False},
                ),
                Asset(
                    id="voice_sample_v1",
                    workspace_id=workspace_id,
                    kind="voice",
                    name="NOVA 示例声音",
                    engine="mock",
                    status="ready",
                    source_name="browser-speech-synthesis",
                    content_type="audio/mock",
                    size_bytes=0,
                    metadata_json={"mock": True, "consent": "synthetic-fixture", "quality_evidence": False},
                ),
            ]
        )

    deployments = [
        (
            "mock-realtime",
            "Mock 实时引擎",
            "realtime",
            {
                "modes": ["text", "microphone", "interrupt", "subtitles"],
                "mock": True,
                "quality_evidence": False,
            },
        ),
        ("mock-render", "Mock 成片引擎", "render", MOCK_RENDER_CAPABILITIES),
    ]
    for deployment_id, name, engine_kind, capabilities in deployments:
        if db.scalar(select(EngineDeployment).where(EngineDeployment.id == deployment_id)):
            continue
        revision_id = f"{deployment_id}-r1"
        deployment = EngineDeployment(
            id=deployment_id,
            workspace_id=workspace_id,
            name=name,
            engine_kind=engine_kind,
            target_kind="local_mock",
            current_revision_id=revision_id,
        )
        revision = DeploymentRevision(
            id=revision_id,
            deployment_id=deployment_id,
            revision=1,
            adapter_type="mock.v1",
            config_json={"deterministic": True},
            image_digest="builtin-dev",
            model_hash="not-a-model",
            capabilities_json=capabilities,
        )
        observation = DeploymentObservation(
            deployment_id=deployment_id,
            healthy=True,
            warm=True,
            latency_ms=5,
            details_json={"profile": "dev", "mock": True},
        )
        db.add_all([deployment, revision, observation])
    db.commit()
