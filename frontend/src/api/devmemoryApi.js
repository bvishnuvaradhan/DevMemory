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

  const timeoutMs = options.timeoutMs || 8000;

  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

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
    const reason = err.name === 'AbortError' ? `Request timed out after ${timeoutMs / 1000}s` : err.message;
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

export function normalizeDiagnosis(diag) {
  if (!diag) return null;
  if (typeof diag === 'string') {
    return {
      summary: diag,
      likelyCause: diag,
      observedEvidence: [diag],
      hypotheses: [diag],
      recommendations: [],
      confidence: 0.85,
      source: 'heuristics',
    };
  }

  // Evidence
  const rawEvidence = diag.observedEvidence ?? diag.evidence ?? diag.observed_evidence ?? [];
  const observedEvidence = Array.isArray(rawEvidence)
    ? rawEvidence
    : typeof rawEvidence === 'string'
    ? [rawEvidence]
    : [];

  // Hypotheses (extract string cause if item is an object)
  const rawHypotheses = diag.hypotheses ?? [];
  const hypotheses = Array.isArray(rawHypotheses)
    ? rawHypotheses.map((h) =>
        typeof h === 'object' && h !== null ? h.cause || h.details || JSON.stringify(h) : String(h)
      )
    : typeof rawHypotheses === 'string'
    ? [rawHypotheses]
    : [];

  // Recommendations / suggested fix
  let recommendations = [];
  if (diag.recommendations) {
    recommendations = Array.isArray(diag.recommendations) ? diag.recommendations : [diag.recommendations];
  } else if (diag.suggested_fix || diag.suggestedFix) {
    const rawFix = diag.suggested_fix || diag.suggestedFix;
    recommendations = Array.isArray(rawFix)
      ? rawFix
      : typeof rawFix === 'string'
      ? rawFix.split(';').map((s) => s.trim()).filter(Boolean)
      : [];
  }

  // Decision Gate & Verification metadata
  const llmSkipped = diag.llm_skipped !== undefined ? Boolean(diag.llm_skipped) : Boolean(diag.llmSkipped);
  const decisionReason = diag.decision_reason || diag.decisionReason || null;
  const isVerifiedFix = diag.is_verified_fix !== undefined ? Boolean(diag.is_verified_fix) : Boolean(diag.isVerifiedFix);

  return {
    ...diag,
    diagnosisId: diag.diagnosisId || diag.diagnosis_id,
    incidentId: diag.incidentId || diag.incident_id,
    summary: diag.summary || diag.likely_cause || diag.likelyCause || '',
    likelyCause: diag.likely_cause || diag.likelyCause || diag.summary || '',
    observedEvidence,
    hypotheses,
    recommendations,
    confidence: diag.confidence !== undefined ? diag.confidence : 0.85,
    source: diag.source || (llmSkipped ? 'DevMemory Memory Bank (Decision Gate Reused)' : 'AI Diagnosis Engine'),
    llmSkipped,
    decisionReason,
    isVerifiedFix,
    matchedMemory: diag.matched_memory || diag.matchedMemory || [],
  };
}

export function normalizeHistoricalMatch(m) {
  if (!m) return m;
  const isGeneralKnowledge = Boolean(
    m.isGeneralKnowledge ||
    m.is_general_knowledge ||
    m.sourceType === 'knowledge_base' ||
    m.source_type === 'knowledge_base' ||
    m.sourceType === 'general_knowledge' ||
    m.source_type === 'general_knowledge'
  );
  const isCrossProject = m.isCrossProject !== undefined ? Boolean(m.isCrossProject) : Boolean(m.is_cross_project);
  const sourceType = m.sourceType || m.source_type || (isGeneralKnowledge ? 'knowledge_base' : (isCrossProject ? 'public_precedent' : 'project_memory'));
  const sourceProject = m.sourceProject || m.source_project || m.projectId || m.project_id || (isGeneralKnowledge ? 'Curated Knowledge Base' : 'Current Project');
  const verified = m.verified !== undefined ? Boolean(m.verified) : (m.verificationStatus === 'VERIFIED' || m.verification_status === 'VERIFIED');
  const similarityScore = m.similarityScore !== undefined ? m.similarityScore : (m.similarity_score !== undefined ? m.similarity_score : 1.0);
  const matchReason = m.matchReason || m.match_reason || m.relevanceReason || m.relevance_reason || m.reason || 'Matched diagnostic evidence';
  const sanitizedFixSummary = m.sanitizedFixSummary || m.sanitized_fix_summary || m.resolutionSummary || m.resolution_summary || m.fixSummary || m.fix_summary || m.explanation || null;

  return {
    id: m.id || m.sourceId || m.source_id || `match_${Math.random().toString(36).substring(2, 9)}`,
    sourceId: m.sourceId || m.source_id || m.id,
    sourceType,
    isCrossProject,
    isGeneralKnowledge,
    sourceProject,
    verified,
    similarityScore,
    matchReason,
    sanitizedFixSummary,
    title: m.title || (isGeneralKnowledge ? m.matchReason || 'Curated General Guidance' : null),
    suggestedResolutions: m.suggestedResolutions || m.suggested_resolutions || (Array.isArray(m.recommendations) ? m.recommendations : []),
  };
}

