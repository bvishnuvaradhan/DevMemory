import React, { useState, useEffect, useMemo } from 'react';
import { Link } from 'react-router-dom';
import {
  TrendingUp,
  Filter,
  RefreshCw,
  FolderGit2,
  AlertTriangle,
  Clock,
  Gauge,
  CheckCircle2,
  ExternalLink,
  ShieldCheck,
  ChevronRight,
  Database,
  ArrowRight,
} from 'lucide-react';
import {
  ResponsiveContainer,
  ComposedChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
} from 'recharts';
import StatCard from '../components/common/StatCard';
import Badge from '../components/common/Badge';
import EmptyState from '../components/common/EmptyState';
import LoadingSpinner from '../components/common/LoadingSpinner';
import PerformanceLab from '../components/performance/PerformanceLab';
import { fetchAllPerformance, fetchProjects } from '../api/devmemoryApi';

export default function PerformanceLabPage() {
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [perfData, setPerfData] = useState(null);
  const [projects, setProjects] = useState([]);
  const [isMock, setIsMock] = useState(true);

  // Selected Scope: 'ALL' or projectId
  const [selectedProjectId, setSelectedProjectId] = useState('ALL');

  const loadData = async (isManual = false) => {
    if (isManual) setRefreshing(true);
    try {
      const [perfRes, projsRes] = await Promise.all([
        fetchAllPerformance(),
        fetchProjects(),
      ]);
      setPerfData(perfRes.data);
      setProjects(projsRes.data);
      setIsMock(perfRes.isMock);
    } catch (err) {
      console.error('Failed to load performance telemetry:', err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const byProject = perfData?.byProject || {};
  const globalTrend = perfData?.trend || [];

  // Platform-wide calculations
  const platformStats = useMemo(() => {
    const projectKeys = Object.keys(byProject);
    const trackedCount = projectKeys.length;
    let validatedBaselines = 0;
    let totalRegressionAlerts = 0;
    const medians = [];

    projectKeys.forEach((key) => {
      const p = byProject[key];
      if (p.baselineMs && Number(p.baselineMs) > 0) {
        validatedBaselines += 1;
      }
      if (Array.isArray(p.runs)) {
        p.runs.forEach((r) => {
          if (r.isRegression) totalRegressionAlerts += 1;
        });
      }
      if (p.medianMs && Number(p.medianMs) > 0) {
        medians.push(Number(p.medianMs));
      }
    });

    const medianAvg = medians.length
      ? Math.round(medians.reduce((a, b) => a + b, 0) / medians.length)
      : 0;

    return {
      trackedCount,
      validatedBaselines,
      totalRegressionAlerts,
      medianAvg,
    };
  }, [byProject]);

  // All active regressions across all projects (only where valid baseline exists)
  const activeRegressions = useMemo(() => {
    const list = [];
    Object.keys(byProject).forEach((key) => {
      const p = byProject[key];
      const hasBaseline = p.baselineMs && Number(p.baselineMs) > 0;
      if (hasBaseline && Array.isArray(p.runs)) {
        p.runs.forEach((r) => {
          if (r.isRegression) {
            list.push({
              ...r,
              projectId: p.projectId,
              projectName: p.projectName,
              baselineMs: p.baselineMs,
            });
          }
        });
      }
    });
    return list;
  }, [byProject]);

  if (loading) {
    return <LoadingSpinner label="Loading performance benchmarks & regressions..." />;
  }

  const selectedProjectPerf = selectedProjectId !== 'ALL' ? byProject[selectedProjectId] : null;

  return (
    <div className="space-y-6 p-3 sm:p-6 max-w-7xl mx-auto">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-slate-900 dark:text-slate-100 font-mono flex items-center gap-2">
            <TrendingUp className="h-5 w-5 sm:h-6 sm:w-6 text-indigo-500 dark:text-indigo-400" />
            Performance Lab & Regression Registry
          </h1>
          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
            Cross-project duration telemetry, valid baseline comparisons, and automated execution regressions.
          </p>
        </div>

        <button
          onClick={() => loadData(true)}
          disabled={refreshing}
          aria-label="Refresh performance telemetry"
          className="inline-flex items-center gap-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-white/80 dark:bg-slate-800/80 px-3.5 py-2 text-xs font-mono text-slate-700 dark:text-slate-300 hover:bg-white dark:hover:bg-slate-800 hover:text-slate-900 dark:hover:text-slate-100 shadow-xs hover:border-slate-300 dark:hover:border-slate-600 transition-all cursor-pointer self-start sm:self-auto"
        >
          <RefreshCw className={`h-3.5 w-3.5 text-indigo-500 dark:text-indigo-400 ${refreshing ? 'animate-spin' : ''}`} />
          <span>Refresh Telemetry</span>
        </button>
      </div>

      {/* Stats Overview */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2.5 sm:gap-3.5">
        <StatCard
          title="Tracked Workspaces"
          value={platformStats.trackedCount}
          icon={FolderGit2}
          subtitle="Registered services"
        />
        <StatCard
          title="Validated Baselines"
          value={platformStats.validatedBaselines}
          icon={Gauge}
          badgeText="Verified Thresholds"
          badgeVariant="brand"
        />
        <StatCard
          title="Regression Alerts"
          value={platformStats.totalRegressionAlerts}
          icon={AlertTriangle}
          badgeText={platformStats.totalRegressionAlerts > 0 ? 'Active Regressions' : 'Normal'}
          badgeVariant={platformStats.totalRegressionAlerts > 0 ? 'danger' : 'success'}
        />
        <StatCard
          title="Platform Median"
          value={`${platformStats.medianAvg}ms`}
          icon={Clock}
          subtitle="Benchmark duration"
        />
      </div>

      {/* Scope Selector Bar */}
      <div className="rounded-2xl border border-white/80 bg-white/75 dark:border-slate-800/80 dark:bg-slate-900/75 backdrop-blur-md p-3.5 sm:p-4 shadow-glass flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div className="flex items-center gap-2 flex-wrap">
          <FolderGit2 className="h-4 w-4 text-slate-400 dark:text-slate-500" />
          <label htmlFor="workspace-scope-select" className="text-xs font-mono text-slate-600 dark:text-slate-300 font-semibold">
            Workspace Scope:
          </label>
          <select
            id="workspace-scope-select"
            aria-label="Filter performance benchmarks by workspace scope"
            value={selectedProjectId}
            onChange={(e) => setSelectedProjectId(e.target.value)}
            className="rounded-xl border border-slate-200 dark:border-slate-700 bg-white/90 dark:bg-slate-800 px-3 py-1.5 text-xs font-mono text-slate-700 dark:text-slate-200 focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500 shadow-xs cursor-pointer font-medium"
          >
            <option value="ALL">⚡ All Projects (Platform Overview)</option>
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name} {byProject[p.id]?.baselineMs ? `(Baseline: ${byProject[p.id].baselineMs}ms)` : '(No baseline)'}
              </option>
            ))}
          </select>
        </div>

        <div className="text-[11px] font-mono text-slate-500 dark:text-slate-400 flex items-center gap-2">
          {selectedProjectId === 'ALL' ? (
            <span>Viewing aggregated cross-project benchmarks</span>
          ) : (
            <Link
              to={`/projects/${selectedProjectId}/performance`}
              className="inline-flex items-center gap-1 text-indigo-600 dark:text-indigo-400 hover:text-indigo-800 dark:hover:text-indigo-300 font-semibold transition-colors"
            >
              <span>Open in Project Workspace</span>
              <ExternalLink className="h-3 w-3" />
            </Link>
          )}
        </div>
      </div>

      {/* Conditional View: All Projects vs Individual Workspace */}
      {selectedProjectId === 'ALL' ? (
        <div className="space-y-6">
          {/* Active Regression Alerts Section */}
          {activeRegressions.length > 0 && (
            <div className="rounded-2xl border border-rose-200/90 dark:border-rose-900/60 bg-rose-50/50 dark:bg-rose-950/30 backdrop-blur-md p-5 shadow-glass space-y-3">
              <div className="flex items-center justify-between border-b border-rose-200/60 dark:border-rose-900/60 pb-2">
                <div className="flex items-center gap-2 text-rose-800 dark:text-rose-300">
                  <AlertTriangle className="h-4 w-4 text-rose-600 dark:text-rose-400" />
                  <h3 className="text-xs font-bold font-mono uppercase tracking-wider">
                    Active Performance Regression Alerts ({activeRegressions.length})
                  </h3>
                </div>
                <span className="text-[11px] font-mono text-rose-700 dark:text-rose-400 font-medium">
                  Verified against compatible baselines
                </span>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {activeRegressions.map((reg, idx) => (
                  <div
                    key={idx}
                    className="p-3.5 rounded-xl border border-rose-200 dark:border-rose-900/60 bg-white/90 dark:bg-slate-800/90 shadow-xs space-y-2 text-xs font-mono"
                  >
                    <div className="flex items-center justify-between">
                      <Link
                        to={`/projects/${reg.projectId}/performance`}
                        className="font-bold text-slate-900 dark:text-slate-100 hover:text-indigo-600 dark:hover:text-indigo-400 flex items-center gap-1"
                      >
                        <span>{reg.projectName}</span>
                        <ChevronRight className="h-3 w-3" />
                      </Link>
                      <span className="rounded-full bg-rose-100 dark:bg-rose-950/60 px-2 py-0.5 text-[10px] text-rose-700 dark:text-rose-300 font-bold border border-rose-200 dark:border-rose-800/60">
                        +{reg.regressionDeltaMs || (reg.durationMs - reg.baselineMs)}ms SLOWDOWN
                      </span>
                    </div>

                    <div className="text-slate-700 dark:text-slate-300 truncate bg-slate-100/90 dark:bg-slate-900/80 p-2 rounded-lg border border-slate-200 dark:border-slate-700">
                      <code>{reg.command}</code>
                    </div>

                    <div className="flex items-center justify-between text-[11px] text-slate-500 dark:text-slate-400">
                      <span>Recorded: {reg.timestamp}</span>
                      <span>
                        Duration: <strong className="text-rose-600 dark:text-rose-400">{reg.durationMs}ms</strong> (Baseline: {reg.baselineMs}ms)
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Cross-Project Summary Comparison Table */}
          <div className="overflow-hidden rounded-2xl border border-white/80 bg-white/75 dark:border-slate-800/80 dark:bg-slate-900/75 backdrop-blur-md shadow-glass">
            <div className="border-b border-slate-100 dark:border-slate-800 px-5 py-4 flex items-center justify-between">
              <div>
                <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100 font-mono">
                  Project Workspace Baseline Comparisons
                </h3>
                <p className="text-xs text-slate-500 dark:text-slate-400">
                  Execution thresholds validated with tolerance allowances.
                </p>
              </div>
              <span className="text-xs font-mono text-slate-400 dark:text-slate-500">Strict baseline comparisons only</span>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs font-mono">
                <thead className="bg-slate-50/80 dark:bg-slate-800/80 text-slate-500 dark:text-slate-400 border-b border-slate-200/80 dark:border-slate-700/80">
                  <tr>
                    <th className="px-5 py-3 font-semibold uppercase tracking-wider text-[10px]">Project</th>
                    <th className="px-5 py-3 font-semibold uppercase tracking-wider text-[10px]">Baseline</th>
                    <th className="px-5 py-3 font-semibold uppercase tracking-wider text-[10px]">Median</th>
                    <th className="px-5 py-3 font-semibold uppercase tracking-wider text-[10px]">Tolerance</th>
                    <th className="px-5 py-3 font-semibold uppercase tracking-wider text-[10px]">Benchmarks</th>
                    <th className="px-5 py-3 font-semibold uppercase tracking-wider text-[10px]">Status</th>
                    <th className="px-5 py-3 font-semibold uppercase tracking-wider text-[10px] text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 dark:divide-slate-800 text-slate-700 dark:text-slate-300">
                  {projects.map((p) => {
                    const perf = byProject[p.id];
                    const hasBaseline = perf?.baselineMs && Number(perf.baselineMs) > 0;
                    const runs = perf?.runs || [];
                    const hasRegressions = runs.some((r) => r.isRegression);

                    return (
                      <tr key={p.id} className="hover:bg-slate-50/60 dark:hover:bg-slate-800/50 transition-colors">
                        <td className="px-5 py-3.5 whitespace-nowrap">
                          <Link
                            to={`/projects/${p.id}/performance`}
                            className="font-bold text-slate-900 dark:text-slate-100 hover:text-brand-600 dark:hover:text-indigo-400 transition-colors"
                          >
                            {p.name}
                          </Link>
                          <div className="text-[10px] text-slate-400 dark:text-slate-500 font-normal">{p.language}</div>
                        </td>

                        <td className="px-5 py-3.5 whitespace-nowrap">
                          {hasBaseline ? (
                            <span className="font-bold text-slate-800 dark:text-slate-200">{perf.baselineMs}ms</span>
                          ) : (
                            <span className="text-slate-400 dark:text-slate-500 italic">No baseline</span>
                          )}
                        </td>

                        <td className="px-5 py-3.5 whitespace-nowrap text-slate-600 dark:text-slate-300">
                          {perf?.medianMs ? `${perf.medianMs}ms` : '—'}
                        </td>

                        <td className="px-5 py-3.5 whitespace-nowrap text-slate-500 dark:text-slate-400">
                          ±{perf?.tolerancePercent || 20}%
                        </td>

                        <td className="px-5 py-3.5 whitespace-nowrap text-slate-600 dark:text-slate-300">
                          {runs.length} runs
                        </td>

                        <td className="px-5 py-3.5 whitespace-nowrap">
                          {!hasBaseline ? (
                            <span className="inline-flex items-center gap-1 rounded-full bg-slate-100 dark:bg-slate-800 px-2 py-0.5 text-[10px] text-slate-600 dark:text-slate-300 font-semibold border border-slate-200 dark:border-slate-700">
                              <span>Uncalibrated</span>
                            </span>
                          ) : hasRegressions ? (
                            <span className="inline-flex items-center gap-1 rounded-full bg-rose-50 dark:bg-rose-950/60 px-2.5 py-0.5 text-[10px] text-rose-700 dark:text-rose-300 font-bold border border-rose-300 dark:border-rose-800/60">
                              <AlertTriangle className="h-3 w-3 text-rose-500 dark:text-rose-400" />
                              <span>Regression Alert</span>
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 dark:bg-emerald-950/60 px-2.5 py-0.5 text-[10px] text-emerald-700 dark:text-emerald-300 font-semibold border border-emerald-300 dark:border-emerald-800/60">
                              <CheckCircle2 className="h-3 w-3 text-emerald-500 dark:text-emerald-400" />
                              <span>Within Threshold</span>
                            </span>
                          )}
                        </td>

                        <td className="px-5 py-3.5 whitespace-nowrap text-right">
                          <button
                            onClick={() => setSelectedProjectId(p.id)}
                            className="inline-flex items-center gap-1 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-2.5 py-1 text-xs text-slate-700 dark:text-slate-200 hover:text-indigo-600 dark:hover:text-indigo-400 hover:border-indigo-200 dark:hover:border-indigo-800/60 transition-colors shadow-xs"
                          >
                            <span>Inspect Project</span>
                            <ArrowRight className="h-3 w-3" />
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>

          {/* Global Platform Pulse Chart */}
          {globalTrend.length > 0 && (
            <div className="rounded-2xl border border-white/80 bg-white/75 dark:border-slate-800/80 dark:bg-slate-900/75 backdrop-blur-md p-5 shadow-glass space-y-4">
              <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-800 pb-3">
                <div className="flex items-center gap-2">
                  <TrendingUp className="h-4 w-4 text-indigo-500 dark:text-indigo-400" />
                  <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100 font-mono">
                    Global Platform Benchmark Trend (Historical Runs)
                  </h3>
                </div>
                <span className="text-xs font-mono text-slate-400 dark:text-slate-500">Duration vs Baseline (ms)</span>
              </div>

              <div className="h-64 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <ComposedChart data={globalTrend} margin={{ top: 10, right: 20, left: -10, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" className="dark:opacity-20" />
                    <XAxis dataKey="timestamp" stroke="#94A3B8" tick={{ fontSize: 11, fill: '#64748B', fontFamily: 'monospace' }} />
                    <YAxis stroke="#94A3B8" tick={{ fontSize: 11, fill: '#64748B', fontFamily: 'monospace' }} unit="ms" />
                    <Tooltip
                      content={({ active, payload }) => {
                        if (active && payload && payload.length) {
                          const d = payload[0].payload;
                          const isReg = d.durationMs > d.baselineMs * 1.2;
                          return (
                            <div className="rounded-xl bg-white/95 dark:bg-slate-900/95 backdrop-blur-md border border-slate-200 dark:border-slate-700 p-2.5 shadow-lg text-xs font-mono text-slate-800 dark:text-slate-100">
                              <span className="text-slate-400 dark:text-slate-500">Time: {d.timestamp}</span>
                              <div className="text-slate-900 dark:text-slate-100 font-bold">Duration: {d.durationMs}ms</div>
                              <div className="text-emerald-600 dark:text-emerald-400 font-semibold">Baseline: {d.baselineMs}ms</div>
                              {isReg && <div className="text-rose-600 dark:text-rose-400 font-bold mt-1">⚠️ Regression</div>}
                            </div>
                          );
                        }
                        return null;
                      }}
                    />
                    <ReferenceLine y={130} stroke="#10B981" strokeDasharray="4 4" label={{ value: 'Target Baseline (130ms)', fill: '#059669', fontSize: 10, fontFamily: 'monospace' }} />
                    <Line
                      type="monotone"
                      dataKey="durationMs"
                      stroke="#6478F5"
                      strokeWidth={2.5}
                      dot={({ cx, cy, payload }) => {
                        const isReg = payload.durationMs > payload.baselineMs * 1.2;
                        return (
                          <circle
                            key={`${cx}-${cy}`}
                            cx={cx}
                            cy={cy}
                            r={isReg ? 5 : 4}
                            fill={isReg ? '#EF4444' : '#6478F5'}
                            stroke="#FFFFFF"
                            strokeWidth={2}
                          />
                        );
                      }}
                    />
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}
        </div>
      ) : (
        /* Single Project Scope View (Reuses PerformanceLab component safely!) */
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <button
              onClick={() => setSelectedProjectId('ALL')}
              className="text-xs font-mono text-indigo-600 dark:text-indigo-400 hover:text-indigo-800 dark:hover:text-indigo-300 font-semibold cursor-pointer"
            >
              ← Back to All Projects
            </button>
            <span className="text-xs font-mono text-slate-500 dark:text-slate-400">
              Workspace: <strong className="text-slate-800 dark:text-slate-200">{selectedProjectPerf?.projectName || selectedProjectId}</strong>
            </span>
          </div>

          <PerformanceLab
            performanceData={selectedProjectPerf}
            isMock={isMock}
          />
        </div>
      )}
    </div>
  );
}
