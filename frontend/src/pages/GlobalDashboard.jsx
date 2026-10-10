import React, { useState, useEffect } from 'react';
import { useLocation, Link } from 'react-router-dom';
import {
  ResponsiveContainer,
  ComposedChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
} from 'recharts';
import {
  Terminal,
  AlertTriangle,
  CheckCircle,
  Clock,
  FolderGit2,
  RefreshCw,
  Repeat,
  ShieldCheck,
  TrendingUp,
} from 'lucide-react';
import StatCard from '../components/common/StatCard';
import ProjectsGrid from '../components/dashboard/ProjectsGrid';
import RecentRunsTable from '../components/dashboard/RecentRunsTable';
import RecurringErrorsWidget from '../components/dashboard/RecurringErrorsWidget';
import FixOutcomesWidget from '../components/dashboard/FixOutcomesWidget';
import LoadingSpinner from '../components/common/LoadingSpinner';
import { fetchGlobalOverview } from '../api/devmemoryApi';

export default function GlobalDashboard({ onDataLoaded }) {
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [overview, setOverview] = useState(null);
  const [isMock, setIsMock] = useState(true);
  const location = useLocation();

  const loadData = async (isManualRefresh = false) => {
    if (isManualRefresh) setRefreshing(true);
    try {
      const res = await fetchGlobalOverview();
      setOverview(res.data);
      setIsMock(res.isMock);
      if (onDataLoaded) onDataLoaded(res.data.projects, res.isMock);
    } catch (err) {
      console.error('Failed to load global overview:', err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  if (loading) {
    return <LoadingSpinner label="Connecting to DevMemory telemetry..." />;
  }

  const { stats, projects, recentRuns, recurringErrors, verifiedFixes } = overview || {};

  return (
    <div className="space-y-6 sm:space-y-8 p-3 sm:p-6 max-w-7xl mx-auto">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 font-mono flex items-center gap-2">
            Global Platform Overview
          </h1>
          <p className="mt-1 text-xs text-slate-500">
            Real-time command telemetry, cross-project memory retrieval, and verified fix rates.
          </p>
        </div>

        <button
          onClick={() => loadData(true)}
          disabled={refreshing}
          aria-label="Refresh platform telemetry"
          className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white/80 px-3.5 py-2 text-xs font-mono text-slate-700 hover:bg-white hover:text-slate-900 shadow-xs hover:border-slate-300 transition-all cursor-pointer self-start sm:self-auto"
        >
          <RefreshCw className={`h-3.5 w-3.5 text-indigo-500 ${refreshing ? 'animate-spin' : ''}`} />
          <span>Refresh Telemetry</span>
        </button>
      </div>

      {/* Global Stat Cards Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2.5 sm:gap-3.5">
        <StatCard
          title="Projects"
          value={stats?.totalProjects ?? 0}
          icon={FolderGit2}
          subtitle="Registered services"
        />
        <StatCard
          title="Command Runs"
          value={stats?.totalRuns ?? 0}
          icon={Terminal}
          subtitle="Captured via CLI"
        />
        <StatCard
          title="Total Failures"
          value={stats?.totalFailures ?? 0}
          icon={AlertTriangle}
          trend={stats?.failureRate}
          trendPositive={false}
          subtitle="Failure rate"
        />
        <StatCard
          title="Fix Success Rate"
          value={stats?.verifiedFixRate ?? '0%'}
          icon={CheckCircle}
          trendPositive={true}
          badgeText="Verified Only"
          badgeVariant="success"
        />
        <StatCard
          title="Recurring Errors"
          value={stats?.recurringErrorsCount ?? 0}
          icon={Repeat}
          subtitle="Active clusters"
        />
        <StatCard
          title="Median Duration"
          value={`${stats?.medianExecutionTimeMs ?? 0}ms`}
          icon={Clock}
          subtitle="Execution benchmark"
        />
      </div>

      {/* Section 1: Registered Projects Grid */}
      <div>
        <div className="mb-4 flex items-center justify-between">
          <div>
            <h2 className="text-base font-semibold text-slate-900">Registered Project Workspaces</h2>
            <p className="text-xs text-slate-500">Select a project to explore its runs, diagnoses, and memory bank.</p>
          </div>
        </div>
        <ProjectsGrid projects={projects} />
      </div>

      {/* Section 2: Recent Command Runs Table */}
      <div>
        <RecentRunsTable runs={recentRuns} />
      </div>

      {/* Section 3: Two-Column Recurring Errors & Verified Fix Bank */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <RecurringErrorsWidget recurringErrors={recurringErrors} />
        <FixOutcomesWidget verifiedFixes={verifiedFixes} />
      </div>

      {/* Section 4: Global Performance Pulse */}
      {overview?.performanceTrend && overview.performanceTrend.length > 0 && (
        <div className="rounded-2xl border border-white/80 bg-white/75 backdrop-blur-md p-5 shadow-glass space-y-4">
          <div className="flex items-center justify-between border-b border-slate-100 pb-3">
            <div className="flex items-center gap-2">
              <TrendingUp className="h-4 w-4 text-brand-500" />
              <h3 className="text-sm font-semibold text-slate-900 font-mono">
                Cross-Project Execution Time Pulse
              </h3>
            </div>
            <Link
              to="/performance"
              className="text-xs font-mono text-indigo-600 hover:text-indigo-800 font-semibold transition-colors flex items-center gap-1"
            >
              <span>Open Performance Lab →</span>
            </Link>
          </div>
          <div className="h-56 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={overview.performanceTrend} margin={{ top: 10, right: 20, left: -10, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" />
                <XAxis dataKey="timestamp" stroke="#94A3B8" tick={{ fontSize: 11, fill: '#64748B', fontFamily: 'monospace' }} />
                <YAxis stroke="#94A3B8" tick={{ fontSize: 11, fill: '#64748B', fontFamily: 'monospace' }} unit="ms" />
                <Tooltip
                  content={({ active, payload }) => {
                    if (active && payload && payload.length) {
                      const d = payload[0].payload;
                      return (
                        <div className="rounded-xl bg-white/95 backdrop-blur-md border border-slate-200 p-2.5 shadow-lg text-xs font-mono">
                          <span className="text-slate-500">Time: {d.timestamp}</span>
                          <div className="text-slate-900 font-bold">Duration: {d.durationMs}ms</div>
                          <div className="text-emerald-600 font-semibold">Baseline: {d.baselineMs}ms</div>
                        </div>
                      );
                    }
                    return null;
                  }}
                />
                <Line
                  type="monotone"
                  dataKey="durationMs"
                  stroke="#6478F5"
                  strokeWidth={2.5}
                  dot={{ r: 4, fill: '#6478F5', stroke: '#FFFFFF', strokeWidth: 2 }}
                  activeDot={{ r: 6, fill: '#4F46E5' }}
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
    </div>
  );
}
