"""Precision root-cause analyzer and diagnosis refiner for DevMemory.

Analyzes exception type, traceback, source snippet, and line context to produce
accurate, evidence-grounded probable causes and specific corrective fixes that directly
address the actual failure without altering intended business logic or inventing details.
"""

from __future__ import annotations

from pathlib import Path
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class RefinedDiagnosis:
    """Refined diagnosis payload containing ground-truth cause and targeted fixes."""
    is_refined: bool
    summary: str
    likely_cause: str
    suggested_fix: str
    suggested_steps: List[str]
    hypotheses: List[str]
    evidence: List[str]
    confidence: float


def _extract_target_code_line(
    source_snippet: Optional[str],
    line: Optional[int],
    stack_trace: Optional[str],
) -> Optional[str]:
    """Extract the specific code line responsible for the exception."""
    if source_snippet:
        lines = source_snippet.splitlines()
        for l in lines:
            # Check for snippet marker '>' e.g. ' >   3 |     return income / 0'
            m = re.match(r"^\s*>\s*\d+\s*\|\s*(.*)$", l)
            if m:
                return m.group(1).strip()
        # If no marker, and line number is known, attempt line index lookup
        if line and 1 <= line <= len(lines):
            return lines[line - 1].strip()
        if lines:
            # Check if snippet has raw lines without prefix
            clean_lines = [l.strip() for l in lines if l.strip() and not l.startswith("File ")]
            if clean_lines:
                return clean_lines[0]

    if stack_trace:
        # Search stack trace for the failing frame's code line
        st_lines = stack_trace.splitlines()
        for i, l in enumerate(st_lines):
            if re.match(r'^\s*File\s+"[^"]+",\s+line\s+\d+', l):
                if i + 1 < len(st_lines):
                    candidate = st_lines[i + 1].strip()
                    if not candidate.startswith("File ") and not re.match(r"^[A-Z][a-zA-Z0-9_]*Error:", candidate):
                        return candidate

    return None


def _extract_function_name(stack_trace: Optional[str]) -> Optional[str]:
    """Extract failing function name from stack trace if available."""
    if not stack_trace:
        return None
    matches = list(re.finditer(r'File\s+"[^"]+",\s+line\s+\d+,\s+in\s+([a-zA-Z0-9_<>]+)', stack_trace))
    if matches:
        fn = matches[-1].group(1)
        if fn != "<module>":
            return fn
    return None


def _collect_source_text(
    source_snippet: Optional[str],
    file_path: Optional[str],
) -> str:
    """Collect source code text from filesystem if accessible, otherwise extract from snippet."""
    if file_path:
        try:
            p = Path(file_path)
            if p.is_file() and p.stat().st_size <= 256 * 1024:
                content = p.read_text(encoding="utf-8", errors="replace")
                if content.strip():
                    return content
        except Exception:
            pass

    if source_snippet:
        cleaned_lines = []
        for l in source_snippet.splitlines():
            m = re.match(r"^\s*>?\s*\d+\s*\|\s*(.*)$", l)
            if m:
                cleaned_lines.append(m.group(1))
            else:
                cleaned_lines.append(l)
        return "\n".join(cleaned_lines)

    return ""


