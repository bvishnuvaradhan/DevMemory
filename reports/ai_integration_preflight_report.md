# DevMemory — Phase 7.0: CLI, Backend, and AI Integration Preflight Audit Report

**Author**: DevMemory Integration Engineering  
**Date**: October 10, 2026  
**Integration Target**: CLI & Backend Integration (`feat/integration-cli-backend`) + AI Engine (`feature/member-3-ai-memory`)  
**Verdict**: **`READY_WITH_ADAPTERS`**  

---

## 1. Executive Summary

A comprehensive, read-only preflight audit was conducted to evaluate the technical feasibility, architectural compatibility, and risk profile of integrating the **DevMemory AI & Memory Engine** (`feature/member-3-ai-memory`) into the **CLI and Backend Integration Branch** (`feat/integration-cli-backend`).

### Key Findings
1. **Branch Compatibility**: The two branches share a clean common ancestor (`fa71ee9`, Initial commit) and have **zero file collisions** outside of `.gitignore` and `LICENSE`.
2. **Component Decoupling**: Ownership boundaries are distinct:
   - CLI resides in `src/devmemory/`.
   - Backend resides in `server/`.
   - AI Engine resides in `ai_engine/`.
3. **Dependency Coexistence**: Both backend and AI components utilize Pydantic v2 and Python 3.9+. No conflicting pinned dependencies or incompatible version constraints exist.
4. **Integration Gap (Adapters Required)**:
   - The backend currently implements a CRUD persistence schema for diagnoses (`server/app/schemas/diagnosis.py`), but does not yet invoke `ai_engine.diagnosis.diagnose_error`.
   - An adapter (`MongoIncidentRepository`) is required to bridge the backend's MongoDB collections to the AI engine's `IncidentRepository` protocol.
   - An adapter is required to map between the backend's incident records and `DiagnosisRequest` / `AuthorizationContext`.
   - An adapter is required to map the AI engine's `DiagnosisResponse` to the CLI's expected `BackendDiagnosisResponse`.

**Preflight Verdict**: **`READY_WITH_ADAPTERS`**. Full integration can proceed safely once adapter layers are implemented in Phase 7.1.

---

## 2. Repository & Git State Verification

### 2.1 Current Working Environment
- **Repository Root**: `D:/projects/DevMemory`
- **Active Working Branch**: `feature/member-3-ai-memory`
- **Active Commit SHA**: `c2c2994d2107d9c0498f4ebad13dc7abdedfbf5e`
- **Active Commit Message**: `docs(ai-engine): freeze release candidate and publish integration contract`
- **Working Tree Status**: Clean (`nothing to commit, working tree clean`)
- **Upstream Sync**: Synchronized with `origin/feature/member-3-ai-memory` (up to date, 0 ahead, 0 behind).

### 2.2 Local & Remote Branch Inventory

```
* feature/member-3-ai-memory                         c2c2994 [origin/feature/member-3-ai-memory] docs(ai-engine): freeze release candidate
  feature/member-1-cli-diagnostics                   fa71ee9 Initial commit
  main                                               fa71ee9 [origin/main] Initial commit
  remotes/origin/HEAD                                -> origin/main
  remotes/origin/feat/integration-cli-backend        8506881 feat(integration): integrate CLI diagnostic engine with FastAPI MongoDB backend
  remotes/origin/feat/member-1-cli-foundation        c97411f test(cli): add end-to-end validation fixtures
  remotes/origin/feature/backend-mongodb             1c60fb3 test(backend): verify end-to-end API integration contracts
  remotes/origin/feature/member-3-ai-memory          c2c2994 docs(ai-engine): freeze release candidate and publish integration contract
  remotes/origin/feature/member-4-frontend-dashboard bdeb435 feat(frontend): add dark mode and light mode theme support
  remotes/origin/main                                fa71ee9 Initial commit
```

