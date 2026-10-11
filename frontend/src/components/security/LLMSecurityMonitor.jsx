import React, { useState, useEffect } from 'react';
import {
  ShieldCheck,
  ShieldAlert,
  Lock,
  Eye,
  CheckCircle2,
  XCircle,
  AlertCircle,
  Clock,
  Key,
  FileText,
  RefreshCw,
  Copy,
  Check,
  Hash,
  Terminal,
  ExternalLink,
} from 'lucide-react';
import Badge from '../common/Badge';
import LoadingSpinner from '../common/LoadingSpinner';
import EmptyState from '../common/EmptyState';
import {
  fetchProjectLLMAudits,
  fetchProjectLLMSecuritySummary,
} from '../../api/devmemoryApi';

export default function LLMSecurityMonitor({ projectId }) {
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [summary, setSummary] = useState(null);
  const [audits, setAudits] = useState([]);
  const [totalAudits, setTotalAudits] = useState(0);
  const [statusFilter, setStatusFilter] = useState('all');
  const [providerFilter, setProviderFilter] = useState('all');
  const [selectedAudit, setSelectedAudit] = useState(null);
  const [copiedHash, setCopiedHash] = useState(false);

  const loadSecurityData = async (isManual = false) => {
    if (isManual) setRefreshing(true);
    try {
      const params = {};
      if (statusFilter !== 'all') params.transmission_status = statusFilter;
      if (providerFilter !== 'all') params.provider = providerFilter;

      const [sumRes, audRes] = await Promise.all([
        fetchProjectLLMSecuritySummary(projectId),
        fetchProjectLLMAudits(projectId, params),
      ]);

      setSummary(sumRes.data);
      const auditItems = audRes.data?.items || (Array.isArray(audRes.data) ? audRes.data : []);
      setAudits(auditItems);
      setTotalAudits(audRes.data?.total ?? auditItems.length);
    } catch (err) {
      console.error('[LLMSecurityMonitor] Error loading security telemetry:', err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    if (projectId) {
      loadSecurityData();
    }
  }, [projectId, statusFilter, providerFilter]);

  const copyToClipboard = (text) => {
    navigator.clipboard?.writeText(text);
    setCopiedHash(true);
    setTimeout(() => setCopiedHash(false), 2000);
  };

  if (loading) {
    return <LoadingSpinner label="Auditing sanitized LLM payloads and security evidence..." />;
  }

  const totalRequests = summary?.total_requests ?? summary?.totalRequests ?? 0;
  const totalRedactions = summary?.total_redactions_applied ?? summary?.totalRedactionsApplied ?? 0;
  const statusCounts = summary?.status_counts ?? summary?.statusCounts ?? {};
  const redactionCategories = summary?.redaction_categories ?? summary?.redactionCategories ?? {};
  const providersUsed = summary?.providers_used ?? summary?.providersUsed ?? [];

  const getStatusBadge = (status) => {
    switch (status?.toLowerCase()) {
      case 'completed':
        return (
          <Badge variant="success" dot>
            Dispatched & Verified
          </Badge>
        );
      case 'dispatched':
        return (
          <Badge variant="info" dot>
            In Flight
          </Badge>
        );
      case 'prepared':
        return (
          <Badge variant="brand" dot>
            Sanitized (Staged)
          </Badge>
        );
      case 'blocked_by_policy':
        return (
          <Badge variant="danger" dot>
            Blocked By Policy
          </Badge>
        );
      case 'failed':
        return (
          <Badge variant="danger" dot>
            Provider Error
          </Badge>
        );
      default:
        return <Badge variant="neutral">{status || 'Unknown'}</Badge>;
    }
  };

  return (
    <div className="space-y-6">
      {/* Security Header Banner */}
      <div className="rounded-2xl border border-indigo-100 dark:border-indigo-900/50 bg-gradient-to-r from-indigo-50/70 via-purple-50/50 to-white/70 dark:from-indigo-950/30 dark:via-purple-950/20 dark:to-slate-900/40 p-5 shadow-glass">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div className="flex items-start gap-3.5">
            <div className="p-2.5 rounded-xl bg-indigo-600 text-white shadow-xs shrink-0 mt-0.5">
              <ShieldCheck className="h-6 w-6" />
            </div>
            <div>
              <div className="flex items-center gap-2.5 flex-wrap">
                <h2 className="text-lg font-bold text-slate-900 dark:text-slate-100 font-mono">
                  Outbound LLM Payload Security Monitor
                </h2>
                <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-mono font-medium bg-emerald-50 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-300 border border-emerald-200/80 dark:border-emerald-800/60">
                  <Lock className="h-3 w-3" />
                  Boundary: provider_adapter_input
                </span>
              </div>
              <p className="mt-1 text-xs text-slate-600 dark:text-slate-400 max-w-3xl leading-relaxed">
                Auditable evidence verifying that all external LLM completions are filtered through DevMemory's
                fail-closed redaction boundary. Raw secrets, tokens, API keys, and environment variables are
                permanently purged immediately before network transmission.
              </p>
            </div>
          </div>

          <button
            onClick={() => loadSecurityData(true)}
            disabled={refreshing}
            className="inline-flex items-center gap-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-white/90 dark:bg-slate-800 px-3.5 py-2 text-xs font-mono text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-700 transition shadow-xs cursor-pointer self-start sm:self-auto shrink-0"
          >
            <RefreshCw className={`h-3.5 w-3.5 text-indigo-500 ${refreshing ? 'animate-spin' : ''}`} />
            <span>Refresh Audit Logs</span>
          </button>
        </div>
      </div>

      {/* Summary KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Card 1: Total Audited Requests */}
        <div className="rounded-xl border border-slate-200/80 dark:border-slate-800 bg-white/80 dark:bg-slate-900/80 p-4 shadow-glass">
          <div className="flex items-center justify-between text-slate-500 dark:text-slate-400">
            <span className="text-xs font-mono uppercase tracking-wider">Outbound Requests</span>
            <FileText className="h-4 w-4 text-indigo-500" />
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="text-2xl font-bold font-mono text-slate-900 dark:text-white">
              {totalRequests}
            </span>
            <span className="text-xs text-slate-500">audited payloads</span>
          </div>
          <div className="mt-2 text-xs text-slate-500 flex gap-2">
            <span>Completed: <strong className="text-emerald-600 dark:text-emerald-400 font-mono">{statusCounts.completed || 0}</strong></span>
            <span>•</span>
            <span>Policy blocked: <strong className="text-rose-600 dark:text-rose-400 font-mono">{statusCounts.blocked_by_policy || 0}</strong></span>
          </div>
        </div>

        {/* Card 2: Cumulative Redactions */}
        <div className="rounded-xl border border-slate-200/80 dark:border-slate-800 bg-white/80 dark:bg-slate-900/80 p-4 shadow-glass">
          <div className="flex items-center justify-between text-slate-500 dark:text-slate-400">
            <span className="text-xs font-mono uppercase tracking-wider">Sanitized Tokens</span>
            <Lock className="h-4 w-4 text-emerald-500" />
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="text-2xl font-bold font-mono text-emerald-600 dark:text-emerald-400">
              {totalRedactions}
            </span>
            <span className="text-xs text-slate-500">secrets stripped</span>
          </div>
          <div className="mt-2 text-xs text-slate-500">
            <span>Guaranteed zero transmission of raw tokens</span>
          </div>
        </div>

        {/* Card 3: Redaction Categories */}
        <div className="rounded-xl border border-slate-200/80 dark:border-slate-800 bg-white/80 dark:bg-slate-900/80 p-4 shadow-glass">
          <div className="flex items-center justify-between text-slate-500 dark:text-slate-400">
            <span className="text-xs font-mono uppercase tracking-wider">Detection Categories</span>
            <Key className="h-4 w-4 text-amber-500" />
          </div>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {Object.keys(redactionCategories).length > 0 ? (
              Object.entries(redactionCategories).map(([cat, count]) => (
                <span
                  key={cat}
                  className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs font-mono bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 border border-slate-200/60 dark:border-slate-700"
                >
                  <span>{cat}:</span>
                  <strong className="text-indigo-600 dark:text-indigo-400">{count}</strong>
                </span>
              ))
            ) : (
              <span className="text-xs text-slate-400 font-mono">No secrets detected yet</span>
            )}
          </div>
        </div>

        {/* Card 4: Providers Contacted */}
        <div className="rounded-xl border border-slate-200/80 dark:border-slate-800 bg-white/80 dark:bg-slate-900/80 p-4 shadow-glass">
          <div className="flex items-center justify-between text-slate-500 dark:text-slate-400">
            <span className="text-xs font-mono uppercase tracking-wider">Active Providers</span>
            <Terminal className="h-4 w-4 text-purple-500" />
          </div>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {providersUsed.length > 0 ? (
              providersUsed.map((p) => (
                <span
                  key={p}
                  className="px-2 py-0.5 rounded-md text-xs font-mono font-medium bg-purple-50 dark:bg-purple-950/60 text-purple-700 dark:text-purple-300 border border-purple-200/60 dark:border-purple-800/60"
                >
                  {p}
                </span>
              ))
            ) : (
              <span className="text-xs text-slate-400 font-mono">None dispatched</span>
            )}
          </div>
          <div className="mt-2 text-xs text-slate-400">
            Isolation: <strong className="text-slate-600 dark:text-slate-300 font-mono">{projectId}</strong>
          </div>
        </div>
      </div>

      {/* Audited Requests List Section */}
      <div className="rounded-2xl border border-slate-200/80 dark:border-slate-800 bg-white/80 dark:bg-slate-900/80 shadow-glass overflow-hidden">
        {/* Table Controls */}
        <div className="p-4 border-b border-slate-200/80 dark:border-slate-800 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 bg-slate-50/50 dark:bg-slate-900/50">
          <div>
            <h3 className="text-sm font-semibold text-slate-900 dark:text-white font-mono flex items-center gap-2">
              <span>Sanitized Payload Audit Stream</span>
              <span className="px-2 py-0.5 rounded-full text-xs font-mono bg-indigo-50 dark:bg-indigo-950/60 text-indigo-600 dark:text-indigo-400 border border-indigo-200/60 dark:border-indigo-800/60">
                {totalAudits} Records
              </span>
            </h3>
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
              Deterministic SHA-256 cryptographically stamped payloads inspected immediately prior to dispatch
            </p>
          </div>

          <div className="flex items-center gap-2 flex-wrap">
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="text-xs font-mono rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-2.5 py-1.5 text-slate-700 dark:text-slate-200 shadow-xs focus:ring-1 focus:ring-indigo-500"
            >
              <option value="all">All Statuses</option>
              <option value="completed">Completed</option>
              <option value="dispatched">Dispatched</option>
              <option value="prepared">Prepared</option>
              <option value="blocked_by_policy">Blocked by Policy</option>
              <option value="failed">Failed</option>
            </select>

            <select
              value={providerFilter}
              onChange={(e) => setProviderFilter(e.target.value)}
              className="text-xs font-mono rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-2.5 py-1.5 text-slate-700 dark:text-slate-200 shadow-xs focus:ring-1 focus:ring-indigo-500"
            >
              <option value="all">All Providers</option>
              {providersUsed.map((pr) => (
                <option key={pr} value={pr}>
                  {pr}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Audits Table */}
        {audits.length === 0 ? (
          <div className="p-8">
            <EmptyState
              title="No LLM audit records found"
              description={`No external LLM diagnostic payloads recorded for project ${projectId} with the current filter criteria.`}
            />
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse text-xs">
              <thead>
                <tr className="border-b border-slate-200 dark:border-slate-800 bg-slate-100/60 dark:bg-slate-800/60 font-mono text-slate-500 dark:text-slate-400 uppercase tracking-wider">
                  <th className="py-3 px-4">Audit ID</th>
                  <th className="py-3 px-4">Timestamp</th>
                  <th className="py-3 px-4">Incident / Event</th>
                  <th className="py-3 px-4">Provider & Model</th>
                  <th className="py-3 px-4">Redactions</th>
                  <th className="py-3 px-4">Status</th>
                  <th className="py-3 px-4">Latency</th>
                  <th className="py-3 px-4 text-right">Sanitized Payload</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800/60 font-mono">
                {audits.map((item) => {
                  const redactionCount = item.redaction_summary?.total_redactions ?? 0;
                  const dateStr = item.created_at
                    ? new Date(item.created_at).toLocaleString('en-US', {
                        month: 'short',
                        day: 'numeric',
                        hour: '2-digit',
                        minute: '2-digit',
                        second: '2-digit',
                      })
                    : '—';

                  return (
                    <tr
                      key={item.audit_id}
                      className="hover:bg-slate-50/80 dark:hover:bg-slate-800/40 transition-colors"
                    >
                      <td className="py-3 px-4 text-indigo-600 dark:text-indigo-400 font-semibold font-mono">
                        {item.audit_id}
                      </td>
                      <td className="py-3 px-4 text-slate-500 dark:text-slate-400 whitespace-nowrap">
                        {dateStr}
                      </td>
                      <td className="py-3 px-4 text-slate-700 dark:text-slate-300">
                        {item.incident_id ? (
                          <span className="text-slate-900 dark:text-slate-100 font-medium">
                            {item.incident_id}
                          </span>
                        ) : item.event_id ? (
                          <span>{item.event_id}</span>
                        ) : (
                          <span className="text-slate-400">—</span>
                        )}
                        {item.attempt > 1 && (
                          <span className="ml-1.5 px-1.5 py-0.2 rounded text-[10px] bg-amber-100 dark:bg-amber-950/60 text-amber-700 dark:text-amber-300 border border-amber-200 dark:border-amber-800">
                            Attempt #{item.attempt}
                          </span>
                        )}
                      </td>
                      <td className="py-3 px-4">
                        <div className="flex flex-col">
                          <span className="font-semibold text-slate-800 dark:text-slate-200">
                            {item.provider}
                          </span>
                          <span className="text-[11px] text-slate-400">{item.model}</span>
                        </div>
                      </td>
                      <td className="py-3 px-4">
                        {redactionCount > 0 ? (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-emerald-50 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800">
                            <Lock className="h-3 w-3" />
                            {redactionCount} Redacted
                          </span>
                        ) : (
                          <span className="text-slate-400 text-xs">Clean (0)</span>
                        )}
                      </td>
                      <td className="py-3 px-4">{getStatusBadge(item.transmission_status)}</td>
                      <td className="py-3 px-4 text-slate-500 whitespace-nowrap">
                        {item.duration_ms ? `${Math.round(item.duration_ms)}ms` : '—'}
                      </td>
                      <td className="py-3 px-4 text-right">
                        <button
                          onClick={() => setSelectedAudit(item)}
                          className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg border border-indigo-200 dark:border-indigo-800 bg-indigo-50/60 dark:bg-indigo-950/40 text-indigo-700 dark:text-indigo-300 hover:bg-indigo-100 dark:hover:bg-indigo-900/60 transition cursor-pointer text-xs font-mono font-medium shadow-2xs"
                        >
                          <Eye className="h-3.5 w-3.5" />
                          <span>Inspect</span>
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Inspect Sanitized Payload Modal */}
      {selectedAudit && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/60 backdrop-blur-xs">
          <div className="w-full max-w-4xl max-h-[90vh] flex flex-col rounded-2xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-150">
            {/* Modal Header */}
            <div className="p-4 sm:p-5 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between bg-slate-50 dark:bg-slate-950/60">
              <div className="flex items-center gap-3">
                <div className="p-2 rounded-xl bg-indigo-600 text-white shadow-xs">
                  <ShieldCheck className="h-5 w-5" />
                </div>
                <div>
                  <h3 className="text-base font-bold text-slate-900 dark:text-white font-mono flex items-center gap-2">
                    <span>Audit Record: {selectedAudit.audit_id}</span>
                    {getStatusBadge(selectedAudit.transmission_status)}
                  </h3>
                  <p className="text-xs text-slate-500 font-mono mt-0.5">
                    Provider: <strong className="text-slate-700 dark:text-slate-300">{selectedAudit.provider}</strong> ({selectedAudit.model}) • Project: {selectedAudit.project_id}
                  </p>
                </div>
              </div>

              <button
                onClick={() => setSelectedAudit(null)}
                className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-slate-800 transition"
              >
                <XCircle className="h-5 w-5" />
              </button>
            </div>

            {/* Modal Body */}
            <div className="p-4 sm:p-6 overflow-y-auto space-y-5 text-xs">
              {/* Security Evidence Verification Card */}
              <div className="rounded-xl border border-emerald-200/80 dark:border-emerald-800/60 bg-emerald-50/50 dark:bg-emerald-950/30 p-3.5 space-y-2">
                <div className="flex items-center justify-between flex-wrap gap-2">
                  <div className="flex items-center gap-2 text-emerald-800 dark:text-emerald-300 font-semibold font-mono">
                    <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                    <span>Cryptographic Evidence & Boundary Stamp</span>
                  </div>
                  <span className="px-2 py-0.5 rounded text-[11px] font-mono bg-emerald-100 dark:bg-emerald-900/60 text-emerald-800 dark:text-emerald-200 border border-emerald-300 dark:border-emerald-700">
                    Capture Boundary: {selectedAudit.capture_boundary || 'provider_adapter_input'}
                  </span>
                </div>

                <div className="flex items-center gap-2 font-mono text-[11px] bg-white/80 dark:bg-slate-900/80 p-2 rounded-lg border border-emerald-200 dark:border-emerald-900/50">
                  <Hash className="h-3.5 w-3.5 text-slate-400 shrink-0" />
                  <span className="text-slate-500 shrink-0">SHA-256 Digest:</span>
                  <span className="text-slate-800 dark:text-slate-200 truncate select-all">
                    {selectedAudit.payload_hash}
                  </span>
                  <button
                    onClick={() => copyToClipboard(selectedAudit.payload_hash)}
                    className="ml-auto p-1 rounded hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-500 hover:text-slate-800 dark:hover:text-white transition shrink-0"
                    title="Copy payload hash"
                  >
                    {copiedHash ? (
                      <Check className="h-3.5 w-3.5 text-emerald-500" />
                    ) : (
                      <Copy className="h-3.5 w-3.5" />
                    )}
                  </button>
                </div>

                <p className="text-[11px] text-emerald-900 dark:text-emerald-300/80 leading-relaxed">
                  DevMemory enforces fail-closed secret redaction before network transmission. The raw
                  unsanitized execution payload is permanently withheld from third-party model inference.
                </p>
              </div>

              {/* Redaction Summary Breakdown */}
              <div className="space-y-2">
                <h4 className="font-mono font-semibold text-slate-800 dark:text-slate-200 flex items-center gap-2">
                  <Lock className="h-3.5 w-3.5 text-indigo-500" />
                  <span>Redaction Summary</span>
                </h4>
                <div className="flex flex-wrap gap-2">
                  <span className="px-2.5 py-1 rounded-lg bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 font-mono">
                    Total Redactions:{' '}
                    <strong className="text-indigo-600 dark:text-indigo-400">
                      {selectedAudit.redaction_summary?.total_redactions ?? 0}
                    </strong>
                  </span>
                  {selectedAudit.redaction_summary?.categories &&
                    Object.entries(selectedAudit.redaction_summary.categories).map(([k, v]) => (
                      <span
                        key={k}
                        className="px-2.5 py-1 rounded-lg bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 font-mono"
                      >
                        {k}: <strong className="text-emerald-600 dark:text-emerald-400">{v}</strong>
                      </span>
                    ))}
                </div>
              </div>

              {/* Sanitized System Prompt */}
              <div className="space-y-1.5">
                <h4 className="font-mono font-semibold text-slate-800 dark:text-slate-200 flex items-center gap-2">
                  <Terminal className="h-3.5 w-3.5 text-indigo-500" />
                  <span>Sanitized System Prompt (Passed to Adapter)</span>
                </h4>
                <pre className="p-3.5 rounded-xl bg-slate-950 text-slate-200 font-mono text-[11px] overflow-x-auto whitespace-pre-wrap max-h-48 border border-slate-800">
                  {selectedAudit.sanitized_payload?.system_prompt || '—'}
                </pre>
              </div>

              {/* Sanitized User Prompt */}
              <div className="space-y-1.5">
                <h4 className="font-mono font-semibold text-slate-800 dark:text-slate-200 flex items-center gap-2">
                  <Terminal className="h-3.5 w-3.5 text-indigo-500" />
                  <span>Sanitized User Context (Passed to Adapter)</span>
                </h4>
                <pre className="p-3.5 rounded-xl bg-slate-950 text-slate-200 font-mono text-[11px] overflow-x-auto whitespace-pre-wrap max-h-64 border border-slate-800">
                  {selectedAudit.sanitized_payload?.user_prompt || '—'}
                </pre>
              </div>

              {/* Provider Messages Array if present */}
              {selectedAudit.sanitized_payload?.messages &&
                selectedAudit.sanitized_payload.messages.length > 0 && (
                  <div className="space-y-2">
                    <h4 className="font-mono font-semibold text-slate-800 dark:text-slate-200">
                      Formatted Messages Array ({selectedAudit.sanitized_payload.messages.length})
                    </h4>
                    <div className="space-y-2 max-h-56 overflow-y-auto">
                      {selectedAudit.sanitized_payload.messages.map((msg, idx) => (
                        <div
                          key={idx}
                          className="p-3 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950 font-mono"
                        >
                          <div className="font-bold text-indigo-600 dark:text-indigo-400 mb-1 uppercase text-[10px]">
                            {msg.role || 'message'}
                          </div>
                          <div className="whitespace-pre-wrap text-slate-700 dark:text-slate-300 text-[11px]">
                            {msg.content}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
            </div>

            {/* Modal Footer */}
            <div className="p-4 border-t border-slate-200 dark:border-slate-800 flex justify-end bg-slate-50 dark:bg-slate-950/60">
              <button
                onClick={() => setSelectedAudit(null)}
                className="px-4 py-2 rounded-xl bg-slate-200 hover:bg-slate-300 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-800 dark:text-slate-200 font-mono text-xs transition cursor-pointer"
              >
                Close Audit Inspector
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
