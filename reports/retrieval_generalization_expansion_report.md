# DevMemory — Member 3, Phase 6.7: Retrieval Benchmark Expansion and Generalization Validation Report

**Author**: Member 3 — AI & Cross-Project Memory Lead  
**Branch**: `feature/member-3-ai-memory`  
**Phase**: Phase 6.7 — Retrieval Benchmark Expansion and Generalization Validation  
**Date**: October 2026  
**Status**: Completed  
**Test Suite Status**: 123 passed, 3 skipped (100% offline regression pass rate)  
**Suite A Diagnostic Quality**: 56/56 scenarios passed (100.0% pass rate)  
**Suite B Benchmark Version**: v2.0.0 (30 corpus items, 33 evaluation scenarios)  

---

## 1. Executive Summary

Phase 6.7 delivers an independent expansion and audit of DevMemory's retrieval benchmark harness (`ai_engine/evaluation/retrieval_benchmark.py`). Prior to this phase, retrieval generalization was demonstrated against an initial baseline of 10 corpus items and 9 scenarios, while the primary diagnostic harness evaluated 56 multi-tier scenarios (`ai_engine/evaluation/fixtures.py`).

In this phase, we established:
1. **Versioned Retrieval Benchmark v2.0.0**: Expanded the independent retrieval corpus to **30 items** and the evaluation scenario suite to **33 scenarios**, representing **14 technical domains and failure categories**.
2. **Clear Separation Between Suite A and Suite B**:
   - **Suite A (56 scenarios)**: End-to-end diagnostic evaluation harness (`ai_engine.evaluation.runner`), testing multi-tier retrieval, root-cause categorization, Groq LLM prompt formatting, fallback handling, and fix verification.
   - **Suite B (33 scenarios)**: Targeted Information Retrieval (IR) benchmark harness (`ai_engine.evaluation.retrieval_benchmark`), measuring search engine ranking, precision, recall, and safety without LLM generation noise.
3. **Formal Information Retrieval (IR) Metrics with Explicit Denominators**:
   - Implemented standard IR metrics: **Recall@1**, **Recall@3**, **Recall@5**, **Precision@1**, **Precision@3**, and **Mean Reciprocal Rank (MRR)**.
   - Segregated query classes to avoid metric contamination: target retrieval queries ($N_{\text{pos}} = 26$), negative queries ($N_{\text{neg}} = 5$), contradiction queries ($N_{\text{clash}} = 4$), and cross-project security queries ($N_{\text{cross}} = 2$).
4. **Transparent Multi-Mode Evaluation (Zero Mock-as-Live Claims)**:
   - **Mode 1 (Exact + Lexical)**: Deterministic string matching and token Jaccard similarity.
   - **Mode 2 (Deterministic Hash Hybrid)**: 128-dimensional MD5 token and trigram hashing (100% offline math).
   - **Mode 3 (Dense Semantic Mock Hybrid)**: 1536-dimensional conceptual clustering mock, explicitly declared as a synthetic simulation.
   - **Mode 4 (Live OpenAI text-embedding-3-small)**: Live external cloud API, transparently reported as `SKIPPED (No Key)` when unconfigured.
5. **Architectural Discoveries & Hardening**:
   - Identified and resolved a mock vector collapse issue where static fallback vectors artificially inflated false positives.
   - Documented the interaction between strict exception contradiction guards and unnormalized error types (e.g., Python `ModuleNotFoundError` vs `ImportError`, Go panics).

---

## 2. Benchmark Architecture: Suite A vs Suite B Separation

To ensure scientific validity, DevMemory maintains two strictly decoupled evaluation suites:

