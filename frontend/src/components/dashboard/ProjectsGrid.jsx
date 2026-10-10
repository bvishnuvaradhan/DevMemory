import React from 'react';
import { Link } from 'react-router-dom';
import { FolderGit2, ArrowRight, Activity, CheckCircle, AlertOctagon } from 'lucide-react';
import Badge from '../common/Badge';

export default function ProjectsGrid({ projects = [] }) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
      {projects.map((proj) => {
        const hasFailures = proj.failureCount > 0;
        return (
          <Link
            key={proj.id}
            to={`/projects/${proj.id}`}
            className="group relative flex flex-col justify-between rounded-xl border border-slate-800 bg-slate-900/50 p-5 hover:border-brand-500/50 hover:bg-slate-900/80 transition-all duration-200"
          >
            <div>
              <div className="flex items-center justify-between">
                <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-slate-800 text-brand-400 group-hover:bg-brand-500/20 group-hover:text-brand-300 transition-colors">
                  <FolderGit2 className="h-4 w-4" />
                </div>
                <Badge
                  variant={proj.lastRunStatus === 'success' ? 'success' : 'danger'}
                  dot
                  size="xs"
                >
                  {proj.lastRunStatus === 'success' ? 'Healthy' : 'Needs Fix'}
                </Badge>
              </div>

              <h3 className="mt-3 text-sm font-semibold text-white group-hover:text-brand-300 transition-colors">
                {proj.name}
              </h3>
              <p className="mt-1 text-xs text-slate-400 line-clamp-2 leading-relaxed">
                {proj.description}
              </p>

              <div className="mt-3 flex items-center gap-2">
                <span className="rounded bg-slate-800/80 px-2 py-0.5 text-[10px] font-mono text-slate-300 border border-slate-700/60">
                  {proj.language}
                </span>
                <span className="rounded bg-slate-800/80 px-2 py-0.5 text-[10px] font-mono text-slate-400 border border-slate-700/60">
                  {proj.framework}
                </span>
              </div>
            </div>

            <div className="mt-5 pt-4 border-t border-slate-800/80">
              <div className="grid grid-cols-3 gap-2 text-center text-xs font-mono">
                <div>
                  <span className="block text-slate-500 text-[10px] uppercase">Runs</span>
                  <span className="font-semibold text-slate-200">{proj.totalRuns}</span>
                </div>
                <div>
                  <span className="block text-slate-500 text-[10px] uppercase">Errors</span>
                  <span
                    className={`font-semibold ${
                      hasFailures ? 'text-rose-400' : 'text-slate-200'
                    }`}
                  >
                    {proj.failureCount}
                  </span>
                </div>
                <div>
                  <span className="block text-slate-500 text-[10px] uppercase">Fixed</span>
                  <span className="font-semibold text-emerald-400">
                    {proj.verifiedFixCount}
                  </span>
                </div>
              </div>

              <div className="mt-3 flex items-center justify-between text-xs text-slate-400 group-hover:text-brand-400 transition-colors pt-2">
                <span className="text-[11px] font-mono">Workspace</span>
                <ArrowRight className="h-3.5 w-3.5 group-hover:translate-x-1 transition-transform" />
              </div>
            </div>
          </Link>
        );
      })}
    </div>
  );
}
