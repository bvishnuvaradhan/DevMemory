# DevMemory — Backend Service

The core FastAPI backend and MongoDB persistence layer for DevMemory, providing data ingestion, incident tracking, multi-level memory storage, AI diagnosis persistence, verified-fix tracking, and troubleshooting analytics.

## Prerequisites

- **Python**: 3.12+ (Python 3.12 recommended)
- **MongoDB**: 6.0+ (Running on `127.0.0.1:27017`)

---

## Setup Instructions (Windows PowerShell)

### 1. Create and Activate Virtual Environment

From the repository root (`DevMemory`):

```powershell
# Navigate to the server folder
cd server

# Create a virtual environment using Python 3.12
py -3.12 -m venv .venv

# Activate the virtual environment
.\.venv\Scripts\Activate.ps1
```

### 2. Install Dependencies

```powershell
pip install -r requirements.txt
```

### 3. Configure Environment

Copy `.env.example` to `.env` (or customize variables as needed):

```powershell
Copy-Item .env.example .env
```

Configuration variables:
- `MONGODB_URI`: `mongodb://127.0.0.1:27017`
- `DATABASE_NAME`: `devmemory`
- `MONGODB_SERVER_SELECTION_TIMEOUT_MS`: `2000`
- `API_HOST`: `127.0.0.1`
- `API_PORT`: `8000`
- `FRONTEND_ORIGIN`: `http://localhost:5173`

### 4. Run Automated Tests

```powershell
pytest -v
```

### 5. Start the Development Server

```powershell
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

---

## Architecture & Data Contracts (Phases 1, 2, 3, & 4)

### Standard Response Envelope

All API endpoints return JSON responses wrapped in a consistent envelope:

```json
{
  "success": true,
  "data": { ... },
  "error": null
}
```

On error, `success` is `false`, `data` is `null`, and `error` contains a clear description without leaking internal database strings or stack traces:

```json
{
  "success": false,
  "data": null,
  "error": "Cannot mark fix as verified without supporting verification evidence."
}
```

---

## Distinction: AI Recommendations vs. Verified Fixes

A fundamental architectural principle of DevMemory is that **an AI diagnosis recommendation is a hypothesis, not a proven fix**:

1. **AI Diagnoses**: Represent AI-generated explanations and suggested fixes (`POST /incidents/{incident_id}/diagnosis`). They may include speculative hypotheses, confidence scores, and historical references. They are stored in `diagnoses` and marked as hypotheses.
2. **Proposed Fixes**: Developers create proposed fix records in `fix_outcomes` with initial status `proposed`.
3. **Verification Evidence**: A proposed fix **cannot** be marked as `verified` simply because an LLM recommended it or a user asserts it works. A fix requires recorded empirical evidence:
   - **Automated Command Execution**: Executing a verification command with an actual exit code of `0` (e.g. `pytest`, `npm test`).
   - **Explicit User Confirmation**: Documented manual confirmation clearly distinguished from automated verification (`verification_source: "user_confirmation"`).

---

## Fix Status Transition State Machine

Fix records follow an enforced state machine:

```text
               ┌───────────► applied ───────────┐
               │                                │
               │                                ▼
proposed ──────┼────────────────────────► verifying ─────(with evidence)───► verified
               │                                │                                │
               │                                ▼                                ▼
               └───────────► failed ◄───────────┴──────────────────────────── reverted
```

- **Allowed transitions**:
  - `proposed` $\to$ `applied`, `verifying`, `failed`, `reverted`
  - `applied` $\to$ `verifying`, `failed`, `reverted`
  - `verifying` $\to$ `verified` (*requires evidence*), `failed`, `reverted`
  - `verified` $\to$ `reverted`, `failed`
  - `failed` $\to$ `verifying`, `proposed`, `reverted`
  - `reverted` $\to$ `proposed`, `verifying`
- **Enforcement**: Invalid status transitions return **HTTP 409 Conflict**. Attempting to verify without evidence returns **HTTP 422**.
- **Timestamps**: `verified_at` is set only when transitioning to `verified` with valid evidence, and is cleared to `null` if the fix is subsequently reverted or failed.

---

## Implemented API Endpoints

### Health Check

| Method | Path | Status | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/health` | 200 / 503 | Root health check |
| `GET` | `/api/v1/health` | 200 / 503 | Versioned health check |
| `GET` | `/docs` | 200 | Interactive OpenAPI / Swagger UI |

### Projects & Analytics

| Method | Path | Status | Description |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/projects` | 201 / 409 | Register a project |
| `GET` | `/api/v1/projects` | 200 | List registered projects (paginated) |
| `GET` | `/api/v1/projects/{project_id}` | 200 / 404 | Retrieve project details |
| `GET` | `/api/v1/projects/{project_id}/runs` | 200 / 404 | List project runs (supports `status=success\|failure`, `limit`, `skip`) |
| `GET` | `/api/v1/projects/{project_id}/incidents` | 200 / 404 | List project incidents (paginated) |
| `GET` | `/api/v1/projects/{project_id}/analytics/recurring` | 200 / 404 | Top recurring errors grouped by error signature |
| `GET` | `/api/v1/projects/{project_id}/analytics` | 200 / 404 | Summary metrics (runs, success/fail counts, duration) |

### Command Runs

| Method | Path | Status | Description |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/runs` | 201 / 200 / 404 / 409 / 422 | Ingest command run event (idempotent) |
| `GET` | `/api/v1/runs/{event_id}` | 200 / 404 | Retrieve command run by event ID |

### Incidents, Memory, & Diagnoses