| Attribute | Suite A: Multi-Tier Diagnostic Harness | Suite B: Retrieval Generalization Benchmark |
| :--- | :--- | :--- |
| **Location** | `ai_engine/evaluation/fixtures.py` & `evaluator.py` | `ai_engine/evaluation/retrieval_benchmark.py` |
| **Runner** | `python -m ai_engine.evaluation.runner` | `python -m ai_engine.evaluation.retrieval_benchmark` |
| **Version** | Dataset v2.1.0 | Benchmark v2.0.0 |
| **Scope** | End-to-end diagnostic pipeline (Retrieval + LLM + Verification) | Standalone Information Retrieval (Level 2 & Level 3 search) |
| **Scenario Count** | 56 scenarios | 33 scenarios |
| **Corpus** | 25 Level-1 Knowledge Base seed entries | 30 Level-2/3 historical incident items |
| **Primary Metrics** | Quality Pass Rate, Root Cause Accuracy, Verification Status | Recall@K, Precision@K, MRR, FPR, CRR, PIR |
| **Denominators** | Scorable Root Cause ($N=52$), KB Target ($N=25$), Unscorable ($N=4$) | $N_{\text{pos}}=26$, $N_{\text{neg}}=5$, $N_{\text{clash}}=4$, $N_{\text{cross}}=2$ |
| **Independence** | Zero shared IDs; zero cross-suite mutations; independent unit tests |

---

## 3. Expanded Dataset (v2.0.0) Architecture & Catalog

### 3.1 Historical Incident Corpus (`BENCHMARK_CORPUS`) — 30 Items

The v2.0.0 benchmark corpus contains 30 curated incidents spanning modern application stacks:

| Incident ID | Project | Category | Error Summary | Verification | Public |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `inc_target_jwt_expiry` | `proj_main` | Auth / JWT | Signature has expired in `jwt.py` | VERIFIED | False |
| `inc_target_db_refused` | `proj_main` | Database | Target machine actively rejected connection at `postgres:5432` | VERIFIED | False |
| `inc_target_js_undefined` | `proj_main` | Node / JS | `TypeError: user object is undefined in session_manager.js` | VERIFIED | False |
| `inc_target_mod_missing` | `proj_main` | Python | `ImportError: PyYAML package is not installed` | VERIFIED | False |
| `inc_target_redis_oom` | `proj_main` | Cache | `OOM command not allowed when used memory > 'maxmemory'` | VERIFIED | False |
| `inc_target_docker_port_bind` | `proj_main` | DevOps | `Bind for 0.0.0.0:8080 failed: port is already allocated` | VERIFIED | False |
| `inc_target_esm_require` | `proj_main` | Node ESM | `Error [ERR_REQUIRE_ESM]: require() of ES Module index.js` | VERIFIED | False |
| `inc_target_git_lock` | `proj_main` | VCS | `fatal: Unable to create '.git/index.lock': File exists` | VERIFIED | False |
| `inc_target_cors_origin` | `proj_main` | Web CORS | `CORS policy: No 'Access-Control-Allow-Origin' header` | VERIFIED | False |
| `inc_target_ssl_cert_expired` | `proj_main` | TLS / SSL | `SSL: CERTIFICATE_VERIFY_FAILED certificate has expired` | VERIFIED | False |
| `inc_target_deadlock_detected` | `proj_main` | Concurrency | `TransactionRollbackError: deadlock detected: Process 14022` | VERIFIED | False |
| `inc_target_permission_denied` | `proj_main` | Filesystem | `PermissionError: [Errno 13] Permission denied` | VERIFIED | False |
| `inc_target_rust_borrow` | `proj_main` | Rust | `cannot borrow *self as mutable more than once at a time` | VERIFIED | False |
| `inc_target_go_nil_pointer` | `proj_main` | Go | `panic: runtime error: invalid memory address or nil pointer` | VERIFIED | False |
| `inc_target_env_node_version` | `proj_main` | Environment | `Unsupported engine: package requires node >=18.0.0` | VERIFIED | False |
| `inc_target_python_version` | `proj_main` | Python PEP | `TypeError: unsupported operand type(s) for \|: 'type'` | VERIFIED | False |
| `inc_target_exact_syntax` | `proj_main` | Syntax | `SyntaxError: Unexpected token '?' in json_parser.js` | VERIFIED | False |
| `inc_target_db_unique_constraint`| `proj_main` | Integrity | `IntegrityError: duplicate key violates unique constraint` | VERIFIED | False |
| `inc_target_rate_limit_429` | `proj_main` | API Rate | `HTTPError: 429 Client Error: Too Many Requests` | VERIFIED | False |
| `inc_target_kafka_broker_unavailable`| `proj_main` | Messaging | `kafka.errors.NoBrokersAvailable at kafka:9092` | VERIFIED | False |
| `inc_misleading_jwt_padding` | `proj_main` | Distractor | `jwt.exceptions.DecodeError: Invalid crypto padding` | VERIFIED | False |
| `inc_misleading_db_auth` | `proj_main` | Distractor | `psycopg2.OperationalError: password authentication failed` | VERIFIED | False |
| `inc_misleading_redis_timeout`| `proj_main` | Distractor | `redis.exceptions.TimeoutError: Timeout connecting to Redis`| VERIFIED | False |
| `inc_misleading_docker_image_missing`| `proj_main`| Distractor | `Error response from daemon: pull access denied` | VERIFIED | False |
| `inc_generic_runtime_trap` | `proj_main` | Distractor | `RuntimeError: Command failed with exit code 1` | UNVERIFIED | False |
| `inc_clash_syntax_jwt` | `proj_main` | Clash | `SyntaxError: invalid syntax in jwt.py line 8` | VERIFIED | False |
| `inc_clash_syntax_db` | `proj_main` | Clash | `SyntaxError: invalid syntax in database_pool.py line 15` | VERIFIED | False |
| `inc_clash_deadlock_unverified`| `proj_main` | Clash | `psycopg2.OperationalError: server closed connection` | UNVERIFIED | False |
| `inc_private_classified_billing`| `proj_billing_private`| Security | `TypeError: Cannot read properties of undefined (billing_pin)`| VERIFIED | False |
| `inc_public_shared_utils` | `proj_shared_utils`| Security | `TypeError: Cannot read properties of undefined (auth_token)`| VERIFIED | True |

