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

export async function checkBackendHealth() {
  if (FORCE_MOCK) return false;
  try {
    const res = await fetch(`${BASE_URL}/health`, { method: 'GET', signal: AbortSignal.timeout(2000) });
    isBackendLive = res.ok;
    return isBackendLive;
  } catch {
    isBackendLive = false;
    return false;
  }
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
  try {
    if (!FORCE_MOCK) {
      const res = await fetch(`${BASE_URL}/analytics/overview`);
      if (res.ok) {
        const raw = await res.json();
        isBackendLive = true;
        const normalized = {
          stats: raw.stats || raw,
          projects: Array.isArray(raw.projects) ? raw.projects.map(normalizeProject) : [],
          recentRuns: Array.isArray(raw.recentRuns || raw.recent_runs)
            ? (raw.recentRuns || raw.recent_runs).map(normalizeRun)
            : [],
          recurringErrors: raw.recurringErrors || raw.recurring_errors || [],
          verifiedFixes: raw.verifiedFixes || raw.verified_fixes || [],
          performanceTrend: raw.performanceTrend || raw.performance_trend || [],
        };
        return { data: normalized, isMock: false };
      }
    }
  } catch (err) {
    console.warn('[DevMemory API] Backend unreachable, using demonstration dataset:', err.message);
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
  try {
    if (!FORCE_MOCK) {
      const res = await fetch(`${BASE_URL}/projects`);
      if (res.ok) {
        const data = await res.json();
        return {
          data: Array.isArray(data) ? data.map(normalizeProject) : [],
          isMock: false,
        };
      }
    }
  } catch (err) {
    console.warn('[DevMemory API] Falling back to mock projects:', err.message);
  }

  return { data: MOCK_PROJECTS.map(normalizeProject), isMock: true };
}

export async function fetchProject(projectId) {
  try {
    if (!FORCE_MOCK) {
      const res = await fetch(`${BASE_URL}/projects/${projectId}`);
      if (res.ok) {
        const data = await res.json();
        return { data: normalizeProject(data), isMock: false };
      }
    }
  } catch (err) {
    console.warn('[DevMemory API] Falling back to mock project:', err.message);
  }

  const proj = MOCK_PROJECTS.find((p) => p.id === projectId) || MOCK_PROJECTS[0];
  return { data: normalizeProject(proj), isMock: true };
}

export async function fetchProjectRuns(projectId) {
  try {
    if (!FORCE_MOCK) {
      const res = await fetch(`${BASE_URL}/projects/${projectId}/runs`);
      if (res.ok) {
        const data = await res.json();
        return {
          data: Array.isArray(data) ? data.map(normalizeRun) : [],
          isMock: false,
        };
      }
    }
  } catch (err) {
    console.warn('[DevMemory API] Falling back to mock project runs:', err.message);
  }

  const runs = MOCK_RECENT_RUNS.filter((r) => r.projectId === projectId);
  const selectedRuns = runs.length ? runs : MOCK_RECENT_RUNS;
  return { data: selectedRuns.map(normalizeRun), isMock: true };
}

export async function fetchProjectIncidents(projectId) {
  try {
    if (!FORCE_MOCK) {
      const res = await fetch(`${BASE_URL}/projects/${projectId}/incidents`);
      if (res.ok) {
        const data = await res.json();
        return {
          data: Array.isArray(data) ? data.map(normalizeIncident) : [],
          isMock: false,
        };
      }
    }
  } catch (err) {
    console.warn('[DevMemory API] Falling back to mock incidents:', err.message);
  }

  const incidents = projectId
    ? MOCK_INCIDENTS.filter((inc) => inc.projectId === projectId)
    : MOCK_INCIDENTS;

  return { data: incidents.map(normalizeIncident), isMock: true };
}

export async function fetchIncident(incidentId) {
  try {
    if (!FORCE_MOCK) {
      const res = await fetch(`${BASE_URL}/incidents/${incidentId}`);
      if (res.ok) {
        const data = await res.json();
        return { data: normalizeIncident(data), isMock: false };
      }
    }
  } catch (err) {
    console.warn('[DevMemory API] Falling back to mock incident detail:', err.message);
  }

  const incident = MOCK_INCIDENTS.find((i) => i.incidentId === incidentId) || MOCK_INCIDENTS[0];
  return { data: normalizeIncident(incident), isMock: true };
}

export async function fetchProjectPerformance(projectId) {
  try {
    if (!FORCE_MOCK) {
      const res = await fetch(`${BASE_URL}/projects/${projectId}/performance`);
      if (res.ok) {
        const data = await res.json();
        return { data: normalizePerformance(data), isMock: false };
      }
    }
  } catch (err) {
    console.warn('[DevMemory API] Falling back to mock performance:', err.message);
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
  try {
    if (!FORCE_MOCK) {
      const res = await fetch(`${BASE_URL}/events`);
      if (res.ok) {
        const data = await res.json();
        return {
          data: Array.isArray(data) ? data.map(normalizeEvent) : [],
          isMock: false,
        };
      }
    }
  } catch (err) {
    console.warn('[DevMemory API] Falling back to mock global events:', err.message);
  }

  return {
    data: MOCK_EVENTS.map(normalizeEvent),
    isMock: true,
  };
}

export async function fetchProjectEvents(projectId) {
  try {
    if (!FORCE_MOCK) {
      const res = await fetch(`${BASE_URL}/projects/${projectId}/events`);
      if (res.ok) {
        const data = await res.json();
        return {
          data: Array.isArray(data) ? data.map(normalizeEvent) : [],
          isMock: false,
        };
      }
    }
  } catch (err) {
    console.warn('[DevMemory API] Falling back to mock project events:', err.message);
  }

  const events = projectId
    ? MOCK_EVENTS.filter((e) => e.projectId === projectId)
    : MOCK_EVENTS;

  return {
    data: events.map(normalizeEvent),
    isMock: true,
  };
}


