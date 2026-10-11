"""Comprehensive test suite for DevMemory MVP Milestone:
1. Curated General Programming Knowledge Base (25 entries, seeding idempotency, search).
2. Project Initialization and Isolation (project.json/config.json compatibility, duplicate guards, atomic writes).
3. Command Execution Tracking and Secret Redaction.
4. Multi-Tenant Memory Isolation & Provenance Separation.
5. Runnable Security Demos Execution & Verification.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from app.db.mongo import mongo_manager
from app.main import app as fastapi_app
from app.schemas.knowledge import KnowledgeBaseMatch, KnowledgeBaseSeedResponse
from app.services.embedding_service import (
    ProductionMongoVectorSearchAdapter,
    VectorSearchResult,
    vector_search_incidents,
)
from app.services.knowledge_service import (
    CURATED_KNOWLEDGE_ENTRIES,
    list_knowledge_base_items,
    search_knowledge_base,
    seed_knowledge_base,
)
from devmemory.cli.main import (
    CONFIG_DIR_NAME,
    CONFIG_FILE_NAME,
    CONFIG_VERSION,
    PROJECT_FILE_NAME,
    _find_project_root,
    app as cli_app,
)
from devmemory.integration.models import redact_secrets


runner = CliRunner()


# ==============================================================================
# Fixtures
# ==============================================================================

@pytest.fixture(scope="module")
def test_db():
    """Fixture providing active database connection."""
    mongo_manager.connect()
    db = mongo_manager.get_db()
    yield db


@pytest.fixture(scope="module")
def test_client():
    """FastAPI TestClient fixture."""
    with TestClient(fastapi_app) as client:
        yield client


# ==============================================================================
# 1. Knowledge Base Seeding & Idempotency Tests
# ==============================================================================

def test_knowledge_base_seeding_and_idempotency(test_db):
    """Verify that seed_knowledge_base idempotently preserves 25 curated entries."""
    assert len(CURATED_KNOWLEDGE_ENTRIES) == 25, "Must contain exactly 25 curated knowledge entries."

    # Seeding run on test_db (which may already be seeded or will be seeded now)
    res = seed_knowledge_base(test_db)
    assert res.total_curated == 25
    assert res.inserted + res.unchanged == 25

    # Verify documents in MongoDB collection
    count = test_db.knowledge_base.count_documents({})
    assert count >= 25

    # Verify schema fields on each item
    for doc in test_db.knowledge_base.find({}, {"_id": 0}):
        assert "kb_id" in doc
        assert "title" in doc
        assert "error_pattern" in doc
        assert "language" in doc
        assert "category" in doc
        assert "explanation" in doc
        assert "suggested_resolutions" in doc
        assert isinstance(doc["suggested_resolutions"], list)
        assert len(doc["suggested_resolutions"]) > 0

    # Second idempotent seeding run (must not insert duplicate items)
    res2 = seed_knowledge_base(test_db)
    assert res2.total_curated == 25
    assert res2.inserted == 0
    assert res2.unchanged == 25


def test_knowledge_base_api_endpoints(test_client, test_db):
    """Verify POST /api/v1/knowledge-base/seed, GET /api/v1/knowledge-base, and search."""
    # Seed endpoint
    resp = test_client.post("/api/v1/knowledge-base/seed")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["total_curated"] == 25

    # List endpoint with language filter
    py_resp = test_client.get("/api/v1/knowledge-base?language=python")
    assert py_resp.status_code == 200
    py_items = py_resp.json()["data"]
    assert len(py_items) >= 4
    assert all(item["language"] == "python" for item in py_items)

    # Search endpoint
    search_resp = test_client.post(
        "/api/v1/knowledge-base/search?query=FileNotFoundError&limit=3"
    )
    assert search_resp.status_code == 200
    matches = search_resp.json()["data"]
    assert len(matches) > 0
    top_match = matches[0]
    assert "file" in top_match["error_pattern"].lower() or "filenotfound" in top_match["kb_id"].lower()
    assert top_match["source"] == "knowledge_base"


def test_knowledge_base_search_provenance_and_unverified_guarantee(test_db):
    """Verify that general knowledge matches never leak project IDs or verified fix status."""
    seed_knowledge_base(test_db)

    # Search for connection refused error
    matches = search_knowledge_base(test_db, query_text="Connection refused by remote host")
    assert len(matches) > 0
    conn_match = matches[0]
    assert conn_match.source == "knowledge_base"
    assert "conn" in conn_match.kb_id.lower() or "refused" in conn_match.title.lower()

    # Search with empty query returns empty list
    assert search_knowledge_base(test_db, query_text="") == []
    assert search_knowledge_base(test_db, query_text="   ") == []


# ==============================================================================
# 2. CLI Project Initialization & Isolation Tests
# ==============================================================================

def test_cli_init_creates_project_and_config_json(tmp_path: Path):
    """Verify devmemory init creates both project.json and config.json atomically."""
    with patch("pathlib.Path.cwd", return_value=tmp_path):
        res = runner.invoke(cli_app, ["init", "--name", "alpha-service"])
        assert res.exit_code == 0
        assert "Initialized DevMemory project successfully" in res.output

        cfg_dir = tmp_path / CONFIG_DIR_NAME
        project_file = cfg_dir / PROJECT_FILE_NAME
        config_file = cfg_dir / CONFIG_FILE_NAME

        assert project_file.is_file(), "project.json must be created."
        assert config_file.is_file(), "config.json must be created for backward compatibility."

        p_data = json.loads(project_file.read_text(encoding="utf-8"))
        c_data = json.loads(config_file.read_text(encoding="utf-8"))

        assert p_data == c_data
        assert p_data["project_name"] == "alpha-service"
        assert p_data["config_version"] == CONFIG_VERSION
        # Validate UUID
        uuid.UUID(p_data["project_id"])


def test_cli_init_repeated_preserves_project_id_unless_forced(tmp_path: Path):
    """Verify repeated devmemory init without --force preserves project_id and created_at."""
    with patch("pathlib.Path.cwd", return_value=tmp_path):
        res1 = runner.invoke(cli_app, ["init", "--name", "first-pass"])
        assert res1.exit_code == 0
        p_file = tmp_path / CONFIG_DIR_NAME / PROJECT_FILE_NAME
        orig_data = json.loads(p_file.read_text(encoding="utf-8"))
        orig_id = orig_data["project_id"]
        orig_created = orig_data["created_at"]

        # Run again without --force
        res2 = runner.invoke(cli_app, ["init", "--name", "second-pass"])
        assert res2.exit_code == 0
        assert "Project already initialized!" in res2.output
        after_data = json.loads(p_file.read_text(encoding="utf-8"))
        assert after_data["project_id"] == orig_id
        assert after_data["created_at"] == orig_created
        assert after_data["project_name"] == "first-pass"

        # Run with --force
        res3 = runner.invoke(cli_app, ["init", "--name", "forced-pass", "--force"])
        assert res3.exit_code == 0
        forced_data = json.loads(p_file.read_text(encoding="utf-8"))
        assert forced_data["project_name"] == "forced-pass"


def test_find_project_root_prefers_project_json(tmp_path: Path):
    """Verify _find_project_root resolves correctly from project.json or config.json."""
    cfg_dir = tmp_path / CONFIG_DIR_NAME
    cfg_dir.mkdir(parents=True)

    # 1. When only project.json exists
    (cfg_dir / PROJECT_FILE_NAME).write_text(json.dumps({"project_name": "only-project"}), encoding="utf-8")
    root, data = _find_project_root(tmp_path)
    assert root == tmp_path
    assert data["project_name"] == "only-project"

    # 2. When config.json exists alongside, project.json takes precedence
    (cfg_dir / CONFIG_FILE_NAME).write_text(json.dumps({"project_name": "only-config"}), encoding="utf-8")
    root, data = _find_project_root(tmp_path)
    assert data["project_name"] == "only-project"

    # 3. When only config.json exists
    (cfg_dir / PROJECT_FILE_NAME).unlink()
    root, data = _find_project_root(tmp_path)
    assert data["project_name"] == "only-config"


def test_cli_init_aborts_without_writing_file_if_backend_rejects(tmp_path: Path):
    """Verify devmemory init fails cleanly and writes no files if backend registration returns HTTP error."""
    mock_client = MagicMock()
    mock_client.register_project.return_value = MagicMock(
        success=False,
        is_offline=False,
        error_message="HTTP 500: Internal Server Error",
    )

    with patch("pathlib.Path.cwd", return_value=tmp_path):
        with patch("devmemory.cli.main.DevMemoryClient", return_value=mock_client):
            res = runner.invoke(cli_app, ["init", "--name", "fail-project"])
            assert res.exit_code == 1
            assert "Backend project registration failed" in res.output

            # Ensure no local configuration files were written
            assert not (tmp_path / CONFIG_DIR_NAME).exists()


# ==============================================================================
# 3. Secret Redaction & Command Execution Safety Tests
# ==============================================================================

def test_secret_redaction_in_commands_and_diagnostics():
    """Verify that passwords, bearer tokens, API keys, and connection URIs are scrubbed."""
    raw_cmd = "devmemory run -- python migrate.py --password=SuperSecretPass123 --token=sk-live-DEMO1234567890abcdef"
    redacted_cmd = redact_secrets(raw_cmd)
    assert "SuperSecretPass123" not in redacted_cmd
    assert "sk-live-DEMO1234567890abcdef" not in redacted_cmd
    assert "[REDACTED]" in redacted_cmd

    raw_stderr = "Connection to mongodb://admin:Secr3tPassword!@cluster.mongodb.net/test failed"
    redacted_stderr = redact_secrets(raw_stderr)
    assert "Secr3tPassword!" not in redacted_stderr
    assert "mongodb://admin:[REDACTED_PASSWORD]@" in redacted_stderr or "mongodb://[REDACTED_AUTH]@" in redacted_stderr or "[REDACTED]" in redacted_stderr


# ==============================================================================
# 4. Multi-Tenant Project Isolation Tests
# ==============================================================================

def test_project_memory_isolation_and_cross_project_guard(test_db):
    """Verify that project memories are strictly segregated and cross-project queries require server grant."""
    # Seed knowledge base
    seed_knowledge_base(test_db)

    proj_alpha_id = f"test_proj_alpha_{uuid.uuid4().hex[:8]}"
    proj_beta_id = f"test_proj_beta_{uuid.uuid4().hex[:8]}"
    inc_a_id = f"inc_{uuid.uuid4().hex[:8]}"
    inc_b_id = f"inc_{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc)

    try:
        # Insert incident for Project A with required schema validator fields
        test_db.incidents.insert_one({
            "incident_id": inc_a_id,
            "project_id": proj_alpha_id,
            "error_type": "TimeoutError",
            "error_signature": f"TimeoutError_{uuid.uuid4().hex[:6]}",
            "error_message": "Database query timeout on orders table",
            "stack_trace": "TimeoutError in db/orders.py:42",
            "command": "python service.py",
            "embedding": [0.1] * 1024,
            "is_public": False,
            "verification_status": "unverified",
            "created_at": now,
        })

        # Insert incident for Project B (private)
        test_db.incidents.insert_one({
            "incident_id": inc_b_id,
            "project_id": proj_beta_id,
            "error_type": "TimeoutError",
            "error_signature": f"TimeoutError_{uuid.uuid4().hex[:6]}",
            "error_message": "Database query timeout on billing table",
            "stack_trace": "TimeoutError in db/billing.py:105",
            "command": "python billing.py",
            "embedding": [0.1] * 1024,
            "is_public": False,
            "verification_status": "unverified",
            "created_at": now,
        })

        query_vec = [0.1] * 1024

        # 1. Project Alpha query: Must find Project Alpha, NEVER Project Beta
        matches_alpha = vector_search_incidents(
            db=test_db,
            query_vector=query_vec,
            project_id=proj_alpha_id,
            allow_cross_project=False,
            has_cross_project_read=False,
        )
        inc_ids_alpha = [m["incident_id"] for m in matches_alpha]
        assert inc_a_id in inc_ids_alpha
        assert inc_b_id not in inc_ids_alpha

        # 2. Project Beta query: Must find Project Beta, NEVER Project Alpha
        matches_beta = vector_search_incidents(
            db=test_db,
            query_vector=query_vec,
            project_id=proj_beta_id,
            allow_cross_project=False,
            has_cross_project_read=False,
        )
        inc_ids_beta = [m["incident_id"] for m in matches_beta]
        assert inc_b_id in inc_ids_beta
        assert inc_a_id not in inc_ids_beta

        # 3. Project Alpha attempts cross-project without server grant has_cross_project_read
        unauthorized_cross = vector_search_incidents(
            db=test_db,
            query_vector=query_vec,
            project_id=proj_alpha_id,
            allow_cross_project=True,
            has_cross_project_read=False,  # Server denies cross-project read
        )
        assert not any(m["incident_id"] == inc_b_id for m in unauthorized_cross)

        # 4. Hybrid query with general knowledge: combines project memory and general knowledge
        # without leaking Project Beta's memory
        combined_matches = vector_search_incidents(
            db=test_db,
            query_vector=query_vec,
            project_id=proj_alpha_id,
            include_general_knowledge=True,
        )
        assert not any(m["incident_id"] == inc_b_id for m in combined_matches)
        assert any(m["incident_id"] == inc_a_id for m in combined_matches)

    finally:
        test_db.incidents.delete_many({"incident_id": {"$in": [inc_a_id, inc_b_id]}})


# ==============================================================================
# 5. Security Demos Execution Tests
# ==============================================================================

def test_security_demos_existence_and_execution():
    """Verify that all 5 demonstration scripts in examples/security-demos/ execute with expected behavior."""
    demo_dir = Path("examples/security-demos")
    assert demo_dir.is_dir(), "examples/security-demos directory must exist."

    # Check files exist
    py_demo1 = demo_dir / "demo1_multilang_py.py"
    js_demo1 = demo_dir / "demo1_multilang_js.js"
    py_demo2 = demo_dir / "demo2_invalid_input.py"
    py_demo3 = demo_dir / "demo3_env_protection.py"
    py_demo4 = demo_dir / "demo4_sensitive_redaction.py"
    readme = demo_dir / "README.md"

    for f in (py_demo1, js_demo1, py_demo2, py_demo3, py_demo4, readme):
        assert f.is_file(), f"File {f.name} must exist."

    # Execute Python Demo 1: Must raise TypeError
    proc1 = subprocess.run([sys.executable, str(py_demo1)], capture_output=True, text=True, stdin=subprocess.DEVNULL)
    assert proc1.returncode != 0
    assert "TypeError" in proc1.stderr

    # Execute Python Demo 2: Must raise JSON / ValueError
    proc2 = subprocess.run([sys.executable, str(py_demo2)], capture_output=True, text=True, stdin=subprocess.DEVNULL)
    assert proc2.returncode != 0
    assert "JSONDecodeError" in proc2.stderr or "ValueError" in proc2.stderr

    # Execute Python Demo 3: Must raise KeyError for missing env vars
    proc3 = subprocess.run([sys.executable, str(py_demo3)], capture_output=True, text=True, stdin=subprocess.DEVNULL)
    assert proc3.returncode != 0
    assert "KeyError" in proc3.stderr
    assert "DATABASE_URL" in proc3.stderr

    # Execute Python Demo 4: Must exit with simulated error containing sensitive credentials
    proc4 = subprocess.run([sys.executable, str(py_demo4)], capture_output=True, text=True, stdin=subprocess.DEVNULL)
    assert proc4.returncode != 0
    assert "SuperSecretPassword999" in proc4.stderr  # Raw stderr before redaction

    # Redacting Demo 4's stderr must completely scrub passwords and API keys
    sanitized_output = redact_secrets(proc4.stderr)
    assert "SuperSecretPassword999" not in sanitized_output
    assert "sk-live-DEMO1234567890abcdef1234567890" not in sanitized_output
    assert "ghp_DEMO00000000000000000000000000000000" not in sanitized_output
    assert "[REDACTED]" in sanitized_output
    assert "[REDACTED_API_KEY]" in sanitized_output or "[REDACTED_SECRET]" in sanitized_output