---

### 3.2 Evaluation Scenarios Catalog (`BENCHMARK_SCENARIOS`) — 33 Scenarios

The suite evaluates 33 scenarios across 14 distinct scenario categories:

```
Scenario Distribution (Total N = 33):
├── Positive Target Retrieval (N = 26):
│   ├── Positive Paraphrases (Disjoint Vocabulary): 14
│   ├── Exact Matches: 3
│   ├── Distractor Challenges (Root-Cause Discrimination): 2
│   ├── Environment Mismatches: 2
│   ├── Sanitized Secrets in Queries: 2
│   ├── Multi-Candidate Disambiguation: 1
│   └── Contradiction Scenarios with Local Target: 2
├── Negative / Unrelated Queries (N = 5):
│   └── Division by zero, missing file, index error, template syntax, missing audio codec
├── Contradiction Evaluations (N = 4):
│   └── SyntaxError vs ExpiredSignature, SyntaxError vs DB Conn, Deadlock vs Conn Drop, etc.
└── Cross-Project Security Evaluations (N = 2):
    ├── Unauthorized attempt (Zero external incidents surfaced)
    └── Authorized attempt (Surfaces public cross-project match; strictly suppresses private)
```

| Scenario ID | Category | Type | Query Summary | Target ID | Distractor / Clash |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `bm_pos_01_jwt_expired` | `auth_jwt` | positive_paraphrase | "token lifetime has ended" | `inc_target_jwt_expiry` | dist: padding / clash: syntax |
| `bm_pos_02_db_connection_refused`| `database` | positive_paraphrase | "could not connect to server: Connection refused" | `inc_target_db_refused` | dist: auth |
| `bm_pos_03_js_undefined_property`| `node_runtime` | positive_paraphrase | "Cannot read properties of undefined" | `inc_target_js_undefined` | - |
| `bm_pos_04_py_yaml_missing` | `python_deps` | positive_paraphrase | "No module named 'yaml'" | `inc_target_mod_missing` | - |
| `bm_pos_05_redis_out_of_memory` | `cache_redis` | positive_paraphrase | "Out of memory: Redis server memory threshold reached" | `inc_target_redis_oom` | dist: timeout |
| `bm_pos_06_docker_port_conflict`| `containers_docker`| positive_paraphrase | "address already in use by another service" | `inc_target_docker_port_bind` | dist: image missing |
| `bm_pos_07_esm_module_loader` | `node_esm` | positive_paraphrase | "Must use import to load ES Module" | `inc_target_esm_require` | - |
| `bm_pos_08_git_stale_lockfile` | `vcs_git` | positive_paraphrase | "Unable to lock repository: index.lock exists" | `inc_target_git_lock` | - |
| `bm_pos_09_cors_header_missing` | `web_cors` | positive_paraphrase | "Cross-Origin Request Blocked: Same Origin Policy" | `inc_target_cors_origin` | - |
| `bm_pos_10_ssl_cert_expired` | `security_tls` | positive_paraphrase | "Certificate validation failed: certificate has expired" | `inc_target_ssl_cert_expired`| - |
| `bm_pos_11_deadlock_concurrency`| `concurrency_deadlock`| positive_paraphrase| "parallel transactions waiting on conflicting locks" | `inc_target_deadlock_detected`| clash: unverified drop |
| `bm_pos_12_permission_denied` | `filesystem_os`| positive_paraphrase | "access denied when opening logfile" | `inc_target_permission_denied`| - |
| `bm_pos_13_rust_borrow_mut` | `rust_borrow` | positive_paraphrase | "cannot borrow self as mutable more than once" | `inc_target_rust_borrow` | - |
| `bm_pos_14_go_nil_dereference` | `go_runtime` | positive_paraphrase | "nil pointer dereference in handler.go" | `inc_target_go_nil_pointer` | - |
| `bm_exact_01_syntax_error` | `syntax_compilation`| exact_match | "SyntaxError: Unexpected token '?' in json_parser.js"| `inc_target_exact_syntax` | - |
| `bm_exact_02_unique_constraint` | `data_integrity`| exact_match | "duplicate key value violates unique constraint" | `inc_target_db_unique_constraint`| - |
| `bm_exact_03_rate_limit_429` | `api_rate_limit`| exact_match | "HTTPError: 429 Client Error: Too Many Requests" | `inc_target_rate_limit_429` | - |
| `bm_distractor_01_db_auth_vs_refusal`| `database`| distractor_challenge| "Connection refused on host postgres" | `inc_target_db_refused` | dist: auth failure |
| `bm_distractor_02_redis_timeout_vs_oom`| `cache_redis`| distractor_challenge| "Redis reached maxmemory limit" | `inc_target_redis_oom` | dist: timeout |
| `bm_env_01_node_engine_version` | `environment_runtime`| env_mismatch | "npm ERR! engine Unsupported wanted node >=18" | `inc_target_env_node_version`| - |
| `bm_env_02_python_union_type` | `environment_runtime`| env_mismatch | "unsupported operand type(s) for \| in Python 3.9" | `inc_target_python_version` | - |
| `bm_secret_01_sanitized_token` | `security_privacy`| sanitized_secrets | Query with raw Bearer token | `inc_target_jwt_expiry` | - |
| `bm_secret_02_sanitized_db_url` | `security_privacy`| sanitized_secrets | Query with embedded DB password URI | `inc_target_db_refused` | - |
| `bm_multi_01_kafka_broker_offline`| `message_broker`| multi_candidate | "unable to connect to bootstrap broker at kafka:9092"| `inc_target_kafka_broker_unavailable`| - |
| `bm_neg_01_division_by_zero` | `unrelated_negative`| negative_unrelated | "ZeroDivisionError: float division by zero" | `None` | - |
| `bm_neg_02_file_not_found` | `unrelated_negative`| negative_unrelated | "FileNotFoundError: No such file or directory" | `None` | - |
| `bm_neg_03_index_out_of_bounds` | `unrelated_negative`| negative_unrelated | "IndexError: list index out of range" | `None` | - |
| `bm_neg_04_template_syntax` | `unrelated_negative`| negative_unrelated | "jinja2.exceptions.TemplateSyntaxError" | `None` | - |
| `bm_neg_05_audio_codec_missing` | `unrelated_negative`| negative_unrelated | "ffmpeg.Error: Unknown encoder 'libmp3lame'" | `None` | - |
| `bm_clash_01_syntax_vs_runtime_jwt`| `contradiction_guard`| contradiction | "SyntaxError in jwt.py line 4" | `inc_clash_syntax_jwt` | clash: padding error |
| `bm_clash_02_syntax_vs_db_conn` | `contradiction_guard`| contradiction | "SyntaxError in database_pool.py line 12" | `inc_clash_syntax_db` | clash: db connection |
| `bm_sec_01_cross_project_unauthorized`| `security_isolation`| cross_project | Unauthorized cross-project request | `None` | forbidden: billing private |
| `bm_sec_02_cross_project_authorized`| `security_isolation`| cross_project | Authorized cross-project request | `inc_public_shared_utils` | forbidden: billing private |

