from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class SourceSnippet:
    """Represents an extracted context snippet from a local source file."""
    file_path: str
    target_line: int
    target_col: Optional[int]
    start_line: int
    end_line: int
    lines: List[str]
    is_safe: bool = True
    error: Optional[str] = None


@dataclass
class StackFrame:
    """Represents an individual frame in an execution stack trace."""
    raw_frame: str
    file_path: Optional[str] = None
    line_number: Optional[int] = None
    column_number: Optional[int] = None
    function_name: Optional[str] = None
    code_line: Optional[str] = None
    is_project_file: bool = False
    snippet: Optional[SourceSnippet] = None


@dataclass
class DiagnosticResult:
    """Structured diagnostic information extracted from command execution output."""
    language: str  # "python", "javascript", "unknown"
    error_type: str  # e.g., "TypeError", "SyntaxError", "ReferenceError"
    message: str
    frames: List[StackFrame] = field(default_factory=list)
    primary_frame: Optional[StackFrame] = None
    raw_traceback: str = ""
    confidence: float = 0.0  # 0.0 to 1.0 confidence score of the parser extraction
    has_diagnostic: bool = False
