import React from 'react';
import { CheckCircle2, ShieldCheck, Terminal, Sparkles } from 'lucide-react';
import Badge from '../common/Badge';

export default function FixOutcomesWidget({ verifiedFixes = [] }) {
  return (
    <div className="rounded-2xl border border-white/80 bg-white/75 backdrop-blur-md p-5 shadow-glass">
      <div className="flex items-center justify-between border-b border-slate-100 pb-3">
        <div className="flex items-center gap-2">
          <ShieldCheck className="h-4 w-4 text-emerald-600" />
          <h3 className="text-sm font-semibold text-slate-900 font-mono">Verified Fix Bank</h3>
        </div>
        <span className="text-[11px] font-mono text-emerald-700 bg-emerald-50 px-2.5 py-0.5 rounded-full border border-emerald-200 font-medium">
          Proven Fixes Only
        </span>
      </div>

      <div className="mt-4 space-y-3">
        {verifiedFixes.map((fix) => (
          <div
            key={fix.id}
            className="rounded-xl border border-emerald-100 bg-white/90 p-3.5 hover:border-emerald-300 hover:shadow-xs transition-all"
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-mono text-xs font-semibold text-emerald-700">
                    {fix.errorType}
                  </span>
                  <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-700 font-mono border border-slate-200/60 font-medium">
                    {fix.projectName}
                  </span>
                </div>
                <p className="mt-1.5 text-xs text-slate-700 leading-relaxed font-sans">
                  {fix.solutionSummary}
                </p>
              </div>

              <Badge variant="success" size="xs" dot>
                {fix.status}
              </Badge>
            </div>

            {/* Verification Command */}
            <div className="mt-3 rounded-lg bg-emerald-50/50 p-2 font-mono text-[11px] text-emerald-900 border border-emerald-200/60">
              <div className="flex items-center gap-1.5 text-[10px] text-slate-500 mb-1">
                <Terminal className="h-3 w-3 text-emerald-600" />
                <span>Verification Command:</span>
              </div>
              <code className="text-emerald-800 break-all font-semibold">{fix.verificationMethod}</code>
            </div>

            <div className="mt-2.5 flex items-center justify-between text-[10px] text-slate-500 font-mono">
              <span className="flex items-center gap-1">
                <Sparkles className="h-3 w-3 text-brand-500" />
                {fix.author}
              </span>
              <span className="text-emerald-700 font-semibold">
                Recurrence: {fix.recurrenceCountAfterFix}x
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
