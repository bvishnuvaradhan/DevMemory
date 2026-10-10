import React from 'react';
import { Link } from 'react-router-dom';
import { AlertTriangle, Repeat, Layers } from 'lucide-react';
import Badge from '../common/Badge';

export default function RecurringErrorsWidget({ recurringErrors = [] }) {
  return (
    <div className="rounded-2xl border border-white/80 bg-white/75 backdrop-blur-md p-5 shadow-glass">
      <div className="flex items-center justify-between border-b border-slate-100 pb-3">
        <div className="flex items-center gap-2">
          <AlertTriangle className="h-4 w-4 text-amber-500" />
          <h3 className="text-sm font-semibold text-slate-900 font-mono">Recurring Errors</h3>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant="warning" size="xs">
            {recurringErrors.length} Detected
          </Badge>
          <Link
            to="/incidents"
            className="text-xs font-mono text-indigo-600 hover:text-indigo-800 font-semibold transition-colors"
          >
            All Incidents →
          </Link>
        </div>
      </div>

      <div className="mt-4 space-y-3">
        {recurringErrors.map((err, idx) => (
          <div
            key={idx}
            className="rounded-xl border border-slate-200/80 bg-white/90 p-3.5 hover:border-indigo-200 hover:shadow-xs transition-all"
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-mono text-xs font-semibold text-rose-600">
                    {err.errorType}
                  </span>
                  <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-600 font-medium">
                    {err.category}
                  </span>
                </div>
                <p className="mt-1.5 font-mono text-[11px] text-slate-600 line-clamp-2 bg-slate-50 p-2 rounded-lg border border-slate-200/70">
                  {err.sampleMessage}
                </p>
              </div>

              <div className="flex flex-col items-end shrink-0">
                <span className="flex items-center gap-1 font-mono text-xs font-bold text-amber-600">
                  <Repeat className="h-3 w-3" />
                  {err.occurrences}x
                </span>
                <span className="text-[10px] text-slate-500 mt-0.5">recurred</span>
              </div>
            </div>

            <div className="mt-3 flex items-center justify-between pt-2 border-t border-slate-100 text-[10px] text-slate-500 font-mono">
              <div className="flex items-center gap-1.5">
                <Layers className="h-3 w-3 text-slate-400" />
                <span>Projects:</span>
                {err.affectedProjects.map((p, i) => (
                  <span key={i} className="text-slate-700 bg-slate-100 px-1.5 py-0.5 rounded border border-slate-200/60 font-medium">
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
