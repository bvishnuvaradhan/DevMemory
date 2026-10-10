import React, { useState, useEffect, useMemo } from 'react';
import { Link } from 'react-router-dom';
import {
  AlertTriangle,
  Search,
  Filter,
  RefreshCw,
  FolderGit2,
  FileCode2,
  Clock,
  Sparkles,
  ShieldCheck,
  Repeat,
  ExternalLink,
  ChevronRight,
  Info,
  CheckCircle2,
  BrainCircuit,
  Terminal,
} from 'lucide-react';
import Badge from '../components/common/Badge';
import StatCard from '../components/common/StatCard';
import LoadingSpinner from '../components/common/LoadingSpinner';
import EmptyState from '../components/common/EmptyState';
import { fetchAllIncidents, fetchProjects } from '../api/devmemoryApi';

export default function ErrorsDiagnosesPage() {
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [incidents, setIncidents] = useState([]);
  const [projects, setProjects] = useState([]);
  const [isMock, setIsMock] = useState(true);

  // Filters & Search
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedProject, setSelectedProject] = useState('ALL');
  const [selectedType, setSelectedType] = useState('ALL');
  const [selectedStatus, setSelectedStatus] = useState('ALL');

  const loadData = async (isManual = false) => {
    if (isManual) setRefreshing(true);
    try {
      const [incRes, projsRes] = await Promise.all([
        fetchAllIncidents(),
        fetchProjects(),
      ]);
      setIncidents(incRes.data);
      setProjects(projsRes.data);
      setIsMock(incRes.isMock);
    } catch (err) {
      console.error('Failed to load error incidents:', err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  // Unique error types for dropdown
  const errorTypes = useMemo(() => {
    const set = new Set();
    incidents.forEach((inc) => {
      if (inc.errorType) set.add(inc.errorType);
    });
    return Array.from(set);
  }, [incidents]);

  // Filtered incidents
  const filteredIncidents = useMemo(() => {
    return incidents.filter((inc) => {
      // Search
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const typeMatch = (inc.errorType || '').toLowerCase().includes(q);
        const msgMatch = (inc.errorMessage || '').toLowerCase().includes(q);
        const projMatch = (inc.projectName || '').toLowerCase().includes(q);
        const fileMatch = (inc.sourceLocation?.file || '').toLowerCase().includes(q);
        if (!typeMatch && !msgMatch && !projMatch && !fileMatch) return false;
      }

      // Project filter
      if (selectedProject !== 'ALL' && inc.projectId !== selectedProject) {
        return false;
      }

      // Type filter
      if (selectedType !== 'ALL' && inc.errorType !== selectedType) {
        return false;
      }

      // Status filter
      if (selectedStatus !== 'ALL') {
        const status = (inc.fixOutcome?.status || 'PENDING').toUpperCase();
        if (selectedStatus === 'RECURRING') {
          if (status !== 'RECURRING' && !(inc.fixOutcome?.recurrenceAfterFix > 0)) {
            return false;
          }
        } else if (status !== selectedStatus) {
          return false;
        }
      }

      return true;
    });
  }, [incidents, searchQuery, selectedProject, selectedType, selectedStatus]);

  const stats = useMemo(() => {
    const total = incidents.length;
    const affectedProjects = new Set(incidents.map((i) => i.projectId)).size;
    const recurring = incidents.filter(
      (i) => i.fixOutcome?.status === 'RECURRING' || (i.fixOutcome?.recurrenceAfterFix || 0) > 0
    ).length;
    const verified = incidents.filter(
      (i) => i.fixOutcome?.status === 'VERIFIED' && (i.fixOutcome?.recurrenceAfterFix || 0) === 0
    ).length;
    return { total, affectedProjects, recurring, verified };
  }, [incidents]);

  if (loading) {
    return <LoadingSpinner label="Loading cross-project troubleshooting incidents..." />;
  }

  return (
    <div className="space-y-6 p-3 sm:p-6 max-w-7xl mx-auto">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-slate-900 dark:text-slate-100 font-mono flex items-center gap-2">
            <AlertTriangle className="h-5 w-5 sm:h-6 sm:w-6 text-rose-500 dark:text-rose-400" />
            Errors & AI Diagnoses
          </h1>
          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
            Cross-project troubleshooting repository separating <strong className="text-slate-800 dark:text-slate-200">observed runtime evidence</strong> from <strong className="text-indigo-600 dark:text-indigo-400">AI-generated fix hypotheses</strong>.
          </p>
        </div>

        <button
          onClick={() => loadData(true)}
          disabled={refreshing}
          aria-label="Refresh error incidents telemetry"
          className="inline-flex items-center gap-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-white/80 dark:bg-slate-800/80 px-3.5 py-2 text-xs font-mono text-slate-700 dark:text-slate-300 hover:bg-white dark:hover:bg-slate-800 hover:text-slate-900 dark:hover:text-slate-100 shadow-xs hover:border-slate-300 dark:hover:border-slate-600 transition-all cursor-pointer self-start sm:self-auto"
        >
          <RefreshCw className={`h-3.5 w-3.5 text-rose-500 dark:text-rose-400 ${refreshing ? 'animate-spin' : ''}`} />
          <span>Refresh Incidents</span>
        </button>
      </div>

      {/* Stats Overview */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2.5 sm:gap-3.5">
        <StatCard
          title="Active Incidents"
          value={stats.total}
          icon={AlertTriangle}
          subtitle="Across all workspaces"
        />
        <StatCard
          title="Affected Projects"
          value={stats.affectedProjects}
          icon={FolderGit2}
          subtitle="Workspaces impacted"
        />
        <StatCard
          title="Recurring Issues"
          value={stats.recurring}
          icon={Repeat}
          badgeText="Alert Flagged"
          badgeVariant="danger"
        />
        <StatCard
          title="Verified Mitigations"
          value={stats.verified}
          icon={ShieldCheck}
          badgeText="Verified Only"
          badgeVariant="success"
        />
      </div>

      {/* Filter and Search Bar */}
      <div className="rounded-2xl border border-white/80 bg-white/75 dark:border-slate-800/80 dark:bg-slate-900/75 backdrop-blur-md p-3.5 sm:p-4 shadow-glass space-y-3">
        <div className="flex flex-col md:flex-row md:items-center gap-3">
          {/* Search */}
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-400 dark:text-slate-500" />
            <input
              type="text"
              placeholder="Search error type, message, project, or file..."
              aria-label="Search error incidents by message or file"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full rounded-xl border border-slate-200 dark:border-slate-700 bg-white/90 dark:bg-slate-800/90 pl-9 pr-3.5 py-2 text-xs font-mono text-slate-800 dark:text-slate-100 placeholder-slate-400 dark:placeholder-slate-500 focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500 shadow-xs transition-colors"
            />
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {/* Project Filter */}
            <div className="flex items-center gap-1.5 flex-1 sm:flex-initial">
              <FolderGit2 className="h-3.5 w-3.5 text-slate-400 dark:text-slate-500 hidden sm:inline" />
              <select
                value={selectedProject}
                aria-label="Filter incidents by project"
                onChange={(e) => setSelectedProject(e.target.value)}
                className="w-full sm:w-auto rounded-xl border border-slate-200 dark:border-slate-700 bg-white/90 dark:bg-slate-800 px-3 py-2 text-xs font-mono text-slate-700 dark:text-slate-200 focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500 shadow-xs cursor-pointer"
              >
                <option value="ALL">All Projects ({projects.length})</option>
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </div>

            {/* Error Type Filter */}
            <div className="flex items-center gap-1.5 flex-1 sm:flex-initial">
              <AlertTriangle className="h-3.5 w-3.5 text-slate-400 dark:text-slate-500 hidden sm:inline" />
              <select
                value={selectedType}
                aria-label="Filter incidents by error type"
                onChange={(e) => setSelectedType(e.target.value)}
                className="w-full sm:w-auto rounded-xl border border-slate-200 dark:border-slate-700 bg-white/90 dark:bg-slate-800 px-3 py-2 text-xs font-mono text-slate-700 dark:text-slate-200 focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500 shadow-xs cursor-pointer"
              >
                <option value="ALL">All Error Types</option>
                {errorTypes.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </div>

            {/* Status Filter */}
            <div className="flex items-center gap-1.5 flex-1 sm:flex-initial">
              <Filter className="h-3.5 w-3.5 text-slate-400 dark:text-slate-500 hidden sm:inline" />
              <select
                value={selectedStatus}
                aria-label="Filter incidents by verification status"
                onChange={(e) => setSelectedStatus(e.target.value)}
                className="w-full sm:w-auto rounded-xl border border-slate-200 dark:border-slate-700 bg-white/90 dark:bg-slate-800 px-3 py-2 text-xs font-mono text-slate-700 dark:text-slate-200 focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500 shadow-xs cursor-pointer"
              >
                <option value="ALL">All Statuses</option>
                <option value="VERIFIED">Verified Fix</option>
                <option value="PENDING">Pending Verification</option>
                <option value="RECURRING">Recurring (Invalidated)</option>
              </select>
            </div>

            {/* Reset */}
            {(searchQuery || selectedProject !== 'ALL' || selectedType !== 'ALL' || selectedStatus !== 'ALL') && (
              <button
                onClick={() => {
                  setSearchQuery('');
                  setSelectedProject('ALL');
                  setSelectedType('ALL');
                  setSelectedStatus('ALL');
                }}
                className="rounded-xl border border-rose-200 dark:border-rose-900/60 bg-rose-50/70 dark:bg-rose-950/50 px-3 py-2 text-xs font-mono text-rose-700 dark:text-rose-300 hover:bg-rose-100/80 dark:hover:bg-rose-900/60 transition-colors cursor-pointer"
              >
                Clear Filters
              </button>
            )}
          </div>
        </div>

        <div className="text-[11px] font-mono text-slate-500 dark:text-slate-400 flex items-center justify-between pt-1 border-t border-slate-100 dark:border-slate-800">
          <span>Showing {filteredIncidents.length} of {incidents.length} incidents</span>
          {isMock && (
            <span className="text-amber-600 dark:text-amber-400 font-semibold">Demo Troubleshooting Bank</span>
          )}
        </div>
      </div>

      {/* Incidents List */}
      {filteredIncidents.length === 0 ? (
        <EmptyState
          title="No Matching Incidents Found"
          description="No error incidents match the current filters. Adjust your search criteria to inspect troubleshooting records."
          icon={CheckCircle2}
          actionLabel="Reset All Filters"
          onAction={() => {
            setSearchQuery('');
            setSelectedProject('ALL');
            setSelectedType('ALL');
            setSelectedStatus('ALL');
          }}
        />
      ) : (
        <div className="space-y-6">
          {filteredIncidents.map((inc) => {
            const isRecurring =
              inc.fixOutcome?.status === 'RECURRING' ||
              (inc.fixOutcome?.recurrenceAfterFix || 0) > 0;
            const isVerified =
              inc.fixOutcome?.status === 'VERIFIED' && !isRecurring;

            return (
              <div
                key={inc.incidentId}
                className="rounded-2xl border border-white/80 bg-white/75 dark:border-slate-800/80 dark:bg-slate-900/75 backdrop-blur-md p-6 shadow-glass space-y-5"
              >
                {/* Incident Card Top Header */}
                <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 border-b border-slate-100 dark:border-slate-800 pb-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="inline-flex items-center gap-1.5 rounded-full bg-rose-50 dark:bg-rose-950/60 px-3 py-1 text-xs font-mono font-bold text-rose-700 dark:text-rose-300 border border-rose-200 dark:border-rose-800/60 shadow-xs">
                      <AlertTriangle className="h-3.5 w-3.5 text-rose-500 dark:text-rose-400" />
                      <span>{inc.errorType}</span>
                    </span>

                    <Link
                      to={`/projects/${inc.projectId}`}
                      className="rounded-full bg-slate-100 dark:bg-slate-800 px-3 py-1 text-xs font-mono font-medium text-slate-700 dark:text-slate-300 hover:bg-brand-50 dark:hover:bg-indigo-950/60 hover:text-brand-600 dark:hover:text-indigo-400 border border-slate-200 dark:border-slate-700 transition-colors"
                    >
                      {inc.projectName}
                    </Link>

                    {isRecurring && (
                      <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 dark:bg-amber-950/60 px-3 py-1 text-xs font-mono font-bold text-amber-700 dark:text-amber-300 border border-amber-300 dark:border-amber-800/60 animate-pulse">
                        <Repeat className="h-3.5 w-3.5 text-amber-600 dark:text-amber-400" />
                        <span>Recurring Issue ({inc.fixOutcome?.recurrenceAfterFix || 1}x)</span>
                      </span>
                    )}

                    {isVerified && (
                      <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 dark:bg-emerald-950/60 px-3 py-1 text-xs font-mono font-semibold text-emerald-700 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800/60">
                        <ShieldCheck className="h-3.5 w-3.5 text-emerald-600 dark:text-emerald-400" />
                        <span>Verified Fix</span>
                      </span>
                    )}

                    {!isRecurring && !isVerified && (
                      <span className="inline-flex items-center gap-1 rounded-full bg-sky-50 dark:bg-sky-950/60 px-3 py-1 text-xs font-mono font-semibold text-sky-700 dark:text-sky-300 border border-sky-200 dark:border-sky-800/60">
                        <Clock className="h-3.5 w-3.5 text-sky-600 dark:text-sky-400" />
                        <span>Pending Verification</span>
                      </span>
                    )}
                  </div>

                  <div className="flex items-center gap-3 text-xs font-mono text-slate-400 dark:text-slate-500">
                    <span>Incident ID: <strong className="text-slate-700 dark:text-slate-300">{inc.incidentId}</strong></span>
                    <span>•</span>
                    <span>{inc.timestamp ? new Date(inc.timestamp).toLocaleString() : 'Recorded'}</span>
                  </div>
                </div>

                {/* Error Message Display */}
                <div>
                  <span className="text-[10px] font-mono uppercase font-semibold text-slate-400 dark:text-slate-500 block mb-1">
                    Error Message & Command
                  </span>
                  <div className="p-3 bg-rose-50/60 dark:bg-rose-950/40 border border-rose-200/80 dark:border-rose-900/60 rounded-xl text-xs font-mono text-rose-900 dark:text-rose-200 break-words">
                    {inc.errorMessage}
                  </div>
                  {inc.command && (
                    <div className="mt-2 flex items-center gap-2 text-xs font-mono text-slate-600 dark:text-slate-400">
                      <Terminal className="h-3.5 w-3.5 text-slate-400 dark:text-slate-500" />
                      <span className="text-slate-400 dark:text-slate-500">Triggered by:</span>
                      <code className="bg-slate-100 dark:bg-slate-800 px-2 py-0.5 rounded text-slate-800 dark:text-slate-200 border border-slate-200 dark:border-slate-700">
                        {inc.command}
                      </code>
                    </div>
                  )}
                </div>

                {/* Source Location */}
                <div className="flex items-center gap-2 text-xs font-mono">
                  <FileCode2 className="h-4 w-4 text-slate-400 dark:text-slate-500" />
                  <span className="text-slate-400 dark:text-slate-500">Source Location:</span>
                  {inc.sourceLocation?.file ? (
                    <span className="text-slate-800 dark:text-slate-200 bg-slate-100 dark:bg-slate-800 px-2 py-0.5 rounded border border-slate-200 dark:border-slate-700 font-semibold">
                      {inc.sourceLocation.file}:{inc.sourceLocation.line || 0}
                    </span>
                  ) : (
                    <span className="text-slate-400 dark:text-slate-500 italic bg-slate-50 dark:bg-slate-805/50 px-2 py-0.5 rounded border border-slate-200 dark:border-slate-700">
                      No source file location available (OS-level signal / Container termination)
                    </span>
                  )}
                </div>

                {/* CRITICAL: Clear separation of Observed Evidence vs AI Hypotheses */}
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 pt-2">
                  {/* Left Column: Observed Runtime Evidence */}
                  <div className="rounded-xl border border-slate-200/90 dark:border-slate-800 bg-white/90 dark:bg-slate-800/80 p-4 shadow-xs space-y-3">
                    <div className="flex items-center gap-2 text-slate-800 dark:text-slate-200 border-b border-slate-100 dark:border-slate-700 pb-2">
                      <ShieldCheck className="h-4 w-4 text-slate-600 dark:text-slate-400" />
                      <h4 className="text-xs font-bold font-mono uppercase tracking-wider text-slate-700 dark:text-slate-200">
                        Observed Runtime Evidence (Ground Truth)
                      </h4>
                    </div>
                    {inc.aiDiagnosis?.observedEvidence && inc.aiDiagnosis.observedEvidence.length > 0 ? (
                      <ul className="space-y-2 text-xs font-mono text-slate-700 dark:text-slate-300">
                        {inc.aiDiagnosis.observedEvidence.map((ev, idx) => (
                          <li key={idx} className="flex items-start gap-2">
                            <span className="h-1.5 w-1.5 rounded-full bg-slate-400 dark:bg-slate-500 mt-1.5 shrink-0" />
                            <span className="leading-relaxed">{ev}</span>
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="text-xs font-mono text-slate-400 dark:text-slate-500 italic">
                        Raw exit code {inc.exitCode} captured. Stack trace analysis available.
                      </p>
                    )}
                  </div>

                  {/* Right Column: AI-Generated Hypotheses & Recommendations */}
                  <div className="rounded-xl border border-indigo-100 dark:border-indigo-900/50 bg-indigo-50/40 dark:bg-indigo-950/30 p-4 shadow-xs space-y-3">
                    <div className="flex items-center justify-between border-b border-indigo-100 dark:border-indigo-900/60 pb-2">
                      <div className="flex items-center gap-2 text-indigo-700 dark:text-indigo-300">
                        <Sparkles className="h-4 w-4 text-indigo-500 dark:text-indigo-400" />
                        <h4 className="text-xs font-bold font-mono uppercase tracking-wider">
                          AI Hypotheses & Recommendations
                        </h4>
                      </div>
                      {inc.aiDiagnosis?.confidence && (
                        <span className="rounded-full bg-indigo-100 dark:bg-indigo-900/60 px-2.5 py-0.5 text-[10px] font-mono font-bold text-indigo-700 dark:text-indigo-300 border border-indigo-200 dark:border-indigo-800/60">
                          {inc.aiDiagnosis.confidence}
                        </span>
                      )}
                    </div>

                    <div className="space-y-2 text-xs font-mono">
                      {inc.aiDiagnosis?.hypotheses && (
                        <div>
                          <span className="text-[10px] font-semibold uppercase text-indigo-900/60 dark:text-indigo-300/70 block mb-1">
                            Hypotheses
                          </span>
                          <ul className="space-y-1.5 text-indigo-950 dark:text-indigo-200">
                            {inc.aiDiagnosis.hypotheses.map((hyp, idx) => (
                              <li key={idx} className="flex items-start gap-2">
                                <span className="h-1.5 w-1.5 rounded-full bg-indigo-400 dark:bg-indigo-500 mt-1.5 shrink-0" />
                                <span className="leading-relaxed">{hyp}</span>
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}

                      {inc.aiDiagnosis?.recommendations && (
                        <div className="pt-2 border-t border-indigo-100/80 dark:border-indigo-900/60">
                          <span className="text-[10px] font-semibold uppercase text-indigo-900/60 dark:text-indigo-300/70 block mb-1">
                            Recommended Actions
                          </span>
                          <ul className="space-y-1.5 text-indigo-950 dark:text-indigo-200">
                            {inc.aiDiagnosis.recommendations.map((rec, idx) => (
                              <li key={idx} className="flex items-start gap-2">
                                <ChevronRight className="h-3 w-3 text-indigo-500 dark:text-indigo-400 mt-0.5 shrink-0" />
                                <span className="leading-relaxed">{rec}</span>
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>
                  </div>
                </div>

                {/* Fix Outcome & Deep Links Footer */}
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-3 border-t border-slate-100 dark:border-slate-800">
                  <div className="text-xs font-mono text-slate-600 dark:text-slate-400">
                    {inc.fixOutcome?.proposedSolution ? (
                      <div>
                        <strong className="text-slate-800 dark:text-slate-200">Proposed Solution: </strong>
                        <span>{inc.fixOutcome.proposedSolution}</span>
                      </div>
                    ) : (
                      <span className="text-slate-400 dark:text-slate-500 italic">No solution submitted yet.</span>
                    )}
                  </div>

                  <div className="flex items-center gap-2 shrink-0">
                    <Link
                      to={`/projects/${inc.projectId}/errors`}
                      className="inline-flex items-center gap-1.5 rounded-xl border border-indigo-200 dark:border-indigo-800/60 bg-indigo-50/80 dark:bg-indigo-950/60 px-3 py-1.5 text-xs font-mono text-indigo-700 dark:text-indigo-300 hover:bg-indigo-100 dark:hover:bg-indigo-900/60 transition-colors shadow-xs font-semibold"
                    >
                      <BrainCircuit className="h-3.5 w-3.5" />
                      <span>Source-Aware Error Inspector</span>
                      <ExternalLink className="h-3 w-3" />
                    </Link>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
