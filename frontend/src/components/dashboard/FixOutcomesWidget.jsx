import React from 'react';
import { CheckCircle2, ShieldCheck, Terminal, Sparkles } from 'lucide-react';
import Badge from '../common/Badge';

export default function FixOutcomesWidget({ verifiedFixes = [] }) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-5 shadow-sm">
      <div className="flex items-center justify-between border-b border-slate-800/80 pb-3">
        <div className="flex items-center gap-2">
          <ShieldCheck className="h-4 w-4 text-emerald-400" />
          <h3 className="text-sm font-semibold text-white">Verified Fix Bank</h3>
        </div>
        <span className="text-[11px] font-mono text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/20">
          Proven Fixes Only
        </span>
      </div>

      <div className="mt-4 space-y-3">
        {verifiedFixes.map((fix) => (
          <div
            key={fix.id}
            className="rounded-lg border border-slate-800/80 bg-slate-950/60 p-3.5 hover:border-emerald-500/30 transition-colors"
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-mono text-xs font-semibold text-emerald-300">
                    {fix.errorType}
                  </span>
                  <span className="rounded bg-slate-800 px-1.5 py-0.5 text-[10px] text-slate-300 font-mono">
                    {fix.projectName}
                  </span>
                </div>
                <p className="mt-1.5 text-xs text-slate-200 leading-relaxed font-sans">
                  {fix.solutionSummary}
                </p>
              </div>

              <Badge variant="success" size="xs" dot>
                {fix.status}
              </Badge>
            </div>

            {/* Verification Command */}
            <div className="mt-3 rounded bg-slate-900/80 p-2 font-mono text-[11px] text-slate-300 border border-slate-800/60">
              <div className="flex items-center gap-1.5 text-[10px] text-slate-500 mb-1">
                <Terminal className="h-3 w-3" />
                <span>Verification Command:</span>
              </div>
              <code className="text-emerald-300/90 break-all">{fix.verificationMethod}</code>
            </div>

            <div className="mt-2.5 flex items-center justify-between text-[10px] text-slate-500 font-mono">
              <span className="flex items-center gap-1">
                <Sparkles className="h-3 w-3 text-brand-400" />
                {fix.author}
              </span>
              <span className="text-emerald-400">
                Recurrence: {fix.recurrenceCountAfterFix}x
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