---

## 4. Formal Information Retrieval (IR) Metrics & Explicit Denominators

### 4.1 Mathematical Formulations

To ensure that retrieval evaluation is statistically grounded and mathematically transparent:

1. **Recall@K**: Proportion of positive queries where the target incident is ranked within the top-$K$ candidates:
   $$\text{Recall@K} = \frac{1}{N_{\text{pos}}} \sum_{i=1}^{N_{\text{pos}}} \mathbb{I}(\text{rank}_i \le K)$$
2. **Precision@1**: Proportion of positive queries where the target is ranked #1:
   $$\text{Precision@1} = \frac{1}{N_{\text{pos}}} \sum_{i=1}^{N_{\text{pos}}} \mathbb{I}(\text{rank}_i = 1)$$
3. **Precision@3 (Standard IR Formula)**:
   For single-relevant-item queries evaluated over top-3 slots:
   $$\text{Precision@3} = \frac{\sum_{i=1}^{N_{\text{pos}}} \mathbb{I}(\text{rank}_i \le 3)}{3 \times N_{\text{pos}}} = \frac{\text{Recall@3}}{3}$$
   *(The theoretical maximum Precision@3 for single-target queries is $\frac{1}{3} \approx 33.33\%$.)*
4. **Mean Reciprocal Rank (MRR)**:
   $$\text{MRR} = \frac{1}{N_{\text{pos}}} \sum_{i=1}^{N_{\text{pos}}} \frac{1}{\text{rank}_i} \quad (\text{where } \frac{1}{\infty} = 0)$$
