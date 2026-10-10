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

## Architecture & Data Contracts (Phases 1 & 2)

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

## Error Signature Normalization

Every incident receives a normalized `error_signature`:
- Hexadecimal addresses (`0x...`) $\to$ `<hex>`
- Absolute file paths $\to$ `<path>`
- UUIDs and hashes $\to$ `<uuid>`, `<hash>`
- Embedded line/column numbers $\to$ `<loc>`
- Timestamps $\to$ `<datetime>`

This creates a stable grouping key (e.g., `sig_TypeError_a1b2c3d4e5f6`) used for historical incident grouping.

---

## Implemented API Endpoints

### Health Check

| Method | Path | Status | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/health` | 200 / 503 | Root health check |
| `GET` | `/api/v1/health` | 200 / 503 | Versioned health check |
| `GET` | `/docs` | 200 | Interactive OpenAPI / Swagger UI |

### Projects

| Method | Path | Status | Description |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/projects` | 201 / 409 | Register a project |
| `GET` | `/api/v1/projects` | 200 | List registered projects (paginated) |
| `GET` | `/api/v1/projects/{project_id}` | 200 / 404 | Retrieve project details |
| `GET` | `/api/v1/projects/{project_id}/runs` | 200 / 404 | List project runs (supports `status=success\|failure`, `limit`, `skip`) |
| `GET` | `/api/v1/projects/{project_id}/incidents` | 200 / 404 | List project incidents (paginated) |

### Command Runs

| Method | Path | Status | Description |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/runs` | 201 / 200 / 404 / 409 / 422 | Ingest command run event (idempotent) |
| `GET` | `/api/v1/runs/{event_id}` | 200 / 404 | Retrieve command run by event ID |

### Incidents

| Method | Path | Status | Description |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/incidents` | 201 / 404 / 422 | Register an incident explicitly |
| `GET` | `/api/v1/incidents/{incident_id}` | 200 / 404 | Retrieve incident details |

---

## Request & Response Examples

### Register Project (`POST /api/v1/projects`)

**Request**:
```json
{
  "name": "ShopApp Frontend",
  "project_id": "proj_shopapp",
  "language": "javascript",
  "settings": {
    "framework": "react"
  }
}
```

**Response (HTTP 201 Created)**:
```json
{
  "success": true,
  "data": {
    "project_id": "proj_shopapp",
    "name": "ShopApp Frontend",
    "language": "javascript",
    "settings": {
      "framework": "react"
    },
    "created_at": "2026-10-10T12:00:00Z",
    "updated_at": "2026-10-10T12:00:00Z"
  },
  "error": null
}
```

---

### Ingest Failed Command Run (`POST /api/v1/runs`)

**Request**:
```json
{
  "event_id": "evt_demo_001",
  "project_id": "proj_shopapp",
  "command": "npm test",
  "exit_code": 1,
  "duration_ms": 1250,
  "stdout": "",
  "stderr": "TypeError: data.map is not a function",
  "environment": {
    "os": "Windows",
    "runtime_version": "v22.19.0"
  },
  "error_context": {
    "error_type": "TypeError",
    "message": "data.map is not a function",
    "file_path": "src/App.jsx",
    "line": 24,
    "column": 8,
    "snippet": "data.map(item => item.name)"
  }
}
```

**Response (HTTP 201 Created)**:
```json
{
  "success": true,
  "data": {
    "event_id": "evt_demo_001",
    "project_id": "proj_shopapp",
    "command": "npm test",
    "exit_code": 1,
    "status": "failure",
    "duration_ms": 1250,
    "stdout": "",
    "stderr": "TypeError: data.map is not a function",
    "started_at": "2026-10-10T12:00:00Z",
    "finished_at": "2026-10-10T12:00:01.250000Z",
    "created_at": "2026-10-10T12:00:01Z",
    "environment": {
      "os": "Windows",
      "runtime_version": "v22.19.0",
      "git_branch": null,
      "git_commit": null
    },
    "error_context": {
      "error_type": "TypeError",
      "message": "data.map is not a function",
      "file_path": "src/App.jsx",
      "line": 24,
      "column": 8,
      "snippet": "data.map(item => item.name)"
    },
    "idempotent": false,
    "incident_id": "inc_evt_demo_001"
  },
  "error": null
}
```

---

## MongoDB Indexes and Schema Validation

Index initialization runs automatically during FastAPI startup (`lifespan`) and is completely idempotent:

- **`projects`**:
  - `idx_projects_project_id_unique`: Unique on `project_id`.
  - Schema validator ensuring `project_id`, `name`, `created_at`, `updated_at`.
- **`command_runs`**:
  - `idx_runs_event_id_unique`: Unique on `event_id`.
  - `idx_runs_project_started_at`: Compound on `{project_id: 1, started_at: -1}`.
  - Schema validator ensuring `event_id`, `project_id`, `command`, `exit_code`, `duration_ms`.
- **`incidents`**:
  - `idx_incidents_incident_id_unique`: Unique on `incident_id`.
  - `idx_incidents_project_event_unique`: Partial unique on `{project_id: 1, event_id: 1}` where `event_id` is a string.
  - `idx_incidents_project_created_at`: Compound on `{project_id: 1, created_at: -1}`.
  - `idx_incidents_error_signature`: Index on `error_signature`.
  - Schema validator ensuring `incident_id`, `project_id`, `error_type`, `error_message`, `error_signature`.
