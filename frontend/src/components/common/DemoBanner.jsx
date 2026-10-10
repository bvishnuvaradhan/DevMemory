import React from 'react';
import { AlertCircle, Database, CheckCircle2 } from 'lucide-react';

export default function DemoBanner({ isMock = true }) {
  if (!isMock) {
    return (
      <div className="bg-emerald-50/90 backdrop-blur-md border-b border-emerald-200/80 px-4 py-2 text-xs text-emerald-900 flex items-center justify-between shadow-xs">
        <div className="flex items-center gap-2">
          <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" />
          <span>Connected to live DevMemory FastAPI backend & MongoDB database.</span>
        </div>
        <span className="font-mono text-[10px] text-emerald-700 font-bold bg-emerald-100 px-2 py-0.5 rounded border border-emerald-200">
          API: LIVE
        </span>
      </div>
    );
  }

  return (
    <div
      role="status"
      aria-live="polite"
      className="bg-amber-50/90 backdrop-blur-md border-b border-amber-200/80 px-3 sm:px-4 py-1.5 sm:py-2 text-xs text-amber-900 flex flex-col sm:flex-row sm:items-center justify-between gap-1.5 sm:gap-2 shadow-xs"
    >
      <div className="flex items-center gap-2">
        <AlertCircle className="h-3.5 w-3.5 text-amber-600 shrink-0" />
        <span className="text-[11px] sm:text-xs">
          <strong className="font-semibold text-amber-950">DEMO MODE:</strong> Sample demonstration dataset. Live backend not detected on{' '}
          <code className="bg-amber-100/80 px-1.5 py-0.5 rounded text-amber-900 font-mono border border-amber-200 text-[10px] sm:text-[11px]">
            localhost:8000
          </code>.
        </span>
      </div>
      <div className="flex items-center gap-2 shrink-0 self-start sm:self-auto">
        <span className="inline-flex items-center gap-1 rounded bg-amber-100 px-2 py-0.5 text-[10px] font-mono font-semibold uppercase text-amber-900 border border-amber-300 shadow-xs">
          <Database className="h-3 w-3" />
          Mock Data
        </span>
      </div>
    </div>
  );
}