- **Target Integration Branch**: `origin/feat/integration-cli-backend` (commit `8506881`).
- **Target AI Engine Branch**: `origin/feature/member-3-ai-memory` (commit `c2c2994`, baseline implementation `930a961`).
- **Merge-Base**: Commit `fa71ee9b4fe803ca12460a641a1ee7039f505a8a` (`Initial commit`).

---

## 3. Integration Branch Inspection (`feat/integration-cli-backend`)

### 3.1 Architectural Layout
```
feat/integration-cli-backend/
├── pyproject.toml              # CLI project specification & packaging
├── server/                     # Member 2 FastAPI Backend
│   ├── app/
│   │   ├── main.py             # FastAPI entry point & lifespan management
│   │   ├── config.py           # Pydantic Settings (MongoDB URI, host, port)
│   │   ├── db/                 # MongoManager & index initialization
│   │   ├── routes/             # REST endpoints (runs, incidents, fixes, health)
│   │   ├── schemas/            # Request/Response Pydantic schemas
│   │   ├── services/           # Service layer (runs, incidents, analytics)
│   │   └── utils/              # Command normalization & signature computation
│   ├── requirements.txt        # Server dependencies (FastAPI, pymongo, etc.)
│   └── tests/                  # 14 backend test modules
├── src/devmemory/              # Member 1 CLI Application
│   ├── cli/main.py             # Typer CLI entry point (devmemory run, init)
│   ├── diagnostics/            # Language parsers (Python, JS) & snippet extractors
│   ├── integration/            # DevMemoryClient & HTTP models
│   └── runner.py               # Process execution & bounded stdout/stderr streaming
└── tests/                      # 5 CLI & integration test modules
```

### 3.2 CLI Execution & Data Flow
1. Developer executes `devmemory run -- <command>`.
2. `CommandRunner` executes child process, streams output to terminal, and buffers up to 512 KB stdout/stderr.
3. If `exit_code != 0`, `analyze_error_output` parses stack frames and extracts source snippets.
4. `DevMemoryClient.submit_incident` sends an `IncidentPayload` (`RunCreate`) to backend `POST /api/v1/runs`.
5. Backend creates a `command_runs` record and derives an incident in `incidents` if an error occurred.
6. CLI queries `GET /api/v1/incidents/{incident_id}/history` and displays exact-signature memory matches.

### 3.3 Current Backend Limitations Regarding AI Diagnosis
- **No Active LLM Invocation**: `server/app/routes/incidents.py` defines `POST /{incident_id}/diagnosis`, but it merely accepts and stores a client-provided `DiagnosisCreate` payload in MongoDB `db.diagnoses`. It does not execute diagnosis logic.
- **Lexical/Signature-Only History**: `analytics_service.get_incident_history` queries matching `error_signature` strings. It does not perform semantic, hybrid, or exception-taxonomy matching.
- **Unauthenticated Backend**: The API routes currently operate without user identity/token verification.

---

## 4. AI Engine Branch Inspection (`feature/member-3-ai-memory`)

### 4.1 Architectural Layout
```
feature/member-3-ai-memory/
├── ai_engine/                  # Member 3 AI & Memory Engine
│   ├── diagnosis.py            # Primary orchestrator (diagnose_error) & fallback
│   ├── retrieval.py            # 3-level memory orchestrator (retrieve_memory)
│   ├── matching.py             # Deterministic lexical similarity & error signatures
│   ├── hybrid.py               # Lexical + vector fusion & contradiction guards
│   ├── taxonomy.py             # Language-aware static exception hierarchies
│   ├── vector.py               # Dense & deterministic embedding providers, Mongo adapter
│   ├── llm_client.py           # GroqLLMClient & MockLLMClient
│   ├── privacy.py              # Secret redaction (6 classes) & path sanitization
│   ├── prompts.py              # Bounded prompts & untrusted data fencing
│   ├── schemas.py              # Pydantic schemas (DiagnosisRequest, DiagnosisResponse)
│   ├── knowledge/seed_data.json# Preloaded curated troubleshooting rules
│   └── evaluation/             # Reproducible evaluation suites (Suite A & Suite B)
├── docs/                       # ai-engine-integration-contract.md (RC1 freeze)
├── reports/                    # Audit and benchmark verification reports
├── requirements-ai.txt         # AI engine dependencies (pydantic, groq, pytest)
└── tests/                      # 18 unit, contract, and regression test modules
```

