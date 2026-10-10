"""Deterministic error matching and relevance ranking for DevMemory.

Provides functions to:
1. Normalize error messages while preserving meaningful semantic distinctions.
2. Extract exception types and stack-frame metadata.
3. Compute stable error signatures for grouping recurring errors.
4. Calculate explainable similarity scores between current errors and candidates.
5. Rank candidate incidents or knowledge-base entries with human-readable explanations.
"""

import difflib
import hashlib
import os
import re
from typing import Any, Dict, List, Optional, Tuple


# Regex patterns for common exception/error types
EXCEPTION_TYPE_REGEX = re.compile(
    r"\b([A-Za-z_][A-Za-z0-9_]*(?:Error|Exception|Warning|Fault|Panic))\b|"
    r"\b(NullPointerException|IllegalStateException|IllegalArgumentException|"
    r"ArrayIndexOutOfBoundsException|ClassCastException)\b|"
    r"\b(ECONNREFUSED|EADDRINUSE|ENOENT|EACCES|EEXIST|ETIMEDOUT|ECONNRESET)\b|"
    r"\b(SIGSEGV|SIGABRT|SIGBUS)\b|"
    r"\b(panic: [^\n]+)\b",
    re.IGNORECASE,
)

# Regex patterns for transient/ephemeral details to normalize
HEX_ADDRESS_REGEX = re.compile(r"0x[0-9a-fA-F]{4,16}\b")
UUID_REGEX = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
TIMESTAMP_REGEX = re.compile(
    r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?\b"
)
PID_THREAD_REGEX = re.compile(r"\b(?:pid|process|thread|worker)\s*[:=]?\s*\d+\b", re.IGNORECASE)
FILE_LINE_IN_TEXT_REGEX = re.compile(r"\bline\s+\d+\b", re.IGNORECASE)
IP_PORT_REGEX = re.compile(
    r"\b(?:\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}|localhost|0\.0\.0\.0|::1)(?::\d+)?\b",
    re.IGNORECASE,
)


# Stack frame extraction patterns
PYTHON_FRAME_REGEX = re.compile(
    r'File\s+["\']([^"\']+)["\'],\s+line\s+(\d+)(?:,\s+in\s+([A-Za-z0-9_<>\.]+))?',
    re.IGNORECASE,
)
JS_FRAME_REGEX = re.compile(
    r"at\s+(?:([A-Za-z0-9_$.<>]+)\s+)?\(?(?:file:\/\/)?([^:)\n]+):(\d+)(?::(\d+))?\)?",
    re.IGNORECASE,
)


def extract_exception_type(error_message: str, stack_trace: Optional[str] = None) -> Optional[str]:
    """Extract primary exception or error classification name.
    
    Inspects error_message first, then falls back to stack_trace lines.
    Returns normalized exception name (e.g. 'TypeError', 'KeyError') or None.
    """
    if not error_message and not stack_trace:
        return None

    # Search in error message first
    if error_message:
        # Check for explicit 'ErrorType: ...' format
        prefix_match = re.search(r"^([A-Za-z_][A-Za-z0-9_]*(?:Error|Exception)):\s*", error_message.strip())
        if prefix_match:
            return prefix_match.group(1)

        # General regex search
        match = EXCEPTION_TYPE_REGEX.search(error_message)
        if match:
            # Return first non-None capture group
            for group in match.groups():
                if group:
                    return group.strip()

    # Search stack trace lines (especially last or first lines)
    if stack_trace:
        lines = [line.strip() for line in stack_trace.splitlines() if line.strip()]
        for line in reversed(lines):
            prefix_match = re.search(r"^([A-Za-z_][A-Za-z0-9_]*(?:Error|Exception)):\s*", line)
            if prefix_match:
                return prefix_match.group(1)
            match = EXCEPTION_TYPE_REGEX.search(line)
            if match:
                for group in match.groups():
                    if group:
                        return group.strip()

    return None


