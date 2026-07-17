from dataclasses import dataclass, field


@dataclass
class NovaError(Exception):
    code: str
    message: str
    status_code: int = 400
    retryable: bool = False
    details: dict = field(default_factory=dict)

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


class InvalidTransitionError(NovaError):
    def __init__(self, current: str, target: str):
        super().__init__(
            code="NOVA-JOB-3001",
            message=f"Cannot transition from {current} to {target}.",
            status_code=409,
            details={"current": current, "target": target, "fix": "Reload the latest job snapshot."},
        )


class IdempotencyConflictError(NovaError):
    def __init__(self):
        super().__init__(
            code="NOVA-JOB-3002",
            message="This Idempotency-Key was already used with a different request.",
            status_code=409,
            details={"fix": "Reuse the original payload or generate a new Idempotency-Key."},
        )


class NotFoundError(NovaError):
    def __init__(self, resource: str):
        super().__init__(
            code="NOVA-API-1404",
            message=f"{resource} was not found.",
            status_code=404,
            details={"fix": "Reload the list and select an available resource."},
        )


class CapabilityMismatchError(NovaError):
    def __init__(self, reasons: list[str]):
        super().__init__(
            code="NOVA-ENG-2001",
            message="The selected assets or output are not supported by this deployment.",
            status_code=422,
            details={"reasons": reasons, "fix": "Use a compatible deployment or output specification."},
        )