### 4.2 Verified Release Baseline Status
- **Reported Implementation Baseline**: Commit `930a961`.
- **Release Freeze Documentation Commit**: Commit `c2c2994`.
- **Verification Commands Executed & Confirmed**:
  - `pytest tests/ -v`: **146 passed, 3 skipped, 0 failed** (12.55s).
  - `python -m ai_engine.evaluation.runner`: **56 / 56 scenarios passed (100.0%)**.
  - `python -m ai_engine.evaluation.retrieval_benchmark`: **Benchmark v2.1.0 (36 scenarios, 100% CRR, 100% PIR)**.
  - `python -m ai_engine.validate_live_provider`: External Provider `SKIPPED`, Atlas Vector Search `NOT EXERCISED`, Pipeline Builder `VALIDATED`.
- **No Implementation Drift**: The commit diff between `930a961` and `c2c2994` consists solely of markdown documentation files (`docs/` and `reports/`). Implementation code is frozen.

---

## 5. File & Dependency Conflict Analysis

### 5.1 File Overlap Comparison
A complete path intersection across both branches reveals **zero conflicting implementation files**:

| Branch | Exclusive Directories & Files | Common Paths |
| :--- | :--- | :--- |
| `feat/integration-cli-backend` | `src/`, `server/`, `fixtures/`, `pyproject.toml`, `server/requirements.txt` | `.gitignore`, `LICENSE` |
| `feature/member-3-ai-memory` | `ai_engine/`, `docs/`, `reports/`, `requirements-ai.txt` | `.gitignore`, `LICENSE` |

- **`.gitignore`**: The only differing file. Can be trivially merged by taking the union of ignore rules.
- **`LICENSE`**: Byte-for-byte identical.
- **`tests/` directory**: Both branches contain a `tests/` directory at the root, but **zero filename collisions** exist:
  - Integration branch: `test_cli.py`, `test_cli_backend_integration.py`, `test_diagnostics.py`, `test_e2e_fixtures.py`, `test_integration.py`.
  - AI branch: `test_diagnosis.py`, `test_ai_contract_validation.py`, `test_retrieval.py`, `test_security.py`, etc.
  - *Note*: `test_diagnostics.py` (CLI parser) and `test_diagnosis.py` (AI engine) have distinct names.

### 5.2 Dependency Manifest Analysis

| Component | Manifest File | Primary Dependencies | Version Compatibility |
| :--- | :--- | :--- | :--- |
| **CLI** | `pyproject.toml` | `typer>=0.9.0`, `rich>=13.0.0` | Compatible |
| **Backend** | `server/requirements.txt` | `fastapi>=0.115.0`, `pymongo>=4.8.0`, `pydantic-settings>=2.4.0`, `httpx>=0.27.0` | Compatible |
| **AI Engine**| `requirements-ai.txt` | `pydantic>=2.7.0`, `groq>=0.9.0`, `pytest>=8.0.0` | Compatible |

**Zero Version Clashes**: Both backend and AI engine use Pydantic v2. FastAPI 0.115 natively works with Pydantic v2. `groq` uses standard `httpx`.

### 5.3 Configuration & Environment Variable Compatibility

