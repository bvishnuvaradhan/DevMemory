# DevMemory Security & Multi-Language Demonstrations

This directory contains standalone, minimal demo programs showcasing DevMemory's core capabilities:
- **Language-Independent Diagnostics**: Automatic error detection and stack parsing across Python, Node.js, and shell commands.
- **Curated Knowledge Base Grounding**: Immediate recommendations from curated programming knowledge without requiring external LLM API calls.
- **Strict Multi-Tenant Isolation**: Separation of project memories, commands, and incidents.
- **Comprehensive Secret Redaction**: Prevention of credential leaks (MongoDB URIs, API keys, tokens) in console output and persistent backend storage.
- **Unverified Fix Guarantee**: General knowledge and unverified precedents are never marked as proven resolutions.

---

## Demo Catalog

| File | Language | Purpose | Expected Error | Redaction / Protection Checked |
| :--- | :--- | :--- | :--- | :--- |
| `demo1_multilang_py.py` | Python | Source-aware Python traceback analysis | `TypeError: unsupported operand type` | Project-scoped isolation |
| `demo1_multilang_js.js` | JavaScript | Language-independent Node.js traceback analysis | `TypeError: Cannot read properties of undefined` | Safe multi-language frame parsing |
| `demo2_invalid_input.py` | Python | Syntax and JSON configuration parsing errors | `json.decoder.JSONDecodeError` | Curated Knowledge Base resolution match |
| `demo3_env_protection.py` | Python | Environment variable missing configuration | `KeyError: Missing required environment variables` | Environment variable name safety |
| `demo4_sensitive_redaction.py` | Python | Secret redaction in stderr and command output | Simulated connection failure with fake secrets | API keys, MongoDB URIs, and GitHub tokens masked |

---

## Safe Execution Instructions

### Prerequisites
1. Ensure your DevMemory workspace is initialized:
   ```bash
   devmemory init
   ```
2. (Optional) Run the DevMemory backend API server:
   ```bash
   uvicorn server.app.main:app --port 8000
   ```
   *Note: If the backend is offline, DevMemory runs locally with graceful offline diagnostics.*

### Running the Demos

#### Demo 1: Multi-Language Python
```bash
devmemory run -- python examples/security-demos/demo1_multilang_py.py
```
**Observed Behavior**:
- Identifies failing line (`total = base_limit + bonus_units`).
- Displays code context window with line marker `>`.
- Matches curated Python knowledge base entry for type operations.

#### Demo 1: Multi-Language JavaScript / Node.js
```bash
devmemory run -- node examples/security-demos/demo1_multilang_js.js
```
**Observed Behavior**:
- Parses Node.js stack trace.
- Flags undefined property access (`session.auth.token`).
- Recommends defensive optional chaining (`session?.auth?.token`).

#### Demo 2: Input Validation Error
```bash
devmemory run -- python examples/security-demos/demo2_invalid_input.py
```
**Observed Behavior**:
- Detects JSON parsing failure.
- Suggests checking JSON delimiter syntax and validating payload against schema.

#### Demo 3: Environment Variable Protection
```bash
devmemory run -- python examples/security-demos/demo3_env_protection.py
```
**Observed Behavior**:
- Flags missing configuration keys (`DATABASE_URL`, `API_SIGNING_SECRET`).
- Advises populating `.env` template without logging any system environment values.

#### Demo 4: Sensitive Secret Redaction
```bash
devmemory run -- python examples/security-demos/demo4_sensitive_redaction.py
```
**Observed Behavior**:
- Plaintext database URI `mongodb://cluster_admin:SuperSecretPassword999@...` is redacted to `mongodb://cluster_admin:[REDACTED_PASSWORD]@...` or `mongodb://[REDACTED_AUTH]@...`.
- Client API key `sk-live-DEMO...` is redacted to `[REDACTED_API_KEY]`.
- GitHub token `ghp_DEMO...` is redacted to `[REDACTED_SECRET]`.
- All persisted incident records on MongoDB backend contain only sanitized text.

---

## Security Verification Guarantees

1. **Secret Redaction**:
   All tokens matching standard credential formats (PEM certificates, Bearer tokens, cloud API keys, password flags, DB URIs) are scrubbed before terminal printing and before database transmission.

2. **Project Isolation**:
   Incidents logged under one project are never visible to another project unless explicit cross-project access (`has_cross_project_read=True` and `is_public=True`) is authorized.

3. **Curated Knowledge Integrity**:
   Items from the general programming knowledge base provide reference guidance (`source="knowledge_base"`) and are never misrepresented as verified project fixes.