def normalize_error_message(error_message: str) -> str:
    """Normalize error text by replacing ephemeral tokens while preserving semantics.
    
    Replaces timestamps, GUIDs, memory addresses, and process IDs with stable tokens.
    Does NOT erase variable names, key names, or exception terms.
    """
    if not error_message:
        return ""

    text = error_message.strip()
    text = TIMESTAMP_REGEX.sub("<timestamp>", text)
    text = UUID_REGEX.sub("<uuid>", text)
    text = HEX_ADDRESS_REGEX.sub("<address>", text)
    text = PID_THREAD_REGEX.sub("<pid>", text)
    text = FILE_LINE_IN_TEXT_REGEX.sub("<line>", text)
    text = IP_PORT_REGEX.sub("<host>:<port>", text)


    # Collapse multiple whitespaces and trim
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_stack_frames(stack_trace: Optional[str]) -> List[Dict[str, str]]:
    """Parse stack frames into structured dictionaries of file basename and function.
    
    Returns list of dicts: [{'file': 'app.py', 'func': 'handle_request', 'line': '45'}, ...]
    """
    frames: List[Dict[str, str]] = []
    if not stack_trace:
        return frames

    for line in stack_trace.splitlines():
        line_clean = line.strip()

        # Check Python frame format
        py_match = PYTHON_FRAME_REGEX.search(line_clean)
        if py_match:
            full_path, line_num, func = py_match.groups()
            basename = os.path.basename(full_path.replace("\\", "/"))
            frames.append({
                "file": basename,
                "func": func or "<module>",
                "line": line_num,
            })
            continue

        # Check JS/TS frame format
        js_match = JS_FRAME_REGEX.search(line_clean)
        if js_match:
            func, full_path, line_num, _col = js_match.groups()
            basename = os.path.basename(full_path.replace("\\", "/"))
            frames.append({
                "file": basename,
                "func": func or "<anonymous>",
                "line": line_num,
            })

    return frames


def compute_error_signature(
    error_message: str,
    stack_trace: Optional[str] = None,
    command: Optional[str] = None,
) -> str:
    """Generate a stable, deterministic signature for grouping recurring errors.
    
    Combines normalized exception type, normalized error message, and top stack frame.
    Returns a deterministic SHA256 hex prefix (16 characters) with a readable prefix.
    """
    exc_type = extract_exception_type(error_message, stack_trace) or "UnknownError"
    norm_msg = normalize_error_message(error_message).lower()
    frames = extract_stack_frames(stack_trace)

    top_frame = ""
    if frames:
        top_frame = f"{frames[-1]['file']}:{frames[-1]['func']}"

    cmd_prefix = ""
    if command:
        cmd_tokens = command.strip().split()
        if cmd_tokens:
            cmd_prefix = os.path.basename(cmd_tokens[0])

    content = f"{exc_type}|{norm_msg}|{top_frame}|{cmd_prefix}"
    sig_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
    return f"sig:{exc_type}:{sig_hash}"


def _tokenize(text: str) -> set:
    """Tokenize text into lowercase alphanumeric words."""
    if not text:
        return set()
    return set(re.findall(r"[A-Za-z0-9_]+", text.lower()))


def _token_jaccard_similarity(text1: str, text2: str) -> float:
    """Compute Jaccard token overlap between two strings."""
    tokens1 = _tokenize(text1)
    tokens2 = _tokenize(text2)
    if not tokens1 and not tokens2:
        return 1.0
    if not tokens1 or not tokens2:
        return 0.0
    intersection = tokens1.intersection(tokens2)
    union = tokens1.union(tokens2)
    return len(intersection) / len(union)


def _sequence_similarity(text1: str, text2: str) -> float:
    """Compute string sequence ratio via difflib."""
    if not text1 and not text2:
        return 1.0
    if not text1 or not text2:
        return 0.0
    return difflib.SequenceMatcher(None, text1.lower(), text2.lower()).ratio()


