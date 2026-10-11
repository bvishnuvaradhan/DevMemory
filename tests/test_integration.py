import json
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from devmemory.integration.client import (
    INCIDENTS_ENDPOINT_PATH,
    PROJECTS_ENDPOINT_PATH,
    RUNS_ENDPOINT_PATH,
    DevMemoryClient,
    IngestionResult,
    ProjectRegistrationResult,
)
from devmemory.integration.models import (
    CLIENT_SCHEMA_VERSION,
    BackendEnvironmentInfo,
    BackendErrorContext,
    IncidentPayload,
    redact_secrets,
)


# ---------------------------------------------------------------------------
# Secret Redaction Tests
# ---------------------------------------------------------------------------

def test_redact_secrets_api_keys():
    """Verify that common API keys and tokens are redacted from output text."""
    raw_output = "Error connecting with api_key='sk-1234567890abcdef1234567890abcdef' to service"
    redacted = redact_secrets(raw_output)
    assert "sk-1234567890abcdef" not in redacted
    assert "[REDACTED]" in redacted or "[REDACTED_SECRET]" in redacted


def test_redact_secrets_github_tokens():
    """Verify GitHub personal access tokens are sanitized."""
    token = "ghp_123456789012345678901234567890123456"
    raw_output = f"Git auth failed using token {token}"
    redacted = redact_secrets(raw_output)
    assert token not in redacted
    assert "[REDACTED_SECRET]" in redacted


def test_redact_secrets_mongodb_uris():
    """Verify MongoDB credentials in URIs are redacted."""
    raw_output = "Connecting to mongodb://admin:SuperSecretPass123@cluster0.abc.mongodb.net/devmemory"
    redacted = redact_secrets(raw_output)
    assert "SuperSecretPass123" not in redacted
    assert "mongodb://[REDACTED_AUTH]@" in redacted


def test_redact_secrets_clean_text():
    """Verify text without secrets is preserved unmodified."""
    clean = "Traceback (most recent call last):\n  File 'app.py', line 10\nValueError: invalid literal"
    assert redact_secrets(clean) == clean


# ---------------------------------------------------------------------------
# Incident Payload Model Tests (RunCreate alignment)
# ---------------------------------------------------------------------------

def test_incident_payload_serialization_matches_backend_schema():
    """Verify IncidentPayload strictly serializes to backend RunCreate schema."""
    err_ctx = BackendErrorContext(
        error_type="ZeroDivisionError",
        message="division by zero",
        file_path="src/calc.py",
        line=5,
        column=1,
        snippet="return a / b",
    )
    env_info = BackendEnvironmentInfo(os="Windows", runtime_version="3.13.5")
    payload = IncidentPayload(
        event_id="evt-123",
        project_id="proj-456",
        project_name="test-project",
        command="python calc.py",
        cwd="/workspace",
        started_at="2026-10-10T12:00:00Z",
        ended_at="2026-10-10T12:00:01Z",
        duration_ms=105,
        exit_code=1,
        interrupted=False,
        stdout="",
        stderr="ZeroDivisionError: division by zero",
        environment=env_info,
        error_context=err_ctx,
    )

    data = payload.to_dict()
    assert data["event_id"] == "evt-123"
    assert data["project_id"] == "proj-456"
    assert isinstance(data["command"], str)
    assert data["command"] == "python calc.py"
    assert isinstance(data["duration_ms"], int)
    assert data["error_context"]["error_type"] == "ZeroDivisionError"
    assert data["error_context"]["file_path"] == "src/calc.py"
    assert data["error_context"]["line"] == 5

    # Must be 100% JSON dumpable
    json_str = json.dumps(data)
    assert "ZeroDivisionError" in json_str


# ---------------------------------------------------------------------------
# Project Registration Tests
# ---------------------------------------------------------------------------

def test_client_project_registration_success():
    """Verify registering a new project succeeds."""
    client = DevMemoryClient(base_url="http://localhost:8000")
    mock_resp = MagicMock()
    mock_resp.getcode.return_value = 201
    mock_resp.read.return_value = json.dumps({"success": True, "data": {"project_id": "proj-1"}}).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        res = client.register_project(project_id="proj-1", name="Test Service")
        assert res.success is True
        assert res.is_offline is False
        assert res.project_id == "proj-1"


