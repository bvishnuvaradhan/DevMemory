# DevMemory — Member 3, Phase 6.8: Language-Aware Exception Taxonomy and Safe Contradiction Handling Report

**Author**: Member 3 — AI & Cross-Project Memory Lead  
**Branch**: `feature/member-3-ai-memory`  
**Phase**: Phase 6.8 — Language-Aware Exception Taxonomy and Safe Contradiction Handling  
**Date**: October 2026  
**Status**: Completed  
**Test Suite Status**: 134 passed, 3 skipped (100% offline regression pass rate)  
**Suite A Diagnostic Quality**: 56/56 scenarios passed (100.0% pass rate)  
**Suite B Benchmark Version**: v2.1.0 (30 corpus items, 36 evaluation scenarios)  

---

## 1. Executive Verdict

Phase 6.8 successfully implements a conservative, language-aware exception taxonomy layer ([`ai_engine/taxonomy.py`](file:///d:/projects/DevMemory/ai_engine/taxonomy.py)) and integrates it into DevMemory's hybrid ranking engine ([`ai_engine/hybrid.py`](file:///d:/projects/DevMemory/ai_engine/hybrid.py)) and multi-level memory retrieval architecture ([`ai_engine/retrieval.py`](file:///d:/projects/DevMemory/ai_engine/retrieval.py)).

### Key Accomplishments:
1. **Targeted Subtype Recognition**: Python's `ModuleNotFoundError` is now recognized as a verified subtype of `ImportError` within Python runtime contexts, safely lifting the contradiction suppression that previously wiped out valid resolutions with disjoint lexical wording.
2. **Runtime Panic Standardization**: Normalized Go runtime panic variants (`panic: runtime error: nil pointer dereference` vs `panic: runtime error: invalid memory address or nil pointer dereference`), achieving cross-version compatibility without altering error semantics.
3. **Subtype vs Exact Equality Calibration**: Explicitly distinguished subtype compatibility from exact exception equality by applying a calibrated 10% discount on vector contributions. Exact matches consistently outrank subtype matches.
4. **Conservative Sibling & Cross-Language Discrimination**:
   - Sibling exceptions sharing a common parent (e.g. `KeyError` vs `IndexError` under `LookupError`, or `FileNotFoundError` vs `PermissionError` under `OSError`) are strictly evaluated as `INCOMPATIBLE` because their root causes and resolutions differ.
   - Cross-language runtime mismatches (e.g. Node.js `TypeError` vs Python `TypeError`) are evaluated as `INCOMPATIBLE` to prevent cross-stack false positives.
5. **Retrieval Quality Impact**:
   - Mode 3 (Dense Semantic Mock Hybrid) **Recall@1 rose from 88.5% to 96.3%**; **Recall@3 reached 100.0%**; and **MRR rose from 0.9038 to 0.9815**.
   - Mode 2 (Deterministic Hash Hybrid) **MRR rose from 0.8718 to 0.9136**.
   - Safety guarantees were preserved with zero regressions: **Contradiction Rejection Rate = 100.0% (6/6)**, **False-Positive Rate = 0.0% (0/5)**, and **Project Isolation Rate = 100.0% (2/2)**.

---

## 2. Audit of Previous Contradiction Handling

In Phase 6.7, DevMemory evaluated exception compatibility via exact, lowercased string equality:
```python
# Previous implementation in ai_engine/hybrid.py & ai_engine/retrieval.py
if q_type and c_type and q_type.lower() != c_type.lower():
    has_contradictory_type = True
    fused = min(lexical_score * 0.7, 0.35)
```

### Specific Deficiencies Identified:
1. **False Contradictions on Verified Subtypes**:
   When diagnosing `ModuleNotFoundError: No module named 'yaml'`, a historical incident recorded with `ImportError: PyYAML package is not installed` was treated as an active contradiction (`modulenotfounderror != importerror`). Even when semantic embeddings detected 1.0 similarity, the contradiction guard capped the score to `0.0 * 0.7 = 0.0`, rendering the resolution unretrievable.
2. **False Contradictions on Go Panics**:
   `extract_exception_type` matched Go panics via `panic: [^\n]+`. Differences in file paths or runtime strings (e.g., `invalid memory address or nil pointer dereference at handler.go:88` vs `nil pointer dereference in handler.go`) caused string inequality, incorrectly penalizing identical Go runtime faults.
3. **Risks of Broad Normalization**:
   Relaxing string equality without taxonomy (e.g. via fuzzy string distance or broad category buckets) would incorrectly merge distinct failures:
   - `KeyError` vs `IndexError`: Both involve element lookup, but dictionary key creation vs list bounds checking require different fixes.
   - `FileNotFoundError` vs `PermissionError`: Both relate to file access, but file creation vs permission changes require different fixes.
   - `SyntaxError` vs `OperationalError`: Superficial lexical overlap in database configuration code must not mask syntax errors.

---

## 3. Implemented Conservative Exception Taxonomy Architecture

To resolve false contradictions safely, we created [`ai_engine/taxonomy.py`](file:///d:/projects/DevMemory/ai_engine/taxonomy.py) adhering to strict design constraints:
- **Zero Dynamic Code Execution**: No `eval()`, `importlib`, or dynamic class loading.
- **Pure Declarative Hierarchy**: Static mapping based strictly on Python PEP 3151 and PEP 352 standard library specifications.
- **Runtime Context Verification**: Subtype rules activate only when runtime context (command, stack trace, or file extensions) matches the language.

### 3.1 Taxonomy Classification Enum

```python
class ExceptionCompatibility(str, Enum):
    EXACT = "exact"              # Identical normalized exception name in compatible context
    SUBTYPE = "subtype"          # Verified ancestor or descendant relationship
    EQUIVALENT = "equivalent"    # Standardized cross-syntax equivalence (e.g. Go panics)
    INCOMPATIBLE = "incompatible"# Conflicting exception types or language runtimes
    UNKNOWN = "unknown"          # Missing or unextractable exception identifiers
```

### 3.2 Verified Standard Python Hierarchy

```python
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

    # Lookup errors (KeyError and IndexError are siblings under LookupError)
    "IndexError": {"LookupError"},
    "KeyError": {"LookupError"},
}
```

### 3.3 Strict Ancestor vs Sibling Rules

Under [`is_python_subtype_compatible`](file:///d:/projects/DevMemory/ai_engine/taxonomy.py):
- $\text{Compatibility}$ is `True` **if and only if** $A \in \text{Ancestors}(B)$ or $B \in \text{Ancestors}(A)$.
- Sibling types (where $\text{Ancestors}(A) \cap \text{Ancestors}(B) \ne \emptyset$, but neither is ancestor of the other) evaluate to **`False`**.
- Example: `ModuleNotFoundError` is an ancestor/descendant of `ImportError` $\to$ **`SUBTYPE`**.
- Example: `KeyError` and `IndexError` both inherit from `LookupError`, but neither inherits from the other $\to$ **`INCOMPATIBLE`**.
- Example: `FileNotFoundError` and `PermissionError` both inherit from `OSError`, but neither inherits from the other $\to$ **`INCOMPATIBLE`**.

### 3.4 Runtime Panic & Module Qualification Normalization

[`normalize_exception_identifier`](file:///d:/projects/DevMemory/ai_engine/taxonomy.py):
1. **Module Stripping**: Strips Python package qualification (e.g. `psycopg2.OperationalError` $\to$ `OperationalError`, `jwt.exceptions.ExpiredSignatureError` $\to$ `ExpiredSignatureError`).
2. **Go Panic Normalization**: Standardizes panic strings matching `panic: ... nil pointer dereference` into `GoNilPointerPanic`, and `panic: ... index out of range` into `GoIndexOutOfRangePanic`.
3. **Cross-Language Guard**: Evaluates command, stack trace, and error text via `detect_runtime_language()`. If query runtime is `javascript` (e.g. `npm test`) and candidate is `python` (e.g. `pytest`), evaluates as **`INCOMPATIBLE`** even if both share the string `TypeError`.

---

## 4. Integration with Hybrid Ranking & Retrieval

In [`ai_engine/hybrid.py`](file:///d:/projects/DevMemory/ai_engine/hybrid.py) and [`ai_engine/retrieval.py`](file:///d:/projects/DevMemory/ai_engine/retrieval.py):

### 4.1 Hybrid Scoring Calibration

```python
compat = evaluate_exception_compatibility(
    query_type=q_type,
    candidate_type=c_type,
    query_command=q_cmd,
    query_stack=q_stack,
    candidate_command=c_cmd,
    candidate_stack=c_stack,
)

if compat == ExceptionCompatibility.INCOMPATIBLE:
    # Contradiction guard active: strict 0.35 ceiling
    fused = min(lexical_score * 0.7, 0.35)
elif compat == ExceptionCompatibility.SUBTYPE:
    # Subtype compatibility: 10% calibration discount on vector contribution
    subtype_vector_score = vector_score * 0.90
    fused = 0.55 * lexical_score + 0.45 * subtype_vector_score + reliability_boost
else:
    # Exact or equivalent match: standard fusion
    fused = 0.55 * lexical_score + 0.45 * vector_score + reliability_boost
```

### 4.2 Distinguishing Subtype from Exact Equality

- **Exact Match** with `vector_score = 0.90`, `lexical = 0.0`, `verified = 0.05`:
  $$\text{fused} = 0.55(0.0) + 0.45(0.90) + 0.05 = \mathbf{0.455}$$
- **Subtype Match** with identical `vector_score = 0.90`, `lexical = 0.0`, `verified = 0.05`:
  $$\text{fused} = 0.55(0.0) + 0.45(0.90 \times 0.90) + 0.05 = \mathbf{0.4145}$$
- **Contradictory Match** with identical `vector_score = 0.90`, `lexical = 0.0`:
  $$\text{fused} = \min(0.0 \times 0.7, 0.35) = \mathbf{0.000}$$

Exact matches rank strictly higher than subtype matches, while subtype matches comfortably clear the 0.30 retrieval threshold.

---

## 5. Before-and-After Evaluation & Benchmark Results

### 5.1 Suite B Retrieval Benchmark (v2.0.0 vs v2.1.0)

| Metric | Mode 1 (Lexical) Before $\to$ After | Mode 2 (Deterministic) Before $\to$ After | Mode 3 (Dense Mock) Before $\to$ After | Mode 4 (Live OpenAI) |
| :--- | :---: | :---: | :---: | :---: |
| **Recall@1** | 84.6% $\to$ **85.2%** | 84.6% $\to$ **88.9%** | 88.5% $\to$ **96.3%** | SKIPPED |
| **Recall@3** | 84.6% $\to$ **85.2%** | 92.3% $\to$ **96.3%** | 92.3% $\to$ **100.0%** | SKIPPED |
| **Recall@5** | 84.6% $\to$ **85.2%** | 92.3% $\to$ **96.3%** | 92.3% $\to$ **100.0%** | SKIPPED |
| **Precision@1** | 84.6% $\to$ **85.2%** | 84.6% $\to$ **88.9%** | 88.5% $\to$ **96.3%** | SKIPPED |
| **Precision@3** | 28.2% $\to$ **28.4%** | 30.8% $\to$ **32.1%** | 30.8% $\to$ **33.3%** | SKIPPED |
| **MRR** | 0.8462 $\to$ **0.8519** | 0.8718 $\to$ **0.9136** | 0.9038 $\to$ **0.9815** | SKIPPED |
| **False-Positive Rate** | 0.0% $\to$ **0.0%** | 0.0% $\to$ **0.0%** | 0.0% $\to$ **0.0%** | SKIPPED |
| **Contradiction Rejection** | 100.0% $\to$ **100.0%** | 100.0% $\to$ **100.0%** | 100.0% $\to$ **100.0%** | SKIPPED |
| **Project Isolation Rate** | 100.0% $\to$ **100.0%** | 100.0% $\to$ **100.0%** | 100.0% $\to$ **100.0%** | SKIPPED |

*Note: In Mode 3, Precision@3 reaches 33.3%, which is the mathematical theoretical maximum for single-relevant-item queries ($\frac{1}{3} \approx 33.33\%$).*

### 5.2 Targeted Scenario Ranks Before vs After

| Scenario ID | Query vs Precedent Exception | Mode 2 Before $\to$ After | Mode 3 Before $\to$ After | Note |
| :--- | :--- | :---: | :---: | :--- |
| `bm_pos_04_py_yaml_missing` | `ModuleNotFoundError` vs `ImportError` | Not Retrieved $\to$ Not Retrieved | Not Retrieved $\to$ **Rank 1 (0.5408)** | Subtype compatibility allows dense cluster retrieval |
| `bm_pos_14_go_nil_dereference` | Variant Go nil-pointer panic strings | Not Retrieved $\to$ **Rank 1 (0.6828)** | Not Retrieved $\to$ **Rank 1 (0.7456)** | Go panic normalization unifies error semantics |
| `bm_compat_01_import_hierarchy` | `ImportError` vs `ImportError` / `ModuleNotFound` | N/A $\to$ **Rank 1 (0.5724)** | N/A $\to$ **Rank 1 (0.5724)** | New v2.1.0 scenario validating import hierarchy |
| `bm_clash_03_filenotfound_vs_permission` | `FileNotFoundError` vs `PermissionError` | Suppressed ($\le 0.35$) | Suppressed ($\le 0.35$) | Sibling OSErrors strictly rejected |
| `bm_clash_04_cross_lang_typeerror` | Node `TypeError` vs Python `TypeError` | Suppressed ($\le 0.35$) | Suppressed ($\le 0.35$) | Cross-language runtime mismatch strictly rejected |

---

## 6. Exact Metric Denominators Table (Benchmark v2.1.0)

| Denominator Variable | Definition | Count | Status |
| :--- | :--- | :---: | :--- |
| $N_{\text{pos}}$ | Queries with a local project target | **27** | Used for Recall@1/3/5, Precision@1/3, and MRR. Excludes negative and cross-project queries. |
| $N_{\text{neg}}$ | Unrelated / negative queries | **5** | Evaluates False-Positive Rate (FPR). |
| $N_{\text{clash}}$ | Queries evaluated against clashing candidates | **6** | Evaluates Contradiction Rejection Rate (CRR). |
| $N_{\text{cross}}$ | Cross-project isolation queries | **2** | Evaluates Project Isolation Rate (PIR). |
| $N_{\text{total}}$ | Total scenario count | **36** | $27\text{ pos} + 5\text{ neg} + 2\text{ cross} + 2\text{ clash-only} = 36$. |

---

## 7. Safety, Privacy, and Authorization Invariants

1. **Authorization Precedence**:
   Under [`test_cross_project_retrieval_with_missing_authorization`](file:///d:/projects/DevMemory/tests/test_exception_taxonomy.py), an exact exception match between a query and an external incident returns **0 matches** if `has_cross_project_read=False`. Compatibility never overrides authorization.
2. **Zero Private Leakage**:
   Under [`test_private_incidents_with_high_similarity`](file:///d:/projects/DevMemory/tests/test_exception_taxonomy.py), private external incidents (`is_public=False`) are never returned even with 1.0 exact exception match and 1.0 vector similarity.
3. **Verification Status Independence**:
   Under [`test_verified_fix_status_independence_from_compatibility`](file:///d:/projects/DevMemory/tests/test_exception_taxonomy.py), compatible exception types do not alter or fabricate `FixVerificationStatus.UNVERIFIED`.
4. **Contradiction Guard Integrity**:
   Contradiction Rejection Rate remains **100.0% (6/6)** across all executed retrieval modes.

---

## 8. Verification and Test Evidence

### 8.1 Full Automated Regression Suite
```
python -m pytest tests/ -v
======================= 134 passed, 3 skipped in 8.90s ========================
```

### 8.2 Suite A Diagnostic Runner
```
python -m ai_engine.evaluation.runner
[*] Running DevMemory AI Engine Evaluation (live_llm=False)...
[+] Evaluation Completed Successfully!
    Total Scenarios: 56
    Passed:          56
    Failed:          0
    Quality Pass Rate: 100.0%
```

### 8.3 Live Provider & Atlas Offline Validation
```
python -m ai_engine.validate_live_provider
[1] EXTERNAL EMBEDDING PROVIDER: SKIPPED (OPENAI_API_KEY is not configured)
[2] MONGODB ATLAS VECTOR SEARCH: NOT EXERCISED (MONGODB_ATLAS_URI is not configured)
```

---

## 9. Limitations & Extension Strategy

1. **Language Scope**: The current static taxonomy provides verified relationships for Python standard library exceptions and Go runtime panics. Extending to JVM (Java/Kotlin), Rust `Result`/`panic`, or C++ standard exceptions will follow the same declarative, verified pattern in [`ai_engine/taxonomy.py`](file:///d:/projects/DevMemory/ai_engine/taxonomy.py).
2. **Offline Simulation Bounds**: Mode 3 demonstrates semantic dense retrieval via a simulated clustering mock (`is_simulated_mock=True`). Real cloud inference latency and network behavior require live credentials in staging.
