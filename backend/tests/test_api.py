import time

import httpx

from nova.config import get_settings
from nova import main as main_module

def test_health_assets_and_deployments(client):
    health = client.get("/healthz")
    assert health.status_code == 200
    assert health.json()["profile"] == "dev"

    assets = client.get("/api/v1/assets").json()
    assert {item["id"] for item in assets} >= {"avatar_sample_v1", "voice_sample_v1"}

    deployments = client.get("/api/v1/engine-deployments").json()
    assert {item["id"] for item in deployments} >= {"mock-realtime", "mock-render"}
    probe = client.post("/api/v1/engine-deployments/mock-render/probe")
    assert probe.status_code == 200
    assert probe.json()["healthy"] is True

    summary = client.get("/api/v1/system/summary")
    assert summary.status_code == 200
    assert summary.json()["mock_mode"] is True

    compute = client.get("/api/v1/system/compute-plan")
    assert compute.status_code == 200
    assert compute.json()["provider"] == "ModelScope Notebook"
    assert compute.json()["gpu"] == "A10 24GB"
    assert compute.json()["scale_to_zero"] is True
    assert compute.json()["local_gpu_required"] is False
    assert compute.json()["estimated_gpu_cost_per_output_minute_usd"] == 0
    assert "社区免费" in compute.json()["free_quota_label"]


def test_asset_preflight_and_error_envelope(client):
    uploaded = client.post(
        "/api/v1/assets/preflight?kind=avatar",
        files={"file": ("portrait.png", b"not-a-real-image-but-valid-protocol-fixture", "image/png")},
    )
    assert uploaded.status_code == 201
    assert uploaded.json()["asset"]["kind"] == "avatar"
    assert uploaded.json()["overall"] == "warning"
    asset_id = uploaded.json()["asset"]["id"]
    content = client.get(f"/api/v1/assets/{asset_id}/content")
    assert content.status_code == 200
    assert content.headers["content-type"].startswith("image/png")

    assert client.get("/api/v1/assets/avatar_sample_v1/content").status_code == 404
    assert client.get("/api/v1/assets/missing/content").status_code == 404

    invalid_kind = client.post(
        "/api/v1/assets/preflight?kind=document",
        files={"file": ("notes.txt", b"notes", "text/plain")},
    )
    assert invalid_kind.status_code == 422
    assert invalid_kind.json()["code"] == "NOVA-ASSET-1101"
    assert invalid_kind.json()["request_id"].startswith("req_")

    empty = client.post(
        "/api/v1/assets/preflight?kind=voice",
        files={"file": ("empty.wav", b"", "audio/wav")},
    )
    assert empty.status_code == 422
    assert empty.json()["code"] == "NOVA-ASSET-1102"


def test_missing_resources_return_stable_errors(client):
    assert client.post("/api/v1/engine-deployments/missing/probe").status_code == 404
    assert client.get("/api/v1/video-jobs/missing").json()["code"] == "NOVA-API-1404"
    assert client.post("/api/v1/video-jobs/missing/cancel").status_code == 404
    assert client.get("/api/v1/artifacts/missing/download").status_code == 404


def test_realtime_turn_uses_real_language_model(monkeypatch, client):
    settings = get_settings()
    monkeypatch.setattr(settings, "llm_api_key", "test-key")
    monkeypatch.setattr(settings, "llm_model", "test-model")

    def fake_call(url, headers, payload):
        assert url.endswith("/chat/completions")
        assert headers["Authorization"] == "Bearer test-key"
        assert payload["messages"][-1] == {"role": "user", "content": "你好"}
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "你好！今天想聊点什么？"}}]},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(main_module, "_call_llm", fake_call)
    created = client.post("/api/v1/realtime/sessions", json={"deployment_id": "mock-realtime"})
    assert created.status_code == 201
    session_id = created.json()["session_id"]

    turn = client.post(f"/api/v1/realtime/sessions/{session_id}/turns", json={"text": "你好"})
    assert turn.status_code == 200
    assert turn.json()["assistant_text"] == "你好！今天想聊点什么？"

    refreshed = client.post(f"/api/v1/realtime/sessions/{session_id}/credentials/refresh")
    assert refreshed.status_code == 200
    assert refreshed.json()["credential_epoch"] == 2

    interrupted = client.post(f"/api/v1/realtime/sessions/{session_id}/interrupt")
    assert interrupted.json()["acknowledged"] is True
    assert interrupted.json()["state"] == "connected"

    closed = client.delete(f"/api/v1/realtime/sessions/{session_id}")
    assert closed.json()["state"] == "ended"
    after_close = client.post(f"/api/v1/realtime/sessions/{session_id}/turns", json={"text": "还在吗"})
    assert after_close.status_code == 409
    assert after_close.json()["code"] == "NOVA-RT-2409"
    refresh_after_close = client.post(f"/api/v1/realtime/sessions/{session_id}/credentials/refresh")
    assert refresh_after_close.status_code == 409

    assert client.post("/api/v1/realtime/sessions", json={"deployment_id": "missing"}).status_code == 404
    assert client.post("/api/v1/realtime/sessions/missing/interrupt").status_code == 404
    assert client.delete("/api/v1/realtime/sessions/missing").status_code == 404


