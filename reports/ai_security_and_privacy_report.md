# DevMemory — AI Security & Privacy Hardening Report (Phase 5.2)

**Author:** Member 3 — AI & Cross-Project Memory Lead  
**Component:** AI Engine (`ai_engine/`)  
**Branch:** `feature/member-3-ai-memory`  
**Dataset Version:** `2.1.0` (56 scenarios)  
**Regression Test Count:** 72 passed (57 unit tests + 15 security regression tests)  

---

## 1. Threat Model & Data-Flow Findings

### 1.1 Outbound Data-Flow Map
In the DevMemory architecture, user diagnostic data flows from `DiagnosisRequest` into the external LLM through the following pipeline:

```
[Developer Command / Execution Failure]
         │
         ▼
[DiagnosisRequest] (command, error_message, stack_trace, locations, source_snippets)
         │
         ├────────────────────────► [3-Level Memory Retrieval]
         │                            ├── Level 1: Curated Knowledge Base
         │                            ├── Level 2: Project Incidents (Sanitized)
         │                            └── Level 3: Cross-Project Precedents (Auth-gated & Sanitized)
         │
         ▼
[Privacy Sanitization Pipeline]
   ├── Redact Secrets (Regex, heuristics, multi-line blocks)
   ├── Normalize Local Paths (~/...)
   ├── Filter High-Risk Files (.env, id_rsa, service-account.json)
   ├── Truncate Frames & Code Budget (Minimization)
   └── Escape Prompt Delimiters (Prompt Injection Defense)
         │
         ▼
[Outbound Policy Safety Validation] (validate_outbound_payload_safety)
   ├── PASS ──► [LLM Client / Groq API Payload]
   └── FAIL ──► [Deterministic Local Fallback] (Fail-Closed)
         │
         ▼
[Post-Processing Sanitization] (Scrub echoes from LLM response)
         │
         ▼
[DiagnosisResponse] (Strictly fix_status = unverified)
```

### 1.2 Vulnerabilities Discovered During Audit
1. **Unsanitized Memory Precedents in Level 2:**
   - *Discovery:* Level 2 project incident resolutions were passed directly to prompt construction without sanitization. An internal secret or machine path logged in a past incident could be transmitted to external LLM providers.
   - *Remediation:* Enforced `redact_secrets` and `sanitize_file_path` on all memory levels (`_match_project_memory`, `_match_general_knowledge`, `_match_cross_project_memory`, and `build_diagnosis_prompt`).
2. **Missing High-Risk Credential Redaction:**
   - *Discovery:* PEM private keys (`BEGIN RSA PRIVATE KEY`), X.509 certificates, session cookies, Basic Auth headers, and cloud tokens (Slack `xoxb-`, Stripe `sk_live_`, SendGrid `SG.`) were not covered by standard API key regexes.
   - *Remediation:* Added multi-line block matchers and specific token recognizers in `ai_engine/privacy.py`.
3. **Sensitive Configuration File Exfiltration via Snippets:**
   - *Discovery:* If a developer incident captured lines from `.env`, `.env.production`, or `service-account.json`, the full content could be sent as a source snippet.
   - *Remediation:* Implemented `is_sensitive_file()` filter in `sanitize_source_snippet()`. Content from sensitive files is completely stripped and replaced with `[EXCLUDED_SENSITIVE_FILE_CONTENT]`.
4. **Prompt Delimiter Spoofing (Injection Breakout):**
   - *Discovery:* Attackers embedding `=== INSTRUCTIONS ===` in raw error logs or traces could spoof section headers.
   - *Remediation:* Implemented `escape_prompt_delimiters()` which safely converts untrusted `=== ... ===` strings to `--- ... ---`.
5. **No Offline Privacy Opt-Out Mechanism:**
   - *Discovery:* There was no programmatic or environment-based switch for air-gapped or sensitive environments to disable external inference.
   - *Remediation:* Added `disable_external_inference` parameter and `DEV_MEMORY_DISABLE_EXTERNAL_AI` / `AI_PRIVACY_OFFLINE_ONLY` environment variable support in `diagnose_error()`.
6. **Provider Exception Leaks:**
   - *Discovery:* HTTP or connection failures in `GroqLLMClient` raised raw exceptions that could contain authorization headers or query parameters in the stack trace.
   - *Remediation:* Masked exception messages via `redact_secrets(str(exc))` and detached root causes using `from None`.

---

## 2. Fields Allowed & Blocked in Outbound Requests

