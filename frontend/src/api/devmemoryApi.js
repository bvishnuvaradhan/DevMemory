/**
 * DevMemory API Client Layer
 *
 * This service abstracts HTTP requests to the FastAPI backend.
 * Unwraps ResponseEnvelope and PaginatedResponse structures.
 * Falls back to demonstration data ONLY if the backend service is offline
 * or if VITE_USE_MOCK_DATA is explicitly enabled.
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
 * Accurately tracks isBackendLive.
 */
async function safeApiFetch(endpoint, options = {}) {
  if (FORCE_MOCK) {
    return { ok: false, data: null, status: null, isMock: true };
  }

  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 4000);

    const res = await fetch(`${BASE_URL}${endpoint}`, {
      ...options,
      signal: options.signal || controller.signal,
    });

    clearTimeout(timeoutId);

    // If we received any HTTP response from the server, the backend is reachable
    isBackendLive = true;

    if (!res.ok) {
      let errDetail = `HTTP ${res.status} (${res.statusText || 'Error'})`;
      try {
        const errJson = await res.json();
        errDetail = errJson.error || errJson.detail || errDetail;
      } catch (_) {}
      console.warn(`[DevMemory API] ${endpoint} returned error:`, errDetail);
      return { ok: false, data: null, status: res.status, isMock: false, error: errDetail };
    }

    const contentType = res.headers.get('content-type') || '';
    if (!contentType.includes('application/json')) {
      console.warn(`[DevMemory API] Non-JSON payload received from ${endpoint}`);
      return { ok: false, data: null, status: res.status, isMock: false, error: 'Non-JSON response' };
    }

    const data = await res.json();
    return { ok: true, data, status: res.status, isMock: false };
  } catch (err) {
    const reason = err.name === 'AbortError' ? 'Request timed out after 4.0s' : err.message;
    console.warn(`[DevMemory API] Network request to ${endpoint} failed (${reason}).`);
    isBackendLive = false;
    return { ok: false, data: null, status: null, isMock: true, error: reason };
  }
}

/**
 * Unwraps FastAPI ResponseEnvelope: { success: true, data: ..., error: null }
 */
function unwrapData(result) {
  if (!result || !result.ok) return null;
  const payload = result.data;
  if (payload && typeof payload === 'object' && 'success' in payload && 'data' in payload) {
    return payload.data;
  }
  return payload;
}

/**
 * Unwraps paginated or plain list responses into a JavaScript Array.
 * Handles:
 * - Plain Array: [ ... ]
 * - PaginatedResponse: { items: [ ... ], total: N, ... }
 * - ResponseEnvelope wrapping either of the above
 */