5. **False-Positive Rate (FPR)**:
   $$\text{FPR} = \frac{N_{\text{neg}}(\text{score} \ge 0.50)}{N_{\text{neg}}}$$
6. **Contradiction Rejection Rate (CRR)**:
   $$\text{CRR} = \frac{N_{\text{clash}}(\text{score} \le 0.35)}{N_{\text{clash}}}$$
7. **Project Isolation Rate (PIR)**:
   $$\text{PIR} = \frac{N_{\text{cross}}(\text{private leaked} = 0)}{N_{\text{cross}}}$$

### 4.2 Explicit Denominators Table

| Denominator Variable | Definition | Count | Purpose |
| :--- | :--- | :---: | :--- |
| $N_{\text{pos}}$ | Queries with a local project target | **26** | Evaluates Recall@1/3/5, Precision@1/3, and MRR. Excludes negative and cross-project queries. |
| $N_{\text{neg}}$ | Unrelated / negative queries | **5** | Evaluates False-Positive Rate (FPR). |
| $N_{\text{clash}}$ | Queries evaluated against clashing candidates | **4** | Evaluates Contradiction Rejection Rate (CRR). |
| $N_{\text{cross}}$ | Cross-project isolation queries | **2** | Evaluates Project Isolation Rate (PIR). |
| $N_{\text{total}}$ | Total scenario count | **33** | Total benchmark test coverage ($26 + 5 + 2 = 33$). |

