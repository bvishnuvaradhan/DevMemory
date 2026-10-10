import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { FolderGit2, ArrowRight, ChevronDown, ChevronUp } from 'lucide-react';
import Badge from '../common/Badge';
import EmptyState from '../common/EmptyState';

export default function ProjectsGrid({
  projects = [],
  initialLimit = 4,
  showAll: controlledShowAll,
  onToggleShowAll,
}) {
  const [internalShowAll, setInternalShowAll] = useState(false);

  const isControlled = typeof controlledShowAll === 'boolean';
  const showAll = isControlled ? controlledShowAll : internalShowAll;

  const handleToggle = () => {
    if (isControlled && onToggleShowAll) {
      onToggleShowAll();
    } else {
      setInternalShowAll((prev) => !prev);
    }
  };

  if (!projects || projects.length === 0) {
    return (
      <EmptyState
        title="No Workspaces Registered"
        description="No project workspaces found. Run commands with DevMemory CLI to register a workspace."
        icon={FolderGit2}
      />
    );
  }

  const hasMore = projects.length > initialLimit;
  const visibleProjects = hasMore && !showAll ? projects.slice(0, initialLimit) : projects;

  return (
    <div className="space-y-4">
      <div
        id="workspaces-grid"
        className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4"
      >
        {visibleProjects.map((proj) => {
          const hasFailures = proj.failureCount > 0;
          return (
            <Link
              key={proj.id}
              to={`/projects/${proj.id}`}
              className="group relative flex flex-col justify-between rounded-2xl border border-white/85 bg-white/75 dark:border-slate-800/80 dark:bg-slate-900/75 p-5 shadow-glass hover:shadow-glass-hover hover:border-indigo-200/90 dark:hover:border-indigo-500/50 hover:-translate-y-1 transition-all duration-200 backdrop-blur-md"
            >
              <div>
                <div className="flex items-center justify-between">
                  <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-50 to-purple-50 dark:from-indigo-950/60 dark:to-purple-950/60 text-indigo-600 dark:text-indigo-400 border border-indigo-100 dark:border-indigo-800/60 group-hover:bg-indigo-100/80 dark:group-hover:bg-indigo-900/60 transition-colors shadow-xs">
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

                <h3 className="mt-3 text-sm font-semibold text-slate-900 dark:text-slate-100 group-hover:text-indigo-600 dark:group-hover:text-indigo-400 transition-colors">
                  {proj.name}
                </h3>
                <p className="mt-1 text-xs text-slate-500 dark:text-slate-400 line-clamp-2 leading-relaxed">
                  {proj.description}
                </p>

                <div className="mt-3 flex items-center gap-2">
                  <span className="rounded-lg bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 px-2 py-0.5 text-[10px] font-mono border border-slate-200/80 dark:border-slate-700">
                    {proj.language}
                  </span>
                  <span className="rounded-lg bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400 px-2 py-0.5 text-[10px] font-mono border border-slate-200/80 dark:border-slate-700">
                    {proj.framework}
                  </span>
                </div>
              </div>

              <div className="mt-5 pt-4 border-t border-slate-100 dark:border-slate-800">
                <div className="grid grid-cols-3 gap-2 text-center text-xs font-mono">
                  <div>
                    <span className="block text-slate-400 dark:text-slate-500 text-[10px] uppercase font-semibold">Runs</span>
                    <span className="font-semibold text-slate-800 dark:text-slate-200">{proj.totalRuns}</span>
                  </div>
                  <div>
                    <span className="block text-slate-400 dark:text-slate-500 text-[10px] uppercase font-semibold">Errors</span>
                    <span
                      className={`font-semibold ${
                        hasFailures ? 'text-rose-600 dark:text-rose-400' : 'text-slate-800 dark:text-slate-200'
                      }`}
                    >
                      {proj.failureCount}
                    </span>
                  </div>
                  <div>
                    <span className="block text-slate-400 dark:text-slate-500 text-[10px] uppercase font-semibold">Fixed</span>
                    <span className="font-semibold text-emerald-600 dark:text-emerald-400">
                      {proj.verifiedFixCount}
                    </span>
                  </div>
                </div>

                <div className="mt-3 flex items-center justify-between text-xs text-slate-500 dark:text-slate-400 group-hover:text-indigo-600 dark:group-hover:text-indigo-400 transition-colors pt-2">
                  <span className="text-[11px] font-mono font-medium">Open Workspace</span>
                  <ArrowRight className="h-3.5 w-3.5 group-hover:translate-x-1 transition-transform" />
                </div>
              </div>
            </Link>
          );
        })}
      </div>

      {/* Show More / Show Less toggle */}
      {hasMore && (
        <div className="flex justify-center pt-1">
          <button
            type="button"
            onClick={handleToggle}
            aria-expanded={showAll}
            aria-controls="workspaces-grid"
            aria-label={
              showAll
                ? 'Show Less workspaces'
                : `Show More workspaces (${projects.length - initialLimit} remaining)`
            }
            className="inline-flex items-center gap-2 rounded-xl border border-slate-200/90 dark:border-slate-700/90 bg-white/80 dark:bg-slate-800/80 px-4 py-2 text-xs font-mono font-medium text-slate-700 dark:text-slate-200 hover:text-slate-900 dark:hover:text-white hover:bg-white dark:hover:bg-slate-700/90 shadow-xs hover:border-slate-300 dark:hover:border-slate-600 transition-all cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500"
          >
            <span>{showAll ? 'Show Less' : 'Show More'}</span>
            {showAll ? (
              <ChevronUp className="h-3.5 w-3.5 text-indigo-500 dark:text-indigo-400" />
            ) : (
              <>
                <span className="text-[11px] text-slate-400 dark:text-slate-500 font-normal">
                  ({projects.length - initialLimit} more)
                </span>
                <ChevronDown className="h-3.5 w-3.5 text-indigo-500 dark:text-indigo-400" />
              </>
            )}
          </button>
        </div>
      )}
    </div>
  );
}