function unwrapList(result) {
  const unwrapped = unwrapData(result);
  if (!unwrapped) return null;
  if (Array.isArray(unwrapped)) return unwrapped;
  if (unwrapped && typeof unwrapped === 'object' && Array.isArray(unwrapped.items)) {
    return unwrapped.items;
  }
  return null;
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
    description: p.description || '',
    language: p.language || '',
    framework: p.framework || '',
    repository: p.repository || '',
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
    command: r.command || '',
    exitCode: r.exitCode !== undefined ? r.exitCode : (r.exit_code !== undefined ? r.exit_code : 0),
    status: r.status || (r.exit_code === 0 ? 'success' : 'failure'),
    durationMs: r.durationMs !== undefined ? r.durationMs : (r.duration_ms || 0),
    timestamp: r.timestamp || r.started_at || r.created_at,
    sourceFile: r.sourceFile || r.source_file,
    lineNumber: r.lineNumber !== undefined ? r.lineNumber : r.line_number,
    errorSummary: r.errorSummary || r.error_summary || r.errorMessage || r.error_message || r.stderr || null,
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
    errorSignature: inc.errorSignature || inc.error_signature,
    sourceLocation: inc.sourceLocation || inc.source_location || (inc.file_path ? {
      file: inc.file_path,
      line: inc.line,
      column: inc.column,
      snippet: inc.source_snippet,
    } : null),
    aiDiagnosis: inc.aiDiagnosis || inc.ai_diagnosis,
    historicalMatches: inc.historicalMatches || inc.historical_matches || [],
    fixOutcome: inc.fixOutcome || inc.fix_outcome,
    createdAt: inc.createdAt || inc.created_at,
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
  const data = unwrapData(result);
  if (result.ok && data) {
    const raw = data;
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

  if (!isBackendLive || FORCE_MOCK) {
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

  return {
    data: {
      stats: { totalProjects: 0, totalRuns: 0, totalFailures: 0, failureRate: '0%', verifiedFixes: 0, verifiedFixRate: '0%', recurringErrorsCount: 0, medianExecutionTimeMs: 0 },
      projects: [],
      recentRuns: [],
      recurringErrors: [],
      verifiedFixes: [],
      performanceTrend: [],
    },
    isMock: false,
    error: result.error || 'Failed to load telemetry overview',
  };
}

export async function fetchProjects() {
  const result = await safeApiFetch('/projects');
  const list = unwrapList(result);
  if (result.ok && list !== null) {
    return {
      data: list.map(normalizeProject),
      isMock: false,
    };
  }

  if (!isBackendLive || FORCE_MOCK) {
    return { data: MOCK_PROJECTS.map(normalizeProject), isMock: true };
  }

  return { data: [], isMock: false, error: result.error || 'Failed to fetch projects' };
}

export async function fetchProject(projectId) {
  const result = await safeApiFetch(`/projects/${projectId}`);
  const data = unwrapData(result);
  if (result.ok && data) {
    return { data: normalizeProject(data), isMock: false };
  }

  if (!isBackendLive || FORCE_MOCK) {
    const proj = MOCK_PROJECTS.find((p) => p.id === projectId) || MOCK_PROJECTS[0];
    return { data: normalizeProject(proj), isMock: true };
  }

  return { data: null, isMock: false, error: result.error || 'Project not found' };
}

export async function fetchProjectRuns(projectId) {
  const result = await safeApiFetch(`/projects/${projectId}/runs`);
  const list = unwrapList(result);
  if (result.ok && list !== null) {
    return {
      data: list.map(normalizeRun),
      isMock: false,
    };
  }

  if (!isBackendLive || FORCE_MOCK) {
    const runs = MOCK_RECENT_RUNS.filter((r) => r.projectId === projectId);
    const selectedRuns = runs.length ? runs : MOCK_RECENT_RUNS;
    return { data: selectedRuns.map(normalizeRun), isMock: true };
  }

  return { data: [], isMock: false, error: result.error || 'Failed to fetch project runs' };
}

export async function fetchProjectIncidents(projectId) {
  const result = await safeApiFetch(`/projects/${projectId}/incidents`);
  const list = unwrapList(result);
  if (result.ok && list !== null) {
    return {
      data: list.map(normalizeIncident),
      isMock: false,
    };
  }

  if (!isBackendLive || FORCE_MOCK) {
    const incidents = projectId
      ? MOCK_INCIDENTS.filter((inc) => inc.projectId === projectId)
      : MOCK_INCIDENTS;
    return { data: incidents.map(normalizeIncident), isMock: true };
  }

  return { data: [], isMock: false, error: result.error || 'Failed to fetch project incidents' };
}

export async function fetchIncident(incidentId) {
  const result = await safeApiFetch(`/incidents/${incidentId}`);
  const data = unwrapData(result);
  if (result.ok && data) {
    return { data: normalizeIncident(data), isMock: false };
  }

  if (!isBackendLive || FORCE_MOCK) {
    const incident = MOCK_INCIDENTS.find((i) => i.incidentId === incidentId) || MOCK_INCIDENTS[0];
    return { data: normalizeIncident(incident), isMock: true };
  }

  return { data: null, isMock: false, error: result.error || 'Incident not found' };
}

export async function fetchProjectPerformance(projectId) {
  const result = await safeApiFetch(`/projects/${projectId}/performance`);
  const data = unwrapData(result);
  if (result.ok && data) {
    return { data: normalizePerformance(data), isMock: false };
  }

  if (!isBackendLive || FORCE_MOCK) {
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

  return {
    data: { projectId, projectName: projectId, baselineMs: null, medianMs: null, runs: [] },
    isMock: false,
    error: result.error || 'Failed to fetch performance data',
  };
}

export async function fetchGlobalEvents() {
  const result = await safeApiFetch('/events');
  const list = unwrapList(result);
  if (result.ok && list !== null) {
    return {
      data: list.map(normalizeEvent),
      isMock: false,
    };
  }

  if (!isBackendLive || FORCE_MOCK) {
    return {
      data: MOCK_EVENTS.map(normalizeEvent),
      isMock: true,
    };
  }

  return { data: [], isMock: false, error: result.error || 'Failed to fetch events' };
}

export async function fetchProjectEvents(projectId) {
  const result = await safeApiFetch(`/projects/${projectId}/events`);
  const list = unwrapList(result);
  if (result.ok && list !== null) {
    return {
      data: list.map(normalizeEvent),
      isMock: false,
    };
  }

  if (!isBackendLive || FORCE_MOCK) {
    const events = projectId
      ? MOCK_EVENTS.filter((e) => e.projectId === projectId)
      : MOCK_EVENTS;
    return {
      data: events.map(normalizeEvent),
      isMock: true,
    };
  }

  return { data: [], isMock: false, error: result.error || 'Failed to fetch project events' };
}

export async function fetchAllRuns() {
  const result = await safeApiFetch('/runs');
  const list = unwrapList(result);
  if (result.ok && list !== null) {
    return {
      data: list.map(normalizeRun),
      isMock: false,
    };
  }

  if (!isBackendLive || FORCE_MOCK) {
    return {
      data: MOCK_RECENT_RUNS.map(normalizeRun),
      isMock: true,
    };
  }

  return { data: [], isMock: false, error: result.error || 'Failed to fetch command runs' };
}

export async function fetchAllIncidents() {
  const result = await safeApiFetch('/incidents');
  const list = unwrapList(result);
  if (result.ok && list !== null) {
    return {
      data: list.map(normalizeIncident),
      isMock: false,
    };
  }

  if (!isBackendLive || FORCE_MOCK) {
    return {
      data: MOCK_INCIDENTS.map(normalizeIncident),
      isMock: true,
    };
  }

  return { data: [], isMock: false, error: result.error || 'Failed to fetch incidents' };
}

export async function fetchAllFixes() {
  const result = await safeApiFetch('/fixes');
  const list = unwrapList(result);
  if (result.ok && list !== null) {
    return { data: list, isMock: false };
  }

  if (!isBackendLive || FORCE_MOCK) {
    return { data: MOCK_VERIFIED_FIXES, isMock: true };
  }

  return { data: [], isMock: false, error: result.error || 'Failed to fetch fixes' };
}

export async function fetchAllPerformance() {
  const result = await safeApiFetch('/analytics/performance');
  const data = unwrapData(result);
  if (result.ok && data) {
    return { data, isMock: false };
  }

  if (!isBackendLive || FORCE_MOCK) {
    return {
      data: {
        trend: MOCK_PERFORMANCE_TREND,
        byProject: MOCK_PERFORMANCE_BY_PROJECT,
      },
      isMock: true,
    };
  }

  return {
    data: { trend: [], byProject: {} },
    isMock: false,
    error: result.error || 'Failed to fetch performance analytics',
  };
}

// ============================================================================
// LLM Outbound Payload Security Audits & Evidence API
// ============================================================================

export async function fetchProjectLLMAudits(projectId, params = {}) {
  const query = new URLSearchParams(params).toString();
  const endpoint = `/projects/${projectId}/llm-audits${query ? `?${query}` : ''}`;
  const result = await safeApiFetch(endpoint);
  const data = unwrapData(result);
  if (result.ok && data) {
    const items = Array.isArray(data.items) ? data.items : (Array.isArray(data) ? data : []);
    return { data: { items, total: data.total ?? items.length }, isMock: false };
  }
  return {
    data: { items: [], total: 0 },
    isMock: false,
    error: result.error || 'Failed to fetch LLM audits',
  };
}

export async function fetchProjectLLMSecuritySummary(projectId) {
  const result = await safeApiFetch(`/projects/${projectId}/llm-audits/summary`);
  const data = unwrapData(result);
  if (result.ok && data) {
    return { data, isMock: false };
  }
  return {
    data: {
      projectId,
      totalRequests: 0,
      statusCounts: {},
      totalRedactionsApplied: 0,
      redactionCategories: {},
      providersUsed: [],
      latestTransmissionAt: null,
    },
    isMock: false,
    error: result.error || 'Failed to fetch security summary',
  };
}

export async function fetchLLMAuditItem(projectId, auditId) {
  const result = await safeApiFetch(`/projects/${projectId}/llm-audits/${auditId}`);
  const data = unwrapData(result);
  if (result.ok && data) {
    return { data, isMock: false };
  }
  return { data: null, isMock: false, error: result.error || 'Audit item not found' };
}
