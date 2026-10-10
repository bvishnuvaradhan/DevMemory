# DevMemory — AI Engine Evaluation & Quality Benchmark Report

**Dataset Version:** `2.1.0`  
**Component:** Member 3 — AI & Cross-Project Memory Engine  
**Branch:** `feature/member-3-ai-memory`  
**Evaluation Tier:** Deterministic & Mock-LLM Offline Pipeline  
**Model / Engine Under Test:** `MockLLMClient (Dynamic Grounded Provider)`  
**Total Scenarios Evaluated:** 56 (56 passed, 0 failed)  
**Overall Quality Pass Rate:** 100.0%  
**Explicitly Unscorable Cases:** 4 (strictly excluded from accuracy denominators)  

---

## 1. Multi-Tier Evaluation Architecture

DevMemory distinguishes five clear tiers of verification:
1. **Deterministic Unit Tests:** 57+ unit tests covering deterministic normalization, signatures, regex sanitizers, and schemas.
2. **Offline Pipeline Benchmarks:** 56 scenarios executed against deterministic 3-level retrieval and grounded mock LLM with simulated provider failure modes.
3. **Optional Live Groq Benchmarks:** Opt-in real model testing (`--live-llm`) with live rate limit and JSON schema handling.
4. **Independent Diagnosis Quality Scoring:** Ground-truth category checks and token evidence grounding without permissive confidence bypasses.
5. **Unscorable Boundary Exclusions:** Unknown formats or hardware traps are explicitly labeled unscorable rather than falsely awarded full credit.

---

## 2. Measured Evaluation Metrics & Mathematical Formulations

| Metric Name | Value | Numerator / Denominator | Definition |
| :--- | :---: | :---: | :--- |
| **RetrievalRecall@3** | **100.0%** | `Hits in top-3 / Scenarios with expected KB target` | Proportion of scenarios with a target KB item where the target was present in the top-3 ranked results. |
| **RetrievalPrecision@1** | **100.0%** | `Top-1 exact hits / Scenarios with expected KB target` | Proportion of scenarios with a target KB item where the top-ranked result matched the target. |
| **FalsePositiveRate** | **0.0%** | `Non-target queries scoring >= 0.70 / Non-target scenarios` | Proportion of scenarios without a valid error target where unrelated items scored >= threshold. |
| **ProjectScopingAccuracy** | **100.0%** | `Zero cross-project leaks into Level 2 / Total project queries` | Proportion of project queries where incidents from other projects were completely excluded from Level 2 memory. |
| **CrossProjectAuthAccuracy** | **100.0%** | `Compliant auth & sanitization / Authorized cross-project queries` | Proportion of cross-project queries where server-side authorization and public policy were strictly enforced. |
| **SecretRedactionRate** | **100.0%** | `Completely sanitized outputs / Credential-bearing scenarios` | Proportion of credential-bearing scenarios where all synthetic secrets were redacted before processing. |
| **UnverifiedStatusCompliance** | **100.0%** | `Preserved 'unverified' status / Total diagnosed scenarios` | Proportion of diagnosed scenarios where fix_status was correctly set to unverified (preventing premature verification claims). |
| **EventIdPreservationRate** | **100.0%** | `Output event_id strictly equal to input / Total scenarios` | Proportion of diagnosed scenarios where output event_id strictly matches originating request event_id. |
| **RootCauseAccuracy** | **100.0%** | `Diagnosed category in expected categories / Scorable scenarios` | Proportion of scorable scenarios where diagnosis correctly identified an acceptable root cause category. |
| **EvidenceGroundingRate** | **100.0%** | `Retained >=50% key tokens in diagnosis evidence / Scenarios with evidence tokens` | Proportion of scenarios where diagnosis evidence retained essential diagnostic tokens from the input. |
| **UnsupportedClaimRate** | **0.0%** | `Hallucinated verifications or ungrounded claims / Total scenarios` | Proportion of scenarios where unverified solutions were prematurely marked verified or ungrounded locations were hallucinated. |
| **InsufficientEvidenceHandlingRate** | **100.0%** | `Explicitly acknowledged uncertainty / Insufficient evidence scenarios` | Proportion of scenarios with truncated or vague errors where uncertainty was explicitly acknowledged. |
| **FallbackResilienceRate** | **100.0%** | `Successful deterministic fallback executions / Provider failure scenarios` | Proportion of simulated provider failure scenarios (timeouts, malformed JSON) where deterministic fallback succeeded. |