def _detect_language_mismatch(
    source_snippet: Optional[str],
    file_path: Optional[str],
    error_type: str,
    error_message: str,
    line: Optional[int],
    code_line: Optional[str],
    loc_str: str,
) -> Optional[RefinedDiagnosis]:
    """Detect when a file executed by Python appears to contain C/C++, Java, or Go source code."""
    source_text = _collect_source_text(source_snippet, file_path)
    if not source_text or not source_text.strip():
        return None

    # Derive filenames and stems safely
    fname = "The source file"
    stem = "source"
    if file_path:
        fname = file_path.replace("\\", "/").split("/")[-1]
        stem = Path(file_path).stem or "source"

    # Filter out pure Python comments for keyword checks,
    # but preserve preprocessor directives (which start with #include, #define, etc.)
    non_comment_lines = []
    for raw_l in source_text.splitlines():
        stripped = raw_l.strip()
        if stripped.startswith("#"):
            if re.match(r"^#(?:include|define|pragma|ifdef|ifndef|endif)\b", stripped):
                non_comment_lines.append(raw_l)
        else:
            non_comment_lines.append(raw_l)
    code_body = "\n".join(non_comment_lines)

    # -------------------------------------------------------------------------
    # 1. C / C++ Detection
    # -------------------------------------------------------------------------
    c_indicators: List[str] = []

    # Category A: Preprocessor
    if re.search(r"^\s*#include\s*[<\"].+?[>\"]", source_text, re.MULTILINE):
        c_indicators.append("`#include`")
    elif re.search(r"^\s*#define\s+[A-Za-z0-9_]+", source_text, re.MULTILINE):
        c_indicators.append("`#define`")

    # Category B: Main entry
    if re.search(r"\b(?:int|void)\s+main\s*\([^)]*\)", code_body):
        c_indicators.append("`int main()`")

    # Category C: C/C++ I/O & memory functions
    has_cout = bool(re.search(r"\b(?:std::cout|std::cin|std::endl|std::vector|std::string)\b|\bcout\s*<<|\bcin\s*>>", code_body))
    has_printf = bool(re.search(r"\b(?:printf|scanf|puts|malloc|free|fprintf)\s*\(", code_body))
    if has_cout:
        c_indicators.append("`std::cout`")
    elif has_printf:
        c_indicators.append("`printf()`")

    # Category D: Constructs (using namespace, type declarations ending with ;)
    if re.search(r"\busing\s+namespace\s+std\s*;", code_body):
        c_indicators.append("`using namespace std`")
    elif re.search(r"\b(?:int|float|double|char|void|size_t|bool)\s+[a-zA-Z0-9_*]+\s*(?:=\s*[^;]+)?\s*;", code_body):
        c_indicators.append("C-style variable declaration")

    if len(c_indicators) >= 2:
        is_cpp = has_cout or "using namespace std" in " ".join(c_indicators) or bool(re.search(r"\b(?:<iostream>|<vector>|<string>)\b", source_text))
        lang_name = "C++" if is_cpp else "C"
        ext = "cpp" if is_cpp else "c"
        compiler = "an installed C++ compiler such as G++ or Clang++" if is_cpp else "an installed C compiler such as GCC or Clang"
        target_name = f"{stem}.{ext}"
        constructs_str = " and ".join(c_indicators[:2])

        likely_cause = (
            f"`{fname}` appears to contain {lang_name} source code, but the command invokes the Python interpreter. "
            f"Python cannot parse {lang_name} constructs such as {constructs_str}."
        )
        summary = f"SyntaxError in {fname}: source appears to contain {lang_name} code rather than Python."
        steps = [
            f"If the intention is to execute {lang_name}, save the source as `{target_name}`, compile it using {compiler}, and run the resulting executable.",
            "If the intention is to run Python, rewrite the source using valid Python syntax.",
        ]
        evidence = [
            f"Observed error: {error_type}: {error_message}",
        ]
        if loc_str:
            evidence.append(f"Failing location: {loc_str.strip()}")
        if code_line:
            evidence.append(f"Failing code line: {code_line}")
        evidence.append(f"Detected {lang_name} indicators: {', '.join(c_indicators)}")

        return RefinedDiagnosis(
            is_refined=True,
            summary=summary,
            likely_cause=likely_cause,
            suggested_fix="; ".join(steps),
            suggested_steps=steps,
            hypotheses=[
                f"Source file language mismatch: {lang_name} source executed using Python interpreter",
                f"File was saved with .py extension instead of .{ext}",
            ],
            evidence=evidence,
            confidence=0.98,
        )

    # -------------------------------------------------------------------------
    # 2. Java Detection
    # -------------------------------------------------------------------------
    java_indicators: List[str] = []
    class_match = re.search(r"\b(?:public\s+)?class\s+([A-Za-z0-9_]+)\s*\{?", code_body)
    class_name = class_match.group(1) if class_match else None

    # Category A: Main entry
    if re.search(r"\bpublic\s+static\s+void\s+main\s*\(\s*String\s*(?:\[\s*\]|\.\.\.)\s*[a-zA-Z0-9_]+\s*\)", code_body):
        java_indicators.append("`public static void main`")

    # Category B: Class declaration
    if class_name:
        java_indicators.append("`public class`" if "public class" in code_body else "`class`")

    # Category C: Imports / packages
    if re.search(r"^\s*import\s+java\.[a-zA-Z0-9_.*]+\s*;", source_text, re.MULTILINE):
        java_indicators.append("`import java.*`")
    elif re.search(r"^\s*package\s+[a-zA-Z0-9_.]+\s*;", source_text, re.MULTILINE):
        java_indicators.append("`package`")

    # Category D: System.out.println
    if re.search(r"\bSystem\.(?:out|err)\.(?:println|print|printf)\s*\(", code_body):
        java_indicators.append("`System.out.println`")

    if len(java_indicators) >= 2:
        target_name = f"{class_name or stem}.java"
        constructs_str = " and ".join(java_indicators[:2])
        likely_cause = (
            f"`{fname}` appears to contain Java source code, but the command invokes the Python interpreter. "
            f"Python cannot parse Java constructs such as {constructs_str}."
        )
        summary = f"SyntaxError in {fname}: source appears to contain Java code rather than Python."
        steps = [
            f"If the intention is to execute Java, save the source as `{target_name}`, compile and run it using an installed Java Development Kit (e.g. `javac {target_name}` and `java {class_name or stem}`).",
            "If the intention is to run Python, rewrite the source using valid Python syntax.",
        ]
        evidence = [
            f"Observed error: {error_type}: {error_message}",
        ]
        if loc_str:
            evidence.append(f"Failing location: {loc_str.strip()}")
        if code_line:
            evidence.append(f"Failing code line: {code_line}")
        evidence.append(f"Detected Java indicators: {', '.join(java_indicators)}")

        return RefinedDiagnosis(
            is_refined=True,
            summary=summary,
            likely_cause=likely_cause,
            suggested_fix="; ".join(steps),
            suggested_steps=steps,
            hypotheses=[
                "Source file language mismatch: Java source executed using Python interpreter",
                "File was saved with .py extension instead of .java",
            ],
            evidence=evidence,
            confidence=0.98,
        )

    # -------------------------------------------------------------------------
    # 3. Go Detection
    # -------------------------------------------------------------------------
    go_indicators: List[str] = []

    # Category A: Package main
    if re.search(r"^\s*package\s+main\b", source_text, re.MULTILINE):
        go_indicators.append("`package main`")

    # Category B: Func main
    if re.search(r"\bfunc\s+main\s*\(\s*\)", code_body):
        go_indicators.append("`func main()`")

    # Category C: Go imports
    if re.search(r'^\s*import\s+(?:\(\s*)?"(?:fmt|os|strings|net/http|io|math)"', source_text, re.MULTILINE):
        go_indicators.append('`import "fmt"`')

    # Category D: Go fmt I/O
    if re.search(r"\bfmt\.(?:Println|Printf|Print|Sprintf)\s*\(", code_body):
        go_indicators.append("`fmt.Println`")

    if len(go_indicators) >= 2:
        target_name = f"{stem}.go"
        constructs_str = " and ".join(go_indicators[:2])
        likely_cause = (
            f"`{fname}` appears to contain Go source code, but the command invokes the Python interpreter. "
            f"Python cannot parse Go constructs such as {constructs_str}."
        )
        summary = f"SyntaxError in {fname}: source appears to contain Go code rather than Python."
        steps = [
            f"If the intention is to execute Go, save the source as `{target_name}` and run or build it using an installed Go toolchain (e.g. `go run {target_name}` or `go build`).",
            "If the intention is to run Python, rewrite the source using valid Python syntax.",
        ]
        evidence = [
            f"Observed error: {error_type}: {error_message}",
        ]
        if loc_str:
            evidence.append(f"Failing location: {loc_str.strip()}")
        if code_line:
            evidence.append(f"Failing code line: {code_line}")
        evidence.append(f"Detected Go indicators: {', '.join(go_indicators)}")

        return RefinedDiagnosis(
            is_refined=True,
            summary=summary,
            likely_cause=likely_cause,
            suggested_fix="; ".join(steps),
            suggested_steps=steps,
            hypotheses=[
                "Source file language mismatch: Go source executed using Python interpreter",
                "File was saved with .py extension instead of .go",
            ],
            evidence=evidence,
            confidence=0.98,
        )

    return None