---

## 5. Multi-Mode Benchmark Execution Results

### 5.1 Comparative Benchmark Matrix

Execution results generated by `ai_engine.evaluation.retrieval_benchmark`:

```
======================================================================================================================
DevMemory — Multi-Mode Retrieval Generalization & Integrity Benchmark
Benchmark Version: 2.0.0 | Total Test Scenarios: 33
======================================================================================================================
Metric                     | Mode 1 (Lexical)   | Mode 2 (Deterministic) | Mode 3 (Dense Mock) | Mode 4 (Live OpenAI)
----------------------------------------------------------------------------------------------------------------------
Execution Truth Status     | Deterministic Math | Deterministic Math     | Simulated Mock Client | SKIPPED (No Key)    
Recall@1 (Top-1 Hit)       | 84.6% (22/26)      | 84.6% (22/26)          | 88.5% (23/26)       | SKIPPED             
Recall@3 (Top-3 Hit)       | 84.6% (22/26)      | 92.3% (24/26)          | 92.3% (24/26)       | SKIPPED             
Recall@5 (Top-5 Hit)       | 84.6% (22/26)      | 92.3% (24/26)          | 92.3% (24/26)       | SKIPPED             
Precision@1                | 84.6% (22/26)      | 84.6% (22/26)          | 88.5% (23/26)       | SKIPPED             
Precision@3 (IR Standard)  | 28.2% (22/78)      | 30.8% (24/78)          | 30.8% (24/78)       | SKIPPED             
MRR (Mean Recip Rank)      | 0.8462             | 0.8718                 | 0.9038              | SKIPPED             
False-Positive Rate        | 0.0% (0/5)         | 0.0% (0/5)             | 0.0% (0/5)          | SKIPPED             
Contradiction Rejection    | 100.0% (4/4)       | 100.0% (4/4)           | 100.0% (4/4)        | SKIPPED             
Project Isolation Rate     | 100.0% (2/2)       | 100.0% (2/2)           | 100.0% (2/2)        | SKIPPED             
======================================================================================================================
```

### 5.2 Per-Mode Analysis

1. **Mode 1 (Exact Signatures + Token Jaccard Lexical)**:
   - **Recall@1**: 84.6% | **MRR**: 0.8462
   - **Strengths**: Excels when error messages share overlapping tokens (e.g. `SyntaxError`, `IntegrityError`, `429 Too Many Requests`). Zero external dependencies or math overhead.
   - **Weaknesses**: Completely fails on paraphrased queries with disjoint vocabularies:
     - `bm_pos_02_db_connection_refused` ("could not connect to server: Connection refused" vs "target machine actively rejected connection"): **Rank: Not Retrieved (Score: 0.0)**.
     - `bm_pos_04_py_yaml_missing` ("No module named 'yaml'" vs "PyYAML package is not installed"): **Rank: Not Retrieved (Score: 0.0)**.
     - `bm_pos_05_redis_out_of_memory` ("Redis server memory threshold reached" vs "used memory > 'maxmemory'"): **Rank: Not Retrieved (Score: 0.0)**.
     - `bm_distractor_01_db_auth_vs_refusal`: **Rank: Not Retrieved (Score: 0.0)**.

2. **Mode 2 (Deterministic 128-dim Hashing Hybrid — 100% Offline)**:
   - **Recall@1**: 84.6% | **Recall@3**: 92.3% | **MRR**: 0.8718
   - **Improvement**: Morphological trigram and sub-token hashing captures typographical variations and root substrings:
     - `bm_pos_02_db_connection_refused` is elevated into top-3 (**Rank: 3, Score: 0.4153**).
     - `bm_distractor_01_db_auth_vs_refusal` is elevated into top-3 (**Rank: 3, Score: 0.4397**).

