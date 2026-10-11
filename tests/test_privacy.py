"""Tests for privacy and sanitization utilities in ai_engine.privacy."""

import pytest

from ai_engine.privacy import (
    is_cross_project_sharing_permitted,
    redact_secrets,
    sanitize_diagnosis_request,
    sanitize_file_path,
    sanitize_source_location,
    sanitize_source_snippet,
)
from ai_engine.schemas import DiagnosisRequest, SourceLocation, SourceSnippet


def test_api_key_and_bearer_token_redaction():
    """Synthetic API keys, Bearer tokens, and AWS keys must be redacted."""
    raw_text = (
        "Failed request with Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.e30.t-ID "
        "and header X-API-Key: gsk_sampleFakeTestKey1234567890abcdef123456 "
        "and AWS key AKIAIOSFODNN7EXAMPLE."
    )
    sanitized = redact_secrets(raw_text)

    assert "Bearer [REDACTED_TOKEN]" in sanitized
    assert "gsk_sampleFakeTestKey1234567890abcdef123456" not in sanitized
    assert "[REDACTED_API_KEY]" in sanitized or "[REDACTED_CREDENTIAL]" in sanitized
    assert "AKIAIOSFODNN7EXAMPLE" not in sanitized
    assert "[REDACTED_AWS_KEY]" in sanitized


def test_password_and_credential_assignment_redaction():
    """Passwords in connection strings and variable assignments must be redacted."""
    raw_url = "Connect failed to postgresql://dbuser:superSecretPassword123@db.internal:5432/main"
    sanitized_url = redact_secrets(raw_url)
    assert "superSecretPassword123" not in sanitized_url
    assert "postgresql://dbuser:[REDACTED_PASSWORD]@db.internal:5432/main" in sanitized_url

    raw_assign = "Config loaded: api_key='myPrivateSecretVal123' and password=\"anotherPass987\""
    sanitized_assign = redact_secrets(raw_assign)
    assert "myPrivateSecretVal123" not in sanitized_assign
    assert "anotherPass987" not in sanitized_assign
    assert "[REDACTED_CREDENTIAL]" in sanitized_assign


def test_path_sanitization():
    """Windows and Unix user home paths should be normalized to avoid exposing usernames."""
    win_path = r"C:\Users\johndoe\projects\DevMemory\backend\main.py"
    sanitized_win = sanitize_file_path(win_path)
    assert "johndoe" not in sanitized_win
    assert "~/projects/DevMemory/backend/main.py" in sanitized_win

    unix_path = "/home/developer/workspace/app/index.js"
    sanitized_unix = sanitize_file_path(unix_path)
    assert "developer" not in sanitized_unix
    assert "~/workspace/app/index.js" in sanitized_unix


def test_source_snippet_sanitization():
    """Snippets should have secrets redacted and paths normalized without mutating original."""
    original_snippet = SourceSnippet(
        file_path=r"C:\Users\alice\repo\secrets.py",
        start_line=1,
        end_line=3,
        content="auth_token = 'token_abcdef1234567890'\nprint('ready')",
    )

    sanitized = sanitize_source_snippet(original_snippet)

    # Sanitized check
    assert "alice" not in sanitized.file_path
    assert "token_abcdef1234567890" not in sanitized.content
    assert "[REDACTED_CREDENTIAL]" in sanitized.content or "[REDACTED_TOKEN]" in sanitized.content

    # Original must remain untouched
    assert "alice" in original_snippet.file_path
    assert "token_abcdef1234567890" in original_snippet.content


def test_ordinary_diagnostic_text_remains_intact():
    """Standard error messages without secrets must not be corrupted."""
    err = "TypeError: Cannot read properties of undefined (reading 'map')"
    sanitized = redact_secrets(err)
    assert sanitized == err

    code = "def add(a, b):\n    return a + b"
    sanitized_code = redact_secrets(code)
    assert sanitized_code == code


def test_repeated_sanitization_is_idempotent():
    """Running sanitization multiple times should produce consistent output."""
    raw = "Connect to http://admin:pass12345@localhost:8080 with token gsk_fake1234567890abcdef1234"
    pass1 = redact_secrets(raw)
    pass2 = redact_secrets(pass1)
    pass3 = redact_secrets(pass2)

    assert pass1 == pass2 == pass3


def test_sanitize_diagnosis_request_immutability():
    """sanitize_diagnosis_request returns a clean copy without mutating input."""
    raw_req = DiagnosisRequest(
        event_id="evt_privacy_01",
        project_id="proj_alpha",
        command="python run.py --token=gsk_secretKey9876543210123456",
        exit_code=1,
        error_message="AuthError: api_key='secret123456' rejected",
        stack_trace=r"File 'C:\Users\tester\run.py', line 12",
        locations=[
            SourceLocation(file_path=r"C:\Users\tester\run.py", line=12)
        ],
        source_snippets=[
            SourceSnippet(
                file_path=r"C:\Users\tester\run.py",
                start_line=10,
                end_line=15,
                content="api_key = 'secret123456'",
            )
        ],
    )

    sanitized_req = sanitize_diagnosis_request(raw_req)

    # Verify sanitized copy
    assert "secretKey9876543210123456" not in sanitized_req.command
    assert "secret123456" not in sanitized_req.error_message
    assert "tester" not in sanitized_req.locations[0].file_path
    assert "secret123456" not in sanitized_req.source_snippets[0].content

    # Verify original is intact
    assert "secretKey9876543210123456" in raw_req.command
    assert "secret123456" in raw_req.error_message
    assert "tester" in raw_req.locations[0].file_path


def test_cross_project_sharing_authorization():
    """Cross-project sharing must be governed strictly by server-side authorization."""
    # 1. Same project: always allowed
    assert is_cross_project_sharing_permitted("proj_1", "proj_1", candidate_is_public=False) is True
    assert is_cross_project_sharing_permitted("proj_1", "proj_1", candidate_is_public=True) is True

    # 2. Different project: blocked if candidate is private even if user opted in
    assert is_cross_project_sharing_permitted(
        requester_project_id="proj_1",
        candidate_project_id="proj_2",
        candidate_is_public=False,
        requester_prefers_cross_project=True,
    ) is False

    # 3. Different project: allowed if candidate is public AND requester prefers it
    assert is_cross_project_sharing_permitted(
        requester_project_id="proj_1",
        candidate_project_id="proj_2",
        candidate_is_public=True,
        requester_prefers_cross_project=True,
    ) is True

    # 4. Different project: blocked if requester opted out, even if candidate is public
    assert is_cross_project_sharing_permitted(
        requester_project_id="proj_1",
        candidate_project_id="proj_2",
        candidate_is_public=True,
        requester_prefers_cross_project=False,
    ) is False
