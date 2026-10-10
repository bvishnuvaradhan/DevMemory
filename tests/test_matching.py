"""Tests for deterministic matching and relevance ranking in ai_engine.matching."""

import pytest

from ai_engine.matching import (
    calculate_similarity,
    compute_error_signature,
    extract_exception_type,
    extract_stack_frames,
    normalize_error_message,
    rank_candidates,
)


def test_identical_errors():
    """Identical errors should receive a very high score and clear explanation."""
    err1 = {
        "error_message": "TypeError: Cannot read properties of undefined (reading 'map')",
        "stack_trace": "at UserList (src/components/UserList.tsx:24:18)\n  at renderWithHooks (react-dom.js:150:10)",
        "command": "npm test",
    }
    err2 = {
        "error_message": "TypeError: Cannot read properties of undefined (reading 'map')",
        "stack_trace": "at UserList (src/components/UserList.tsx:24:18)\n  at renderWithHooks (react-dom.js:150:10)",
        "command": "npm test",
    }

    score, explanation = calculate_similarity(err1, err2)
    assert score >= 0.95
    assert "Identical exception type 'TypeError'" in explanation
    assert "Message similarity: 100%" in explanation


def test_same_exception_different_messages():
    """Same exception type with different message should yield moderate score."""
    err1 = {
        "error_message": "KeyError: 'user_id'",
        "stack_trace": "File 'auth.py', line 12, in get_user\n  return d['user_id']",
        "command": "pytest",
    }
    err2 = {
        "error_message": "KeyError: 'database_timeout_ms'",
        "stack_trace": "File 'config.py', line 99, in load_config\n  return c['database_timeout_ms']",
        "command": "pytest",
    }

    score, explanation = calculate_similarity(err1, err2)
    # Type matches (0.35), command matches (0.10), message has low token similarity
    assert 0.40 <= score <= 0.65
    assert "Identical exception type 'KeyError'" in explanation
    assert "Message similarity" in explanation


def test_different_exception_types():
    """Different exception types should yield lower score than matching types."""
    err1 = {
        "error_message": "ValueError: invalid literal for int() with base 10: 'abc'",
        "stack_trace": "File 'parse.py', line 5, in to_int\n  return int(x)",
        "command": "python app.py",
    }
    err2 = {
        "error_message": "ZeroDivisionError: division by zero",
        "stack_trace": "File 'calc.py', line 8, in div\n  return a / b",
        "command": "python app.py",
    }

    score, explanation = calculate_similarity(err1, err2)
    assert score < 0.35
    assert "Different exception types" in explanation


def test_similar_versus_unrelated_stack_traces():
    """Shared stack frames should increase similarity score compared to unrelated frames."""
    base_err = {
        "error_message": "IndexError: list index out of range",
        "stack_trace": "File 'engine.py', line 40, in process_batch\nFile 'worker.py', line 15, in run\n  return items[idx]",
        "command": "python run.py",
    }
    similar_stack_err = {
        "error_message": "IndexError: list index out of range",
        "stack_trace": "File 'engine.py', line 45, in process_batch\nFile 'worker.py', line 18, in run\n  return items[idx]",
        "command": "python run.py",
    }
    unrelated_stack_err = {
        "error_message": "IndexError: list index out of range",
        "stack_trace": "File 'db.py', line 100, in fetch_one\nFile 'driver.py', line 22, in cursor\n  return rows[0]",
        "command": "python run.py",
    }

    score_similar, expl_similar = calculate_similarity(base_err, similar_stack_err)
    score_unrelated, expl_unrelated = calculate_similarity(base_err, unrelated_stack_err)

    assert score_similar > score_unrelated
    assert "Shared" in expl_similar


def test_empty_and_unknown_error_formats():
    """Empty or unformatted errors should not cause exceptions or crashes."""
    empty_err = {"error_message": "", "stack_trace": "", "command": ""}
    cand_err = {"error_message": "", "stack_trace": "", "command": ""}

    score, explanation = calculate_similarity(empty_err, cand_err)
    assert score == 0.0
    assert "Both error messages are empty" in explanation

    # Malformed error without exception type
    freeform_1 = {"error_message": "build exited with status code 2"}
    freeform_2 = {"error_message": "compilation failed with code 2"}
    score, explanation = calculate_similarity(freeform_1, freeform_2)
    assert 0.0 <= score <= 1.0


def test_stable_error_signatures():
    """Equivalent errors with varying timestamps, memory addresses, or line numbers must have identical signatures."""
    err_a = "TypeError: object at 0x7fff5fbff8a0 has no attribute 'name' at 2026-10-10T12:00:00Z"
    err_b = "TypeError: object at 0x10293847 has no attribute 'name' at 2026-10-10T14:30:15Z"
    stack = "File 'user.py', line 10, in get_name\n  return user.name"

    sig_a = compute_error_signature(err_a, stack, "python main.py")
    sig_b = compute_error_signature(err_b, stack, "python main.py")

    assert sig_a == sig_b
    assert sig_a.startswith("sig:TypeError:")


def test_rank_candidates():
    """rank_candidates should rank matches in descending order and filter below threshold."""
    query = {
        "error_message": "ModuleNotFoundError: No module named 'requests'",
        "command": "python script.py",
    }
    candidates = [
        {
            "id": "c1",
            "error_pattern": "SyntaxError: invalid syntax",
            "command": "python other.py",
        },
        {
            "id": "c2",
            "error_pattern": "ModuleNotFoundError: No module named 'requests'",
            "command": "python script.py",
        },
        {
            "id": "c3",
            "error_pattern": "ModuleNotFoundError: No module named 'numpy'",
            "command": "python script.py",
        },
    ]

    ranked = rank_candidates(query, candidates, min_threshold=0.1)
    assert len(ranked) >= 2
    # Best match must be c2 (exact match)
    assert ranked[0]["id"] == "c2"
    # Second best should be c3 (same exception, partially same message)
    assert ranked[1]["id"] == "c3"
    assert ranked[0]["similarity_score"] > ranked[1]["similarity_score"]
    assert "match_explanation" in ranked[0]
