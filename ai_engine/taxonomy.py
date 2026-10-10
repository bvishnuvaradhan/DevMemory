"""Conservative, language-aware exception taxonomy and compatibility evaluation.

Provides deterministic, static classification of exception relationships to:
1. Distinguish exact exception matches, subtype compatibility, normalized equivalences,
   and genuinely contradictory/incompatible exception types.
2. Recognize verified inheritance relationships (e.g. Python ModuleNotFoundError is a
   subtype of ImportError) within verified runtime context.
3. Preserve strict fail-closed contradiction penalties for genuinely clashing exception types.
4. Normalize runtime errors (e.g. Go nil-pointer panics) safely without executing code.
"""

from enum import Enum
import re
from typing import Any, Dict, FrozenSet, List, Optional, Set, Tuple


class ExceptionCompatibility(str, Enum):
    """Classification of the relationship between two exception types."""
    EXACT = "exact"                      # Identical normalized exception type
    SUBTYPE = "subtype"                  # Verified ancestor or descendant relationship
    EQUIVALENT = "equivalent"            # Standardized cross-syntax equivalence (e.g. Go panic variants)
    INCOMPATIBLE = "incompatible"        # Genuinely conflicting exception types
    UNKNOWN = "unknown"                  # One or both exception types cannot be identified


# Declarative, verified standard Python exception hierarchy (Child -> Parent set)
# Based strictly on Python standard library documentation (PEP 3151, PEP 352).
PYTHON_EXCEPTION_HIERARCHY: Dict[str, Set[str]] = {
    # Import errors (PEP 3151 / Python 3.6+)
    "ModuleNotFoundError": {"ImportError"},

    # Network / OS connection errors (PEP 3151)
    "ConnectionRefusedError": {"ConnectionError", "OSError"},
    "ConnectionResetError": {"ConnectionError", "OSError"},
    "ConnectionAbortedError": {"ConnectionError", "OSError"},

    # File / Filesystem errors (PEP 3151)
    "FileExistsError": {"OSError"},
    "IsADirectoryError": {"OSError"},
    "NotADirectoryError": {"OSError"},

    # Arithmetic errors
    "ZeroDivisionError": {"ArithmeticError"},
    "OverflowError": {"ArithmeticError"},
    "FloatingPointError": {"ArithmeticError"},

    # Lookup errors
    "IndexError": {"LookupError"},
    "KeyError": {"LookupError"},
}


def get_python_ancestors(exception_name: str) -> Set[str]:
    """Get all statically verified ancestors of a Python exception name."""
    ancestors: Set[str] = set()
    to_visit = [exception_name]
    visited: Set[str] = set()
    while to_visit:
        curr = to_visit.pop()
        if curr in visited:
            continue
        visited.add(curr)
        parents = PYTHON_EXCEPTION_HIERARCHY.get(curr, set())
        for p in parents:
            ancestors.add(p)
            to_visit.append(p)
    return ancestors


def is_python_subtype_compatible(type_a: str, type_b: str) -> bool:
    """Check if one Python exception is a verified ancestor or descendant of the other."""
    if type_a.lower() == type_b.lower():
        return True
    ancestors_a = get_python_ancestors(type_a)
    ancestors_b = get_python_ancestors(type_b)
    # Must have direct ancestor-descendant link; sibling relationships return False
    return type_b in ancestors_a or type_a in ancestors_b