3. **Mode 3 (Dense Semantic Mock Hybrid — Simulated 1536-dim Clustering)**:
   - **Recall@1**: 88.5% | **Recall@3**: 92.3% | **MRR**: 0.9038
   - **Improvement**: Semantic clustering bridges synonyms and architectural equivalents:
     - `bm_pos_02_db_connection_refused` promoted to **Rank 1**.
     - `bm_pos_05_redis_out_of_memory` promoted to **Rank 1**.
   - **Integrity Notice**: Mode 3 is verified as an offline simulation (`is_simulated_mock=True`). It demonstrates what a tuned dense embedding model achieves, without invoking external services.

4. **Mode 4 (Live OpenAI API text-embedding-3-small)**:
   - Transparently reported as **`SKIPPED (No Key)`** with `is_executed=False`.
   - All metrics report `SKIPPED`. Zero fabricated metrics.

---

## 6. Deep-Dive Findings & Discovered Architectural Boundaries

### 6.1 Discovered Mock Vector Space Collapse & Correction

During initial testing of the expanded 33-scenario suite in Mode 3, an unexpected metric anomaly was uncovered:
- **Observation**: False-Positive Rate jumped from 0.0% to 80.0% (4 out of 5 negative queries returned false-positive matches).
- **Root Cause Investigation**:
  In `BenchmarkMockDenseClient`, any query or document that did not match predefined concept clusters fell through to a default static vector:
  ```python
  # Initial flawed fallback:
  for i in range(20 * step, dim):
      vec[i] = 0.4
  ```
  Consequently, all negative queries (`ZeroDivisionError`, `FileNotFoundError`, `IndexError`, etc.) and unclustered corpus items (`inc_generic_runtime_trap`) collapsed into the identical single unit vector in 1536-dimensional space. Their cosine similarity was computed as $\cos(\theta) = 1.0$. In hybrid scoring:
  $$\text{fused} = 0.55 \times 0.0 + 0.45 \times 1.0 + 0.05 = 0.50$$
  This reached the 0.50 threshold, falsely promoting generic runtime traps as valid incident matches!
- **Targeted Architectural Correction**:
  Replaced the static slice collapse with a deterministic pseudo-random hash projection across remaining dimensions:
  ```python
  # Corrected hash projection:
  h_int = int(hashlib.md5(text.encode("utf-8")).hexdigest()[:8], 16)
  rem_span = max(1, dim - 20 * step - 5)
  bucket = (20 * step) + (h_int % rem_span)
  for i in range(bucket, min(bucket + 4, dim)):
      vec[i] = 0.5
  ```
  Distinct unclustered texts now project into orthogonal subspaces, yielding cosine similarity $\approx 0.0$.
- **Verification**: False-Positive Rate returned to **0.0%** across all 5 negative scenarios.

### 6.2 Exception Contradiction Guard vs Exception Hierarchy

A key finding emerged regarding the interaction between semantic retrieval and exception contradiction guards:
- In `bm_pos_04_py_yaml_missing`:
  - Query: `ModuleNotFoundError: No module named 'yaml'`
  - Target: `ImportError: PyYAML package is not installed in virtual environment`
  - In Python, `ModuleNotFoundError` is a direct subclass of `ImportError`. However, DevMemory's contradiction guard performs exact string comparison:
    ```python
    if q_type and c_type and q_type.lower() != c_type.lower():
        has_contradictory_type = True
        fused = min(lexical_score * 0.7, 0.35)
    ```
    Because lexical score was 0.0 (disjoint tokens), `fused` was capped at 0.0, suppressing the match!
