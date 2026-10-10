import React, { useState, useEffect, useMemo } from 'react';
import { Link } from 'react-router-dom';
import {
  CheckCircle,
  Search,
  Filter,
  RefreshCw,
  FolderGit2,
  AlertTriangle,
  Clock,
  Repeat,
  ShieldCheck,
  Terminal,
  ExternalLink,
  CheckCircle2,
  XCircle,
  Copy,
  Check,
  BrainCircuit,
} from 'lucide-react';
import Badge from '../components/common/Badge';
import StatCard from '../components/common/StatCard';
import LoadingSpinner from '../components/common/LoadingSpinner';
import EmptyState from '../components/common/EmptyState';
import VerifyFixModal from '../components/errors/VerifyFixModal';
import { fetchAllFixes, fetchProjects } from '../api/devmemoryApi';

export default function VerifiedFixesPage() {
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [fixes, setFixes] = useState([]);
  const [projects, setProjects] = useState([]);
  const [isMock, setIsMock] = useState(true);
  const [copiedId, setCopiedId] = useState(null);
  const [verifyModalOpen, setVerifyModalOpen] = useState(false);
  const [selectedFixForVerify, setSelectedFixForVerify] = useState(null);

  // Filters & Search
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedProject, setSelectedProject] = useState('ALL');
  const [selectedStatus, setSelectedStatus] = useState('ALL'); // 'ALL' | 'VERIFIED' | 'PENDING' | 'RECURRING'

  const loadData = async (isManual = false) => {
    if (isManual) setRefreshing(true);
    try {
      const [fixesRes, projsRes] = await Promise.all([
        fetchAllFixes(),
        fetchProjects(),
      ]);
      setFixes(fixesRes.data);
      setProjects(projsRes.data);
      setIsMock(fixesRes.isMock);
    } catch (err) {
      console.error('Failed to load fixes:', err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleCopy = (cmd, id, e) => {
    e.stopPropagation();
    navigator.clipboard?.writeText(cmd);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  // Filtered fixes with strict verification & recurrence check
  const filteredFixes = useMemo(() => {
    return fixes.filter((fix) => {
      // Search
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const solMatch = (fix.solutionSummary || '').toLowerCase().includes(q);
        const errMatch = (fix.errorType || '').toLowerCase().includes(q);
        const projMatch = (fix.projectName || '').toLowerCase().includes(q);
        const cmdMatch = (fix.verificationMethod || '').toLowerCase().includes(q);
        if (!solMatch && !errMatch && !projMatch && !cmdMatch) return false;
      }

      // Project filter
      if (selectedProject !== 'ALL' && fix.projectId !== selectedProject) {
        return false;
      }

      // Status filter
      if (selectedStatus !== 'ALL') {
        const isRecurring = fix.status === 'RECURRING' || (fix.recurrenceCountAfterFix || 0) > 0;
        if (selectedStatus === 'RECURRING' && !isRecurring) return false;
        if (selectedStatus === 'VERIFIED' && (fix.status !== 'VERIFIED' || isRecurring)) return false;
        if (selectedStatus === 'PENDING' && fix.status !== 'PENDING') return false;
      }

      return true;
    });
  }, [fixes, searchQuery, selectedProject, selectedStatus]);

  const stats = useMemo(() => {
    const total = fixes.length;
    // Strict definition: only count as verified if status is VERIFIED AND 0 recurrences
    const verified = fixes.filter(
      (f) => f.status === 'VERIFIED' && (f.recurrenceCountAfterFix || 0) === 0
    ).length;
    const recurring = fixes.filter(
      (f) => f.status === 'RECURRING' || (f.recurrenceCountAfterFix || 0) > 0
    ).length;
    const pending = fixes.filter((f) => f.status === 'PENDING').length;
    const verifiedRate = total ? `${Math.round((verified / total) * 100)}%` : '0%';

    return { total, verified, recurring, pending, verifiedRate };
  }, [fixes]);

  if (loading) {
    return <LoadingSpinner label="Loading verified fixes & outcome benchmarks..." />;
  }

  return (
    <div className="space-y-6 p-3 sm:p-6 max-w-7xl mx-auto">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-slate-900 dark:text-slate-100 font-mono flex items-center gap-2">
            <CheckCircle className="h-5 w-5 sm:h-6 sm:w-6 text-emerald-500 dark:text-emerald-400" />
            Verified Fixes & Solutions
          </h1>
          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
            Troubleshooting memory registry with real execution verification outcomes and automated recurrence detection.
          </p>
        </div>

        <button
          onClick={() => loadData(true)}
          disabled={refreshing}
          aria-label="Refresh verified fixes telemetry"
          className="inline-flex items-center gap-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-white/80 dark:bg-slate-800/80 px-3.5 py-2 text-xs font-mono text-slate-700 dark:text-slate-300 hover:bg-white dark:hover:bg-slate-800 hover:text-slate-900 dark:hover:text-slate-100 shadow-xs hover:border-slate-300 dark:hover:border-slate-600 transition-all cursor-pointer self-start sm:self-auto"
        >
          <RefreshCw className={`h-3.5 w-3.5 text-emerald-500 dark:text-emerald-400 ${refreshing ? 'animate-spin' : ''}`} />
          <span>Refresh Fixes</span>
        </button>
      </div>

      {/* Stats Overview */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2.5 sm:gap-3.5">
        <StatCard
          title="Tracked Fixes"
          value={stats.total}
          icon={CheckCircle}
          subtitle="Across all workspaces"
        />
        <StatCard
          title="Verified Clean Fixes"
          value={stats.verified}
          icon={ShieldCheck}
          badgeText="Verified Only"
          badgeVariant="success"
        />
        <StatCard
          title="Verification Rate"
          value={stats.verifiedRate}
          icon={CheckCircle2}
          subtitle="Passes verification test"
        />
        <StatCard
          title="Recurring Flagged"
          value={stats.recurring}
          icon={Repeat}
          badgeText="Invalidated Fix"
          badgeVariant="danger"
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
              placeholder="Search solutions, error types, projects, or verification commands..."
              aria-label="Search verified fixes and solutions"
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
                aria-label="Filter fixes by project workspace"
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

            {/* Status Filter */}
            <div className="flex items-center gap-1.5 flex-1 sm:flex-initial">
              <Filter className="h-3.5 w-3.5 text-slate-400 dark:text-slate-500 hidden sm:inline" />
              <select
                value={selectedStatus}
                aria-label="Filter fixes by verification status"
                onChange={(e) => setSelectedStatus(e.target.value)}
                className="w-full sm:w-auto rounded-xl border border-slate-200 dark:border-slate-700 bg-white/90 dark:bg-slate-800 px-3 py-2 text-xs font-mono text-slate-700 dark:text-slate-200 focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500 shadow-xs cursor-pointer"
              >
                <option value="ALL">All Fix Statuses</option>
                <option value="VERIFIED">Verified Only (0 Recurrences)</option>
                <option value="PENDING">Pending Verification</option>
                <option value="RECURRING">Recurring (Invalidated)</option>
              </select>
            </div>

            {/* Reset */}
            {(searchQuery || selectedProject !== 'ALL' || selectedStatus !== 'ALL') && (
              <button
                onClick={() => {
                  setSearchQuery('');
                  setSelectedProject('ALL');
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
          <span>Showing {filteredFixes.length} of {fixes.length} tracked fix outcomes</span>
          {isMock && (
            <span className="text-amber-600 dark:text-amber-400 font-semibold">Demo Memory Registry</span>
          )}
        </div>
      </div>

      {/* Fixes Cards Grid */}
      {filteredFixes.length === 0 ? (
        <EmptyState
          title="No Fix Records Found"
          description="No fixes match your active filter criteria. Try clearing search queries or choosing all statuses."
          icon={CheckCircle}
          actionLabel="Reset All Filters"
          onAction={() => {
            setSearchQuery('');
            setSelectedProject('ALL');
            setSelectedStatus('ALL');
          }}
        />
      ) : (
        <div className="space-y-4">
          {filteredFixes.map((fix) => {
            const isRecurring =
              fix.status === 'RECURRING' || (fix.recurrenceCountAfterFix || 0) > 0;
            const isVerified =
              fix.status === 'VERIFIED' && !isRecurring;
            const isPending = fix.status === 'PENDING';

            return (
              <div
                key={fix.id}
                className={`rounded-2xl border bg-white/80 dark:bg-slate-900/80 backdrop-blur-md p-5 shadow-glass space-y-4 transition-all ${
                  isRecurring
                    ? 'border-amber-300/80 dark:border-amber-800/70 bg-amber-50/20 dark:bg-amber-950/20'
                    : isVerified
                    ? 'border-emerald-200/80 dark:border-emerald-800/70'
                    : 'border-slate-200/80 dark:border-slate-800/80'
                }`}
              >
                {/* Header */}
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-100 dark:border-slate-800 pb-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-xs font-bold text-slate-900 dark:text-slate-100 bg-slate-100 dark:bg-slate-800 px-2.5 py-1 rounded-lg border border-slate-200 dark:border-slate-700">
                      {fix.id}
                    </span>

                    <span className="font-mono text-xs font-semibold text-rose-700 dark:text-rose-300 bg-rose-50 dark:bg-rose-950/60 px-2.5 py-1 rounded-lg border border-rose-200 dark:border-rose-800/60">
                      {fix.errorType}
                    </span>

                    <Link
                      to={`/projects/${fix.projectId}`}
                      className="font-mono text-xs text-slate-700 dark:text-slate-300 hover:text-brand-600 dark:hover:text-indigo-400 bg-slate-100/80 dark:bg-slate-800/80 px-2.5 py-1 rounded-lg border border-slate-200 dark:border-slate-700 transition-colors"
                    >
                      {fix.projectName}
                    </Link>

                    {/* Strict Status Badging */}
                    {isVerified && (
                      <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 dark:bg-emerald-950/60 px-3 py-1 text-xs font-mono font-bold text-emerald-700 dark:text-emerald-300 border border-emerald-300 dark:border-emerald-800/60 shadow-xs">
                        <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600 dark:text-emerald-400" />
                        <span>VERIFIED (0 Recurrences)</span>
                      </span>
                    )}

                    {isRecurring && (
                      <span className="inline-flex items-center gap-1 rounded-full bg-rose-50 dark:bg-rose-950/60 px-3 py-1 text-xs font-mono font-bold text-rose-700 dark:text-rose-300 border border-rose-300 dark:border-rose-800/60 shadow-xs animate-pulse">
                        <Repeat className="h-3.5 w-3.5 text-rose-600 dark:text-rose-400" />
                        <span>RECURRING ({fix.recurrenceCountAfterFix || 2}x Invalidation)</span>
                      </span>
                    )}

                    {isPending && (
                      <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 dark:bg-amber-950/60 px-3 py-1 text-xs font-mono font-bold text-amber-700 dark:text-amber-300 border border-amber-300 dark:border-amber-800/60 shadow-xs">
                        <Clock className="h-3.5 w-3.5 text-amber-600 dark:text-amber-400" />
                        <span>PENDING VERIFICATION</span>
                      </span>
                    )}
                  </div>

                  <div className="text-xs font-mono text-slate-400 dark:text-slate-500">
                    {fix.verifiedAt ? (
                      <span>Verified: {new Date(fix.verifiedAt).toLocaleDateString()}</span>
                    ) : (
                      <span className="italic">Unverified</span>
                    )}
                  </div>
                </div>

                {/* Recurrence Warning Banner */}
                {isRecurring && (
                  <div className="rounded-xl border border-rose-200 dark:border-rose-900/60 bg-rose-50/80 dark:bg-rose-950/50 p-3 text-xs font-mono text-rose-900 dark:text-rose-200 flex items-start gap-2.5">
                    <AlertTriangle className="h-4 w-4 text-rose-600 dark:text-rose-400 mt-0.5 shrink-0" />
                    <div>
                      <strong className="font-bold">Automated Recurrence Alert: </strong>
                      This error recurred {fix.recurrenceCountAfterFix || 2} times after the initial fix was deployed.
                      Per DevMemory accuracy guarantees, this fix is invalidated and cannot be marked as verified.
                    </div>
                  </div>
                )}

                {/* Proposed Solution */}
                <div>
                  <span className="text-[10px] font-mono uppercase font-semibold text-slate-400 dark:text-slate-500 block mb-1">
                    Proposed Solution
                  </span>
                  <p className="text-xs font-mono text-slate-800 dark:text-slate-200 leading-relaxed bg-slate-50/70 dark:bg-slate-800/60 p-3 rounded-xl border border-slate-200/80 dark:border-slate-700/80 font-medium">
                    {fix.solutionSummary}
                  </p>
                </div>

                {/* Verification Command & Test Result */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-1">
                  <div>
                    <span className="text-[10px] font-mono uppercase font-semibold text-slate-400 dark:text-slate-500 block mb-1">
                      Verification Command
                    </span>
                    <div className="flex items-center justify-between p-2.5 rounded-lg bg-slate-900 dark:bg-black/80 dark:border dark:border-slate-800 text-slate-100 font-mono text-xs">
                      <code className="truncate">{fix.verificationMethod}</code>
                      <button
                        onClick={(e) => handleCopy(fix.verificationMethod, fix.id, e)}
                        className="text-slate-400 hover:text-white ml-2 shrink-0 p-0.5"
                        title="Copy command"
                      >
                        {copiedId === fix.id ? (
                          <Check className="h-3.5 w-3.5 text-emerald-400" />
                        ) : (
                          <Copy className="h-3.5 w-3.5" />
                        )}
                      </button>
                    </div>
                  </div>

                  <div>
                    <span className="text-[10px] font-mono uppercase font-semibold text-slate-400 dark:text-slate-500 block mb-1">
                      Verification Test Result
                    </span>
                    <div
                      className={`p-2.5 rounded-lg border font-mono text-xs flex items-center gap-2 ${
                        isVerified
                          ? 'bg-emerald-50/80 dark:bg-emerald-950/50 border-emerald-200 dark:border-emerald-800/60 text-emerald-800 dark:text-emerald-300'
                          : isRecurring
                          ? 'bg-rose-50/80 dark:bg-rose-950/50 border-rose-200 dark:border-rose-900/60 text-rose-800 dark:text-rose-300'
                          : 'bg-amber-50/80 dark:bg-amber-950/50 border-amber-200 dark:border-amber-800/60 text-amber-800 dark:text-amber-300'
                      }`}
                    >
                      {isVerified ? (
                        <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600 dark:text-emerald-400 shrink-0" />
                      ) : isRecurring ? (
                        <XCircle className="h-3.5 w-3.5 text-rose-600 dark:text-rose-400 shrink-0" />
                      ) : (
                        <Clock className="h-3.5 w-3.5 text-amber-600 dark:text-amber-400 shrink-0" />
                      )}
                      <span className="truncate">{fix.testResult || 'Awaiting command execution'}</span>
                    </div>
                  </div>
                </div>

                {/* Footer with links */}
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-3 border-t border-slate-100 dark:border-slate-800 text-xs font-mono">
                  <div className="text-slate-500 dark:text-slate-400">
                    <span>Source: </span>
                    <strong className="text-slate-700 dark:text-slate-300">{fix.author || 'AI + Dev Verification'}</strong>
                  </div>

                  <div className="flex items-center gap-3 flex-wrap">
                    {!isRecurring && (
                      <button
                        onClick={() => {
                          setSelectedFixForVerify(fix);
                          setVerifyModalOpen(true);
                        }}
                        className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl font-mono text-xs font-bold transition-all cursor-pointer shadow-xs ${
                          isVerified
                            ? 'bg-emerald-50 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-300 border border-emerald-300 dark:border-emerald-800 hover:bg-emerald-100'
                            : 'bg-emerald-600 hover:bg-emerald-700 text-white border border-emerald-600'
                        }`}
                      >
                        <ShieldCheck className="h-3.5 w-3.5" />
                        <span>{isVerified ? 'Re-Verify Fix' : 'Verify Fix'}</span>
                      </button>
                    )}

                    {fix.relatedIncidentId && (
                      <Link
                        to={`/projects/${fix.projectId}/errors`}
                        className="inline-flex items-center gap-1 text-indigo-600 dark:text-indigo-400 hover:text-indigo-800 dark:hover:text-indigo-300 font-semibold"
                      >
                        <BrainCircuit className="h-3.5 w-3.5" />
                        <span>Inspect in Project Errors</span>
                        <ExternalLink className="h-3 w-3" />
                      </Link>
                    )}
                    <Link
                      to={`/projects/${fix.projectId}`}
                      className="inline-flex items-center gap-1 text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200"
                    >
                      <span>Open Workspace</span>
                      <ExternalLink className="h-3 w-3" />
                    </Link>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {verifyModalOpen && (
        <VerifyFixModal
          isOpen={verifyModalOpen}
          onClose={() => {
            setVerifyModalOpen(false);
            setSelectedFixForVerify(null);
          }}
          fix={selectedFixForVerify}
          projectId={selectedFixForVerify?.projectId}
          onVerified={() => {
            loadData();
          }}
        />
      )}
    </div>
  );
}
