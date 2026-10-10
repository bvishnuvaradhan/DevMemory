# DevMemory — Phase 6: Hybrid Retrieval and MongoDB Vector Search Report

**Component**: AI & Cross-Project Memory Engine (`ai_engine`)  
**Lead**: Member 3 — AI & Cross-Project Memory Lead  
**Branch**: `feature/member-3-ai-memory`  
**Evaluation Dataset**: `v2.1.0` (56 scenarios)  
**Regression Test Status**: 82 / 82 tests passing  

---

## 1. Executive Summary

In Phase 6, DevMemory's retrieval architecture was upgraded from purely deterministic lexical and rule-based matching to an enterprise-grade **Hybrid Retrieval Architecture**. This system unifies:
1. **Exact Error Signature Matching**: Deterministic, hash-anchored grouping for identical errors.
2. **Lexical Matching**: Token-level Jaccard similarity across error messages, stack traces, and commands.
3. **Semantic Vector Search**: High-dimensional vector space similarity powered by MongoDB Atlas `$vectorSearch` and offline in-memory cosine adapters.
4. **Evidence-Contradiction Guards**: Hard constraints ensuring semantic similarity never overrules contradictory exception types or conflicting runtime contexts.

This architecture delivers high semantic recall for paraphrased errors and configuration mismatches while eliminating vector hallucinations and root-cause misdiagnoses.

---

## 2. Environment Audit: Atlas vs. MongoDB Community Edition

During the Phase 6 environment audit, the local development environment was inspected:
- **MongoDB Server**: MongoDB Community Edition 8.0.13 (`mongodb://localhost:27017`).
- **Driver**: `pymongo` 4.18.2.

### Crucial Finding: `$vectorSearch` Availability
In MongoDB, `$vectorSearch` is a proprietary aggregation stage available exclusively on **MongoDB Atlas** (cloud-managed clusters) or specialized Atlas CLI local deployments with Atlas Search binaries. In standard Community Edition standalone servers, executing:
```javascript
db.incidents.aggregate([
  {
    $vectorSearch: {
      index: "vector_index",
      path: "embedding",
      queryVector: [...],
      numCandidates: 50,
      limit: 5
    }
  }
])
```
results in `OperationFailure: Unrecognized pipeline stage name: '$vectorSearch' (code 40324)`.

### Architectural Solution: Resilient Adapters & Graceful Fallback
To ensure that production Atlas clusters leverage native vector indexing while local development, offline CI, and air-gapped test runners never break:
1. **`MongoVectorSearchAdapter`**:
   - Implements the official MongoDB Atlas `$vectorSearch` aggregation pipeline.
   - Includes query pre-filtering (`project_id` scoping and `is_public` checks) directly in the aggregation stage.
   - Catches `OperationFailure` and network errors gracefully, logging a structured warning and returning an empty list so retrieval falls back to lexical matching without interruption.
2. **`MockVectorSearchAdapter`**:
   - 100% in-memory vector store providing exact cosine similarity.
   - Strict project scoping and cross-project authorization guarantees.
   - Enables fast offline regression testing and reproducible quality benchmarks.
3. **`DeterministicEmbeddingProvider`**:
   - 100% offline, reproducible 128-dimensional unit-normalized L2 embedding generator.
   - Secret-sanitized prior to embedding computation: sensitive credentials are never translated into embeddings.

---

## 3. Hybrid Retrieval Architecture & Contradiction Guards

### The Problem with Naive Vector Search
In software diagnostics, two error messages can share high semantic token overlap while representing completely different root causes. For example:
- **Query**: `KeyError: 'user_session' in auth.py line 40`
- **Candidate Incident**: `SyntaxError: invalid syntax in auth.py line 40`

A naive vector search model scores these very high (~88-93% similarity) because `auth.py`, `line 40`, and `user_session` dominate the embedding space. If an AI diagnosis engine treats vector similarity as proof of root cause, it will propose syntax adjustments for missing dictionary keys.

### The Contradiction Guard Solution
DevMemory implements explicit multi-signal fusion rules in `ai_engine.hybrid.calculate_hybrid_score`:

```mermaid
flowchart TD
    Query[Diagnosis Query] --> SigCheck{Exact Signature Match?}
    SigCheck -- Yes --> ExactScore["Score = max(0.98, Lexical) (Definitive Precedent)"]
    SigCheck -- No --> ClashCheck{Clashing Exception Types?}
    
    ClashCheck -- Yes (e.g. KeyError vs SyntaxError) --> ClashPenalty["Contradiction Penalty Applied: Score capped <= 0.35"]
    ClashCheck -- No --> TechCheck{Incompatible Runtime Stack?}
    
    TechCheck -- Yes (e.g. Python vs Rust) --> TechPenalty["Runtime Discount: Score scaled by 0.75"]
    TechCheck -- No --> BalancedFusion["Hybrid Fusion: 55% Lexical + 45% Vector"]
    
    BalancedFusion --> VerifiedBonus{Is Past Fix Verified?}
    VerifiedBonus -- Yes --> AddBonus["+0.05 Verification Reliability Boost"]
    VerifiedBonus -- No --> FinalScore[Final Score Clamped [0.0, 1.0]]
    AddBonus --> FinalScore
```

