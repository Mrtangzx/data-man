import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


TEST_ROOT = Path(__file__).parent / ".runtime"
TEST_ROOT.mkdir(exist_ok=True)
os.environ["NOVA_DATABASE_URL"] = f"sqlite:///{(TEST_ROOT / 'nova-test.db').as_posix()}"
os.environ["NOVA_STORAGE_DIR"] = str(TEST_ROOT / "artifacts")
os.environ["NOVA_PROFILE"] = "dev"

from nova.db import Base, engine  # noqa: E402
from nova.main import app, dispatcher  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def clean_database():
    Base.metadata.drop_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture()
def client():
    dispatcher.stage_seconds = 0.01
    dispatcher.poll_seconds = 0.01
    with TestClient(app) as value:
        yield value
