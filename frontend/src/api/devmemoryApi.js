/**
 * DevMemory API Client Layer
 *
 * This service abstracts HTTP requests to the FastAPI backend (Member 2).
 * When the backend is unreachable or VITE_USE_MOCK_DATA=true, it falls back
 * gracefully to structured mock demonstration data, clearly signaling mock state.
 */

import {
  MOCK_PROJECTS,
  MOCK_GLOBAL_STATS,
  MOCK_RECENT_RUNS,
  MOCK_RECURRING_ERRORS,
  MOCK_VERIFIED_FIXES,
  MOCK_PERFORMANCE_TREND,
  MOCK_INCIDENTS,
  MOCK_PERFORMANCE_BY_PROJECT,
  MOCK_EVENTS,
} from './mockData.js';

const BASE_URL = import.meta.env?.VITE_API_BASE_URL || '/api/v1';
const FORCE_MOCK = import.meta.env?.VITE_USE_MOCK_DATA === 'true';

let isBackendLive = false;

/**
 * Safely requests a DevMemory backend API endpoint.
 * - Confirms response.ok before attempting to parse or treat as successful
 * - Handles HTTP 500, 502, 504, 404, network connection refused, or timeouts gracefully
 * - Retains clean diagnostic warning logs without exposing sensitive information
 * - Sets isBackendLive state accurately
 * - Ensures mock fallback data is activated without crashing React views
 */
async function safeApiFetch(endpoint, options = {}) {
  if (FORCE_MOCK) {
    return { ok: false, data: null, status: null, isMock: true };
  }

  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 3500);

    const res = await fetch(`${BASE_URL}${endpoint}`, {
      ...options,
      signal: options.signal || controller.signal,
    });

    clearTimeout(timeoutId);

    if (!res.ok) {
      console.warn(
        `[DevMemory API] HTTP ${res.status} (${res.statusText || 'Error'}) from ${endpoint}. Gracefully falling back to demonstration dataset.`
      );
      isBackendLive = false;
      return { ok: false, data: null, status: res.status, isMock: true };
    }

    const contentType = res.headers.get('content-type') || '';
    if (!contentType.includes('application/json')) {
      console.warn(
        `[DevMemory API] Non-JSON payload received from ${endpoint} (Content-Type: ${contentType}). Falling back to demonstration dataset.`
      );
      isBackendLive = false;
      return { ok: false, data: null, status: res.status, isMock: true };
    }

    const data = await res.json();
    isBackendLive = true;
    return { ok: true, data, status: res.status, isMock: false };
  } catch (err) {
    const reason = err.name === 'AbortError' ? 'Request timed out after 3.5s' : err.message;
    console.warn(
      `[DevMemory API] Network request to ${endpoint} failed (${reason}). Falling back to demonstration dataset.`
    );
    isBackendLive = false;
    return { ok: false, data: null, status: null, isMock: true, error: reason };
  }
}

export async function checkBackendHealth() {
  if (FORCE_MOCK) return false;
  const result = await safeApiFetch('/health');
  isBackendLive = Boolean(result.ok);
  return isBackendLive;
}

export function getIsUsingMockData() {
  return !isBackendLive || FORCE_MOCK;
}

// Normalization adapters to seamlessly accept both snake_case (FastAPI) and camelCase
export function normalizeProject(p) {
  if (!p) return p;
  return {
    ...p,
    id: p.id || p.project_id || p._id,
    name: p.name || p.project_name || p.id,
    totalRuns: p.totalRuns !== undefined ? p.totalRuns : (p.total_runs || 0),
    failureCount: p.failureCount !== undefined ? p.failureCount : (p.failure_count || 0),
    verifiedFixCount: p.verifiedFixCount !== undefined ? p.verifiedFixCount : (p.verified_fix_count || 0),
    lastRunAt: p.lastRunAt || p.last_run_at,
    lastRunStatus: p.lastRunStatus || p.last_run_status || 'unknown',
    medianDurationMs: p.medianDurationMs !== undefined ? p.medianDurationMs : (p.median_duration_ms || 0),
    baselineDurationMs: p.baselineDurationMs !== undefined ? p.baselineDurationMs : p.baseline_duration_ms,
  };
}

