"""Tests for the curated troubleshooting knowledge base."""

import json
import pytest
from pathlib import Path

from ai_engine.knowledge import get_default_knowledge_base, load_knowledge_base
from ai_engine.schemas import KnowledgeBaseItem


def test_load_default_seed_knowledge():
    """Verify that all default seed knowledge entries validate against the schema."""
    items = get_default_knowledge_base()
    assert len(items) >= 12

    # Check for presence of key representative entries
    kb_ids = {item.kb_id for item in items}
    assert "kb_py_mod_not_found" in kb_ids
    assert "kb_py_attr_err" in kb_ids
    assert "kb_js_type_read_prop" in kb_ids
    assert "kb_js_type_map_not_func" in kb_ids
    assert "kb_node_econnrefused" in kb_ids
    assert "kb_net_eaddrinuse" in kb_ids

    for item in items:
        assert isinstance(item, KnowledgeBaseItem)
        assert len(item.kb_id) > 0
        assert len(item.title) > 0
        assert len(item.error_pattern) > 0
        assert len(item.explanation) > 0
        assert len(item.suggested_resolutions) > 0
        assert len(item.tags) > 0


def test_handling_malformed_json(tmp_path: Path):
    """Loading a malformed JSON file must raise a ValueError with a clear message."""
    bad_file = tmp_path / "bad.json"
    bad_file.write_text("{ this is not valid json : [", encoding="utf-8")

    with pytest.raises(ValueError, match="Malformed JSON"):
        load_knowledge_base(bad_file)


def test_handling_invalid_schema_entry(tmp_path: Path):
    """An entry missing required fields or having extra forbidden fields must raise ValueError."""
    invalid_file = tmp_path / "invalid_entry.json"
    data = [
        {
            "kb_id": "test_missing_pattern",
            "title": "Incomplete Entry",
            # error_pattern and explanation missing
        }
    ]
    invalid_file.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ValueError, match="Validation error in knowledge base entry"):
        load_knowledge_base(invalid_file)


def test_nonexistent_file_raises_not_found(tmp_path: Path):
    """Attempting to load a nonexistent file should raise FileNotFoundError."""
    missing = tmp_path / "nonexistent.json"
    with pytest.raises(FileNotFoundError):
        load_knowledge_base(missing)
