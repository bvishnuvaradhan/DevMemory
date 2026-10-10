import React from 'react';
import { Link } from 'react-router-dom';
import { Terminal, CheckCircle2, XCircle, Clock, FileCode2 } from 'lucide-react';
import Badge from '../common/Badge';

export default function RecentRunsTable({ runs = [] }) {
  return (
    <div className="overflow-hidden rounded-2xl border border-white/80 bg-white/75 backdrop-blur-md shadow-glass">
      <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4">
        <div className="flex items-center gap-2">
          <Terminal className="h-4 w-4 text-brand-500" />
          <h3 className="text-sm font-semibold text-slate-900 font-mono">Recent Command Runs</h3>
        </div>
        <Link
          to="/runs"
          className="text-xs font-mono text-indigo-600 hover:text-indigo-800 font-semibold transition-colors flex items-center gap-1"
        >
          <span>View All Runs →</span>
        </Link>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs font-mono">
          <thead className="bg-slate-50/80 text-slate-500 border-b border-slate-200/80">
            <tr>
              <th className="px-5 py-3 font-semibold uppercase tracking-wider text-[10px]">Status</th>
              <th className="px-5 py-3 font-semibold uppercase tracking-wider text-[10px]">Command</th>
              <th className="px-5 py-3 font-semibold uppercase tracking-wider text-[10px]">Project</th>
              <th className="px-5 py-3 font-semibold uppercase tracking-wider text-[10px]">Exit</th>
              <th className="px-5 py-3 font-semibold uppercase tracking-wider text-[10px]">Duration</th>
              <th className="px-5 py-3 font-semibold uppercase tracking-wider text-[10px]">Evidence / Source</th>
              <th className="px-5 py-3 font-semibold uppercase tracking-wider text-[10px]">Event ID</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 text-slate-700">
            {runs.map((run) => {
              const isSuccess = run.exitCode === 0;
              return (
                <tr key={run.eventId} className="hover:bg-slate-50/60 transition-colors">
                  <td className="px-5 py-3.5 whitespace-nowrap">
                    {isSuccess ? (
                      <span className="inline-flex items-center gap-1.5 text-emerald-600 font-semibold">
                        <CheckCircle2 className="h-3.5 w-3.5" />
                        <span>Pass</span>
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1.5 text-rose-600 font-semibold">
                        <XCircle className="h-3.5 w-3.5" />
                        <span>Fail</span>
                      </span>
                    )}
                  </td>
                  <td className="px-5 py-3.5">
                    <div className="max-w-xs md:max-w-sm truncate text-slate-800 bg-slate-100/90 px-2.5 py-1 rounded-lg border border-slate-200/80 text-xs">
                      {run.command}
                    </div>
                  </td>
                  <td className="px-5 py-3.5 whitespace-nowrap text-slate-700">
                    <Link
                      to={`/projects/${run.projectId}`}
                      className="rounded-md bg-slate-100 px-2 py-0.5 text-slate-700 hover:bg-brand-50 hover:text-brand-600 hover:border-brand-200 border border-slate-200/60 font-medium transition-colors"
                    >
                      {run.projectName}
                    </Link>
                  </td>
                  <td className="px-5 py-3.5 whitespace-nowrap">
                    <Badge variant={isSuccess ? 'success' : 'danger'} size="xs">
                      {run.exitCode}
                    </Badge>
                  </td>
                  <td className="px-5 py-3.5 whitespace-nowrap text-slate-600">
                    <span className="flex items-center gap-1">
                      <Clock className="h-3 w-3 text-slate-400" />
                      {run.durationMs}ms
                    </span>
                  </td>
                  <td className="px-5 py-3.5 whitespace-nowrap">
                    {run.sourceFile ? (
                      <span className="flex items-center gap-1 text-rose-700 font-mono text-[11px] bg-rose-50 px-2 py-0.5 rounded-md border border-rose-200 font-medium">
                        <FileCode2 className="h-3 w-3" />
                        {run.sourceFile}:{run.lineNumber}
                      </span>
                    ) : (
                      <span className="text-slate-400">—</span>
                    )}
                  </td>
                  <td className="px-5 py-3.5 whitespace-nowrap text-[11px] text-slate-400">
                    {run.eventId}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