export function normalizeRun(r) {
  if (!r) return r;
  return {
    ...r,
    eventId: r.eventId || r.event_id || r.id,
    projectId: r.projectId || r.project_id,
    projectName: r.projectName || r.project_name || r.projectId || r.project_id,
    exitCode: r.exitCode !== undefined ? r.exitCode : (r.exit_code !== undefined ? r.exit_code : 0),
    durationMs: r.durationMs !== undefined ? r.durationMs : (r.duration_ms || 0),
    sourceFile: r.sourceFile || r.source_file,
    lineNumber: r.lineNumber !== undefined ? r.lineNumber : r.line_number,
    errorSummary: r.errorSummary || r.error_summary || r.errorMessage || r.error_message,
  };
}

export function normalizeIncident(inc) {
  if (!inc) return inc;
  return {
    ...inc,
    incidentId: inc.incidentId || inc.incident_id || inc.id,
    eventId: inc.eventId || inc.event_id,
    projectId: inc.projectId || inc.project_id,
    projectName: inc.projectName || inc.project_name || inc.projectId,
    errorType: inc.errorType || inc.error_type || 'UnknownError',
    errorMessage: inc.errorMessage || inc.error_message || '',
    stackTrace: inc.stackTrace || inc.stack_trace,
    sourceLocation: inc.sourceLocation || inc.source_location || (inc.source_file ? {
      file: inc.source_file,
      line: inc.line_number,
      column: inc.column_number,
      snippet: inc.code_snippet,
    } : null),
    aiDiagnosis: inc.aiDiagnosis || inc.ai_diagnosis,
    historicalMatches: inc.historicalMatches || inc.historical_matches || [],
    fixOutcome: inc.fixOutcome || inc.fix_outcome,
  };
}

export function normalizePerformance(perf) {
  if (!perf) return perf;
  const rawRuns = perf.runs || perf.run_records || [];
  return {
    ...perf,
    projectId: perf.projectId || perf.project_id,
    projectName: perf.projectName || perf.project_name,
    baselineMs: perf.baselineMs !== undefined ? perf.baselineMs : perf.baseline_ms,
    medianMs: perf.medianMs !== undefined ? perf.medianMs : perf.median_ms,
    tolerancePercent: perf.tolerancePercent !== undefined ? perf.tolerancePercent : (perf.tolerance_percent || 20),
    runs: Array.isArray(rawRuns) ? rawRuns.map((r, i) => ({
      ...r,
      id: r.id || r.run_id || `run_${i}`,
      timestamp: r.timestamp || r.created_at || `${i + 1}`,
      command: r.command || 'test',
      durationMs: r.durationMs !== undefined ? r.durationMs : (r.duration_ms || 0),
      exitCode: r.exitCode !== undefined ? r.exitCode : (r.exit_code !== undefined ? r.exit_code : 0),
      isRegression: r.isRegression !== undefined ? r.isRegression : Boolean(r.is_regression),
      regressionDeltaMs: r.regressionDeltaMs !== undefined ? r.regressionDeltaMs : r.regression_delta_ms,
    })) : [],
  };
}

export function normalizeEvent(evt) {
  if (!evt) return evt;
  return {
    ...evt,
    eventId: evt.eventId || evt.event_id || evt.id,
    timestamp: evt.timestamp || evt.created_at,
    projectId: evt.projectId || evt.project_id,
    projectName: evt.projectName || evt.project_name || evt.projectId || evt.project_id,
    eventType: (evt.eventType || evt.event_type || 'COMMAND_RUN').toUpperCase(),
    status: (evt.status || 'UNKNOWN').toUpperCase(),
    summary: evt.summary || evt.message || '',
    relatedCommand: evt.relatedCommand || evt.related_command || evt.command,
    relatedIncidentId: evt.relatedIncidentId || evt.related_incident_id || evt.incident_id,
    sourceLocation: evt.sourceLocation || evt.source_location || (evt.source_file ? {
      file: evt.source_file,
      line: evt.line_number,
      column: evt.column_number,
    } : null),
    details: evt.details || evt.description || '',
  };
}