def test_realtime_requires_llm_configuration(monkeypatch, client):
    monkeypatch.setattr(get_settings(), "llm_api_key", "")
    response = client.post("/api/v1/realtime/sessions", json={"deployment_id": "mock-realtime"})
    assert response.status_code == 503
    assert response.json()["code"] == "NOVA-RT-2501"
    assert "无法启动实时交流" in response.json()["message"]


def test_video_job_idempotency_and_artifact(client):
    payload = {
        "script": "这是一段任务协议测试文案",
        "avatar_version_id": "avatar_sample_v1",
        "voice_enrollment_id": "voice_sample_v1",
        "engine_deployment_id": "mock-render",
        "output": {"width": 1280, "height": 720, "fps": 25, "container": "mp4", "motion_profile": "natural"},
    }
    headers = {"Idempotency-Key": "test-idempotency-1"}
    created = client.post("/api/v1/video-jobs", json=payload, headers=headers)
    assert created.status_code == 202
    job_id = created.json()["id"]

    repeated = client.post("/api/v1/video-jobs", json=payload, headers=headers)
    assert repeated.status_code == 202
    assert repeated.json()["id"] == job_id

    changed = {**payload, "script": "同一个键但是不同的文案"}
    conflict = client.post("/api/v1/video-jobs", json=changed, headers=headers)
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "NOVA-JOB-3002"

    snapshot = None
    for _ in range(150):
        snapshot = client.get(f"/api/v1/video-jobs/{job_id}").json()
        if snapshot["state"] == "succeeded":
            break
        time.sleep(0.02)
    assert snapshot is not None
    assert snapshot["state"] == "succeeded"
    assert snapshot["output"]["motion_profile"] == "natural"
    assert snapshot["event_cursor"] > 0
    artifact = client.get(snapshot["download_url"])
    assert artifact.status_code == 200
    assert artifact.headers["content-type"].startswith("video/mp4")

    listed = client.get("/api/v1/video-jobs")
    assert listed.status_code == 200
    assert any(item["id"] == job_id for item in listed.json()["items"])

    with client.stream("GET", f"/api/v1/video-jobs/{job_id}/events?after=0") as events:
        body = "\n".join(events.iter_lines())
    assert "job.succeeded" in body
    assert "state_version" in body

    terminal_cancel = client.post(f"/api/v1/video-jobs/{job_id}/cancel")
    assert terminal_cancel.json()["state"] == "succeeded"


def test_video_job_requires_key_and_valid_capabilities(client):
    missing_key = client.post("/api/v1/video-jobs", json={"script": "缺少幂等键"})
    assert missing_key.status_code == 400
    assert missing_key.json()["code"] == "NOVA-JOB-3003"

    unsupported = client.post(
        "/api/v1/video-jobs",
        json={"script": "不支持的尺寸", "output": {"width": 640, "height": 360, "fps": 25, "container": "mp4"}},
        headers={"Idempotency-Key": "unsupported-resolution"},
    )
    assert unsupported.status_code == 422
    assert unsupported.json()["code"] == "NOVA-ENG-2001"


def test_video_cancel_is_acknowledged(client):
    created = client.post(
        "/api/v1/video-jobs",
        json={"script": "请取消这个测试任务"},
        headers={"Idempotency-Key": "cancel-test-1"},
    )
    job_id = created.json()["id"]
    cancelled = client.post(f"/api/v1/video-jobs/{job_id}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["desired_state"] == "cancel"