| Category | Field / Content | Status | Treatment & Defense |
| :--- | :--- | :---: | :--- |
| **Identifiers** | `event_id` | **ALLOWED** | Preserved for request-response correlation. |
| **Identifiers** | `project_id` | **BLOCKED (Outbound)** | Omitted from prompts sent to LLM; only active project ID used locally. |
| **Execution** | `command` | **SANITIZED** | Paths normalized, secrets redacted, capped at 500 characters. |
| **Execution** | `exit_code` | **ALLOWED** | Clean integer/string code. |
| **Diagnostics** | `error_message` | **SANITIZED** | Secrets redacted, paths normalized, capped at 2,000 characters. |
| **Diagnostics** | `stack_trace` | **MINIMIZED** | Redacted, middle frames truncated if > 3,000 characters. |
| **Code** | `locations` | **BUDGETED** | Local machine paths normalized to `~/...`, max 10 frames. |
| **Code** | `source_snippets` | **FILTERED** | Max 3 snippets, max 40 lines/2,000 chars each; **Blocked** if file is `.env*`, `*.pem`, `id_*`, or credentials JSON. |
| **Memory** | General KB Matches | **SANITIZED** | Max 3 items; title and guidance sanitized. |
| **Memory** | Project Incidents | **SANITIZED** | Max 3 items; resolution summaries and explanations scrubbed. |
| **Memory** | Cross-Project Incidents | **FILTERED** | Strict server-side authorization check; private incidents strictly blocked; sanitized summaries only. |
| **Credentials** | API Keys, Tokens, Passwords | **STRICTLY BLOCKED** | Redacted across all outbound fields. |
| **Credentials** | PEM Private Keys & Certs | **STRICTLY BLOCKED** | Multi-line redaction + outbound policy fail-closed check. |

---

## 3. Privacy Configuration & Opt-Out Behavior

DevMemory provides a zero-leakage offline opt-out mechanism:

1. **Programmatic Opt-Out:**
   ```python
   response = diagnose_error(
       request=req,
       auth_context=auth,
       disable_external_inference=True,
   )
   ```
2. **Environment Variable Opt-Out:**
   ```bash
   export DEV_MEMORY_DISABLE_EXTERNAL_AI=true
   # or
   export AI_PRIVACY_OFFLINE_ONLY=true
   ```
3. **Behavior When Opted Out:**
   - The AI engine **never invokes Groq** or any remote HTTP transport.
   - Diagnoses are synthesized entirely from local Level 1 curated knowledge items and Level 2 project incidents.
   - `uncertainty_description` explicitly documents: `"Fallback diagnosis synthesized from local knowledge base (External AI inference disabled by privacy configuration)."`.
   - `fix_status` remains strictly `unverified`.

---

## 4. Test Cases, Commands & Exact Results

### 4.1 Regression Suite Execution
Executed complete test suite via `pytest tests/ -v`:

```bash
python -m pytest tests/ -v
```

**Results:**
- `tests/test_security.py`: 15 passed in 0.19s
  - `test_redact_private_keys_pem`: PASSED
  - `test_redact_certificates_pem`: PASSED
  - `test_redact_url_encoded_db_credentials`: PASSED
  - `test_redact_cookies_and_auth_headers`: PASSED
  - `test_redact_cloud_vendor_tokens`: PASSED
  - `test_sensitive_file_snippet_exclusion`: PASSED
  - `test_snippet_and_stack_trace_truncation`: PASSED
  - `test_prompt_injection_delimiter_escaping`: PASSED
  - `test_outbound_payload_safety_validator`: PASSED
  - `test_offline_privacy_opt_out_disables_external_llm`: PASSED
  - `test_outbound_prompt_never_contains_raw_secrets`: PASSED
  - `test_response_sanitization_prevents_echoed_secrets`: PASSED
  - `test_provider_failure_does_not_leak_raw_payload_in_exception`: PASSED
  - `test_cross_project_zero_leakage_and_sanitization`: PASSED
  - `test_normal_diagnostic_context_preserved`: PASSED
- `tests/test_diagnosis.py`: 5 passed
- `tests/test_evaluation.py`: 4 passed
- `tests/test_knowledge.py`: 4 passed
- `tests/test_llm_client.py`: 4 passed
- `tests/test_matching.py`: 7 passed
- `tests/test_privacy.py`: 8 passed
- `tests/test_prompts.py`: 3 passed
- `tests/test_retrieval.py`: 12 passed
- `tests/test_schemas.py`: 10 passed
- **Total: 72 passed, 0 failed in 1.87s.**

### 4.2 Offline Evaluation Benchmark Execution
Executed 56-scenario evaluation harness:

```bash
python -m ai_engine.evaluation.runner
```

**Results:**
- **Total Scenarios Evaluated:** 56
- **Passed:** 56
- **Failed:** 0
- **SecretRedactionRate:** 100.0%
- **CrossProjectAuthAccuracy:** 100.0%
- **ProjectScopingAccuracy:** 100.0%
- **UnverifiedStatusCompliance:** 100.0%
- **Quality Pass Rate:** 100.0%

---

## 5. Known Limitations & Residual Risks

1. **Heuristic & Pattern-Based Boundary:**
   - Secret redaction is defense-in-depth, combining pattern matching, file-type exclusion, token budgeting, and outbound safety gates. However, high-entropy proprietary strings without known prefixes or key-value context cannot be mathematically guaranteed to be detected.
   - Organizations must continue enforcing pre-commit secret scanners (e.g. `gitleaks`, `trufflehog`) upstream.
2. **Third-Party Provider Guarantees:**
   - When external LLM inference is enabled (`disable_external_inference=False`), requests are routed to Groq Cloud API. Data retention and processing at the provider level depend on the organization's enterprise agreement with Groq; client-side controls ensure minimization and redaction prior to wire transmission.
3. **Cross-Member Dependencies for Storage:**
   - In-memory incident candidate filtering correctly enforces `is_public` and server-side authorization. When integrating with Member 2's MongoDB repository in Phase 6, database query filters must mirror these constraints at the database index level.