export async function fetchGlobalOverview() {
  const result = await safeApiFetch('/analytics/overview');
  if (result.ok && result.data) {
    const raw = result.data;
    const normalized = {
      stats: raw.stats || raw,
      projects: Array.isArray(raw.projects) ? raw.projects.map(normalizeProject) : [],
      recentRuns: Array.isArray(raw.recentRuns || raw.recent_runs)
        ? (raw.recentRuns || raw.recent_runs).map(normalizeRun)
        : [],
      recurringErrors: Array.isArray(raw.recurringErrors || raw.recurring_errors)
        ? (raw.recurringErrors || raw.recurring_errors)
        : [],
      verifiedFixes: Array.isArray(raw.verifiedFixes || raw.verified_fixes)
        ? (raw.verifiedFixes || raw.verified_fixes)
        : [],
      performanceTrend: Array.isArray(raw.performanceTrend || raw.performance_trend)
        ? (raw.performanceTrend || raw.performance_trend)
        : [],
    };
    return { data: normalized, isMock: false };
  }

  return {
    data: {
      stats: MOCK_GLOBAL_STATS,
      projects: MOCK_PROJECTS.map(normalizeProject),
      recentRuns: MOCK_RECENT_RUNS.map(normalizeRun),
      recurringErrors: MOCK_RECURRING_ERRORS,
      verifiedFixes: MOCK_VERIFIED_FIXES,
      performanceTrend: MOCK_PERFORMANCE_TREND,
    },
    isMock: true,
  };
}

export async function fetchProjects() {
  const result = await safeApiFetch('/projects');
  if (result.ok && Array.isArray(result.data)) {
    return {
      data: result.data.map(normalizeProject),
      isMock: false,
    };
  }

  return { data: MOCK_PROJECTS.map(normalizeProject), isMock: true };
}

export async function fetchProject(projectId) {
  const result = await safeApiFetch(`/projects/${projectId}`);
  if (result.ok && result.data) {
    return { data: normalizeProject(result.data), isMock: false };
  }

  const proj = MOCK_PROJECTS.find((p) => p.id === projectId) || MOCK_PROJECTS[0];
  return { data: normalizeProject(proj), isMock: true };
}

export async function fetchProjectRuns(projectId) {
  const result = await safeApiFetch(`/projects/${projectId}/runs`);
  if (result.ok && Array.isArray(result.data)) {
    return {
      data: result.data.map(normalizeRun),
      isMock: false,
    };
  }

  const runs = MOCK_RECENT_RUNS.filter((r) => r.projectId === projectId);
  const selectedRuns = runs.length ? runs : MOCK_RECENT_RUNS;
  return { data: selectedRuns.map(normalizeRun), isMock: true };
}

export async function fetchProjectIncidents(projectId) {
  const result = await safeApiFetch(`/projects/${projectId}/incidents`);
  if (result.ok && Array.isArray(result.data)) {
    return {
      data: result.data.map(normalizeIncident),
      isMock: false,
    };
  }

  const incidents = projectId
    ? MOCK_INCIDENTS.filter((inc) => inc.projectId === projectId)
    : MOCK_INCIDENTS;

  return { data: incidents.map(normalizeIncident), isMock: true };
}

export async function fetchIncident(incidentId) {
  const result = await safeApiFetch(`/incidents/${incidentId}`);
  if (result.ok && result.data) {
    return { data: normalizeIncident(result.data), isMock: false };
  }

  const incident = MOCK_INCIDENTS.find((i) => i.incidentId === incidentId) || MOCK_INCIDENTS[0];
  return { data: normalizeIncident(incident), isMock: true };
}

export async function fetchProjectPerformance(projectId) {
  const result = await safeApiFetch(`/projects/${projectId}/performance`);
  if (result.ok && result.data) {
    return { data: normalizePerformance(result.data), isMock: false };
  }

  const perf = MOCK_PERFORMANCE_BY_PROJECT[projectId] || {
    projectId,
    projectName: projectId,
    baselineMs: null,
    medianMs: null,
    sampleCount: 0,
    runs: [],
  };

  return { data: normalizePerformance(perf), isMock: true };
}

export async function fetchGlobalEvents() {
  const result = await safeApiFetch('/events');
  if (result.ok && Array.isArray(result.data)) {
    return {
      data: result.data.map(normalizeEvent),
      isMock: false,
    };
  }

  return {
    data: MOCK_EVENTS.map(normalizeEvent),
    isMock: true,
  };
}

export async function fetchProjectEvents(projectId) {
  const result = await safeApiFetch(`/projects/${projectId}/events`);
  if (result.ok && Array.isArray(result.data)) {
    return {
      data: result.data.map(normalizeEvent),
      isMock: false,
    };
  }

  const events = projectId
    ? MOCK_EVENTS.filter((e) => e.projectId === projectId)
    : MOCK_EVENTS;

  return {
    data: events.map(normalizeEvent),
    isMock: true,
  };
}

export async function fetchAllRuns() {
  const result = await safeApiFetch('/runs');
  if (result.ok && Array.isArray(result.data)) {
    return {
      data: result.data.map(normalizeRun),
      isMock: false,
    };
  }

  return {
    data: MOCK_RECENT_RUNS.map(normalizeRun),
    isMock: true,
  };
}

