import React from 'react';
import { AlertCircle, Database, CheckCircle2 } from 'lucide-react';

export default function DemoBanner({ isMock = true }) {
  if (!isMock) {
    return (
      <div className="bg-emerald-950/40 border-b border-emerald-800/40 px-4 py-2 text-xs text-emerald-300 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
          <span>Connected to live DevMemory FastAPI backend & MongoDB database.</span>
        </div>
        <span className="font-mono text-[10px] text-emerald-400/80">API: LIVE</span>
      </div>
    );
  }

  return (
    <div className="bg-amber-950/40 border-b border-amber-800/40 px-4 py-2 text-xs text-amber-200/90 flex items-center justify-between">
      <div className="flex items-center gap-2">
        <AlertCircle className="h-3.5 w-3.5 text-amber-400 shrink-0" />
        <span>
          <strong className="font-semibold text-amber-300">DEMO MODE:</strong> Showing sample demonstration dataset. Live backend not detected on <code className="bg-amber-900/50 px-1 py-0.5 rounded text-amber-200 font-mono">localhost:8000</code>.
        </span>
      </div>
      <div className="flex items-center gap-2 shrink-0">
        <span className="inline-flex items-center gap-1 rounded bg-amber-500/20 px-2 py-0.5 text-[10px] font-mono font-semibold uppercase text-amber-300 border border-amber-500/30">
          <Database className="h-3 w-3" />
          Mock Data
        </span>
      </div>
    </div>
  );
}
