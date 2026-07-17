from __future__ import annotations

import time
from hashlib import sha256
from typing import Any

from .base import Capabilities, ExecutionTargetAdapter, RemoteOperation


class MockExecutionTargetAdapter(ExecutionTargetAdapter):
    """Deterministic protocol mock. It proves orchestration behavior, not avatar quality."""

    def __init__(self) -> None:
        self._operations: dict[str, RemoteOperation] = {}

    def discover_capabilities(self) -> Capabilities:
        return Capabilities(
            inputs=("text", "avatar_version", "voice_enrollment"),
            outputs=("video/mp4",),
            max_duration_seconds=600,
            resolutions=("1280x720", "1920x1080"),
            supports_progress=True,
            supports_callback=False,
            supports_cancel=True,
            supports_idempotency=True,
            supports_client_reference_lookup=True,
            concurrency_limit=1,
            extra={"mock": True, "quality_evidence": False},
        )

    def validate_execution_plan(self, plan: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        if not plan.get("script_hash"):
            errors.append("script_hash is required")
        output = plan.get("output", {})
        resolution = f"{output.get('width')}x{output.get('height')}"
        if resolution not in self.discover_capabilities().resolutions:
            errors.append(f"resolution {resolution} is unsupported")
        motion_profile = output.get("motion_profile", "natural")
        if motion_profile not in {"steady", "natural", "expressive"}:
            errors.append(f"motion profile {motion_profile} is unsupported")
        return errors

    def submit(self, client_request_id: str, plan: dict[str, Any], callback_url: str | None = None) -> RemoteOperation:
        existing = next((value for value in self._operations.values() if value.client_request_id == client_request_id), None)
        if existing:
            return existing
        operation_id = "mock_" + sha256(client_request_id.encode()).hexdigest()[:16]
        operation = RemoteOperation(operation_id, "running", client_request_id, {"submitted_at": time.time()})
        self._operations[operation_id] = operation
        return operation

    def get_status(self, remote_operation_id: str) -> RemoteOperation:
        return self._operations[remote_operation_id]

    def cancel(self, remote_operation_id: str) -> RemoteOperation:
        current = self._operations[remote_operation_id]
        cancelled = RemoteOperation(current.id, "cancelled", current.client_request_id, current.metadata)
        self._operations[remote_operation_id] = cancelled
        return cancelled

    def fetch_result_manifest(self, remote_operation_id: str) -> dict[str, Any]:
        operation = self._operations[remote_operation_id]
        return {"operation_id": operation.id, "media_type": "video/mp4", "mock": True}

    def normalize_error(self, error: Exception) -> dict[str, Any]:
        return {"code": "NOVA-MOCK-5001", "message": str(error), "retryable": False}

    def health_check(self) -> dict[str, Any]:
        return {"healthy": True, "warm": True, "latency_ms": 5, "mock": True}