export async function fetchAllIncidents() {
  const result = await safeApiFetch('/incidents');
  if (result.ok && Array.isArray(result.data)) {
    return {
      data: result.data.map(normalizeIncident),
      isMock: false,
    };
  }

  return {
    data: MOCK_INCIDENTS.map(normalizeIncident),
    isMock: true,
  };
}

export async function fetchAllFixes() {
  const result = await safeApiFetch('/fixes');
  if (result.ok && Array.isArray(result.data)) {
    return { data: result.data, isMock: false };
  }

  const combinedFixes = [
    {
      id: 'fix_01',
      projectId: 'proj_auth_service',
      projectName: 'auth-service',
      errorType: 'ExpiredSignatureError',
      solutionSummary: 'Added leeway window (leeway=30s) to jwt.decode() and refresh token clock skew tolerance',
      verificationMethod: 'devmemory run -- pytest tests/test_token_refresh.py -k test_clock_skew',
      testResult: '3 passed, 0 failed in 0.42s (exit code: 0)',
      status: 'VERIFIED',
      verifiedAt: '2026-10-09T16:45:00Z',
      recurrenceCountAfterFix: 0,
      author: 'AI Recommendation + Developer Verification',
      relatedIncidentId: 'inc_auth_01',
    },
    {
      id: 'fix_02',
      projectId: 'proj_data_pipeline',
      projectName: 'data-pipeline',
      errorType: 'OutOfMemoryError (CUDA)',
      solutionSummary: 'Implemented gradient checkpointing and dynamic batch sizing with torch.cuda.empty_cache() on fallback',
      verificationMethod: 'devmemory run -- python -m pipeline.preprocess --eval-batch-memory',
      testResult: '1 passed in 2.14s (exit code: 0)',
      status: 'VERIFIED',
      verifiedAt: '2026-10-09T14:10:00Z',
      recurrenceCountAfterFix: 0,
      author: 'AI Recommendation + Developer Verification',
      relatedIncidentId: 'inc_cuda_02',
    },
    {
      id: 'fix_03',
      projectId: 'proj_payment_worker',
      projectName: 'payment-worker',
      errorType: 'StripeIdempotencyKeyError',
      solutionSummary: 'Scoped idempotency keys with SHA-256 payload digest rather than raw user_id timestamp',
      verificationMethod: 'devmemory run -- npm test -- tests/idempotency.test.ts',
      testResult: '5 passed, 0 failed in 0.38s (exit code: 0)',
      status: 'VERIFIED',
      verifiedAt: '2026-10-08T19:30:00Z',
      recurrenceCountAfterFix: 0,
      author: 'Cross-Project Memory Hit (from checkout-web) + Verified',
      relatedIncidentId: 'inc_worker_03',
    },
    {
      id: 'fix_04',
      projectId: 'proj_data_pipeline',
      projectName: 'data-pipeline',
      errorType: 'OutOfMemoryError (CUDA)',
      solutionSummary: 'Add torch.inference_mode() and detach tensor features to CPU RAM immediately',
      verificationMethod: 'devmemory run -- python -m pipeline.preprocess --eval-batch-memory',
      testResult: 'Awaiting execution of verification command',
      status: 'PENDING',
      verifiedAt: null,
      recurrenceCountAfterFix: 0,
      author: 'AI Recommendation',
      relatedIncidentId: 'inc_cuda_02',
    },
    {
      id: 'fix_05',
      projectId: 'proj_payment_worker',
      projectName: 'payment-worker',
      errorType: 'SIGKILL (Container Out of Memory)',
      solutionSummary: 'Increased container memory limit to 512MB and added BullMQ concurrency cap',
      verificationMethod: 'devmemory run -- npm run test:load',
      testResult: 'Process spiked again under 10k messages/sec surge (exit code: 137)',
      status: 'RECURRING',
      verifiedAt: null,
      recurrenceCountAfterFix: 2,
      author: 'AI Recommendation + Manual Adjustments',
      relatedIncidentId: 'inc_sys_04',
    },
  ];

  return { data: combinedFixes, isMock: true };
}

export async function fetchAllPerformance() {
  const result = await safeApiFetch('/analytics/performance');
  if (result.ok && result.data) {
    return { data: result.data, isMock: false };
  }

  return {
    data: {
      trend: MOCK_PERFORMANCE_TREND,
      byProject: MOCK_PERFORMANCE_BY_PROJECT,
    },
    isMock: true,
  };
}