| Variable Name | Backend Usage (`server/app/config.py`) | AI Engine Usage (`ai_engine/`) | Conflict Status |
| :--- | :--- | :--- | :--- |
| `MONGODB_URI` / `MONGODB_ATLAS_URI` | `MONGODB_URI` (default: `mongodb://localhost:27017`) | `MONGODB_URI` or `MONGODB_ATLAS_URI` | **Compatible** (shared connection string) |
| `MONGODB_DATABASE` vs `MONGODB_DB_NAME` | Uses `MONGODB_DB_NAME` (default: `devmemory`) | Uses `MONGODB_DATABASE` (default: `devmemory`) | **Adapter / Alias Required**: Standardize on `devmemory` default. |
| `MONGODB_COLLECTION` | Uses `incidents`, `command_runs`, `diagnoses` | Defaults to `incidents` | **Compatible** |
| `MONGODB_VECTOR_INDEX` | Not used in backend | `devmemory_vector_index` | **Compatible** (AI engine exclusive) |
| `GROQ_API_KEY` / `GROQ_MODEL` | Not used in backend | Groq Cloud LLM inference | **Compatible** (AI engine exclusive) |
| `OPENAI_API_KEY` | Not used in backend | Dense vector embeddings | **Compatible** (AI engine exclusive) |
| `DEV_MEMORY_DISABLE_EXTERNAL_AI` | Not used in backend | Offline privacy opt-out | **Compatible** |

---

## 6. Target Directory Placement & Layout Plan

To preserve clean separation of concerns and team ownership, the integrated repository structure will follow:

```
DevMemory/ (Repository Root)
├── ai_engine/                  # Member 3: AI & Memory Engine (Standalone Python Module)
│   ├── diagnosis.py
│   ├── retrieval.py
│   ├── hybrid.py
│   ├── vector.py
│   ├── ...
├── server/                     # Member 2: FastAPI Backend Service
│   ├── app/
│   │   ├── main.py
│   │   ├── routes/
│   │   ├── services/
│   │   │   ├── ai_service.py   # [NEW in Phase 7.1] Adapter invoking ai_engine.diagnosis
│   │   │   └── ...
├── src/devmemory/              # Member 1: Developer CLI
│   ├── cli/main.py
│   ├── runner.py
│   └── ...
├── docs/                       # Integration contracts & architecture specifications
├── reports/                    # Validation, audit, and benchmark reports
├── pyproject.toml              # Unified root project manifest (updated pythonpath)
└── tests/                      # Component tests organized with clear namespacing
```

### Python Package & Import Resolution
- **Current Observation**: On `origin/feat/integration-cli-backend`, `pyproject.toml` defines:
  ```toml
  [tool.pytest.ini_options]
  testpaths = ["tests"]
  pythonpath = ["src"]
  ```
- **Integration Requirement**: When `ai_engine/` resides in the repository root, `pythonpath` must include `.` (the root directory) alongside `src`:
  ```toml
  pythonpath = ["src", "."]
  ```
  This ensures both `devmemory` (CLI) and `ai_engine` are cleanly discoverable by tests and server applications without `sys.path` hacks.

---

## 7. Integration Contract Compatibility Validation

