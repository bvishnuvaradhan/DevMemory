import React from 'react';
import { AlertTriangle, Repeat, Layers } from 'lucide-react';
import Badge from '../common/Badge';

export default function RecurringErrorsWidget({ recurringErrors = [] }) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-5 shadow-sm">
      <div className="flex items-center justify-between border-b border-slate-800/80 pb-3">
        <div className="flex items-center gap-2">
          <AlertTriangle className="h-4 w-4 text-amber-400" />
          <h3 className="text-sm font-semibold text-white">Recurring Errors</h3>
        </div>
        <Badge variant="warning" size="xs">
          {recurringErrors.length} Detected
        </Badge>
      </div>

      <div className="mt-4 space-y-3">
        {recurringErrors.map((err, idx) => (
          <div
            key={idx}
            className="rounded-lg border border-slate-800/80 bg-slate-950/60 p-3.5 hover:border-slate-700 transition-colors"
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-mono text-xs font-semibold text-rose-300">
                    {err.errorType}
                  </span>
                  <span className="rounded bg-slate-800 px-1.5 py-0.5 text-[10px] text-slate-400">
                    {err.category}
                  </span>
                </div>
                <p className="mt-1 font-mono text-[11px] text-slate-400 line-clamp-2 bg-slate-900/60 p-1.5 rounded border border-slate-800/40">
                  {err.sampleMessage}
                </p>
              </div>

              <div className="flex flex-col items-end shrink-0">
                <span className="flex items-center gap-1 font-mono text-xs font-bold text-amber-400">
                  <Repeat className="h-3 w-3" />
                  {err.occurrences}x
                </span>
                <span className="text-[10px] text-slate-500 mt-0.5">recurred</span>
              </div>
            </div>

            <div className="mt-3 flex items-center justify-between pt-2 border-t border-slate-900 text-[10px] text-slate-500 font-mono">
              <div className="flex items-center gap-1.5">
                <Layers className="h-3 w-3 text-slate-400" />
                <span>Projects:</span>
                {err.affectedProjects.map((p, i) => (
                  <span key={i} className="text-slate-300 bg-slate-800/60 px-1.5 py-0.5 rounded">
                    {p}
                  </span>
                ))}
              </div>
              {err.hasVerifiedFix && (
                <Badge variant="success" size="xs">
                  Fix Verified
                </Badge>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