def refine_root_cause_diagnosis(
    error_type: str,
    error_message: str,
    source_snippet: Optional[str] = None,
    stack_trace: Optional[str] = None,
    file_path: Optional[str] = None,
    line: Optional[int] = None,
    column: Optional[int] = None,
    ai_summary: Optional[str] = None,
    ai_likely_cause: Optional[str] = None,
    ai_recommended_steps: Optional[List[str]] = None,
    ai_hypotheses: Optional[List[str]] = None,
    ai_evidence: Optional[List[str]] = None,
) -> RefinedDiagnosis:
    """Analyze the concrete error evidence and produce a strictly grounded diagnosis."""
    norm_type = (error_type or "").strip()
    norm_msg = (error_message or "").strip()
    code_line = _extract_target_code_line(source_snippet, line, stack_trace)
    func_name = _extract_function_name(stack_trace)

    loc_str = ""
    if file_path:
        fname = file_path.replace("\\", "/").split("/")[-1]
        loc_str = f" in {fname}" + (f":{line}" if line else "")
    if func_name:
        loc_str = f" in `{func_name}()`" + (f" ({loc_str.strip()})" if loc_str else "")

    # 1. ZeroDivisionError
    if "ZeroDivisionError" in norm_type or "division by zero" in norm_msg.lower():
        # Check if the code line contains division
        divisor_is_literal_zero = False
        divisor_var: Optional[str] = None
        dividend_expr: Optional[str] = None

        if code_line:
            # Match division or modulo: e.g. 'return income / 0' or 'a / b' or 'x // y'
            div_match = re.search(r"(\b[a-zA-Z0-9_().]+)\s*(/|//|%)\s*([a-zA-Z0-9_().]+)", code_line)
            if div_match:
                dividend_expr = div_match.group(1).strip()
                op = div_match.group(2)
                raw_divisor = div_match.group(3).strip()
                if raw_divisor in ("0", "0.0", "0x0"):
                    divisor_is_literal_zero = True
                else:
                    divisor_var = raw_divisor

        if divisor_is_literal_zero:
            fn_label = f"`{func_name}()`" if func_name else "The program"
            expr_desc = f"'{code_line}'" if code_line else "the expression"
            num_desc = f"'{dividend_expr}'" if dividend_expr else "the numerator"
            
            likely_cause = (
                f"{fn_label} divides {num_desc} by the literal value 0 in {expr_desc}. "
                f"Division by zero is undefined in Python and raises ZeroDivisionError."
            )
            summary = (
                f"Division by zero in {expr_desc}: attempted division by literal value 0{loc_str}."
            )
            steps = [
                "Replace the zero divisor with the intended valid, non-zero denominator.",
                "If the denominator is a variable or parameter, check that it is not zero before dividing.",
                "If a zero denominator is a valid possible input, handle that case explicitly instead of performing the division.",
            ]
        elif divisor_var:
            likely_cause = (
                f"The denominator '{divisor_var}' evaluated to 0 during division in '{code_line}'. "
                f"Division by zero is undefined in Python and raises ZeroDivisionError."
            )
            summary = f"ZeroDivisionError: denominator '{divisor_var}' evaluated to 0{loc_str}."
            steps = [
                f"Validate that '{divisor_var}' is non-zero before performing the division (e.g. add a guard check 'if {divisor_var} != 0:').",
                f"Provide an appropriate fallback, default value, or explicit error handling when '{divisor_var}' is zero.",
                f"Verify the input values or upstream calculation supplying '{divisor_var}'.",
            ]
        else:
            likely_cause = (
                f"The program attempted to divide a number by zero{loc_str}. "
                f"Python does not allow division by zero and raises ZeroDivisionError."
            )
            summary = f"Division by zero encountered{loc_str}."
            steps = [
                "Replace the zero divisor with the intended valid, non-zero denominator.",
                "Validate that the denominator is non-zero before performing the division.",
                "Handle zero inputs explicitly with a guard condition or exception handler.",
            ]

        # Context-dependent multiplication check:
        # ONLY recommend multiplication if the source code explicitly specifies a rate/percentage
        # calculation where multiplication was demonstrably intended and supported by comments/context.
        # Otherwise, DO NOT recommend changing the formula to multiplication.
        if (
            divisor_is_literal_zero
            and source_snippet
            and re.search(r"\bdef\s+[a-zA-Z0-9_]*tax\s*\([^)]*rate[^)]*\)", source_snippet)
        ):
            steps.insert(
                1,
                "If the intended operation is to calculate tax as a percentage or rate of income, use multiplication (e.g. 'return income * rate') instead of division.",
            )

        evidence = [
            f"Observed error: ZeroDivisionError: {norm_msg}",
        ]
        if code_line:
            evidence.append(f"Failing code line: {code_line}")
        if loc_str:
            evidence.append(f"Failing location: {loc_str.strip()}")

        hypotheses = [
            "Divisor was specified as literal 0" if divisor_is_literal_zero else "Divisor dynamically evaluated to zero at runtime",
            "Missing input validation or boundary guard for zero denominator",
        ]

        return RefinedDiagnosis(
            is_refined=True,
            summary=summary,
            likely_cause=likely_cause,
            suggested_fix="; ".join(steps),
            suggested_steps=steps,
            hypotheses=hypotheses,
            evidence=evidence,
            confidence=0.98,
        )

    # 2. NameError
    if "NameError" in norm_type or "is not defined" in norm_msg.lower():
        name_match = re.search(r"name '([^']+)' is not defined", norm_msg)
        var_name = name_match.group(1) if name_match else None
        target = f"'{var_name}'" if var_name else "The identifier"

        likely_cause = (
            f"The name {target} is referenced before it has been defined, assigned, or imported{loc_str}."
        )
        summary = f"NameError: {target} is referenced but not defined{loc_str}."
        steps = [
            f"Define or assign a value to {target} before referencing it.",
            f"Check for spelling errors or typos in {target}.",
            f"If {target} is intended to come from an imported module or package, add the necessary import statement.",
        ]
        evidence = [f"Observed error: NameError: {norm_msg}"]
        if code_line:
            evidence.append(f"Failing code line: {code_line}")
        if loc_str:
            evidence.append(f"Failing location: {loc_str.strip()}")

        hypotheses = [
            f"{target} was misspelled or not declared in the current scope",
            f"Missing import statement for {target}",
        ]

        return RefinedDiagnosis(
            is_refined=True,
            summary=summary,
            likely_cause=likely_cause,
            suggested_fix="; ".join(steps),
            suggested_steps=steps,
            hypotheses=hypotheses,
            evidence=evidence,
            confidence=0.95,
        )

    # 3. SyntaxError / IndentationError
    if "SyntaxError" in norm_type or "IndentationError" in norm_type:
        # Check for conservative, source-aware language mismatch (e.g. C/C++, Java, Go executed with Python)
        mismatch_diagnosis = _detect_language_mismatch(
            source_snippet=source_snippet,
            file_path=file_path,
            error_type=norm_type,
            error_message=norm_msg,
            line=line,
            code_line=code_line,
            loc_str=loc_str,
        )
        if mismatch_diagnosis:
            return mismatch_diagnosis

        likely_cause = (
            f"Invalid Python syntax near line {line or 'unknown'}{loc_str}: {norm_msg}."
        )
        summary = f"SyntaxError: {norm_msg}{loc_str}."
        steps = []
        if code_line:
            # Check for lowercase boolean or null
            if re.search(r"\b(true|false|null)\b", code_line):
                steps.append(
                    "Python keywords for boolean and null literals are capitalized: use 'True', 'False', or 'None'."
                )
            # Check for missing colon after def/if/for/while/class
            if re.match(r"^\s*(def|if|elif|else|for|while|class|try|except|finally|with)\b", code_line) and not code_line.endswith(":"):
                steps.append(
                    "Block statements ('def', 'if', 'for', 'class', etc.) must terminate with a colon ':'."
                )

        steps.extend([
            f"Inspect and correct the syntax at line {line or 1} so it complies with Python grammar.",
            "Verify matching pairs for all parentheses '()', brackets '[]', braces '{}', and quotes.",
        ])

        evidence = [f"Observed error: {norm_type}: {norm_msg}"]
        if code_line:
            evidence.append(f"Failing code line: {code_line}")

        return RefinedDiagnosis(
            is_refined=True,
            summary=summary,
            likely_cause=likely_cause,
            suggested_fix="; ".join(steps),
            suggested_steps=steps,
            hypotheses=["Syntax violation in source code grammar"],
            evidence=evidence,
            confidence=0.95,
        )

    # 4. TypeError
    if "TypeError" in norm_type:
        likely_cause = f"Type mismatch or invalid operation: {norm_msg}{loc_str}."
        summary = f"TypeError: {norm_msg}{loc_str}."
        steps = [
            "Verify that operands or function arguments match expected types.",
            "Add explicit type conversion (e.g. 'int()', 'str()', 'float()') where appropriate.",
            "Check for unexpected 'None' values before invoking methods or performing operations.",
        ]
        evidence = [f"Observed error: TypeError: {norm_msg}"]
        if code_line:
            evidence.append(f"Failing code line: {code_line}")

        return RefinedDiagnosis(
            is_refined=True,
            summary=summary,
            likely_cause=likely_cause,
            suggested_fix="; ".join(steps),
            suggested_steps=steps,
            hypotheses=["Incompatible types passed to operator or function"],
            evidence=evidence,
            confidence=0.90,
        )

    # 5. IndexError and KeyError
    if "IndexError" in norm_type:
        likely_cause = f"Attempted to access an index outside the valid range of the sequence{loc_str}: {norm_msg}."
        summary = f"IndexError: index out of bounds{loc_str}."
        steps = [
            "Check sequence length using 'len()' before accessing elements by index.",
            "Verify that the list or sequence is populated with expected elements.",
            "Use safe iteration (e.g. 'for item in items:') instead of manual index management.",
        ]
        evidence = [f"Observed error: IndexError: {norm_msg}"]
        if code_line:
            evidence.append(f"Failing code line: {code_line}")

        return RefinedDiagnosis(
            is_refined=True,
            summary=summary,
            likely_cause=likely_cause,
            suggested_fix="; ".join(steps),
            suggested_steps=steps,
            hypotheses=["Sequence index out of range bounds"],
            evidence=evidence,
            confidence=0.92,
        )

    if "KeyError" in norm_type:
        key_match = re.search(r"KeyError:\s*['\"]?([^'\"]+)['\"]?", norm_msg) or re.search(r"^['\"]?([^'\"]+)['\"]?$", norm_msg)
        key_name = key_match.group(1) if key_match else "the requested key"
        likely_cause = f"The dictionary key '{key_name}' was not found in the dictionary{loc_str}."
        summary = f"KeyError: key '{key_name}' not found{loc_str}."
        steps = [
            f"Verify that key '{key_name}' exists in the dictionary before accessing it (e.g. 'if \"{key_name}\" in d:').",
            f"Use 'dict.get(\"{key_name}\", default)' to provide a safe fallback value if the key is optional.",
            f"Check dictionary initialization to ensure key '{key_name}' is properly populated.",
        ]
        evidence = [f"Observed error: KeyError: {norm_msg}"]
        if code_line:
            evidence.append(f"Failing code line: {code_line}")

        return RefinedDiagnosis(
            is_refined=True,
            summary=summary,
            likely_cause=likely_cause,
            suggested_fix="; ".join(steps),
            suggested_steps=steps,
            hypotheses=[f"Key '{key_name}' was missing from dictionary"],
            evidence=evidence,
            confidence=0.92,
        )

    # If already provided by AI and sufficiently detailed:
    default_summary = ai_summary or f"Runtime error: {norm_type or 'CommandError'}"
    default_likely = ai_likely_cause or default_summary
    steps = ai_recommended_steps or ["Review the error output and recent codebase changes"]
    
    return RefinedDiagnosis(
        is_refined=False,
        summary=default_summary,
        likely_cause=default_likely,
        suggested_fix="; ".join(steps),
        suggested_steps=steps,
        hypotheses=ai_hypotheses or ["Execution failed"],
        evidence=ai_evidence or [f"Observed error: {norm_msg}"],
        confidence=0.70,
    )