def detect_runtime_language(
    command: Optional[str] = None,
    stack_trace: Optional[str] = None,
    error_message: Optional[str] = None,
) -> str:
    """Detect runtime language context: 'python', 'javascript', 'go', 'rust', or 'unknown'."""
    cmd = (command or "").lower()
    stack = (stack_trace or "").lower()
    err = (error_message or "").lower()

    # Python indicators
    if any(term in cmd for term in ("python", "pytest", "manage.py", "pip", "poetry", "uv", "celery")):
        return "python"
    if 'file "' in stack or "traceback (most recent call last):" in stack or ".py line" in err:
        return "python"
    if any(term in err for term in ("modulenotfounderror", "importerror", "psycopg2", "zerodivisionerror")):
        return "python"

    # JavaScript / TypeScript / Node indicators
    if any(term in cmd for term in ("node", "npm", "yarn", "pnpm", "npx", "jest", "vitest", "tsc")):
        return "javascript"
    if " at " in stack or ".js:" in stack or ".ts:" in stack or "err_require_esm" in err:
        return "javascript"

    # Go indicators
    if any(term in cmd for term in ("go test", "go run", "go build")):
        return "go"
    if "panic:" in err or ".go:" in stack or "goroutine " in stack:
        return "go"

    # Rust indicators
    if any(term in cmd for term in ("cargo test", "cargo build", "cargo run")):
        return "rust"
    if ".rs:" in stack or "error[e" in err:
        return "rust"

    return "unknown"


def normalize_exception_identifier(raw_type: Optional[str]) -> Optional[str]:
    """Normalize exception identifier by stripping module paths and standardizing panics."""
    if not raw_type:
        return None
    cleaned = raw_type.strip()

    # Go runtime panic normalization
    if cleaned.lower().startswith("panic:"):
        lower = cleaned.lower()
        if "nil pointer dereference" in lower:
            return "GoNilPointerPanic"
        if "index out of range" in lower:
            return "GoIndexOutOfRangePanic"
        if "slice bounds out of range" in lower:
            return "GoSliceBoundsPanic"
        return "GoRuntimePanic"

    # Strip package/module qualification (e.g. psycopg2.OperationalError -> OperationalError)
    if "." in cleaned:
        cleaned = cleaned.split(".")[-1].strip()

    return cleaned


def evaluate_exception_compatibility(
    query_type: Optional[str],
    candidate_type: Optional[str],
    query_command: Optional[str] = None,
    query_stack: Optional[str] = None,
    candidate_command: Optional[str] = None,
    candidate_stack: Optional[str] = None,
) -> ExceptionCompatibility:
    """Evaluate compatibility between two exception types.

    Returns:
    - EXACT: Identical normalized exception name in compatible or neutral context.
    - EQUIVALENT: Normalized runtime equivalent (e.g. GoNilPointerPanic).
    - SUBTYPE: Verified inheritance relationship (e.g. ModuleNotFoundError < ImportError).
    - INCOMPATIBLE: Genuinely conflicting exception types or conflicting language runtimes.
    - UNKNOWN: One or both types cannot be extracted.
    """
    if not query_type or not candidate_type:
        return ExceptionCompatibility.UNKNOWN

    norm_q = normalize_exception_identifier(query_type)
    norm_c = normalize_exception_identifier(candidate_type)

    if not norm_q or not norm_c:
        return ExceptionCompatibility.UNKNOWN

    # Check for runtime language discrepancy
    lang_q = detect_runtime_language(query_command, query_stack, query_type)
    lang_c = detect_runtime_language(candidate_command, candidate_stack, candidate_type)
    if lang_q != "unknown" and lang_c != "unknown" and lang_q != lang_c:
        # Cross-language runtime mismatch (e.g. Python TypeError vs Node TypeError)
        return ExceptionCompatibility.INCOMPATIBLE

    # Exact normalized match
    if norm_q.lower() == norm_c.lower():
        if norm_q.startswith("Go") and norm_q.endswith("Panic"):
            return ExceptionCompatibility.EQUIVALENT
        return ExceptionCompatibility.EXACT

    # Python verified hierarchy
    if (
        lang_q == "python"
        or lang_c == "python"
        or norm_q in PYTHON_EXCEPTION_HIERARCHY
        or norm_c in PYTHON_EXCEPTION_HIERARCHY
    ):
        if is_python_subtype_compatible(norm_q, norm_c):
            return ExceptionCompatibility.SUBTYPE

    return ExceptionCompatibility.INCOMPATIBLE