| # | Contract Validation Item | Classification | Analysis & Required Adapter |
| :-: | :--- | :---: | :--- |
| **1** | **Backend constructs valid `DiagnosisRequest` from incident data** | `PASS_WITH_ADAPTER_REQUIRED` | Backend `RunCreate` / `IncidentResponse` contains all necessary evidence (`event_id`, `project_id`, `command`, `exit_code`, `error_message`, `stack_trace`, `file_path`, `line`, `snippet`). An adapter function `build_diagnosis_request(incident, run)` must map these fields to `ai_engine.schemas.DiagnosisRequest`. |
| **2** | **Backend supplies trustworthy `AuthorizationContext`** | `PASS_WITH_ADAPTER_REQUIRED` | The backend currently operates without user login/tokens. An adapter function must construct `AuthorizationContext` from verified incident tenancy (`user_id="system"`, `project_id=incident.project_id`, `has_project_access=True`, `has_cross_project_read=False`). |
| **3** | **AI incident repository protocol matches backend storage** | `PASS_WITH_ADAPTER_REQUIRED` | AI engine requires protocol `IncidentRepository` (`get_project_incidents`, `get_cross_project_incidents`). A wrapper `MongoIncidentRepository(db: Database)` must be created in the backend service layer querying `db.incidents`. |
| **4** | **Project and incident identifiers are compatible** | `PASS` | Backend uses string IDs (project_id 1-64 chars, incident_id 1-128 chars). AI engine supports string IDs (1-128 chars). Constraints are fully satisfied. |
| **5** | **Response fields compatible with CLI output requirements** | `PASS_WITH_ADAPTER_REQUIRED` | CLI's `BackendDiagnosisResponse` expects `probable_cause`, `hypotheses`, `suggested_steps`, `similar_incidents`, `is_verified_fix`. AI engine outputs `likely_cause`, `hypotheses`, `recommended_steps`, `related_incidents`, `fix_status`. Direct 1-to-1 mapping exists; adapter required. |
| **6** | **Exceptions and provider failures handled gracefully** | `PASS` | AI engine synthesizes local deterministic fallback on any LLM or vector error. Backend has global JSON exception handlers. CLI catches network timeouts cleanly. |
| **7** | **Offline mode prevents all external AI calls** | `PASS` | `DEV_MEMORY_DISABLE_EXTERNAL_AI`, `DEVMEMORY_OFFLINE_MODE`, and `AI_PRIVACY_OFFLINE_ONLY` are checked at orchestrator and provider entry points. 100% offline verified. |
| **8** | **Private incidents excluded from unauthorized cross-project retrieval** | `PASS_WITH_ADAPTER_REQUIRED` | AI engine enforces `AuthorizationContext.has_cross_project_read` and `candidate.is_public == True`. The backend `MongoIncidentRepository` adapter must ensure queries filter by `is_public: True` for cross-project searches. |
| **9** | **AI engine and backend coexist without conflicting dependencies** | `PASS` | No dependency conflicts. Both utilize Pydantic v2 and Python 3.9+. |
| **10** | **AI engine tests run from integrated layout** | `PASS_WITH_ADAPTER_REQUIRED` | Adding `.` to `pythonpath` in `pyproject.toml` enables seamless discovery of both `src/devmemory` and `ai_engine` across all pytest runs. |

---

## 8. Required Adapters Specification (For Phase 7.1)

To integrate the three components cleanly without modifying Member 3's frozen `ai_engine` or breaking existing CLI/Backend contracts, four lightweight adapters must be introduced during Phase 7.1:

### Adapter 1: `MongoIncidentRepository` (Backend -> AI Engine)
Wraps PyMongo database access to satisfy `ai_engine.retrieval.IncidentRepository`:
```python
class MongoIncidentRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def get_project_incidents(self, project_id: str) -> List[Dict[str, Any]]:
        return list(self.db.incidents.find({"project_id": project_id}, {"_id": 0}))

    def get_cross_project_incidents(self, requesting_project_id: str) -> List[Dict[str, Any]]:
        return list(self.db.incidents.find(
            {"project_id": {"$ne": requesting_project_id}, "is_public": True},
            {"_id": 0}
        ))
```

### Adapter 2: `DiagnosisRequest` & `AuthorizationContext` Builder (Backend -> AI Engine)
Constructs validated AI input payloads from stored backend run and incident documents:
```python
def build_ai_diagnosis_payloads(
    incident: IncidentResponse,
    run: Optional[RunResponse] = None,
) -> tuple[DiagnosisRequest, AuthorizationContext]:
    req = DiagnosisRequest(
        event_id=incident.event_id or f"evt_{incident.incident_id}",
        project_id=incident.project_id,
        command=(run.command if run else "command")[:2000],
        exit_code=run.exit_code if run else 1,
        error_message=incident.error_message[:10000],
        stack_trace=(run.stderr if run and run.stderr else None),
        locations=[SourceLocation(file_path=incident.file_path, line=incident.line)] if incident.file_path and incident.line else [],
        allow_cross_project=True,
    )
    auth = AuthorizationContext(
        user_id="system",
        project_id=incident.project_id,
        has_project_access=True,
        has_cross_project_read=False,  # Default safe boundary
    )
    return req, auth
```

