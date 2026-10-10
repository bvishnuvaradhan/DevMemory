import React from 'react';
import { Terminal, CheckCircle2, XCircle, Clock, FileCode2 } from 'lucide-react';
import Badge from '../common/Badge';

export default function RecentRunsTable({ runs = [] }) {
  return (
    <div className="overflow-hidden rounded-xl border border-slate-800 bg-slate-900/60 shadow-sm">
      <div className="flex items-center justify-between border-b border-slate-800 px-5 py-4">
        <div className="flex items-center gap-2">
          <Terminal className="h-4 w-4 text-brand-400" />
          <h3 className="text-sm font-semibold text-white">Recent Command Runs</h3>
        </div>
        <span className="text-xs font-mono text-slate-400">Captured via CLI runner</span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs font-mono">
          <thead className="bg-slate-950/60 text-slate-400 border-b border-slate-800/80">
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
          <tbody className="divide-y divide-slate-800/60 text-slate-300">
            {runs.map((run) => {
              const isSuccess = run.exitCode === 0;
              return (
                <tr key={run.eventId} className="hover:bg-slate-800/30 transition-colors">
                  <td className="px-5 py-3.5 whitespace-nowrap">
                    {isSuccess ? (
                      <span className="inline-flex items-center gap-1.5 text-emerald-400 font-medium">
                        <CheckCircle2 className="h-3.5 w-3.5" />
                        <span>Pass</span>
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1.5 text-rose-400 font-medium">
                        <XCircle className="h-3.5 w-3.5" />
                        <span>Fail</span>
                      </span>
                    )}
                  </td>
                  <td className="px-5 py-3.5">
                    <div className="max-w-xs md:max-w-sm truncate text-white bg-slate-950/80 px-2.5 py-1 rounded border border-slate-800">
                      {run.command}
                    </div>
                  </td>
                  <td className="px-5 py-3.5 whitespace-nowrap text-slate-300">
                    <span className="rounded bg-slate-800 px-2 py-0.5 text-slate-300">
                      {run.projectName}
                    </span>
                  </td>
                  <td className="px-5 py-3.5 whitespace-nowrap">
                    <Badge variant={isSuccess ? 'success' : 'danger'} size="xs">
                      {run.exitCode}
                    </Badge>
                  </td>
                  <td className="px-5 py-3.5 whitespace-nowrap text-slate-400">
                    <span className="flex items-center gap-1">
                      <Clock className="h-3 w-3 text-slate-500" />
                      {run.durationMs}ms
                    </span>
                  </td>
                  <td className="px-5 py-3.5 whitespace-nowrap">
                    {run.sourceFile ? (
                      <span className="flex items-center gap-1 text-rose-300 font-mono text-[11px] bg-rose-950/30 px-2 py-0.5 rounded border border-rose-900/40">
                        <FileCode2 className="h-3 w-3" />
                        {run.sourceFile}:{run.lineNumber}
                      </span>
                    ) : (
                      <span className="text-slate-600">—</span>
                    )}
                  </td>
                  <td className="px-5 py-3.5 whitespace-nowrap text-[11px] text-slate-500">
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
