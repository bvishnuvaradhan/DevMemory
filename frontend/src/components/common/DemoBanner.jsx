import React from 'react';
import { AlertCircle, Database, CheckCircle2 } from 'lucide-react';

export default function DemoBanner({ isMock = true }) {
  if (!isMock) {
    return (
      <div className="bg-emerald-50/90 dark:bg-emerald-950/60 backdrop-blur-md border-b border-emerald-200/80 dark:border-emerald-800/60 px-4 py-2 text-xs text-emerald-900 dark:text-emerald-200 flex items-center justify-between shadow-xs transition-colors">
        <div className="flex items-center gap-2">
          <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600 dark:text-emerald-400" />
          <span>Connected to live DevMemory FastAPI backend & MongoDB database.</span>
        </div>
        <span className="font-mono text-[10px] text-emerald-700 dark:text-emerald-300 font-bold bg-emerald-100 dark:bg-emerald-900/60 px-2 py-0.5 rounded border border-emerald-200 dark:border-emerald-800">
          API: LIVE
        </span>
      </div>
    );
  }

  return (
    <div
      role="status"
      aria-live="polite"
      className="bg-amber-50/90 dark:bg-amber-950/50 backdrop-blur-md border-b border-amber-200/80 dark:border-amber-900/60 px-3 sm:px-4 py-1.5 sm:py-2 text-xs text-amber-900 dark:text-amber-200 flex flex-col sm:flex-row sm:items-center justify-between gap-1.5 sm:gap-2 shadow-xs transition-colors"
    >
      <div className="flex items-center gap-2">
        <AlertCircle className="h-3.5 w-3.5 text-amber-600 dark:text-amber-400 shrink-0" />
        <span className="text-[11px] sm:text-xs">
          <strong className="font-semibold text-amber-950 dark:text-amber-100">DEMO MODE:</strong> Sample demonstration dataset. Live backend not detected on{' '}
          <code className="bg-amber-100/80 dark:bg-amber-900/60 px-1.5 py-0.5 rounded text-amber-900 dark:text-amber-200 font-mono border border-amber-200 dark:border-amber-800 text-[10px] sm:text-[11px]">
            localhost:8000
          </code>.
        </span>
      </div>
      <div className="flex items-center gap-2 shrink-0 self-start sm:self-auto">
        <span className="inline-flex items-center gap-1 rounded bg-amber-100 dark:bg-amber-900/60 px-2 py-0.5 text-[10px] font-mono font-semibold uppercase text-amber-900 dark:text-amber-200 border border-amber-300 dark:border-amber-700 shadow-xs">
          <Database className="h-3 w-3" />
          Mock Data
        </span>
      </div>
    </div>
  );
}