### Adapter 3: Diagnosis Response Bridge (AI Engine -> Backend / CLI)
Maps `ai_engine.schemas.DiagnosisResponse` to backend's `DiagnosisCreate` and CLI's `BackendDiagnosisResponse`:
```python
def map_ai_response_to_backend_diagnosis(
    ai_resp: DiagnosisResponse,
    incident_id: str,
) -> DiagnosisCreate:
    return DiagnosisCreate(
        summary=ai_resp.summary,
        hypotheses=[
            HypothesisItem(cause=h, is_observed=False, details=None)
            for h in ai_resp.hypotheses
        ],
        suggested_fix="; ".join(ai_resp.recommended_steps),
        matched_memory=[
            MatchedMemoryRef(
                source_id=m.incident_id,
                source_type=m.match_source.value,
                relevance_reason=m.explanation,
            )
            for m in ai_resp.related_incidents
        ],
        evidence=ai_resp.evidence,
        confidence=ai_resp.confidence,
        source="ai_engine/groq-llama-3.3-70b",
    )
```

### Adapter 4: Pyproject PythonPath Configuration
Update `pyproject.toml` to ensure both `src` and root are in pytest path:
```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src", "."]
```

---

## 9. Validation & Verification Plan (Phase 7.1)

Following integration in Phase 7.1, the complete validation plan comprises five automated test tiers:

```
[Tier 1: CLI Regression Tests]       pytest tests/test_cli*.py tests/test_diagnostics.py
[Tier 2: Backend Regression Tests]   pytest server/tests/
[Tier 3: AI Engine Regression Tests] pytest tests/test_diagnosis.py tests/test_ai_contract_validation.py ...
[Tier 4: AI Benchmark Harness]       python -m ai_engine.evaluation.runner
                                     python -m ai_engine.evaluation.retrieval_benchmark
[Tier 5: End-to-End Integration]    pytest tests/test_cli_backend_ai_e2e.py (New in Phase 7.1)
```

### New Integration Test Scenarios for Phase 7.1
1. **End-to-End Command Failure to Diagnosis**: Failed command executed via CLI -> Ingested to Backend -> AI Engine diagnosed -> Diagnosis stored in MongoDB -> Rendered in CLI terminal output.
2. **Offline Fallback Under Network Failure**: CLI runs with backend offline or external AI disabled -> Valid local deterministic diagnosis delivered without crashes.
3. **Multi-Tenant Project Isolation**: Verify that incident from Project A is excluded from Project B unless explicitly marked `is_public` and authorized.
4. **Fix Verification Flow**: Verified fix in backend correctly attaches `FixVerificationStatus.VERIFIED` bonus in subsequent AI retrieval.

---

## 10. Final Preflight Audit Verdict

```
===================================================================================
                     FINAL INTEGRATION PREFLIGHT VERDICT
===================================================================================

                        >>> READY_WITH_ADAPTERS <<<

1. Source Branches:          feat/integration-cli-backend & feature/member-3-ai-memory
2. File Conflicts:           ZERO implementation collisions (.gitignore only)
3. Dependency Conflicts:     ZERO dependency version clashes (Pydantic v2 aligned)
4. AI Engine Status:         Frozen RC1 (146 passed tests, 56/56 eval scenarios)
5. Integration Path:         Copy ai_engine/ into repo root + implement 4 adapters
6. Blockers:                 NONE

===================================================================================
```

**Next Action**: Await explicit authorization from engineering leads before beginning Phase 7.1 implementation.