export function normalizeIncident(inc) {
  if (!inc) return inc;
  const normalizedDiagnosis = normalizeDiagnosis(inc.aiDiagnosis || inc.ai_diagnosis);
  const rawMatches =
    (inc.historicalMatches && inc.historicalMatches.length ? inc.historicalMatches : null) ||
    (inc.historical_matches && inc.historical_matches.length ? inc.historical_matches : null) ||
    normalizedDiagnosis?.matchedMemory ||
    [];

  const historicalMatches = Array.isArray(rawMatches)
    ? rawMatches.map(normalizeHistoricalMatch)
    : [];

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
    diagnosisStatus: inc.diagnosisStatus || inc.diagnosis_status || (normalizedDiagnosis ? 'diagnosed' : 'pending'),
    aiDiagnosis: normalizedDiagnosis,
    historicalMatches,
    fixOutcome: normalizeFixOutcome(inc.fixOutcome || inc.fix_outcome),
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

export function normalizeRecurringError(err) {
  if (!err) return err;
  const rawProjects = err.affectedProjects ?? err.affected_projects;
  const affectedProjects = Array.isArray(rawProjects)
    ? rawProjects
    : (err.projectId || err.project_id ? [err.projectId || err.project_id] : []);

  return {
    ...err,
    clusterId: err.clusterId || err.cluster_id || '',
    errorType: err.errorType || err.error_type || 'UnknownError',
    category: err.category || 'General',
    sampleMessage: err.sampleMessage || err.sample_message || '',
    occurrences: err.occurrences !== undefined ? err.occurrences : (err.count || 1),
    affectedProjects,
    hasVerifiedFix: err.hasVerifiedFix !== undefined ? Boolean(err.hasVerifiedFix) : Boolean(err.has_verified_fix),
  };
}

export function normalizeFixOutcome(fix) {
  if (!fix) return null;
  return normalizeVerifiedFix(fix);
}

export function normalizeVerifiedFix(fix) {
  if (!fix) return fix;
  const rawStatus = (fix.status || 'proposed').toLowerCase();
  const recurrence = Number(
    fix.recurrenceCountAfterFix !== undefined
      ? fix.recurrenceCountAfterFix
      : (fix.recurrence_count_after_fix || fix.recurrenceAfterFix || 0)
  );

  let normStatus = 'PENDING';
  if (recurrence > 0 || rawStatus === 'recurring') {
    normStatus = 'RECURRING';
  } else if (rawStatus === 'verified') {
    normStatus = 'VERIFIED';
  } else if (rawStatus === 'failed') {
    normStatus = 'FAILED';
  } else if (rawStatus === 'reverted') {
    normStatus = 'REVERTED';
  }

  const vMethod =
    fix.verificationMethod ||
    fix.verification_method ||
    fix.verification_command ||
    (normStatus === 'VERIFIED' ? 'Recorded verification' : 'devmemory verify');

  const tResult =
    fix.testResult ||
    fix.test_result ||
    fix.verification_details ||
    (normStatus === 'VERIFIED' ? 'Verified successfully' : 'Pending verification execution');

  return {
    ...fix,
    id: fix.id || fix.fixId || fix.fix_id,
    fixId: fix.fixId || fix.fix_id || fix.id,
    incidentId: fix.incidentId || fix.incident_id,
    projectId: fix.projectId || fix.project_id,
    projectName: fix.projectName || fix.project_name || fix.projectId || fix.project_id,
    errorType: fix.errorType || fix.error_type || 'Resolved Issue',
    solutionSummary: fix.solutionSummary || fix.solution_summary || fix.description || fix.proposedSolution || '',
    proposedSolution: fix.proposedSolution || fix.solutionSummary || fix.solution_summary || fix.description || '',
    verificationMethod: vMethod,
    testResult: tResult,
    status: normStatus,
    rawStatus,
    verifiedAt: fix.verifiedAt || fix.verified_at,
    recurrenceCountAfterFix: recurrence,
    recurrenceAfterFix: recurrence,
    author: fix.author || (fix.verification_source === 'user_confirmation' ? 'Developer Confirmation' : 'AI Recommendation + Verification'),
    verificationEventId: fix.verificationEventId || fix.verification_event_id,
    verificationSource: fix.verificationSource || fix.verification_source,
    verificationExitCode: fix.verificationExitCode !== undefined ? fix.verificationExitCode : fix.verification_exit_code,
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
        ? (raw.recurringErrors || raw.recurring_errors).map(normalizeRecurringError)
        : [],
      verifiedFixes: Array.isArray(raw.verifiedFixes || raw.verified_fixes)
        ? (raw.verifiedFixes || raw.verified_fixes).map(normalizeVerifiedFix)
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
    // If diagnosis is missing on incident doc, attempt progressive fetch from diagnosis endpoint
    if (!data.ai_diagnosis && !data.aiDiagnosis) {
      const diagRes = await safeApiFetch(`/incidents/${incidentId}/diagnosis`);
      const diagData = unwrapData(diagRes);
      if (diagRes.ok && diagData) {
        data.ai_diagnosis = diagData;
      }
    }
    return { data: normalizeIncident(data), isMock: false };
  }

  if (!isBackendLive || FORCE_MOCK) {
    const incident = MOCK_INCIDENTS.find((i) => i.incidentId === incidentId) || MOCK_INCIDENTS[0];
    return { data: normalizeIncident(incident), isMock: true };
  }

  return { data: null, isMock: false, error: result.error || 'Incident not found' };
}

export async function fetchIncidentDiagnosis(incidentId) {
  const result = await safeApiFetch(`/incidents/${incidentId}/diagnosis`);
  const data = unwrapData(result);
  if (result.ok && data) {
    return { data: normalizeDiagnosis(data), isMock: false };
  }
  return { data: null, isMock: false, error: result.error || 'Diagnosis not found' };
}

export async function fetchIncidentHistory(incidentId) {
  const result = await safeApiFetch(`/incidents/${incidentId}/history`);
  const data = unwrapData(result);
  if (result.ok && data) {
    const historicalMatches = Array.isArray(data.historical_matches)
      ? data.historical_matches.map(normalizeHistoricalMatch)
      : [];
    const generalKnowledgeMatches = Array.isArray(data.general_knowledge_matches)
      ? data.general_knowledge_matches.map((gk) =>
          normalizeHistoricalMatch({
            ...gk,
            source_id: gk.kb_id || gk.id,
            source_type: 'knowledge_base',
            is_general_knowledge: true,
            is_cross_project: false,
            source_project: 'Curated Knowledge Base',
            verified: false,
            match_reason: gk.explanation || gk.title,
            sanitized_fix_summary: Array.isArray(gk.suggested_resolutions)
              ? gk.suggested_resolutions.join('; ')
              : (gk.suggested_resolutions || gk.explanation),
          })
        )
      : [];

    return {
      data: {
        incidentId: data.current_incident_id || incidentId,
        errorSignature: data.error_signature,
        historicalMatches,
        generalKnowledgeMatches,
        sameProjectMatches: data.same_project_matches || [],
        crossProjectMatches: data.cross_project_matches || [],
      },
      isMock: false,
    };
  }

  return {
    data: null,
    isMock: false,
    error: result.error || 'Retrieval unavailable: unable to reach DevMemory memory bank',
  };
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
    return { data: list.map(normalizeVerifiedFix), isMock: false };
  }

  if (!isBackendLive || FORCE_MOCK) {
    return { data: MOCK_VERIFIED_FIXES.map(normalizeVerifiedFix), isMock: true };
  }

  return { data: [], isMock: false, error: result.error || 'Failed to fetch fixes' };
}

