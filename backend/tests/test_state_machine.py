import pytest

from nova.errors import InvalidTransitionError
from nova.state_machine import transition_attempt, transition_job


def test_job_happy_path():
    assert transition_job("queued", "running") == "running"
    assert transition_job("running", "succeeded") == "succeeded"


def test_terminal_job_cannot_restart():
    with pytest.raises(InvalidTransitionError):
        transition_job("succeeded", "queued")


def test_attempt_lease_and_run():
    assert transition_attempt("pending", "leased") == "leased"
    assert transition_attempt("leased", "running") == "running"
    assert transition_attempt("running", "succeeded") == "succeeded"
