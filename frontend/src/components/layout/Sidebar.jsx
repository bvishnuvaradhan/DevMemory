import React from 'react';
import { NavLink, useParams } from 'react-router-dom';
import {
  LayoutDashboard,
  FolderGit2,
  TerminalSquare,
  AlertTriangle,
  CheckCircle,
  TrendingUp,
  BrainCircuit,
  Database,
  History,
} from 'lucide-react';

export default function Sidebar({ projects = [] }) {
  const { projectId } = useParams();

  const navItemClass = ({ isActive }) =>
    `flex items-center gap-3 px-3 py-2 text-xs font-medium rounded-xl transition-all duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 ${
      isActive
        ? 'bg-indigo-50/90 text-indigo-600 font-semibold border border-indigo-200/80 shadow-xs'
        : 'text-slate-600 hover:text-slate-900 hover:bg-white/80'
    }`;

  return (
    <aside
      aria-label="Sidebar Navigation"
      className="w-64 shrink-0 h-full border-r border-slate-200/80 bg-white/60 backdrop-blur-md p-4 flex flex-col justify-between hidden md:flex shadow-xs overflow-y-auto z-20"
    >
      <div className="space-y-6">
        {/* Main Navigation */}
        <div>
          <span className="px-3 text-[10px] font-semibold uppercase tracking-wider text-slate-400">
            Platform
          </span>
          <nav aria-label="Platform features" className="mt-2 space-y-1">
            <NavLink to="/" end className={navItemClass}>
              <LayoutDashboard className="h-4 w-4 text-indigo-500" />
              <span>Global Dashboard</span>
            </NavLink>
            <NavLink to="/runs" className={navItemClass}>
              <TerminalSquare className="h-4 w-4 text-sky-500" />
              <span>Command Runs</span>
            </NavLink>
            <NavLink to="/incidents" className={navItemClass}>
              <AlertTriangle className="h-4 w-4 text-rose-500" />
              <span>Errors & Diagnoses</span>
            </NavLink>
            <NavLink to="/fixes" className={navItemClass}>
              <CheckCircle className="h-4 w-4 text-emerald-500" />
              <span>Verified Fixes</span>
            </NavLink>
            <NavLink to="/performance" className={navItemClass}>
              <TrendingUp className="h-4 w-4 text-indigo-500" />
              <span>Performance Lab</span>
            </NavLink>
            <NavLink to="/events" className={navItemClass}>
              <History className="h-4 w-4 text-purple-500" />
              <span>Events & Audit</span>
            </NavLink>
          </nav>
        </div>

        {/* Project Workspaces list */}
        <div>
          <div className="flex items-center justify-between px-3">
            <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">
              Workspaces ({projects.length})
            </span>
          </div>
          <nav aria-label="Project workspaces" className="mt-2 space-y-1">
            {projects.map((p) => (
              <NavLink
                key={p.id}
                to={`/projects/${p.id}`}
                className={({ isActive }) =>
                  `flex items-center justify-between px-3 py-1.5 text-xs rounded-xl transition-all duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 ${
                    isActive
                      ? 'bg-white text-slate-900 font-semibold border border-slate-200/90 shadow-xs'
                      : 'text-slate-600 hover:text-slate-900 hover:bg-white/60'
                  }`
                }
              >
                <div className="flex items-center gap-2 truncate">
                  <FolderGit2 className="h-3.5 w-3.5 text-brand-500 shrink-0" />
                  <span className="truncate">{p.name}</span>
                </div>
                {p.failureCount > 0 && (
                  <span className="rounded-full bg-rose-50 px-2 py-0.5 text-[10px] font-mono text-rose-600 font-semibold border border-rose-200">
                    {p.failureCount}
                  </span>
                )}
              </NavLink>
            ))}
          </nav>
        </div>

        {/* Memory status box */}
        <div className="rounded-2xl border border-indigo-100 bg-gradient-to-br from-indigo-50/70 via-purple-50/40 to-white/60 p-3.5 shadow-xs">
          <div className="flex items-center gap-2 text-indigo-600 text-xs font-semibold">
            <BrainCircuit className="h-4 w-4" />
            <span>3-Tier Dev Memory</span>
          </div>
          <p className="mt-1.5 text-[11px] text-slate-600 leading-relaxed">
            Troubleshooting patterns learn across projects and verify real outcomes.
          </p>
          <div className="mt-2.5 flex items-center gap-1.5 text-[10px] text-indigo-600 font-mono font-medium">
            <Database className="h-3 w-3" />
            <span>MongoDB Persistent</span>
          </div>
        </div>
      </div>

      {/* CLI Quick Usage Box */}
      <div className="mt-6 shrink-0 rounded-xl border border-slate-200 bg-white/80 p-3 text-xs shadow-xs">
        <span className="text-[10px] font-mono text-slate-400 uppercase font-semibold">CLI Command</span>
        <code className="mt-1.5 block font-mono text-[11px] text-slate-800 bg-slate-100/90 p-2 rounded-lg border border-slate-200/80 overflow-x-auto">
          devmemory run -- &lt;cmd&gt;
        </code>
      </div>
    </aside>
  );
}
