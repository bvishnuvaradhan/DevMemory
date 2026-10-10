# DevMemory — Backend Service

The core FastAPI backend and MongoDB persistence layer for DevMemory, providing data ingestion, incident tracking, multi-level memory storage, and developer troubleshooting analytics.

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

## Architecture & Data Contracts (Phases 1, 2, & 3)

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
  "error": "Project with ID 'proj_shopapp' already exists."
}
```

---

## Idempotency and Event Deduplication

1. **Stable Event IDs**: Each CLI run generates a unique `event_id` (e.g. UUIDv4 or prefixed token).
2. **Atomic Ingestion**: The backend utilizes a unique MongoDB index on `command_runs.event_id`.
3. **Retry Handling**: If the same `event_id` is submitted with matching `project_id`, `command`, and `exit_code`, the backend detects the duplicate and returns the existing run with HTTP 200 and `"idempotent": true`. The document count is not incremented.
4. **Conflict Detection**: If an `event_id` is reused with conflicting data (different command, project, or exit code), the server rejects the request with **HTTP 409 Conflict**.
5. **Incident Deduplication**: When a failed run (`exit_code != 0`) has error context, an incident is created idempotently under `inc_{event_id}`. Duplicate submissions of the run will never create duplicate incidents.

---

## Error Signatures & Grouping

Every incident receives a normalized, deterministic `error_signature`:
- Hexadecimal addresses (`0x...`) $\to$ `<hex>`
- Filesystem paths (Windows and POSIX) $\to$ `<path>`
- Trailing contextual file phrases (`in <path>`, `at <path>`) $\to$ stripped
- Contextual location phrases (`line 42`, `col 10`) $\to$ `<loc>` and stripped
- Dynamic tokens / numbers (`(run 0)`, `timeout 30`) $\to$ `<num>`
- Auth headers / keys (`Bearer ...`, `ghp_...`, `sk-...`) $\to$ `<token>`

Example signature: `sig_TypeError_4f8b2c1a9e3d`

### Limitations of Deterministic Fingerprinting
- **Exact Semantics**: Deterministic signatures group structurally and syntactically equivalent errors without requiring an external vector search engine.
- **Different Error Types with Same Cause**: Different exceptions (e.g. `FileNotFoundError` vs `PermissionError`) will receive distinct signatures even if related to the same missing file. Semantic grouping across different exception classes is deferred to Phase 4 (AI diagnosis module).

---

## Cross-Project Privacy Controls & Limitations

When retrieving historical incidents across project boundaries (`GET /api/v1/incidents/{incident_id}/history`):
- **Sanitized Fields**: Only `incident_id`, `project_id`, `error_type`, `error_signature`, `error_message` (sanitized), and `created_at` are disclosed.
- **Redaction**:
  - `source_snippet` and raw code lines are **never** included in cross-project responses.
  - `file_path`, line, and column numbers are **never** included in cross-project responses.
  - User home paths (`C:\Users\<user>\...` or `/home/<user>/...`), auth tokens, passwords, and IP addresses are automatically redacted to `<USER_HOME>`, `<REDACTED>`, and `<HOST:PORT>`.
- **Known Authorization Limitations**: In the current MVP phase, cross-project sharing retrieves sanitized error summaries based on error signature matching across all registered projects in the shared MongoDB database. Multi-tenant workspace RBAC and fine-grained team permission flags are planned for subsequent production releases.

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
| `GET` | `/api/v1/projects/{project_id}/analytics/recurring` | 200 / 404 | **MongoDB Aggregation**: Top recurring errors grouped by error signature |
| `GET` | `/api/v1/projects/{project_id}/analytics` | 200 / 404 | High-level summary metrics (runs, success/fail counts, duration) |

### Command Runs

| Method | Path | Status | Description |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/runs` | 201 / 200 / 404 / 409 / 422 | Ingest command run event (idempotent) |
| `GET` | `/api/v1/runs/{event_id}` | 200 / 404 | Retrieve command run by event ID |

### Incidents & Memory Retrieval

| Method | Path | Status | Description |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/incidents` | 201 / 404 / 422 | Register an incident explicitly |
| `GET` | `/api/v1/incidents/{incident_id}` | 200 / 404 | Retrieve incident details |
| `GET` | `/api/v1/incidents/{incident_id}/history` | 200 / 404 | **Memory Retrieval**: Same-project vs privacy-sanitized cross-project historical incidents |

---

## Response Examples (Phase 3)

### Recurring Error Analytics (`GET /api/v1/projects/{project_id}/analytics/recurring`)

```json
{
  "success": true,
  "data": {
    "items": [
      {
        "error_signature": "sig_TypeError_4f8b2c1a9e3d",
        "error_type": "TypeError",
        "error_message": "data.map is not a function",
        "occurrence_count": 5,
        "latest_occurrence": "2026-10-10T12:30:00Z"
      }
    ],
    "total_groups": 1
  },
  "error": null
}
```

### Project Summary Analytics (`GET /api/v1/projects/{project_id}/analytics`)

```json
{
  "success": true,
  "data": {
    "project_id": "proj_shopapp",
    "total_runs": 12,
    "successful_runs": 8,
    "failed_runs": 4,
    "total_incidents": 4,
    "distinct_error_signatures": 2,
    "recent_incidents_24h": 4,
    "average_duration_ms": 1150
  },
  "error": null
}
```

### Cross-Project Incident History (`GET /api/v1/incidents/{incident_id}/history`)

```json
{
  "success": true,
  "data": {
    "current_incident_id": "inc_evt_demo_001",
    "error_signature": "sig_TypeError_4f8b2c1a9e3d",
    "same_project_matches": [
      {
        "incident_id": "inc_evt_demo_000",
        "event_id": "evt_demo_000",
        "project_id": "proj_shopapp",
        "error_type": "TypeError",
        "error_message": "data.map is not a function",
        "error_signature": "sig_TypeError_4f8b2c1a9e3d",
        "file_path": "src/App.jsx",
        "line": 24,
        "column": 8,
        "source_snippet": "data.map(item => item.name)",
        "diagnosis_status": "pending",
        "created_at": "2026-10-10T10:00:00Z"
      }
    ],
    "cross_project_matches": [
      {
        "incident_id": "inc_evt_other_99",
        "project_id": "proj_billing",
        "error_type": "TypeError",
        "error_signature": "sig_TypeError_4f8b2c1a9e3d",
        "error_message": "data.map is not a function in <PATH>\\view.js",
        "created_at": "2026-10-09T18:00:00Z",
        "diagnosis_summary": null,
        "fix_status": null
      }
    ]
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
| `incidents` | `idx_incidents_project_signature_created` | `{ project_id: 1, error_signature: 1, created_at: -1 }` | **MongoDB Aggregation**: Fast recurring error grouping and same-project history |
| `incidents` | `idx_incidents_signature_created` | `{ error_signature: 1, created_at: -1 }` | **Cross-Project Memory**: Retrieval across all projects by signature |
