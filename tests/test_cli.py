import json
import os
import sys
import time
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from devmemory import __version__
from devmemory.cli.main import (
    CONFIG_DIR_NAME,
    CONFIG_FILE_NAME,
    CONFIG_VERSION,
    DEFAULT_BACKEND_URL,
    app,
)
from devmemory.runner import CommandRunner, ExecutionResult

runner = CliRunner()


def test_cli_help():
    """Verify that `devmemory --help` exits 0 and prints usage info."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "AI-powered developer troubleshooting" in result.output
    assert "init" in result.output
    assert "run" in result.output


def test_cli_version():
    """Verify that `devmemory --version` prints the version and exits 0."""
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert f"DevMemory version {__version__}" in result.output


def test_init_successful(tmp_path: Path):
    """Verify successful initialization creates .devmemory/config.json with correct fields."""
    with patch("pathlib.Path.cwd", return_value=tmp_path):
        result = runner.invoke(app, ["init"])
        assert result.exit_code == 0
        assert "Initialized DevMemory project successfully" in result.output

        config_file = tmp_path / CONFIG_DIR_NAME / CONFIG_FILE_NAME
        assert config_file.exists()

        data = json.loads(config_file.read_text(encoding="utf-8"))
        assert data["config_version"] == CONFIG_VERSION
        assert data["project_name"] == tmp_path.name
        assert data["project_root"] == str(tmp_path)
        assert data["backend_url"] == DEFAULT_BACKEND_URL
        assert "created_at" in data
        parsed_uuid = uuid.UUID(data["project_id"])
        assert str(parsed_uuid) == data["project_id"]


def test_init_with_custom_name_and_backend(tmp_path: Path):
    """Verify `devmemory init --name custom --backend-url http://api.internal` stores custom values."""
    custom_name = "custom-service"
    custom_backend = "http://127.0.0.1:9090"
    with patch("pathlib.Path.cwd", return_value=tmp_path):
        result = runner.invoke(
            app, ["init", "--name", custom_name, "--backend-url", custom_backend]
        )
        assert result.exit_code == 0
        assert custom_name in result.output
        assert custom_backend in result.output

        config_file = tmp_path / CONFIG_DIR_NAME / CONFIG_FILE_NAME
        data = json.loads(config_file.read_text(encoding="utf-8"))
        assert data["project_name"] == custom_name
        assert data["backend_url"] == custom_backend


def test_init_repeated_preserves_existing_config(tmp_path: Path):
    """Verify repeated `devmemory init` does not overwrite project_id or created_at."""
    with patch("pathlib.Path.cwd", return_value=tmp_path):
        res1 = runner.invoke(app, ["init", "--name", "my-first-init"])
        assert res1.exit_code == 0
        config_file = tmp_path / CONFIG_DIR_NAME / CONFIG_FILE_NAME
        initial_data = json.loads(config_file.read_text(encoding="utf-8"))
        initial_id = initial_data["project_id"]
        initial_created = initial_data["created_at"]

        res2 = runner.invoke(app, ["init", "--name", "should-not-overwrite"])
        assert res2.exit_code == 0
        assert "Project already initialized" in res2.output
        assert initial_id in res2.output

        subsequent_data = json.loads(config_file.read_text(encoding="utf-8"))
        assert subsequent_data["project_id"] == initial_id
        assert subsequent_data["created_at"] == initial_created
        assert subsequent_data["project_name"] == "my-first-init"


def test_init_handles_invalid_json(tmp_path: Path):
    """Verify `devmemory init` fails gracefully with clear error if existing config is corrupt."""
    config_dir = tmp_path / CONFIG_DIR_NAME
    config_dir.mkdir(parents=True)
    bad_config = config_dir / CONFIG_FILE_NAME
    bad_config.write_text("{ broken json content ...", encoding="utf-8")

    with patch("pathlib.Path.cwd", return_value=tmp_path):
        result = runner.invoke(app, ["init"])
        assert result.exit_code == 1
        assert "Invalid existing configuration found" in result.output or "Error:" in result.output


def test_init_handles_non_dict_json(tmp_path: Path):
    """Verify `devmemory init` fails if existing config is a JSON array instead of an object."""
    config_dir = tmp_path / CONFIG_DIR_NAME
    config_dir.mkdir(parents=True)
    bad_config = config_dir / CONFIG_FILE_NAME
    bad_config.write_text('["not", "an", "object"]', encoding="utf-8")

    with patch("pathlib.Path.cwd", return_value=tmp_path):
        result = runner.invoke(app, ["init"])
        assert result.exit_code == 1
        assert "not a valid JSON object" in result.output


def test_init_fails_if_dir_is_a_file(tmp_path: Path):
    """Verify `devmemory init` handles collision when .devmemory is a file."""
    bad_dir = tmp_path / CONFIG_DIR_NAME
    bad_dir.write_text("i am a file, not a directory", encoding="utf-8")

    with patch("pathlib.Path.cwd", return_value=tmp_path):
        result = runner.invoke(app, ["init"])
        assert result.exit_code == 1
        assert "exists and is not a directory" in result.output


def test_init_handles_filesystem_write_error(tmp_path: Path):
    """Verify graceful handling when writing the configuration encounters an OS error."""
    with patch("pathlib.Path.cwd", return_value=tmp_path):
        with patch("devmemory.cli.main._write_config_atomic", side_effect=OSError("Permission denied")):
            result = runner.invoke(app, ["init"])
            assert result.exit_code == 1
            assert "Failed to write configuration" in result.output


# ---------------------------------------------------------------------------
# Phase B: Command Execution & Runner Tests
# ---------------------------------------------------------------------------

def test_run_empty_command_fails():
    """Verify `devmemory run` with no command outputs error and exits 2."""
    result = runner.invoke(app, ["run"])
    assert result.exit_code == 2
    assert "No command specified" in result.output


def test_runner_successful_python_command():
    """Verify CommandRunner executes a Python one-liner and returns exit code 0."""
    cr = CommandRunner()
    res = cr.run([sys.executable, "-c", "print('hello devmemory')"])
    assert res.exit_code == 0
    assert "hello devmemory" in res.stdout
    assert res.stderr == ""
    assert res.duration_ms > 0
    assert res.interrupted is False
    assert res.error_message is None


def test_runner_nonzero_exit_code():
    """Verify CommandRunner captures nonzero exit code and stderr."""
    cr = CommandRunner()
    res = cr.run([sys.executable, "-c", "import sys; sys.stderr.write('fatal boom\\n'); sys.exit(42)"])
    assert res.exit_code == 42
    assert "fatal boom" in res.stderr
    assert res.interrupted is False


def test_runner_captures_stdout_and_stderr_separately():
    """Verify stdout and stderr are separated accurately."""
    cr = CommandRunner()
    code = "import sys; sys.stdout.write('out text\\n'); sys.stderr.write('err text\\n')"
    res = cr.run([sys.executable, "-c", code])
    assert res.exit_code == 0
    assert "out text" in res.stdout
    assert "err text" in res.stderr


def test_runner_arguments_with_spaces():
    """Verify arguments with spaces are preserved without string splitting."""
    cr = CommandRunner()
    res = cr.run([sys.executable, "-c", "import sys; print(sys.argv[1])", "argument with spaces and 'quotes'"])
    assert res.exit_code == 0
    assert "argument with spaces and 'quotes'" in res.stdout


def test_runner_missing_executable():
    """Verify missing executable produces exit code 127 and helpful message."""
    cr = CommandRunner()
    res = cr.run(["non_existent_executable_123456789_xyz"])
    assert res.exit_code == 127
    assert res.error_message is not None
    assert "not found" in res.error_message.lower()


def test_runner_buffer_limit():
    """Verify output capture respects max_capture_bytes and doesn't exceed limit."""
    small_limit = 1024  # 1 KB
    cr = CommandRunner(max_capture_bytes=small_limit)
    # Output 10 KB
    code = "print('x' * 10000)"
    res = cr.run([sys.executable, "-c", code])
    assert res.exit_code == 0
    assert len(res.stdout) <= small_limit + 1024  # bounded to buffer chunk limit


def test_cli_run_success():
    """Verify `devmemory run -- python -c '...'` CLI command execution and summary."""
    result = runner.invoke(app, ["run", "--", sys.executable, "-c", "print('CLI RUN SUCCESS')"])
    assert result.exit_code == 0
    assert "CLI RUN SUCCESS" in result.output
    assert "DevMemory Run Summary:" in result.output
    assert "PASSED" in result.output


def test_cli_run_failure_propagates_exit_code():
    """Verify `devmemory run -- python -c 'sys.exit(7)'` propagates exit code 7."""
    result = runner.invoke(app, ["run", "--", sys.executable, "-c", "import sys; sys.exit(7)"])
    assert result.exit_code == 7
    assert "DevMemory Run Summary:" in result.output
    assert "FAILED" in result.output
    assert "Exit code: 7" in result.output


def test_cli_run_missing_executable():
    """Verify CLI handles missing executable cleanly."""
    result = runner.invoke(app, ["run", "--", "definitely_not_a_real_binary_abc_xyz"])
    assert result.exit_code == 127
    assert "Execution error" in result.output
    assert "not found" in result.output.lower()
