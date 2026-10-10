import React, { useState, useEffect } from 'react';
import { useParams, Link, useLocation, useNavigate } from 'react-router-dom';
import {
  FolderGit2,
  Terminal,
  AlertTriangle,
  BrainCircuit,
  TrendingUp,
  ArrowLeft,
  Clock,
  CheckCircle,
  ExternalLink,
  History,
} from 'lucide-react';
import Badge from '../components/common/Badge';
import LoadingSpinner from '../components/common/LoadingSpinner';
import RecentRunsTable from '../components/dashboard/RecentRunsTable';
import ErrorInspector from '../components/errors/ErrorInspector';
import PerformanceLab from '../components/performance/PerformanceLab';
import EventsAuditTable from '../components/events/EventsAuditTable';
import {
  fetchProject,
  fetchProjectRuns,
  fetchProjectIncidents,
  fetchProjectPerformance,
  fetchProjectEvents,
} from '../api/devmemoryApi';

export default function ProjectWorkspace() {
  const { projectId } = useParams();
  const location = useLocation();
  const navigate = useNavigate();

  // Detect subpath tab if present (e.g. /projects/proj_auth_service/errors)
  const currentSubTab = location.pathname.split(`/projects/${projectId}/`)[1]?.split('/')[0];
  const validTabs = ['overview', 'runs', 'errors', 'memory', 'performance', 'events'];
  const initialTab = validTabs.includes(currentSubTab) ? currentSubTab : 'overview';

  const [activeTab, setActiveTab] = useState(initialTab);
  const [project, setProject] = useState(null);
  const [runs, setRuns] = useState([]);
  const [incidents, setIncidents] = useState([]);
  const [performance, setPerformance] = useState(null);
  const [events, setEvents] = useState([]);
  const [isMock, setIsMock] = useState(true);
  const [loading, setLoading] = useState(true);

  // Sync state when URL pathname changes
  useEffect(() => {
    if (currentSubTab && validTabs.includes(currentSubTab)) {
      setActiveTab(currentSubTab);
    } else if (!currentSubTab) {
      setActiveTab('overview');
    }
  }, [currentSubTab]);

  const handleTabChange = (tabId) => {
    setActiveTab(tabId);
    const targetUrl = tabId === 'overview' ? `/projects/${projectId}` : `/projects/${projectId}/${tabId}`;
    navigate(targetUrl);
  };

  useEffect(() => {
    async function load() {
      setLoading(true);
      try {
        const [projRes, runsRes, incRes, perfRes, eventsRes] = await Promise.all([
          fetchProject(projectId),
          fetchProjectRuns(projectId),
          fetchProjectIncidents(projectId),
          fetchProjectPerformance(projectId),
          fetchProjectEvents(projectId),
        ]);
        setProject(projRes.data);
        setRuns(runsRes.data);
        setIncidents(incRes.data);
        setPerformance(perfRes.data);
        setEvents(eventsRes.data);
        setIsMock(projRes.isMock || runsRes.isMock);
      } catch (err) {
        console.error('Failed to load project details:', err);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [projectId]);

  if (loading) {
    return <LoadingSpinner label={`Loading workspace for ${projectId}...`} />;
  }

  const tabs = [
    { id: 'overview', label: 'Overview', icon: FolderGit2 },
    { id: 'runs', label: 'Command Runs', icon: Terminal, count: runs.length },
    { id: 'errors', label: 'Errors & Diagnoses', icon: AlertTriangle, count: incidents.length || project?.failureCount },
    { id: 'memory', label: 'Memory Bank', icon: BrainCircuit },
    { id: 'performance', label: 'Performance Lab', icon: TrendingUp },
    { id: 'events', label: 'Events & Audit', icon: History, count: events.length },
  ];

  return (
    <div className="space-y-6 p-3 sm:p-6 max-w-7xl mx-auto">
      {/* Top Breadcrumb */}
      <div className="flex items-center gap-2 text-xs font-mono text-slate-500 dark:text-slate-400">
        <Link to="/" className="hover:text-slate-900 dark:hover:text-white flex items-center gap-1 transition-colors">
          <ArrowLeft className="h-3 w-3" />
          <span>Global Dashboard</span>
        </Link>
        <span>/</span>
        <span className="text-brand-600 dark:text-brand-400 font-semibold">{project?.name}</span>
      </div>

      {/* Workspace Header */}
      <div className="rounded-2xl border border-white/80 dark:border-slate-800 bg-white/75 dark:bg-slate-900/75 backdrop-blur-md p-4 sm:p-6 shadow-glass">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div className="flex items-start gap-4">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-indigo-50 to-purple-50 dark:from-indigo-950/40 dark:to-purple-950/40 text-indigo-600 dark:text-indigo-400 border border-indigo-100 dark:border-indigo-900/50 shadow-xs shrink-0">
              <FolderGit2 className="h-6 w-6" />
            </div>
            <div>
              <div className="flex items-center gap-3">
                <h1 className="text-xl font-bold text-slate-900 dark:text-white font-mono">{project?.name}</h1>
                <Badge
                  variant={project?.lastRunStatus === 'success' ? 'success' : 'danger'}
                  dot
                  size="xs"
                >
                  {project?.lastRunStatus === 'success' ? 'Passing' : 'Failed'}
                </Badge>
              </div>
              <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{project?.description}</p>
              <div className="mt-2.5 flex items-center gap-2 flex-wrap">
                <span className="rounded-lg bg-slate-100 dark:bg-slate-800 px-2 py-0.5 text-[10px] font-mono text-slate-700 dark:text-slate-300 border border-slate-200/80 dark:border-slate-700 font-medium">
                  {project?.language}
                </span>
                <span className="rounded-lg bg-slate-100 dark:bg-slate-800 px-2 py-0.5 text-[10px] font-mono text-slate-500 dark:text-slate-400 border border-slate-200/80 dark:border-slate-700">
                  {project?.framework}
                </span>
                {project?.repository && (
                  <span className="flex items-center gap-1 text-[10px] font-mono text-slate-500 dark:text-slate-400">
                    <ExternalLink className="h-3 w-3 text-slate-400 dark:text-slate-500" />
                    {project?.repository}
                  </span>
                )}
              </div>
            </div>
          </div>

          <div className="flex sm:flex-col items-center sm:items-end justify-between border-t sm:border-t-0 pt-3 sm:pt-0 border-slate-100 dark:border-slate-800 text-xs font-mono">
            <span className="text-slate-500 dark:text-slate-400">Median Benchmark:</span>
            <span className="text-sm font-bold text-slate-900 dark:text-white mt-0.5">
              {project?.medianDurationMs ?? 0}ms
            </span>
          </div>
        </div>

        {/* Tab Bar */}
        <div
          role="tablist"
          aria-label="Project Workspace Sections"
          className="mt-6 flex border-b border-slate-200 dark:border-slate-800 gap-1 overflow-x-auto"
        >
          {tabs.map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                role="tab"
                aria-selected={isActive}
                aria-controls={`workspace-tabpanel-${tab.id}`}
                onClick={() => handleTabChange(tab.id)}
                className={`flex items-center gap-2 px-3 sm:px-4 py-2.5 text-xs font-medium border-b-2 transition-colors cursor-pointer whitespace-nowrap ${
                  isActive
                    ? 'border-brand-500 text-brand-600 dark:text-brand-400 bg-brand-50/60 dark:bg-brand-950/30 font-semibold rounded-t-lg'
                    : 'border-transparent text-slate-500 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200 hover:border-slate-300 dark:hover:border-slate-700'
                }`}
              >
                <Icon className="h-3.5 w-3.5" />
                <span>{tab.label}</span>
                {tab.count !== undefined && tab.count > 0 && (
                  <span
                    className={`rounded-full px-2 py-0.2 text-[10px] font-mono font-semibold ${
                      tab.id === 'errors'
                        ? 'bg-rose-50 dark:bg-rose-950/40 text-rose-700 dark:text-rose-300 border border-rose-200 dark:border-rose-900/50'
                        : 'bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 border border-slate-200 dark:border-slate-700'
                    }`}
                  >
                    {tab.count}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      </div>

      {/* Tab Contents */}
      <div
        role="tabpanel"
        id={`workspace-tabpanel-${activeTab}`}
        aria-label={tabs.find((t) => t.id === activeTab)?.label}
      >
        {activeTab === 'overview' && (
          <div className="space-y-6">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div className="rounded-2xl border border-white/80 dark:border-slate-800 bg-white/75 dark:bg-slate-900/75 backdrop-blur-md p-5 shadow-glass">
              <span className="text-[10px] uppercase font-mono text-slate-400 dark:text-slate-500 font-semibold">Total Runs</span>
              <p className="mt-1 text-2xl font-bold font-mono text-slate-900 dark:text-white">{project?.totalRuns}</p>
            </div>
            <div className="rounded-2xl border border-white/80 dark:border-slate-800 bg-white/75 dark:bg-slate-900/75 backdrop-blur-md p-5 shadow-glass">
              <span className="text-[10px] uppercase font-mono text-slate-400 dark:text-slate-500 font-semibold">Failures</span>
              <p className="mt-1 text-2xl font-bold font-mono text-rose-600 dark:text-rose-400">{project?.failureCount}</p>
            </div>
            <div className="rounded-2xl border border-white/80 dark:border-slate-800 bg-white/75 dark:bg-slate-900/75 backdrop-blur-md p-5 shadow-glass">
              <span className="text-[10px] uppercase font-mono text-slate-400 dark:text-slate-500 font-semibold">Verified Fixes</span>
              <p className="mt-1 text-2xl font-bold font-mono text-emerald-600 dark:text-emerald-400">{project?.verifiedFixCount}</p>
            </div>
          </div>

          {incidents.length > 0 && (
            <div>
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-semibold text-slate-900 dark:text-white font-mono flex items-center gap-2">
                  <AlertTriangle className="h-4 w-4 text-rose-500" />
                  Active Incident Deep-Dive
                </h3>
                <button
                  onClick={() => handleTabChange('errors')}
                  className="text-xs font-mono text-brand-600 dark:text-brand-400 hover:text-brand-700 dark:hover:text-brand-300 cursor-pointer font-medium"
                >
                  View all incidents →
                </button>
              </div>
              <ErrorInspector
                incidents={incidents.slice(0, 1)}
                currentProjectName={project?.name}
              />
            </div>
          )}

          <div>
            <h3 className="text-sm font-semibold text-slate-900 dark:text-white font-mono mb-3">
              Command Run History
            </h3>
            <RecentRunsTable runs={runs} />
          </div>
        </div>
      )}

      {activeTab === 'runs' && (
        <div>
          <RecentRunsTable runs={runs} />
        </div>
      )}

      {activeTab === 'errors' && (
        <ErrorInspector
          incidents={incidents}
          currentProjectName={project?.name}
        />
      )}

      {activeTab === 'memory' && (
        <div className="rounded-2xl border border-white/80 dark:border-slate-800 bg-white/75 dark:bg-slate-900/75 backdrop-blur-md p-6 shadow-glass space-y-4">
          <div className="flex items-center gap-2 text-indigo-600 dark:text-indigo-400 font-mono text-sm font-semibold">
            <BrainCircuit className="h-5 w-5" />
            <span>3-Tier Troubleshooting Memory for {project?.name}</span>
          </div>
          <p className="text-xs text-slate-600 dark:text-slate-300 leading-relaxed max-w-2xl">
            DevMemory checks 3 tiers of memory when an error occurs:
          </p>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-2">
            <div className="rounded-xl border border-sky-100 dark:border-sky-900/40 bg-sky-50/70 dark:bg-sky-950/30 p-4 space-y-2 shadow-xs">
              <span className="text-[11px] font-mono font-bold text-sky-700 dark:text-sky-300 uppercase">
                Tier 1: General Knowledge
              </span>
              <p className="text-xs text-slate-700 dark:text-slate-300 leading-relaxed">
                Preloaded library of common Python/JS errors, common syntax issues, and runtime exceptions.
              </p>
            </div>
            <div className="rounded-xl border border-emerald-100 dark:border-emerald-900/40 bg-emerald-50/70 dark:bg-emerald-950/30 p-4 space-y-2 shadow-xs">
              <span className="text-[11px] font-mono font-bold text-emerald-700 dark:text-emerald-300 uppercase">
                Tier 2: Project Memory
              </span>
              <p className="text-xs text-slate-700 dark:text-slate-300 leading-relaxed">
                Historical diagnoses and verified fixes specific to <strong>{project?.name}</strong>.
              </p>
            </div>
            <div className="rounded-xl border border-indigo-100 dark:border-indigo-900/40 bg-indigo-50/70 dark:bg-indigo-950/30 p-4 space-y-2 shadow-xs">
              <span className="text-[11px] font-mono font-bold text-indigo-700 dark:text-indigo-300 uppercase">
                Tier 3: Cross-Project Memory
              </span>
              <p className="text-xs text-slate-700 dark:text-slate-300 leading-relaxed">
                Sanitized precedents from other services, respecting privacy and matching patterns.
              </p>
            </div>
          </div>
        </div>
      )}

      {activeTab === 'performance' && (
        <PerformanceLab
          performanceData={performance}
          isMock={isMock}
        />
      )}

      {activeTab === 'events' && (
        <EventsAuditTable
          events={events}
          scopedProjectId={projectId}
          isMock={isMock}
        />
      )}
      </div>
    </div>
  );
}