---

## 3. Failure Pattern Breakdown (Task 5)

| Failure Category | Incident Count | Impact & Notes |
| :--- | :---: | :--- |
| **Incorrect Root Cause** | 0 | Misattributed error origin or invalid hypothesis |
| **Generic Or Irrelevant Recommendations** | 0 | Advice too vague to act upon or unrelated to error |
| **Missing Or Poor Retrieval** | 0 | Target Knowledge Base item omitted or scored below threshold |
| **Unsupported Claims Or Hallucinated Verification** | 0 | Premature verification claims or missing evidence grounding |
| **Insufficient Evidence Handling Failures** | 0 | Failing to disclose uncertainty when logs are vague/truncated |
| **Provider Api Failures** | 0 | Uncaught exception on simulated provider timeout or malformed JSON |
| **Privacy Or Authorization Failures** | 0 | Secret token leakage or unauthorized cross-project data disclosure |

---

## 4. Scenario Results Summary

| Scenario ID | Category | Status | Top Match | Fix Status |
| :--- | :--- | :---: | :--- | :---: |
| `scn_01_py_mod_not_found` | python_runtime | PASSED | `kb_py_mod_not_found` | unverified |
| `scn_02_py_circular_import` | python_runtime | PASSED | `kb_py_import_err` | unverified |
| `scn_03_py_none_attribute` | python_runtime | PASSED | `kb_py_attr_err` | unverified |
| `scn_04_py_type_mismatch` | python_runtime | PASSED | `kb_py_type_err` | unverified |
| `scn_05_py_missing_key` | python_runtime | PASSED | `kb_py_key_err` | unverified |
| `scn_06_py_file_missing` | python_runtime | PASSED | `kb_py_file_not_found` | unverified |
| `scn_07_js_undef_prop` | js_runtime | PASSED | `kb_js_type_read_prop` | unverified |
| `scn_08_js_map_not_function` | js_runtime | PASSED | `kb_js_type_map_not_func` | unverified |
| `scn_09_node_mod_missing` | js_runtime | PASSED | `kb_node_mod_not_found` | unverified |
| `scn_10_node_conn_refused` | network | PASSED | `kb_node_econnrefused` | unverified |
| `scn_11_cfg_missing_env` | configuration | PASSED | `kb_cfg_missing_env` | unverified |
| `scn_12_tst_assert_failure` | testing | PASSED | `kb_tst_assert_err` | unverified |
| `scn_13_net_port_in_use` | network | PASSED | `kb_net_eaddrinuse` | unverified |
| `scn_14_bld_ver_conflict` | dependency | PASSED | `kb_bld_pkg_ver_mismatch` | unverified |
| `scn_15_similar_err_diff_cause_a` | similar_different_cause | PASSED | `kb_py_key_err` | unverified |
| `scn_16_similar_err_diff_cause_b` | similar_different_cause | PASSED | `kb_py_key_err` | unverified |
| `scn_17_insufficient_evidence` | insufficient_evidence | PASSED | `None` | unverified |
| `scn_18_unknown_error_format` | unknown_format (Unscorable) | PASSED | `None` | unverified |
| `scn_19_misleading_history` | misleading_history | PASSED | `inc_hist_01_cache` | unverified |
| `scn_20_secret_api_key_in_command` | privacy_security | PASSED | `None` | unverified |
| `scn_21_secret_bearer_in_log` | privacy_security | PASSED | `None` | unverified |
| `scn_22_secret_db_pass_in_error` | privacy_security | PASSED | `None` | unverified |
| `scn_23_prompt_injection_in_trace` | privacy_security | PASSED | `None` | unverified |
| `scn_24_cross_project_private_isolation` | privacy_security | PASSED | `kb_js_type_read_prop` | unverified |
| `scn_25_cross_project_authorized_sanitization` | privacy_security | PASSED | `inc_hist_03_public_shared` | unverified |
| `scn_26_py_pkg_dep_conflict` | dependency | PASSED | `kb_bld_pkg_ver_mismatch` | unverified |
| `scn_27_py_poetry_lock_stale` | dependency | PASSED | `None` | unverified |
| `scn_28_js_async_unhandled_rejection` | js_runtime | PASSED | `None` | unverified |
| `scn_29_js_syntax_unexpected_token` | js_runtime | PASSED | `None` | unverified |
| `scn_30_js_reference_not_defined` | js_runtime | PASSED | `None` | unverified |
| `scn_31_cfg_malformed_yaml` | configuration | PASSED | `None` | unverified |
| `scn_32_cfg_port_non_numeric` | configuration | PASSED | `None` | unverified |
| `scn_33_py_syntax_missing_colon` | python_runtime | PASSED | `None` | unverified |
| `scn_34_py_indentation_error` | python_runtime | PASSED | `None` | unverified |
| `scn_35_py_zero_division` | python_runtime | PASSED | `None` | unverified |
| `scn_36_py_recursion_error` | python_runtime | PASSED | `None` | unverified |
| `scn_37_build_tsc_type_check_failure` | build | PASSED | `None` | unverified |
| `scn_38_tst_timeout_exceeded` | testing | PASSED | `None` | unverified |
| `scn_39_file_permission_denied` | filesystem | PASSED | `None` | unverified |
| `scn_40_path_windows_backslash_escape` | filesystem | PASSED | `None` | unverified |
| `scn_41_similar_econnrefused_wrong_port` | network | PASSED | `kb_node_econnrefused` | unverified |
| `scn_42_similar_econnrefused_docker_bind` | network | PASSED | `kb_node_econnrefused` | unverified |
| `scn_43_insufficient_generic_nonzero_exit` | insufficient_evidence | PASSED | `None` | unverified |
| `scn_44_insufficient_sigterm_external` | insufficient_evidence | PASSED | `None` | unverified |
| `scn_45_unseen_rust_panic` | unknown_format (Unscorable) | PASSED | `None` | unverified |
| `scn_46_unseen_go_panic` | unknown_format (Unscorable) | PASSED | `None` | unverified |
| `scn_47_misleading_log_red_herring` | misleading_history | PASSED | `None` | unverified |
| `scn_48_unsupported_proposed_fix` | misleading_history | PASSED | `None` | unverified |
| `scn_49_privacy_env_assignment` | privacy_security | PASSED | `None` | unverified |
| `scn_50_provider_groq_timeout` | provider_failure | PASSED | `kb_py_mod_not_found` | unverified |
| `scn_51_provider_groq_malformed_json` | provider_failure | PASSED | `kb_js_type_read_prop` | unverified |
| `scn_52_provider_groq_unwarranted_verified` | provider_failure | PASSED | `kb_py_key_err` | unverified |
| `scn_53_misleading_plausible_match` | misleading_history | PASSED | `None` | unverified |
| `scn_54_contradiction_log_snippet` | similar_different_cause | PASSED | `None` | unverified |
| `scn_55_unknown_architecture_crash` | unknown_format (Unscorable) | PASSED | `None` | unverified |
| `scn_56_similar_econnrefused_redis_sentinel` | similar_different_cause | PASSED | `None` | unverified |

---

## 5. Methodological Audit & Known Limitations

- **Semantic Judgment Limits:** Automated evaluation checks token grounding and category keywords; semantic coherence on novel open-ended errors requires qualitative human review.
- **Live LLM Flakiness:** Real Groq API execution is opt-in and rate-limited; offline evaluation is the single source of deterministic CI truth.
- **Pre-Vector Search State:** Retrieval currently uses explainable token-jaccard and signature matching. Semantic vector search is deferred to Phase 6.

---

## 6. Verification & Reproduction Command

To execute the reproducible offline evaluation and regenerate reports:
```bash
python -m ai_engine.evaluation.runner
python -m pytest tests/test_evaluation.py -v
```