import json
import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from devmemory.cli.main import app
from devmemory.diagnostics import analyze_error_output
from devmemory.runner import CommandRunner

runner = CliRunner()
REPO_ROOT = Path(__file__).resolve().parent.parent


def test_e2e_successful_fixture():
    """Verify running the success fixture executes cleanly and produces no error analysis."""
    fixture_path = REPO_ROOT / "fixtures" / "successful" / "verify.py"
    assert fixture_path.exists()

    result = runner.invoke(app, ["run", "--", sys.executable, str(fixture_path)])
    assert result.exit_code == 0
    assert "DevMemory Success Fixture: All systems operational" in result.output
    assert "Health check: PASS" in result.output
    assert "PASSED" in result.output
    assert "Source-Aware Error Analysis" not in result.output


def test_e2e_python_failing_fixture_matches_disk():
    """Verify running the Python failing fixture accurately extracts snippet matching disk."""
    fixture_path = REPO_ROOT / "fixtures" / "python_failing" / "app.py"
    assert fixture_path.exists()

    result = runner.invoke(app, ["run", "--", sys.executable, str(fixture_path)])
    assert result.exit_code == 1
    assert "ZeroDivisionError" in result.output
    assert "division by zero" in result.output
    assert "compute_ratio" in result.output
    assert "Code Context" in result.output
    # Line 8 must be highlighted
    assert "return numerator / denominator" in result.output


def test_e2e_javascript_failing_fixture_matches_disk():
    """Verify running the JavaScript failing fixture when node is available."""
    if not shutil.which("node"):
        pytest.skip("Node.js runtime not installed on host machine")

    fixture_path = REPO_ROOT / "fixtures" / "javascript_failing" / "index.js"
    assert fixture_path.exists()

    result = runner.invoke(app, ["run", "--", "node", str(fixture_path)])
    assert result.exit_code == 1
    assert "TypeError" in result.output
    assert "Cannot read properties of undefined" in result.output
    assert "getUserProfile" in result.output
    assert "return user.profile.settings.theme" in result.output


def test_e2e_successful_command_avoids_false_diagnosis():
    """Verify that commands that succeed with exit code 0 never produce an error report."""
    cr = CommandRunner()
    res = cr.run([sys.executable, "-c", "import sys; sys.exit(0)"])
    assert res.exit_code == 0
    diag = analyze_error_output(res.stdout, res.stderr)
    assert diag.has_diagnostic is False


def test_e2e_unregistered_project_initialization_flow(tmp_path: Path):
    """Verify full end-to-end flow in an initialized temporary workspace."""
    with patch("pathlib.Path.cwd", return_value=tmp_path):
        # 1. Initialize project
        init_res = runner.invoke(app, ["init", "--name", "e2e-demo-project"])
        assert init_res.exit_code == 0
        cfg_file = tmp_path / ".devmemory" / "config.json"
        assert cfg_file.exists()
        cfg_data = json.loads(cfg_file.read_text(encoding="utf-8"))
        assert cfg_data["project_name"] == "e2e-demo-project"

        # 2. Write a failing script inside the initialized project
        failing_script = tmp_path / "crash.py"
        failing_script.write_text("def explode():\n    raise ValueError('demo explosion')\nexplode()\n", encoding="utf-8")

        # 3. Run script via DevMemory CLI
        run_res = runner.invoke(app, ["run", "--", sys.executable, str(failing_script)])
        assert run_res.exit_code == 1
        assert "ValueError" in run_res.output
        assert "demo explosion" in run_res.output
        assert "explode()" in run_res.output