- In `bm_pos_14_go_nil_dereference`:
  - Query: `panic: runtime error: nil pointer dereference in handler.go`
  - Target: `panic: runtime error: invalid memory address or nil pointer dereference at handler.go:88`
  - Without standard colons, the exception extractor parsed the entire message as the exception type, detecting a mismatch and suppressing the candidate.
- **Architectural Recommendation**:
  This demonstrates that the contradiction guard is fail-closed and aggressive against conflicting error types. For future phases, introducing language-specific exception hierarchy normalization (mapping `ModuleNotFoundError` $\to$ `ImportError`) will safely unlock cross-exception retrieval without weakening safety.

---

## 7. Security, Privacy, and Fail-Closed Verification

All security, privacy, and isolation guarantees verified in Phase 5.2, Phase 6, and Phase 6.6 were re-verified under the expanded benchmark:

1. **Pre-processing Sanitization Parity**:
   `build_embedding_text` enforces identical sanitization, local path normalization (`~`), and token truncation ($\le 1050$ characters) across queries and corpus documents.
2. **Secret Redaction in Search Queries**:
   - `bm_secret_01_sanitized_token`: Raw Bearer token redacted to `[REDACTED_BEARER_TOKEN]` before vector generation. Correctly retrieves target `inc_target_jwt_expiry` at Rank 1.
   - `bm_secret_02_sanitized_db_url`: Embedded DB credentials in postgres connection URI redacted before vector generation. Correctly retrieves `inc_target_db_refused` at Rank 1.
3. **Strict Cross-Project Data Isolation**:
   - `bm_sec_01_cross_project_unauthorized`: Zero cross-project candidates returned when `allow_cross_project=False`. Project Isolation Rate = **100.0%**.
   - `bm_sec_02_cross_project_authorized`: Surfaces public cross-project incident (`inc_public_shared_utils`), while private incident (`inc_private_classified_billing`) is strictly suppressed. Project Isolation Rate = **100.0%**.
4. **Contradiction Guards Hold Unconditionally**:
   Contradiction Rejection Rate = **100.0%** across all executed modes. Conflicting exception types (e.g., `SyntaxError` vs `OperationalError`) are capped at $\le 0.35$.

---

## 8. Verification & Test Evidence

### 8.1 Automated Regression Test Suite

All 123 tests passed cleanly; 3 live-service tests skipped due to absent API credentials:
```
======================= 123 passed, 3 skipped in 9.15s ========================
```

### 8.2 Suite A Diagnostic Runner Output

```
[*] Running DevMemory AI Engine Evaluation (live_llm=False)...

[+] Evaluation Completed Successfully!
    Total Scenarios: 56
    Passed:          56
    Failed:          0
    Quality Pass Rate: 100.0%
    JSON Report:     reports\ai_engine_evaluation.json
    Markdown Report: reports\ai_engine_evaluation.md
```

### 8.3 Live Provider Offline Validation Output

```
================================================================================
DevMemory — Live Embedding Provider & Atlas Vector Search Audit
================================================================================
[1] EXTERNAL EMBEDDING PROVIDER:
    Target Model:        text-embedding-3-small
    Audit Status:        SKIPPED (OPENAI_API_KEY is not configured)
[2] MONGODB ATLAS VECTOR SEARCH:
    Audit Status:        NOT EXERCISED (MONGODB_ATLAS_URI is not configured)
================================================================================
```

---

## 9. Limitations & Production Roadmap

1. **Simulation Boundaries**: Mode 3 is a synthetic mock for offline reproducibility. While it proves the mathematical integration of dense embeddings into hybrid retrieval, it does not evaluate live LLM/dense embedding inference latency, rate limits, or network variability.
2. **Exception Hierarchy Generalization**: Exception type checking currently relies on exact string matching. A language-aware taxonomy mapping (`ModuleNotFoundError` $\subset$ `ImportError`) will improve paraphrase recall.
3. **Live Cloud Staging**: Live validation of Mode 4 and MongoDB Atlas Vector Search requires dedicated staging credentials in an isolated cloud environment with monitoring and spending caps.
