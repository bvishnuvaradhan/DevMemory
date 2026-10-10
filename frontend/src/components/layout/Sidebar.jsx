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
    `flex items-center gap-3 px-3 py-2 text-xs font-medium rounded-lg transition-colors ${
      isActive
        ? 'bg-brand-600/15 text-brand-300 border border-brand-500/30'
        : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900/60'
    }`;

  return (
    <aside className="w-64 shrink-0 border-r border-slate-800/80 bg-slate-950/60 p-4 flex flex-col justify-between hidden md:flex">
      <div className="space-y-6">
        {/* Main Navigation */}
        <div>
          <span className="px-3 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
            Platform
          </span>
          <nav className="mt-2 space-y-1">
            <NavLink to="/" end className={navItemClass}>
              <LayoutDashboard className="h-4 w-4" />
              <span>Global Dashboard</span>
            </NavLink>
            <NavLink to="/runs" className={navItemClass}>
              <TerminalSquare className="h-4 w-4" />
              <span>Command Runs</span>
            </NavLink>
            <NavLink to="/incidents" className={navItemClass}>
              <AlertTriangle className="h-4 w-4" />
              <span>Errors & Diagnoses</span>
            </NavLink>
            <NavLink to="/fixes" className={navItemClass}>
              <CheckCircle className="h-4 w-4" />
              <span>Verified Fixes</span>
            </NavLink>
            <NavLink to="/performance" className={navItemClass}>
              <TrendingUp className="h-4 w-4" />
              <span>Performance Lab</span>
            </NavLink>
            <NavLink to="/events" className={navItemClass}>
              <History className="h-4 w-4" />
              <span>Events & Audit</span>
            </NavLink>
          </nav>
        </div>

        {/* Project Workspaces list */}
        <div>
          <div className="flex items-center justify-between px-3">
            <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">
              Workspaces ({projects.length})
            </span>
          </div>
          <nav className="mt-2 space-y-1">
            {projects.map((p) => (
              <NavLink
                key={p.id}
                to={`/projects/${p.id}`}
                className={({ isActive }) =>
                  `flex items-center justify-between px-3 py-1.5 text-xs rounded-lg transition-colors ${
                    isActive
                      ? 'bg-slate-800/90 text-white font-medium border border-slate-700'
                      : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900/40'
                  }`
                }
              >
                <div className="flex items-center gap-2 truncate">
                  <FolderGit2 className="h-3.5 w-3.5 text-brand-400 shrink-0" />
                  <span className="truncate">{p.name}</span>
                </div>
                {p.failureCount > 0 && (
                  <span className="rounded bg-rose-500/20 px-1.5 py-0.2 text-[10px] font-mono text-rose-300">
                    {p.failureCount}
                  </span>
                )}
              </NavLink>
            ))}
          </nav>
        </div>

        {/* Memory status box */}
        <div className="rounded-xl border border-indigo-900/40 bg-indigo-950/20 p-3.5">
          <div className="flex items-center gap-2 text-brand-400 text-xs font-semibold">
            <BrainCircuit className="h-4 w-4" />
            <span>3-Tier Dev Memory</span>
          </div>
          <p className="mt-1.5 text-[11px] text-slate-400 leading-relaxed">
            Troubleshooting patterns learn across projects and verify real outcomes.
          </p>
          <div className="mt-2.5 flex items-center gap-1.5 text-[10px] text-brand-300 font-mono">
            <Database className="h-3 w-3" />
            <span>MongoDB Persistent</span>
          </div>
        </div>
      </div>

      {/* CLI Quick Usage Box */}
      <div className="rounded-lg border border-slate-800 bg-slate-900/80 p-3 text-xs">
        <span className="text-[10px] font-mono text-slate-500 uppercase">CLI Command</span>
        <code className="mt-1 block font-mono text-[11px] text-slate-200 bg-black/40 p-2 rounded overflow-x-auto">
          devmemory run -- &lt;cmd&gt;
        </code>
      </div>
    </aside>
  );
}
