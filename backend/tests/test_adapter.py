from nova.adapters.base import ExecutionTargetAdapter
from nova.adapters.mock import MockExecutionTargetAdapter


def test_mock_adapter_fulfils_v1_contract():
    adapter: ExecutionTargetAdapter = MockExecutionTargetAdapter()
    capabilities = adapter.discover_capabilities()
    assert capabilities.supports_idempotency
    assert capabilities.supports_client_reference_lookup
    assert adapter.validate_execution_plan(
        {"script_hash": "abc", "output": {"width": 1280, "height": 720, "motion_profile": "natural"}}
    ) == []

    first = adapter.submit("client-1", {})
    duplicate = adapter.submit("client-1", {})
    assert first.id == duplicate.id
    assert adapter.get_status(first.id).state == "running"
    assert adapter.cancel(first.id).state == "cancelled"
    assert adapter.fetch_result_manifest(first.id)["media_type"] == "video/mp4"
    assert adapter.health_check()["healthy"] is True
    assert adapter.normalize_error(RuntimeError("boom"))["code"] == "NOVA-MOCK-5001"


def test_mock_adapter_rejects_incomplete_or_unsupported_plan():
    adapter = MockExecutionTargetAdapter()
    errors = adapter.validate_execution_plan({"output": {"width": 640, "height": 360}})
    assert "script_hash is required" in errors
    assert any("unsupported" in error for error in errors)
    motion_errors = adapter.validate_execution_plan(
        {"script_hash": "abc", "output": {"width": 1280, "height": 720, "motion_profile": "wild"}}
    )
    assert "motion profile wild is unsupported" in motion_errors