export async function verifyFix(fixId, verificationData, projectId = null) {
  const query = projectId ? `?project_id=${encodeURIComponent(projectId)}` : '';
  const result = await safeApiFetch(`/fixes/${fixId}/verify${query}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(verificationData),
  });
  const data = unwrapData(result);
  if (result.ok && data) {
    return { success: true, data: normalizeVerifiedFix(data), isMock: false };
  }
  return {
    success: false,
    data: null,
    isMock: false,
    error: result.error || 'Failed to verify fix',
    status: result.status,
  };
}

export async function createIncidentFix(incidentId, payload, projectId = null) {
  const query = projectId ? `?project_id=${encodeURIComponent(projectId)}` : '';
  const result = await safeApiFetch(`/incidents/${incidentId}/fixes${query}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const data = unwrapData(result);
  if (result.ok && data) {
    return { success: true, data: normalizeVerifiedFix(data), isMock: false };
  }
  return {
    success: false,
    data: null,
    isMock: false,
    error: result.error || 'Failed to create fix proposal',
    status: result.status,
  };
}

export async function fetchIncidentFixes(incidentId, projectId = null) {
  const query = projectId ? `?project_id=${encodeURIComponent(projectId)}` : '';
  const result = await safeApiFetch(`/incidents/${incidentId}/fixes${query}`);
  const list = unwrapList(result);
  if (result.ok && list !== null) {
    return { data: list.map(normalizeVerifiedFix), isMock: false };
  }
  return { data: [], isMock: false, error: result.error || 'Failed to fetch incident fixes' };
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
