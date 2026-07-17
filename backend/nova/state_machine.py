from .errors import InvalidTransitionError


JOB_TRANSITIONS: dict[str, set[str]] = {
    "queued": {"running", "cancelled", "failed"},
    "running": {"reconciling", "succeeded", "failed", "cancelled", "needs_attention"},
    "reconciling": {"running", "queued", "failed", "cancelled", "needs_attention"},
    "succeeded": set(),
    "failed": set(),
    "cancelled": set(),
    "needs_attention": {"reconciling", "cancelled"},
}

ATTEMPT_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"leased", "cancelled"},
    "leased": {"submitting", "running", "reconciling", "cancel_requested", "failed"},
    "submitting": {"running", "reconciling", "cancel_requested", "failed"},
    "running": {"reconciling", "cancel_requested", "succeeded", "failed"},
    "reconciling": {"running", "failed", "cancel_requested", "detached"},
    "cancel_requested": {"cancelled", "detached", "failed"},
    "succeeded": set(),
    "failed": set(),
    "cancelled": set(),
    "detached": set(),
}


def validate_transition(current: str, target: str, transitions: dict[str, set[str]]) -> None:
    if target not in transitions.get(current, set()):
        raise InvalidTransitionError(current, target)


def transition_job(current: str, target: str) -> str:
    validate_transition(current, target, JOB_TRANSITIONS)
    return target


def transition_attempt(current: str, target: str) -> str:
    validate_transition(current, target, ATTEMPT_TRANSITIONS)
    return target

