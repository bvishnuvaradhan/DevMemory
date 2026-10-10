# DevMemory

AI-powered developer troubleshooting and persistent developer-memory platform.

> **Track 3:** Developer Tools for Production Use Cases  
> **Philosophy:** *Debug once, learn across projects, and solve similar problems faster.*

---

## Getting Started (Windows PowerShell)

### 1. Prerequisites
- **Python 3.9+** (Python 3.13 tested)
- **Node.js 18+** (Optional, for JavaScript/TypeScript error analysis)
- **PowerShell 5.1+** or **PowerShell 7+**

### 2. Create and Activate a Virtual Environment

From the root of the repository:

```powershell
# Create the virtual environment
python -m venv .venv

# Activate the virtual environment
.\.venv\Scripts\Activate.ps1
```

*(If script execution is disabled in PowerShell, enable it for the current process: `Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned`)*

### 3. Install DevMemory in Editable Mode

Install DevMemory along with development dependencies (`pytest`):

```powershell
pip install -e ".[dev]"
```

### 4. Running the Complete Test Suite

Execute all 45 automated unit and end-to-end fixture tests:

```powershell
pytest -v
```

---

## Reproducible Demo Guide

DevMemory ships with self-contained, deterministic test fixtures located in the `fixtures/` directory.

### Demo 1: Project Initialization

Initialize DevMemory in any project root directory:

```powershell
devmemory init --name demo-service
```

This creates a local configuration at `.devmemory/config.json`:
- `project_id`: Unique identifier (UUID4) preserved across re-runs.
- `project_name`: Name of the registered project.
- `project_root`: Resolved absolute project path.
- `backend_url`: Target backend ingestion endpoint (defaults to `http://localhost:8000`).
- `created_at`: UTC timestamp of project initialization.
- `config_version`: Version identifier for configuration schema evolution.

*(Note: `.devmemory/` is git-ignored and never contains secrets or API credentials.)*

---

### Demo 2: Running a Successful Command

Run the success verification fixture:

```powershell
devmemory run -- python fixtures/successful/verify.py
```

**Observed Terminal Output:**
```text
DevMemory Success Fixture: All systems operational.
Health check: PASS

DevMemory Run Summary: PASSED
  Command:   python fixtures/successful/verify.py
  Directory: D:\3rd YEAR ODD\DevMemory
  Duration:  32.7ms

Backend Status: Offline (Local mode)
```
- **Exit Code:** `0`
- **Behavior:** No error diagnosis is generated for successful runs.

---

### Demo 3: Python Failure with Source-Aware Diagnostics

Run the failing Python fixture:

```powershell
devmemory run -- python fixtures/python_failing/app.py
```

**Observed Terminal Output:**
```text
Processing transaction for account: ACC-90210
Traceback (most recent call last):
  File "D:\3rd YEAR ODD\DevMemory\fixtures\python_failing\app.py", line 17, in <module>
    process_transaction("ACC-90210", 1500.0, 0)
  File "D:\3rd YEAR ODD\DevMemory\fixtures\python_failing\app.py", line 13, in process_transaction
    return compute_ratio(balance, units)
  File "D:\3rd YEAR ODD\DevMemory\fixtures\python_failing\app.py", line 8, in compute_ratio
    return numerator / denominator
ZeroDivisionError: float division by zero

DevMemory Run Summary: FAILED (Exit code: 1)
  Command:   python fixtures/python_failing/app.py
  Directory: D:\3rd YEAR ODD\DevMemory
  Duration:  73.8ms

--- Source-Aware Error Analysis (Python) ---
  Error Type: ZeroDivisionError
  Message:    float division by zero
  Location:   D:\3rd YEAR ODD\DevMemory\fixtures\python_failing\app.py:8 in `compute_ratio`

  Code Context (app.py:8):
         3 | Throws a ZeroDivisionError with explicit stack depth.
         4 | """
         5 | 
         6 | def compute_ratio(numerator: float, denominator: float) -> float:
         7 |     # Explicit failing operation on line 8
    >    8 |     return numerator / denominator
         9 | 
        10 | 
        11 | def process_transaction(account_id: str, balance: float, units: int) -> float:
        12 |     print(f"Processing transaction for account: {account_id}")
        13 |     return compute_ratio(balance, units)

  Additional Stack Frames (2):
    - D:\3rd YEAR ODD\DevMemory\fixtures\python_failing\app.py:17 (<module>)
    - D:\3rd YEAR ODD\DevMemory\fixtures\python_failing\app.py:13 (process_transaction)

Backend Status: Offline (Local mode)
```
- **Exit Code:** `1` propagated directly to the shell.
- **Diagnostics:** Locates primary frame at line 8 in `compute_ratio`, extracts surrounding context, and highlights the exact failing statement.