def test_client_project_registration_conflict_treated_as_existing():
    """Verify HTTP 409 Conflict treats existing project as already registered."""
    client = DevMemoryClient(base_url="http://localhost:8000")
    http_error = urllib.error.HTTPError(
        url="http://localhost:8000/api/v1/projects",
        code=409,
        msg="Conflict",
        hdrs={},
        fp=None,
    )

    with patch("urllib.request.urlopen", side_effect=http_error):
        res = client.register_project(project_id="proj-existing", name="Existing Service")
        assert res.success is True
        assert res.status_code == 409
        assert res.project_id == "proj-existing"


# ---------------------------------------------------------------------------
# HTTP Client Ingestion Tests
# ---------------------------------------------------------------------------

def test_client_submit_success_extracts_incident_id():
    """Verify client handles a 201 Created ResponseEnvelope from backend."""
    client = DevMemoryClient(base_url="http://localhost:8000")
    payload = IncidentPayload(
        event_id="evt-abc",
        project_id="proj-xyz",
        project_name="demo-app",
        command="python main.py",
        cwd="/app",
        started_at="2026-10-10T12:00:00Z",
        ended_at="2026-10-10T12:00:01Z",
        duration_ms=50,
        exit_code=1,
        interrupted=False,
        stdout="",
        stderr="TypeError: invalid type",
    )

    mock_resp = MagicMock()
    mock_resp.getcode.return_value = 201
    mock_resp_data = {
        "success": True,
        "data": {
            "event_id": "evt-abc",
            "project_id": "proj-xyz",
            "command": "python main.py",
            "exit_code": 1,
            "status": "failure",
            "duration_ms": 50,
            "incident_id": "inc_evt-abc",
        },
        "error": None,
    }
    mock_resp.read.return_value = json.dumps(mock_resp_data).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        res = client.submit_incident(payload)
        assert res.success is True
        assert res.is_offline is False
        assert res.status_code == 201
        assert res.incident_id == "inc_evt-abc"


def test_client_offline_fallback():
    """Verify client degrades gracefully to offline mode on connection refused."""
    client = DevMemoryClient(base_url="http://localhost:8000", max_retries=1, backoff_seconds=0.01)
    payload = IncidentPayload(
        event_id="evt-offline",
        project_id="proj-offline",
        command="python test.py",
        duration_ms=10,
        exit_code=1,
    )

    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Connection refused")):
        res = client.submit_incident(payload)
        assert res.success is False
        assert res.is_offline is True
        assert "Connection failed" in res.error_message


def test_client_no_retry_on_client_4xx_error():
    """Verify client does not retry on 400 Bad Request or 422 Unprocessable Entity."""
    client = DevMemoryClient(base_url="http://localhost:8000", max_retries=3, backoff_seconds=0.01)
    payload = IncidentPayload(
        event_id="evt-400",
        project_id="proj-400",
        command="python",
        duration_ms=10,
        exit_code=1,
    )

    http_error = urllib.error.HTTPError(
        url="http://localhost:8000/api/v1/runs",
        code=422,
        msg="Unprocessable Entity",
        hdrs={},
        fp=None,
    )

    with patch("urllib.request.urlopen", side_effect=http_error) as mock_call:
        res = client.submit_incident(payload)
        assert res.success is False
        assert res.status_code == 422
        assert mock_call.call_count == 1
        assert "Client request error" in res.error_message


def test_client_retries_on_500_server_error():
    """Verify client retries on transient 500 Internal Server Error."""
    client = DevMemoryClient(base_url="http://localhost:8000", max_retries=2, backoff_seconds=0.01)
    payload = IncidentPayload(
        event_id="evt-500",
        project_id="proj-500",
        command="python",
        duration_ms=10,
        exit_code=1,
    )

    http_error = urllib.error.HTTPError(
        url="http://localhost:8000/api/v1/runs",
        code=500,
        msg="Internal Server Error",
        hdrs={},
        fp=None,
    )

    with patch("urllib.request.urlopen", side_effect=http_error) as mock_call:
        res = client.submit_incident(payload)
        assert res.success is False
        assert res.status_code == 500
        assert mock_call.call_count == 3