| Method | Path | Status | Description |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/incidents` | 201 / 404 / 422 | Register an incident explicitly |
| `GET` | `/api/v1/incidents/{incident_id}` | 200 / 404 | Retrieve incident details |
| `GET` | `/api/v1/incidents/{incident_id}/history` | 200 / 404 | Same-project vs privacy-sanitized cross-project historical incidents |
| `POST` | `/api/v1/incidents/{incident_id}/diagnosis` | 201 / 200 / 404 / 422 | Store structured AI diagnosis for incident (idempotent) |
| `GET` | `/api/v1/incidents/{incident_id}/diagnosis` | 200 / 404 | Retrieve latest diagnosis for incident |
| `GET` | `/api/v1/incidents/{incident_id}/diagnoses` | 200 / 404 | List paginated diagnosis history for incident |
| `POST` | `/api/v1/incidents/{incident_id}/fixes` | 201 / 404 / 422 | Register proposed fix for incident |
| `GET` | `/api/v1/incidents/{incident_id}/fixes` | 200 / 404 | List paginated fixes for incident |

### Fix Outcomes

| Method | Path | Status | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/fixes/{fix_id}` | 200 / 404 | Retrieve fix details by ID |
| `PATCH` | `/api/v1/fixes/{fix_id}` | 200 / 404 / 409 / 422 | Update fix status and attach verification evidence |

---

## Response Examples (Phase 4)

### Store AI Diagnosis (`POST /api/v1/incidents/{incident_id}/diagnosis`)

```json
{
  "success": true,
  "data": {
    "diagnosis_id": "diag_01025345b481",
    "incident_id": "inc_evt_demo_001",
    "project_id": "proj_shopapp",
    "summary": "Attempted to divide integer by zero in calculate_ratio()",
    "hypotheses": [
      {
        "cause": "Denominator variable total_count was 0 due to empty queryset",
        "is_observed": true,
        "details": "Observed total_count = 0 in local scope before line 10"
      }
    ],
    "suggested_fix": "Add guard check: if total_count == 0: return 0.0",
    "matched_memory": [
      {
        "source_id": "kb_python_zerodiv",
        "source_type": "knowledge_base",
        "relevance_reason": "Standard Python division by zero guard pattern"
      }
    ],
    "evidence": ["ZeroDivisionError raised at calculator.py:10"],
    "confidence": 0.95,
    "source": "groq/llama-3.3-70b-versatile",
    "created_at": "2026-10-10T12:00:00Z",
    "idempotent": false
  },
  "error": null
}
```

### Verify Fix Outcome (`PATCH /api/v1/fixes/{fix_id}`)

**Request**:
```json
{
  "status": "verified",
  "verification_method": "command",
  "verification_command": "pytest tests/test_calculator.py",
  "verification_exit_code": 0,
  "verification_source": "test_runner",
  "verification_details": "5 passed in 0.22s"
}
```

**Response (HTTP 200 OK)**:
```json
{
  "success": true,
  "data": {
    "fix_id": "fix_d265c73d82fb",
    "incident_id": "inc_evt_demo_001",
    "project_id": "proj_shopapp",
    "description": "Add guard check in calculate_ratio()",
    "status": "verified",
    "verification_method": "command",
    "verification_command": "pytest tests/test_calculator.py",
    "verification_exit_code": 0,
    "verification_details": "5 passed in 0.22s",
    "verification_source": "test_runner",
    "verified_at": "2026-10-10T12:15:30Z",
    "created_at": "2026-10-10T12:05:00Z",
    "updated_at": "2026-10-10T12:15:30Z"
  },
  "error": null
}
```

---

## MongoDB Indexes and Supported Queries

All indexes are verified and initialized idempotently during startup via `init_indexes`:

| Collection | Index Name | Key Pattern | Supported Query Pattern |
| :--- | :--- | :--- | :--- |
| `projects` | `idx_projects_project_id_unique` | `{ project_id: 1 }` (unique) | Unique project lookup and collision prevention |
| `command_runs` | `idx_runs_event_id_unique` | `{ event_id: 1 }` (unique) | Idempotent run ingestion and single run lookup |
| `command_runs` | `idx_runs_project_started_at` | `{ project_id: 1, started_at: -1 }` | Paginated project run history sorted newest first |
| `command_runs` | `idx_runs_project_exit_code` | `{ project_id: 1, exit_code: 1 }` | Fast calculation of successful vs failed runs |
| `incidents` | `idx_incidents_incident_id_unique` | `{ incident_id: 1 }` (unique) | Single incident lookup |
| `incidents` | `idx_incidents_project_event_unique` | `{ project_id: 1, event_id: 1 }` (unique, partial) | Prevents duplicate incidents for the same run |
| `incidents` | `idx_incidents_project_created_at` | `{ project_id: 1, created_at: -1 }` | Paginated incident listing by project |
| `incidents` | `idx_incidents_project_signature_created` | `{ project_id: 1, error_signature: 1, created_at: -1 }` | Recurring error grouping and same-project history |
| `incidents` | `idx_incidents_signature_created` | `{ error_signature: 1, created_at: -1 }` | Cross-Project Memory retrieval across all projects |
| `diagnoses` | `idx_diagnoses_id_unique` | `{ diagnosis_id: 1 }` (unique) | Unique diagnosis retrieval and idempotency |
| `diagnoses` | `idx_diagnoses_incident_created` | `{ incident_id: 1, created_at: -1 }` | Latest diagnosis lookup and paginated history |
| `fix_outcomes` | `idx_fixes_id_unique` | `{ fix_id: 1 }` (unique) | Unique fix lookup and patching |
| `fix_outcomes` | `idx_fixes_project_incident_created` | `{ project_id: 1, incident_id: 1, created_at: -1 }` | Project-scoped fix queries |
| `fix_outcomes` | `idx_fixes_incident_created` | `{ incident_id: 1, created_at: -1 }` | Paginated fixes for an incident |
