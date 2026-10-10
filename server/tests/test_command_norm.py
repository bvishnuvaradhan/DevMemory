"""Unit tests for command normalization, sanitization, and signature generation."""

from app.utils.command_norm import compute_command_signature, sanitize_command


def test_sanitize_command_strips_passwords_and_tokens():
    raw_cmd = "mycli --password=SuperSecret123! --token ghp_123456789012345678901234567890123456"
    sanitized = sanitize_command(raw_cmd)
    assert "SuperSecret123!" not in sanitized
    assert "<REDACTED>" in sanitized or "<TOKEN>" in sanitized


def test_sanitize_command_strips_user_home():
    raw_cmd = r"python C:\Users\alice\projects\app\main.py"
    sanitized = sanitize_command(raw_cmd)
    assert "alice" not in sanitized
    assert "<USER_HOME>" in sanitized


def test_command_signature_normalizes_cross_platform_paths():
    win_cmd = r"pytest tests\unit\test_api.py"
    posix_cmd = "pytest tests/unit/test_api.py"

    sig_win, label_win = compute_command_signature(win_cmd)
    sig_posix, label_posix = compute_command_signature(posix_cmd)

    assert sig_win == sig_posix
    assert "tests/unit/test_api.py" in label_win
    assert "tests/unit/test_api.py" in label_posix


def test_command_signature_strips_exe_extension():
    cmd1 = "python.exe script.py"
    cmd2 = "python script.py"

    sig1, _ = compute_command_signature(cmd1)
    sig2, _ = compute_command_signature(cmd2)

    assert sig1 == sig2


def test_command_signature_distinguishes_materially_different_arguments():
    cmd_a = "pytest tests/test_fast.py"
    cmd_b = "pytest tests/test_slow.py"

    sig_a, _ = compute_command_signature(cmd_a)
    sig_b, _ = compute_command_signature(cmd_b)

    assert sig_a != sig_b
