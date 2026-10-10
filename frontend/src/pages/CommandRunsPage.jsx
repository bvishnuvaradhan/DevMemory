import React, { useState, useEffect, useMemo } from 'react';
import { Link } from 'react-router-dom';
import {
  TerminalSquare,
  Search,
  Filter,
  RefreshCw,
  CheckCircle2,
  XCircle,
  Clock,
  ArrowUpDown,
  ExternalLink,
  FileCode2,
  FolderGit2,
  Copy,
  Check,
  Calendar,
} from 'lucide-react';
import Badge from '../components/common/Badge';
import StatCard from '../components/common/StatCard';
import LoadingSpinner from '../components/common/LoadingSpinner';
import EmptyState from '../components/common/EmptyState';
import { fetchAllRuns, fetchProjects } from '../api/devmemoryApi';

export default function CommandRunsPage() {
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [runs, setRuns] = useState([]);
  const [projects, setProjects] = useState([]);
  const [isMock, setIsMock] = useState(true);
  const [copiedId, setCopiedId] = useState(null);

  // Filters & Search
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedProject, setSelectedProject] = useState('ALL');
  const [selectedStatus, setSelectedStatus] = useState('ALL');
  const [sortOrder, setSortOrder] = useState('newest'); // 'newest' | 'oldest' | 'duration_desc' | 'duration_asc'

  // Selected Run Modal
  const [selectedRunModal, setSelectedRunModal] = useState(null);

  const loadData = async (isManual = false) => {
    if (isManual) setRefreshing(true);
    try {
      const [runsRes, projsRes] = await Promise.all([
        fetchAllRuns(),
        fetchProjects(),
      ]);
      setRuns(runsRes.data);
      setProjects(projsRes.data);
      setIsMock(runsRes.isMock);
    } catch (err) {
      console.error('Failed to load command runs:', err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  // Dismiss modal on Escape key press
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape' && selectedRunModal) {
        setSelectedRunModal(null);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [selectedRunModal]);

  const handleCopyCommand = (cmd, id, e) => {
    e.stopPropagation();
    navigator.clipboard?.writeText(cmd);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  // Filter & Sort Logic
  const filteredRuns = useMemo(() => {
    return runs
      .filter((r) => {
        // Search
        if (searchQuery.trim()) {
          const q = searchQuery.toLowerCase();
          const cmdMatch = (r.command || '').toLowerCase().includes(q);
          const projMatch = (r.projectName || '').toLowerCase().includes(q);
          const errMatch = (r.errorSummary || '').toLowerCase().includes(q);
          const srcMatch = (r.sourceFile || '').toLowerCase().includes(q);
          if (!cmdMatch && !projMatch && !errMatch && !srcMatch) return false;
        }

        // Project filter
        if (selectedProject !== 'ALL' && r.projectId !== selectedProject) {
          return false;
        }

        // Status filter
        if (selectedStatus === 'SUCCESS' && r.exitCode !== 0) return false;
        if (selectedStatus === 'FAILED' && r.exitCode === 0) return false;

        return true;
      })
      .sort((a, b) => {
        if (sortOrder === 'newest') {
          return new Date(b.timestamp || 0) - new Date(a.timestamp || 0);
        }
        if (sortOrder === 'oldest') {
          return new Date(a.timestamp || 0) - new Date(b.timestamp || 0);
        }
        if (sortOrder === 'duration_desc') {
          return (b.durationMs || 0) - (a.durationMs || 0);
        }
        if (sortOrder === 'duration_asc') {
          return (a.durationMs || 0) - (b.durationMs || 0);
        }
        return 0;
      });
  }, [runs, searchQuery, selectedProject, selectedStatus, sortOrder]);

  const stats = useMemo(() => {
    const total = runs.length;
    const passed = runs.filter((r) => r.exitCode === 0).length;
    const failed = total - passed;
    const avgDuration = total
      ? Math.round(runs.reduce((acc, r) => acc + (r.durationMs || 0), 0) / total)
      : 0;
    return { total, passed, failed, avgDuration };
  }, [runs]);

  if (loading) {
    return <LoadingSpinner label="Loading cross-project command telemetry..." />;
  }

  return (
    <div className="space-y-6 p-3 sm:p-6 max-w-7xl mx-auto">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-slate-900 dark:text-slate-100 font-mono flex items-center gap-2">
            <TerminalSquare className="h-5 w-5 sm:h-6 sm:w-6 text-sky-500 dark:text-sky-400" />
            Command Execution History
          </h1>
          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
            Dedicated cross-project execution stream captured through the <code className="bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 px-1.5 py-0.5 rounded border border-slate-200 dark:border-slate-700">devmemory run -- &lt;cmd&gt;</code> wrapper.
          </p>
        </div>

        <button
          onClick={() => loadData(true)}
          disabled={refreshing}
          aria-label="Refresh command execution telemetry"
          className="inline-flex items-center gap-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-white/80 dark:bg-slate-800/80 px-3.5 py-2 text-xs font-mono text-slate-700 dark:text-slate-300 hover:bg-white dark:hover:bg-slate-800 hover:text-slate-900 dark:hover:text-slate-100 shadow-xs hover:border-slate-300 dark:hover:border-slate-600 transition-all cursor-pointer self-start sm:self-auto"
        >
          <RefreshCw className={`h-3.5 w-3.5 text-sky-500 dark:text-sky-400 ${refreshing ? 'animate-spin' : ''}`} />
          <span>Refresh Runs</span>
        </button>
      </div>

      {/* Stats Overview */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2.5 sm:gap-3.5">
        <StatCard
          title="Total Captured Runs"
          value={stats.total}
          icon={TerminalSquare}
          subtitle="Across all workspaces"
        />
        <StatCard
          title="Passing Runs"
          value={stats.passed}
          icon={CheckCircle2}
          badgeText="Exit Code 0"
          badgeVariant="success"
        />
        <StatCard
          title="Failed Runs"
          value={stats.failed}
          icon={XCircle}
          badgeText="Non-zero Exit"
          badgeVariant="danger"
        />
        <StatCard
          title="Avg Duration"
          value={`${stats.avgDuration}ms`}
          icon={Clock}
          subtitle="Execution benchmark"
        />
      </div>

      {/* Filter and Search Bar */}
      <div className="rounded-2xl border border-white/80 bg-white/75 dark:border-slate-800/80 dark:bg-slate-900/75 backdrop-blur-md p-3.5 sm:p-4 shadow-glass space-y-3">
        <div className="flex flex-col md:flex-row md:items-center gap-3">
          {/* Search Input */}
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-400 dark:text-slate-500" />
            <input
              type="text"
              placeholder="Search by command, project, source file, or error..."
              aria-label="Search command execution history"
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
                aria-label="Filter command runs by project"
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
                aria-label="Filter command runs by exit status"
                onChange={(e) => setSelectedStatus(e.target.value)}
                className="w-full sm:w-auto rounded-xl border border-slate-200 dark:border-slate-700 bg-white/90 dark:bg-slate-800 px-3 py-2 text-xs font-mono text-slate-700 dark:text-slate-200 focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500 shadow-xs cursor-pointer"
              >
                <option value="ALL">All Statuses</option>
                <option value="SUCCESS">Passed (Exit 0)</option>
                <option value="FAILED">Failed (Exit ≠ 0)</option>
              </select>
            </div>

            {/* Sort Order */}
            <div className="flex items-center gap-1.5 flex-1 sm:flex-initial">
              <ArrowUpDown className="h-3.5 w-3.5 text-slate-400 dark:text-slate-500 hidden sm:inline" />
              <select
                value={sortOrder}
                aria-label="Sort command execution order"
                onChange={(e) => setSortOrder(e.target.value)}
                className="w-full sm:w-auto rounded-xl border border-slate-200 dark:border-slate-700 bg-white/90 dark:bg-slate-800 px-3 py-2 text-xs font-mono text-slate-700 dark:text-slate-200 focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500 shadow-xs cursor-pointer"
              >
                <option value="newest">Newest First</option>
                <option value="oldest">Oldest First</option>
                <option value="duration_desc">Longest Duration</option>
                <option value="duration_asc">Shortest Duration</option>
              </select>
            </div>

            {/* Reset Filters */}
            {(searchQuery || selectedProject !== 'ALL' || selectedStatus !== 'ALL') && (
              <button
                onClick={() => {
                  setSearchQuery('');
                  setSelectedProject('ALL');
                  setSelectedStatus('ALL');
                  setSortOrder('newest');
                }}
                className="rounded-xl border border-rose-200 dark:border-rose-900/60 bg-rose-50/70 dark:bg-rose-950/50 px-3 py-2 text-xs font-mono text-rose-700 dark:text-rose-300 hover:bg-rose-100/80 dark:hover:bg-rose-900/60 transition-colors cursor-pointer"
              >
                Clear Filters
              </button>
            )}
          </div>
        </div>

        <div className="text-[11px] font-mono text-slate-500 dark:text-slate-400 flex items-center justify-between pt-1 border-t border-slate-100 dark:border-slate-800">
          <span>Showing {filteredRuns.length} of {runs.length} command execution records</span>
          {isMock && (
            <span className="text-amber-600 dark:text-amber-400 font-semibold">Demo Telemetry Dataset</span>
          )}
        </div>
      </div>

      {/* Command Runs Table */}
      {filteredRuns.length === 0 ? (
        <EmptyState
          title="No Command Runs Found"
          description="No execution records match the current filter criteria. Try clearing search queries or selecting all projects."
          icon={TerminalSquare}
          actionLabel="Reset All Filters"
          onAction={() => {
            setSearchQuery('');
            setSelectedProject('ALL');
            setSelectedStatus('ALL');
          }}
        />
      ) : (
        <div className="overflow-hidden rounded-2xl border border-white/80 bg-white/75 dark:border-slate-800/80 dark:bg-slate-900/75 backdrop-blur-md shadow-glass">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs font-mono">
              <thead className="bg-slate-50/80 dark:bg-slate-800/80 text-slate-500 dark:text-slate-400 border-b border-slate-200/80 dark:border-slate-700/80">
                <tr>
                  <th className="px-5 py-3 font-semibold uppercase tracking-wider text-[10px]">Status</th>
                  <th className="px-5 py-3 font-semibold uppercase tracking-wider text-[10px]">Command</th>
                  <th className="px-5 py-3 font-semibold uppercase tracking-wider text-[10px]">Project</th>
                  <th className="px-5 py-3 font-semibold uppercase tracking-wider text-[10px]">Exit</th>
                  <th className="px-5 py-3 font-semibold uppercase tracking-wider text-[10px]">Duration</th>
                  <th className="px-5 py-3 font-semibold uppercase tracking-wider text-[10px]">Source Location</th>
                  <th className="px-5 py-3 font-semibold uppercase tracking-wider text-[10px]">Timestamp</th>
                  <th className="px-5 py-3 font-semibold uppercase tracking-wider text-[10px] text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800 text-slate-700 dark:text-slate-300">
                {filteredRuns.map((run) => {
                  const isSuccess = run.exitCode === 0;
                  return (
                    <tr
                      key={run.eventId}
                      onClick={() => setSelectedRunModal(run)}
                      className="hover:bg-slate-50/80 dark:hover:bg-slate-800/50 transition-colors cursor-pointer group"
                    >
                      <td className="px-5 py-3.5 whitespace-nowrap">
                        {isSuccess ? (
                          <span className="inline-flex items-center gap-1.5 text-emerald-600 dark:text-emerald-400 font-semibold">
                            <CheckCircle2 className="h-3.5 w-3.5" />
                            <span>Pass</span>
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1.5 text-rose-600 dark:text-rose-400 font-semibold">
                            <XCircle className="h-3.5 w-3.5" />
                            <span>Fail</span>
                          </span>
                        )}
                      </td>

                      <td className="px-5 py-3.5 max-w-xs md:max-w-md">
                        <div className="flex items-center gap-2">
                          <code className="truncate text-slate-800 dark:text-slate-200 bg-slate-100/90 dark:bg-slate-800/90 px-2.5 py-1 rounded-lg border border-slate-200/80 dark:border-slate-700/80 text-xs flex-1 block">
                            {run.command}
                          </code>
                          <button
                            onClick={(e) => handleCopyCommand(run.command, run.eventId, e)}
                            className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 transition-colors p-1"
                            title="Copy command"
                          >
                            {copiedId === run.eventId ? (
                              <Check className="h-3.5 w-3.5 text-emerald-600 dark:text-emerald-400" />
                            ) : (
                              <Copy className="h-3.5 w-3.5" />
                            )}
                          </button>
                        </div>
                        {run.errorSummary && (
                          <p className="mt-1 text-[11px] text-rose-600 dark:text-rose-400 truncate font-mono">
                            {run.errorSummary}
                          </p>
                        )}
                      </td>

                      <td className="px-5 py-3.5 whitespace-nowrap">
                        <Link
                          to={`/projects/${run.projectId}`}
                          onClick={(e) => e.stopPropagation()}
                          className="rounded-lg bg-slate-100 dark:bg-slate-800 px-2 py-0.5 text-slate-700 dark:text-slate-300 hover:bg-brand-50 dark:hover:bg-indigo-950/60 hover:text-brand-600 dark:hover:text-indigo-400 hover:border-brand-200 dark:hover:border-indigo-800/60 border border-slate-200/60 dark:border-slate-700/80 font-medium transition-colors"
                        >
                          {run.projectName}
                        </Link>
                      </td>

                      <td className="px-5 py-3.5 whitespace-nowrap">
                        <Badge variant={isSuccess ? 'success' : 'danger'} size="xs">
                          {run.exitCode}
                        </Badge>
                      </td>

                      <td className="px-5 py-3.5 whitespace-nowrap text-slate-600 dark:text-slate-300">
                        <span className="inline-flex items-center gap-1">
                          <Clock className="h-3 w-3 text-slate-400 dark:text-slate-500" />
                          <span>{run.durationMs}ms</span>
                        </span>
                      </td>

                      <td className="px-5 py-3.5 whitespace-nowrap">
                        {run.sourceFile ? (
                          <span className="inline-flex items-center gap-1 text-[11px] text-slate-600 dark:text-slate-300 bg-slate-100/80 dark:bg-slate-800/80 px-2 py-0.5 rounded border border-slate-200/60 dark:border-slate-700/80">
                            <FileCode2 className="h-3 w-3 text-slate-400 dark:text-slate-500" />
                            <span>
                              {run.sourceFile}:{run.lineNumber || 0}
                            </span>
                          </span>
                        ) : (
                          <span className="text-slate-400 dark:text-slate-500">—</span>
                        )}
                      </td>

                      <td className="px-5 py-3.5 whitespace-nowrap text-slate-500 dark:text-slate-400 text-[11px]">
                        {run.timestamp ? new Date(run.timestamp).toLocaleTimeString() : 'Recent'}
                      </td>

                      <td className="px-5 py-3.5 whitespace-nowrap text-right">
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            setSelectedRunModal(run);
                          }}
                          className="inline-flex items-center gap-1 rounded-lg border border-slate-200 dark:border-slate-700 bg-white/80 dark:bg-slate-800/80 px-2 py-1 text-[11px] text-slate-600 dark:text-slate-300 hover:text-slate-900 dark:hover:text-slate-100 hover:bg-slate-50 dark:hover:bg-slate-700 transition-colors shadow-xs"
                        >
                          <span>Inspect</span>
                          <ExternalLink className="h-3 w-3" />
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Run Record Modal */}
      {selectedRunModal && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="run-modal-title"
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 dark:bg-black/60 p-3 sm:p-4 backdrop-blur-sm"
          onClick={(e) => {
            if (e.target === e.currentTarget) setSelectedRunModal(null);
          }}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="run-modal-title"
            className="w-full max-w-xl max-h-[90vh] overflow-y-auto rounded-2xl border border-white/90 dark:border-slate-800 bg-white/95 dark:bg-slate-900/95 backdrop-blur-md p-5 sm:p-6 shadow-2xl space-y-4 text-slate-800 dark:text-slate-100"
          >
            <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-800 pb-3">
              <div className="flex items-center gap-2">
                <TerminalSquare className="h-5 w-5 text-sky-500 dark:text-sky-400" />
                <h3 id="run-modal-title" className="text-sm font-semibold text-slate-900 dark:text-slate-100 font-mono">
                  Execution Run: {selectedRunModal.eventId}
                </h3>
              </div>
              <button
                onClick={() => setSelectedRunModal(null)}
                aria-label="Close run inspection modal"
                className="text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 text-xs font-mono cursor-pointer transition-colors p-1"
              >
                ✕ Close
              </button>
            </div>

            <div className="space-y-3 text-xs font-mono">
              <div className="grid grid-cols-2 gap-2 bg-slate-50 dark:bg-slate-800/60 p-3.5 rounded-xl border border-slate-200/80 dark:border-slate-700/80">
                <div>
                  <span className="text-slate-400 dark:text-slate-500 text-[10px] uppercase font-semibold">Exit Status</span>
                  <div className="mt-1">
                    <Badge variant={selectedRunModal.exitCode === 0 ? 'success' : 'danger'}>
                      Exit Code {selectedRunModal.exitCode} ({selectedRunModal.exitCode === 0 ? 'Success' : 'Failed'})
                    </Badge>
                  </div>
                </div>
                <div>
                  <span className="text-slate-400 dark:text-slate-500 text-[10px] uppercase font-semibold">Duration</span>
                  <div className="mt-1 text-slate-800 dark:text-slate-200 font-bold">{selectedRunModal.durationMs}ms</div>
                </div>
                <div>
                  <span className="text-slate-400 dark:text-slate-500 text-[10px] uppercase font-semibold">Project</span>
                  <div className="mt-1 text-slate-800 dark:text-slate-200 font-medium">
                    {selectedRunModal.projectName} ({selectedRunModal.projectId})
                  </div>
                </div>
                <div>
                  <span className="text-slate-400 dark:text-slate-500 text-[10px] uppercase font-semibold">Timestamp</span>
                  <div className="mt-1 text-slate-700 dark:text-slate-300">{selectedRunModal.timestamp || 'Recorded during session'}</div>
                </div>
              </div>

              <div>
                <span className="text-slate-400 dark:text-slate-500 text-[10px] uppercase font-semibold">Executed Command</span>
                <div className="mt-1 p-2.5 rounded-lg bg-slate-900 dark:bg-black/80 dark:border dark:border-slate-800 text-slate-100 font-mono text-xs overflow-x-auto flex items-center justify-between">
                  <span>{selectedRunModal.command}</span>
                  <button
                    onClick={(e) => handleCopyCommand(selectedRunModal.command, 'modal', e)}
                    className="text-slate-400 hover:text-white ml-2 shrink-0"
                  >
                    {copiedId === 'modal' ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
                  </button>
                </div>
              </div>

              {selectedRunModal.sourceFile && (
                <div>
                  <span className="text-slate-400 dark:text-slate-500 text-[10px] uppercase font-semibold">Source Location</span>
                  <div className="mt-1 p-2.5 rounded-lg bg-slate-100 dark:bg-slate-800 text-slate-800 dark:text-slate-200 border border-slate-200 dark:border-slate-700 flex items-center gap-2">
                    <FileCode2 className="h-4 w-4 text-brand-500 dark:text-brand-400" />
                    <span>
                      {selectedRunModal.sourceFile}:{selectedRunModal.lineNumber || 0}
                    </span>
                  </div>
                </div>
              )}

              {selectedRunModal.errorSummary && (
                <div>
                  <span className="text-slate-400 dark:text-slate-500 text-[10px] uppercase font-semibold">Error Message / Summary</span>
                  <div className="mt-1 p-2.5 rounded-lg bg-rose-50 dark:bg-rose-950/50 text-rose-800 dark:text-rose-300 border border-rose-200 dark:border-rose-900/60">
                    {selectedRunModal.errorSummary}
                  </div>
                </div>
              )}
            </div>

            <div className="flex items-center justify-between border-t border-slate-100 dark:border-slate-800 pt-3">
              <Link
                to={`/projects/${selectedRunModal.projectId}/runs`}
                onClick={() => setSelectedRunModal(null)}
                className="inline-flex items-center gap-1.5 text-xs font-mono text-indigo-600 dark:text-indigo-400 hover:text-indigo-800 dark:hover:text-indigo-300 font-semibold"
              >
                <span>Open Project Workspace Runs</span>
                <ExternalLink className="h-3 w-3" />
              </Link>
              <button
                onClick={() => setSelectedRunModal(null)}
                className="rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-100 dark:bg-slate-800 px-3.5 py-1.5 text-xs font-mono text-slate-700 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
