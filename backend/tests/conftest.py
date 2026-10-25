import os
import shutil
import tempfile

import pytest
from fastapi.testclient import TestClient

os.environ["EMBEDDING_PROVIDER"] = "hashing"
os.environ["LLM_PROVIDER"] = "extractive"
os.environ["STT_PROVIDER"] = "none"
os.environ["TTS_PROVIDER"] = "none"
os.environ["ANONYMIZED_TELEMETRY"] = "False"
os.environ["SERVE_FRONTEND"] = "false"


@pytest.fixture(scope="session")
def client():
    directory = tempfile.mkdtemp(prefix="vesper-test-")
    os.environ["DATA_DIR"] = directory
    os.environ["AUTO_INGEST_EXAMPLES"] = "true"
    from app.main import create_app

    with TestClient(create_app()) as test_client:
        yield test_client
    shutil.rmtree(directory, ignore_errors=True)