def calculate_similarity(
    query_error: Dict[str, Any],
    candidate: Dict[str, Any],
) -> Tuple[float, str]:
    """Calculate an explainable similarity score between a query error and a candidate.
    
    Signals evaluated:
    - Exception Type Match (weight: 0.35)
    - Normalized Message Similarity (weight: 0.40)
    - Stack Frame Similarity (weight: 0.15)
    - Command/Environment Context (weight: 0.10)
    
    Returns:
        (score, explanation) where score is strictly within [0.0, 1.0].
    """
    q_msg = query_error.get("error_message", "") or ""
    q_stack = query_error.get("stack_trace", "") or ""
    q_cmd = query_error.get("command", "") or ""

    c_msg = candidate.get("error_message") or candidate.get("error_pattern", "") or ""
    c_stack = candidate.get("stack_trace", "") or ""
    c_cmd = candidate.get("command", "") or ""

    # Check for empty inputs
    if not q_msg.strip() and not c_msg.strip():
        return 0.0, "Both error messages are empty."

    # 1. Exception Type Signal
    q_type = extract_exception_type(q_msg, q_stack)
    c_type = extract_exception_type(c_msg, c_stack)

    type_match = False
    type_score = 0.0
    if q_type and c_type:
        if q_type.lower() == c_type.lower():
            type_match = True
            type_score = 1.0
        else:
            type_score = 0.0
    elif not q_type and not c_type:
        type_score = 0.5  # Neutral when neither has a standard exception name
    else:
        type_score = 0.2  # Partial penalty when one has an exception name and the other does not

    # 2. Normalized Message Similarity Signal
    q_norm = normalize_error_message(q_msg)
    c_norm = normalize_error_message(c_msg)
    jaccard_sim = _token_jaccard_similarity(q_norm, c_norm)
    seq_sim = _sequence_similarity(q_norm, c_norm)
    msg_score = (jaccard_sim * 0.6) + (seq_sim * 0.4)

    # 3. Stack Frame Signal
    q_frames = extract_stack_frames(q_stack)
    c_frames = extract_stack_frames(c_stack)
    frame_matches = 0
    stack_score = 0.0
    shared_frames_desc = ""

    if q_frames and c_frames:
        q_frame_set = {(f["file"], f["func"]) for f in q_frames}
        c_frame_set = {(f["file"], f["func"]) for f in c_frames}
        shared = q_frame_set.intersection(c_frame_set)
        frame_matches = len(shared)
        total_unique = len(q_frame_set.union(c_frame_set))
        stack_score = frame_matches / total_unique if total_unique > 0 else 0.0
        if shared:
            sample_shared = list(shared)[:2]
            shared_frames_desc = f" ({', '.join(f'{f[0]}:{f[1]}' for f in sample_shared)})"
    elif not q_frames and not c_frames:
        # If neither has stack traces, redistribute weight to message score
        stack_score = msg_score
    else:
        stack_score = 0.2  # One has stack trace, other does not

    # 4. Command Context Signal
    cmd_score = 0.5
    if q_cmd and c_cmd:
        cmd_score = _token_jaccard_similarity(q_cmd, c_cmd)

    # Composite weighted score
    w_type, w_msg, w_stack, w_cmd = 0.35, 0.40, 0.15, 0.10
    raw_score = (
        (type_score * w_type)
        + (msg_score * w_msg)
        + (stack_score * w_stack)
        + (cmd_score * w_cmd)
    )

    # Bound strictly between 0.0 and 1.0
    final_score = max(0.0, min(1.0, round(raw_score, 4)))

    # Construct explainable human-readable description
    reasons = []
    if type_match:
        reasons.append(f"Identical exception type '{q_type}'")
    elif q_type and c_type:
        reasons.append(f"Different exception types ('{q_type}' vs '{c_type}')")
    elif q_type:
        reasons.append(f"Query has '{q_type}' while candidate has no typed exception")

    reasons.append(f"Message similarity: {int(msg_score * 100)}%")

    if frame_matches > 0:
        reasons.append(f"Shared {frame_matches} call frame(s){shared_frames_desc}")
    elif q_frames and c_frames:
        reasons.append("Distinct call stack frames")

    explanation = "; ".join(reasons) + "."
    return final_score, explanation


def rank_candidates(
    query_error: Dict[str, Any],
    candidates: List[Dict[str, Any]],
    min_threshold: float = 0.15,
) -> List[Dict[str, Any]]:
    """Rank candidate incidents or knowledge entries against a query error.
    
    Filters out candidates below min_threshold and sorts descending by similarity_score.
    Each candidate returned includes 'similarity_score' and 'match_explanation'.
    """
    scored_candidates = []
    for cand in candidates:
        cand_copy = dict(cand)
        score, explanation = calculate_similarity(query_error, cand_copy)
        if score >= min_threshold:
            cand_copy["similarity_score"] = score
            cand_copy["match_explanation"] = explanation
            scored_candidates.append(cand_copy)

    # Sort descending by score
    scored_candidates.sort(key=lambda x: x["similarity_score"], reverse=True)
    return scored_candidates
