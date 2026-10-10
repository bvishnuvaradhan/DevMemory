"""Unit tests for deterministic error signatures and privacy sanitization."""

import pytest
from app.utils.signature import compute_error_signature, sanitize_error_message


def test_equivalent_error_inputs_generate_identical_signature():
    """Scenario 1: Memory addresses, line numbers, and timestamps normalize to same signature."""
    msg1 = "TypeError: object at 0x7ffee4b2 line 42 at 2026-10-10 10:00:00"
    msg2 = "TypeError: object at 0x55aa12cf line 999 at 2026-10-10 14:30:25"

    sig1 = compute_error_signature("TypeError", msg1)
    sig2 = compute_error_signature("TypeError", msg2)

    assert sig1 == sig2
    assert sig1.startswith("sig_TypeError_")


def test_path_normalization_preserves_signature_across_environments():
    """Windows and POSIX file paths normalize so same error across machines matches."""
    msg_win = r"ModuleNotFoundError: No module named 'app' in C:\Users\developer\DevMemory\server\main.py"
    msg_posix = "ModuleNotFoundError: No module named 'app' in /home/developer/projects/DevMemory/server/main.py"

    sig_win = compute_error_signature("ModuleNotFoundError", msg_win)
    sig_posix = compute_error_signature("ModuleNotFoundError", msg_posix)

    assert sig_win == sig_posix


def test_different_error_types_remain_distinguishable():
    """Scenario 2: Different error types produce different signatures."""
    sig1 = compute_error_signature("TypeError", "division by zero")
    sig2 = compute_error_signature("ZeroDivisionError", "division by zero")

    assert sig1 != sig2
    assert "TypeError" in sig1
    assert "ZeroDivisionError" in sig2


def test_different_messages_remain_distinguishable():
    """Different error messages for same error type produce distinct signatures."""
    sig1 = compute_error_signature("ValueError", "invalid literal for int(): 'abc'")
    sig2 = compute_error_signature("ValueError", "math domain error")

    assert sig1 != sig2


def test_sanitize_error_message_redacts_private_info():
    """Sanitizer redacts user directories, bearer tokens, and IP addresses."""
    raw_msg = (
        r"Failed connecting to 192.168.1.50:8000 using Bearer secret_api_token_12345 "
        r"at file C:\Users\john_doe\projects\secret_app\main.py"
    )
    sanitized = sanitize_error_message(raw_msg)

    assert "john_doe" not in sanitized
    assert "secret_api_token_12345" not in sanitized
    assert "192.168.1.50" not in sanitized
    assert "<USER_HOME>" in sanitized or "<PATH>" in sanitized
    assert "<REDACTED>" in sanitized
    assert "<HOST:PORT>" in sanitized