---

### Demo 4: JavaScript/Node.js Failure Diagnostics

Run the failing JavaScript fixture (requires Node.js):

```powershell
devmemory run -- node fixtures/javascript_failing/index.js
```

**Observed Terminal Output:**
```text
Rendering dashboard for session: sess_4815162342
D:\3rd YEAR ODD\DevMemory\fixtures\javascript_failing\index.js:8
    return user.profile.settings.theme;
                ^

TypeError: Cannot read properties of undefined (reading 'profile')
    at getUserProfile (D:\3rd YEAR ODD\DevMemory\fixtures\javascript_failing\index.js:8:17)
    at renderDashboard (D:\3rd YEAR ODD\DevMemory\fixtures\javascript_failing\index.js:13:12)
    at Object.<anonymous> (D:\3rd YEAR ODD\DevMemory\fixtures\javascript_failing\index.js:21:1)

DevMemory Run Summary: FAILED (Exit code: 1)
  Command:   node fixtures/javascript_failing/index.js
  Directory: D:\3rd YEAR ODD\DevMemory
  Duration:  87.3ms

--- Source-Aware Error Analysis (Javascript) ---
  Error Type: TypeError
  Message:    Cannot read properties of undefined (reading 'profile')
  Location:   D:\3rd YEAR ODD\DevMemory\fixtures\javascript_failing\index.js:8:17 in `getUserProfile`

  Code Context (index.js:8):
         3 |  * Throws a TypeError accessing a nested property on undefined.
         4 |  */
         5 | 
         6 | function getUserProfile(user) {
         7 |     // Explicit failing operation on line 8
    >    8 |     return user.profile.settings.theme;
         9 | }
        10 | 
        11 | function renderDashboard(session) {
        12 |     console.log("Rendering dashboard for session:", session.sessionId);
        13 |     return getUserProfile(session.user);

  Additional Stack Frames (2):
    - D:\3rd YEAR ODD\DevMemory\fixtures\javascript_failing\index.js:13 (renderDashboard)
    - D:\3rd YEAR ODD\DevMemory\fixtures\javascript_failing\index.js:21 (Object.<anonymous>)

Backend Status: Offline (Local mode)
```

---

## Security, Privacy & Reliability Guarantees

1. **Path Boundary Containment:** Source snippet extraction strictly validates that file paths resolve within the project directory root. Directory traversal attempts (`../`) and symlink escapes are rejected.
2. **Local Secret Redaction:** Output text is scanned and scrubbed for API keys, personal access tokens, passwords, and database URIs before any network transmission.
3. **Safe Subprocess Execution:** Commands are executed as argument vectors without `shell=True`, preventing shell injection vulnerabilities.
4. **Offline Resilience:** If the DevMemory backend service is unreachable, all local source-aware diagnostics continue functioning with zero data loss or CLI crashes.

---

## Project Structure

```text
DevMemory/
├── fixtures/
│   ├── python_failing/
│   │   └── app.py
│   ├── javascript_failing/
│   │   └── index.js
│   └── successful/
│       └── verify.py
├── src/
│   └── devmemory/
│       ├── __init__.py
│       ├── runner.py
│       ├── cli/
│       │   ├── __init__.py
│       │   └── main.py
│       ├── diagnostics/
│       │   ├── __init__.py
│       │   ├── models.py
│       │   ├── python_parser.py
│       │   ├── javascript_parser.py
│       │   └── snippets.py
│       └── integration/
│           ├── __init__.py
│           ├── models.py
│           └── client.py
├── tests/
│   ├── test_cli.py
│   ├── test_diagnostics.py
│   ├── test_integration.py
│   └── test_e2e_fixtures.py
├── .gitignore
├── LICENSE
├── pyproject.toml
└── README.md
```
