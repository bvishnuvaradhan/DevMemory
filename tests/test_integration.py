import json
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from devmemory.integration.client import (
    INGEST_ENDPOINT_PATH,
    DevMemoryClient,
    IngestionResult,
)
from devmemory.integration.models import (
    CLIENT_SCHEMA_VERSION,
    BackendDiagnosisResponse,
    IncidentErrorInfo,
    IncidentPayload,
    IncidentSourceSnippet,
    IncidentStackFrame,
    SimilarIncidentMatch,
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
# Incident Payload Model Tests
# ---------------------------------------------------------------------------

def test_incident_payload_serialization():
    """Verify IncidentPayload serializes cleanly to JSON dictionary."""
    snip = IncidentSourceSnippet(
        file_path="src/calc.py",
        target_line=5,
        target_col=2,
        start_line=1,
        end_line=10,
        lines=["def add(a, b):", "  return a + b"],
    )
    frame = IncidentStackFrame(
        raw_frame="File 'src/calc.py', line 5, in add",
        file_path="src/calc.py",
        line_number=5,
        snippet=snip,
    )
    err = IncidentErrorInfo(
        language="python",
        error_type="ZeroDivisionError",
        message="division by zero",
        frames=[frame],
        primary_frame=frame,
        has_diagnostic=True,
    )
    payload = IncidentPayload(
        event_id="evt-123",
        project_id="proj-456",
        project_name="test-project",
        command=["python", "calc.py"],
        cwd="/workspace",
        started_at="2026-10-10T12:00:00Z",
        ended_at="2026-10-10T12:00:01Z",
        duration_ms=105.5,
        exit_code=1,
        interrupted=False,
        stdout="",
        stderr="ZeroDivisionError: division by zero",
        error_info=err,
    )

    data = payload.to_dict()
    assert data["event_id"] == "evt-123"
    assert data["project_id"] == "proj-456"
    assert data["client_version"] == CLIENT_SCHEMA_VERSION
    assert data["error_info"]["error_type"] == "ZeroDivisionError"
    assert data["error_info"]["frames"][0]["snippet"]["file_path"] == "src/calc.py"

    # Must be 100% JSON dumpable
    json_str = json.dumps(data)
    assert "ZeroDivisionError" in json_str


# ---------------------------------------------------------------------------
# HTTP Client & Ingestion Tests
# ---------------------------------------------------------------------------

def test_client_submit_success():
    """Verify client handles a 200 OK response from backend with diagnosis."""
    client = DevMemoryClient(base_url="http://localhost:8000")
    payload = IncidentPayload(
        event_id="evt-abc",
        project_id="proj-xyz",
        project_name="demo-app",
        command=["python", "main.py"],
        cwd="/app",
        started_at="2026-10-10T12:00:00Z",
        ended_at="2026-10-10T12:00:01Z",
        duration_ms=50.0,
        exit_code=1,
        interrupted=False,
        stdout="",
        stderr="TypeError: invalid type",
    )

    mock_resp = MagicMock()
    mock_resp.getcode.return_value = 200
    mock_resp_data = {
        "status": "success",
        "probable_cause": "Null pointer passed to compute()",
        "hypotheses": ["Argument 'user' was None"],
        "suggested_steps": ["Add validation check: if not user: return"],
        "knowledge_base_match": "Python TypeError on NoneType attributes",
        "similar_incidents": [
            {
                "incident_id": "inc-999",
                "project_name": "auth-service",
                "similarity_score": 0.88,
                "summary": "NoneType user passed in auth handler",
                "verified_fix": "Added null check in middleware",
                "is_cross_project": True,
            }
        ],
    }
    mock_resp.read.return_value = json.dumps(mock_resp_data).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        res = client.submit_incident(payload)
        assert res.success is True
        assert res.is_offline is False
        assert res.status_code == 200
        assert res.diagnosis is not None
        assert res.diagnosis.probable_cause == "Null pointer passed to compute()"
        assert len(res.diagnosis.similar_incidents) == 1
        assert res.diagnosis.similar_incidents[0].is_cross_project is True
        assert res.diagnosis.similar_incidents[0].verified_fix == "Added null check in middleware"


def test_client_offline_fallback():
    """Verify client degrades gracefully to offline mode on connection refused."""
    client = DevMemoryClient(base_url="http://localhost:8000", max_retries=1, backoff_seconds=0.01)
    payload = IncidentPayload(
        event_id="evt-offline",
        project_id="proj-offline",
        project_name="offline-app",
        command=["python", "test.py"],
        cwd="/app",
        started_at="2026-10-10T12:00:00Z",
        ended_at="2026-10-10T12:00:01Z",
        duration_ms=10.0,
        exit_code=1,
        interrupted=False,
        stdout="",
        stderr="",
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
        project_name="bad-payload",
        command=["python"],
        cwd="/app",
        started_at="2026-10-10T12:00:00Z",
        ended_at="2026-10-10T12:00:01Z",
        duration_ms=10.0,
        exit_code=1,
        interrupted=False,
        stdout="",
        stderr="",
    )

    http_error = urllib.error.HTTPError(
        url="http://localhost:8000/api/runs/ingest",
        code=422,
        msg="Unprocessable Entity",
        hdrs={},
        fp=None,
    )

    with patch("urllib.request.urlopen", side_effect=http_error) as mock_call:
        res = client.submit_incident(payload)
        assert res.success is False
        assert res.status_code == 422
        assert mock_call.call_count == 1  # Exactly 1 call, no retries on 4xx
        assert "Client request error" in res.error_message


def test_client_retries_on_500_server_error():
    """Verify client retries on transient 500 Internal Server Error."""
    client = DevMemoryClient(base_url="http://localhost:8000", max_retries=2, backoff_seconds=0.01)
    payload = IncidentPayload(
        event_id="evt-500",
        project_id="proj-500",
        project_name="retry-app",
        command=["python"],
        cwd="/app",
        started_at="2026-10-10T12:00:00Z",
        ended_at="2026-10-10T12:00:01Z",
        duration_ms=10.0,
        exit_code=1,
        interrupted=False,
        stdout="",
        stderr="",
    )

    http_error = urllib.error.HTTPError(
        url="http://localhost:8000/api/runs/ingest",
        code=500,
        msg="Internal Server Error",
        hdrs={},
        fp=None,
    )

    with patch("urllib.request.urlopen", side_effect=http_error) as mock_call:
        res = client.submit_incident(payload)
        assert res.success is False
        assert res.status_code == 500
        assert mock_call.call_count == 3  # 1 initial + 2 retries