### Fusion Formula
1. **Exact Signature Match**:
   $$\text{Score} = \max(0.98, \text{Lexical})$$
2. **Contradictory Exception Clashes** (e.g. `KeyError` vs `SyntaxError`, `TypeError` vs `ValueError`):
   $$\text{Score} = \min(\text{Lexical} \times 0.70, 0.35)$$
   *Semantic vector score is completely discounted due to conflicting error evidence.*
3. **Incompatible Runtime Stacks** (e.g. Python vs Node.js):
   $$\text{Score} = (0.60 \times \text{Lexical} + 0.40 \times \text{Vector}) \times 0.75$$
4. **Standard Compatible Precedents**:
   $$\text{Score} = (0.55 \times \text{Lexical} + 0.45 \times \text{Vector}) + \text{Bonus}_{\text{verified}}$$
   *(where $\text{Bonus}_{\text{verified}} = +0.05$ if the precedent fix was verified by test execution).*

---

## 4. Security, Isolation, and Privacy Hardening

Phase 6 adheres strictly to DevMemory's multi-tenant privacy model:
1. **Zero Secret Leakage in Vectors**:
   `DeterministicEmbeddingProvider` runs `redact_secrets` and `sanitize_file_path` on all diagnostic text *before* generating embeddings. Raw API keys, tokens, and database passwords never produce embedding signatures.
2. **Project Memory Isolation**:
   Level 2 queries filter strictly by `project_id == request.project_id`. Incidents from other projects are unreachable regardless of vector score.
3. **Cross-Project Authorization**:
   Level 3 requires explicit server-side authorization (`has_cross_project_read = True`) and only returns incidents marked `is_public = True`.
4. **Public Precedent Sanitization**:
   All matched cross-project incidents undergo path sanitization (e.g. `/home/user/code/file.py` $\rightarrow$ `~/code/file.py`) and secret redaction prior to LLM prompt injection.
5. **AI Fix Verification Lifecycle**:
   All newly generated diagnoses remain marked as `fix_status: unverified`. Past precedents retain their explicit verification status, boosting confidence only when validated by real test execution.

---

## 5. Verification & Test Suite Results

The Phase 6 test suite validates all requirements:

| Test Module | Coverage Focus | Test Count | Status |
| :--- | :--- | :--- | :--- |
| `tests/test_schemas.py` | Schema validations, constraints, serialization | 10 | **PASSED** |
| `tests/test_matching.py` | Error normalization, signatures, lexical matching | 7 | **PASSED** |
| `tests/test_privacy.py` | Credential redaction, path sanitization, policy | 8 | **PASSED** |
| `tests/test_security.py` | PEM keys, injection escaping, prompt security | 13 | **PASSED** |
| `tests/test_knowledge.py` | Level 1 curated knowledge base | 4 | **PASSED** |
| `tests/test_llm_client.py` | Mock and Groq client implementations | 4 | **PASSED** |
| `tests/test_prompts.py` | Evidence-grounded prompt templates | 3 | **PASSED** |
| `tests/test_retrieval.py` | Three-level memory retrieval architecture | 12 | **PASSED** |
| `tests/test_diagnosis.py` | End-to-end diagnosis & deterministic fallback | 5 | **PASSED** |
| `tests/test_evaluation.py` | Benchmark runner & dataset completeness | 4 | **PASSED** |
| `tests/test_hybrid_retrieval.py` | **Hybrid fusion, vector adapters & contradiction guards** | **12** | **PASSED** |
| **Total** | **Full AI & Memory Engine Suite** | **82** | **100% PASSED** |

### Benchmark Evaluation Runner
- **Command**: `python -m ai_engine.evaluation.runner`
- **Total Scenarios**: 56
- **Passed Scenarios**: 56
- **Quality Pass Rate**: **100.0%**

---

## 6. Public Interface Preserved

Public interfaces were strictly preserved with backwards-compatible optional parameters:
```python
def retrieve_memory(
    request: DiagnosisRequest,
    auth_context: AuthorizationContext,
    repository: Optional[IncidentRepository] = None,
    kb_items: Optional[List[KnowledgeBaseItem]] = None,
    threshold: float = 0.60,
    vector_adapter: Optional[Any] = None,
    embedding_provider: Optional[Any] = None,
) -> RetrievalResult: ...

def diagnose_error(
    request: DiagnosisRequest,
    auth_context: AuthorizationContext,
    repository: Optional[IncidentRepository] = None,
    kb_items: Optional[List[KnowledgeBaseItem]] = None,
    threshold: float = 0.60,
    llm_client: Optional[LLMClient] = None,
    vector_adapter: Optional[Any] = None,
    embedding_provider: Optional[Any] = None,
) -> DiagnosisResponse: ...
```

Existing callers not passing `vector_adapter` continue to operate with 100% functionality via deterministic lexical matching.
