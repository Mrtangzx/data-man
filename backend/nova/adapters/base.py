from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Capabilities:
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    max_duration_seconds: int
    resolutions: tuple[str, ...]
    supports_progress: bool
    supports_callback: bool
    supports_cancel: bool
    supports_idempotency: bool
    supports_client_reference_lookup: bool
    concurrency_limit: int
    extra: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "inputs": self.inputs,
            "outputs": self.outputs,
            "max_duration_seconds": self.max_duration_seconds,
            "resolutions": self.resolutions,
            "supports_progress": self.supports_progress,
            "supports_callback": self.supports_callback,
            "supports_cancel": self.supports_cancel,
            "supports_idempotency": self.supports_idempotency,
            "supports_client_reference_lookup": self.supports_client_reference_lookup,
            "concurrency_limit": self.concurrency_limit,
            **self.extra,
        }


@dataclass(frozen=True)
class RemoteOperation:
    id: str
    state: str
    client_request_id: str
    metadata: dict[str, Any] = field(default_factory=dict)


class ExecutionTargetAdapter(ABC):
    @abstractmethod
    def discover_capabilities(self) -> Capabilities: ...

    @abstractmethod
    def validate_execution_plan(self, plan: dict[str, Any]) -> list[str]: ...

    @abstractmethod
    def submit(self, client_request_id: str, plan: dict[str, Any], callback_url: str | None = None) -> RemoteOperation: ...

    @abstractmethod
    def get_status(self, remote_operation_id: str) -> RemoteOperation: ...

    @abstractmethod
    def cancel(self, remote_operation_id: str) -> RemoteOperation: ...

    @abstractmethod
    def fetch_result_manifest(self, remote_operation_id: str) -> dict[str, Any]: ...

    @abstractmethod
    def normalize_error(self, error: Exception) -> dict[str, Any]: ...

    @abstractmethod
    def health_check(self) -> dict[str, Any]: ...

