import React from 'react';
import { Link } from 'react-router-dom';
import { CheckCircle2, ShieldCheck, Terminal, Sparkles } from 'lucide-react';
import Badge from '../common/Badge';

export default function FixOutcomesWidget({ verifiedFixes = [] }) {
  const safeVerifiedFixes = Array.isArray(verifiedFixes) ? verifiedFixes : [];

  return (
    <div className="rounded-2xl border border-white/80 bg-white/75 dark:border-slate-800/80 dark:bg-slate-900/75 backdrop-blur-md p-5 shadow-glass">
      <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-800 pb-3">
        <div className="flex items-center gap-2">
          <ShieldCheck className="h-4 w-4 text-emerald-600 dark:text-emerald-400" />
          <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100 font-mono">Verified Fix Bank</h3>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[11px] font-mono text-emerald-700 dark:text-emerald-300 bg-emerald-50 dark:bg-emerald-950/50 px-2.5 py-0.5 rounded-full border border-emerald-200 dark:border-emerald-800/60 font-medium">
            Proven Fixes Only
          </span>
          <Link
            to="/fixes"
            className="text-xs font-mono text-indigo-600 dark:text-indigo-400 hover:text-indigo-800 dark:hover:text-indigo-300 font-semibold transition-colors"
          >
            All Fixes →
          </Link>
        </div>
      </div>

      <div className="mt-4 space-y-3">
        {safeVerifiedFixes.length === 0 ? (
          <div className="rounded-xl border border-dashed border-slate-200 dark:border-slate-800 p-6 text-center">
            <p className="text-xs font-mono text-slate-500 dark:text-slate-400">
              No verified fixes recorded yet.
            </p>
          </div>
        ) : (
          safeVerifiedFixes.map((fix, idx) => (
            <div
              key={fix?.id || fix?.fixId || fix?.fix_id || idx}
              className="rounded-xl border border-emerald-100 dark:border-emerald-900/50 bg-white/90 dark:bg-slate-800/80 p-3.5 hover:border-emerald-300 dark:hover:border-emerald-700/60 hover:shadow-xs transition-all"
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-xs font-semibold text-emerald-700 dark:text-emerald-400">
                      {fix?.errorType || fix?.error_type || 'Resolved Issue'}
                    </span>
                    <span className="rounded bg-slate-100 dark:bg-slate-700 px-1.5 py-0.5 text-[10px] text-slate-700 dark:text-slate-300 font-mono border border-slate-200/60 dark:border-slate-600 font-medium">
                      {fix?.projectName || fix?.project_name || fix?.projectId || 'General'}
                    </span>
                  </div>
                  <p className="mt-1.5 text-xs text-slate-700 dark:text-slate-300 leading-relaxed font-sans">
                    {fix?.solutionSummary || fix?.solution_summary || fix?.description || 'Fix applied and verified.'}
                  </p>
                </div>

                <Badge variant="success" size="xs" dot>
                  {fix?.status || 'VERIFIED'}
                </Badge>
              </div>

              {/* Verification Command */}
              <div className="mt-3 rounded-lg bg-emerald-50/50 dark:bg-emerald-950/40 p-2 font-mono text-[11px] text-emerald-900 dark:text-emerald-300 border border-emerald-200/60 dark:border-emerald-900/60">
                <div className="flex items-center gap-1.5 text-[10px] text-slate-500 dark:text-slate-400 mb-1">
                  <Terminal className="h-3 w-3 text-emerald-600 dark:text-emerald-400" />
                  <span>Verification Command:</span>
                </div>
                <code className="text-emerald-800 dark:text-emerald-300 break-all font-semibold">
                  {fix?.verificationMethod || fix?.verification_method || fix?.verification_command || 'devmemory verify'}
                </code>
              </div>

              <div className="mt-2.5 flex items-center justify-between text-[10px] text-slate-500 dark:text-slate-400 font-mono">
                <span className="flex items-center gap-1">
                  <Sparkles className="h-3 w-3 text-brand-500 dark:text-brand-400" />
                  {fix?.author || 'AI + Developer Verification'}
                </span>
                <span className="text-emerald-700 dark:text-emerald-400 font-semibold">
                  Recurrence: {fix?.recurrenceCountAfterFix ?? 0}x
                </span>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
