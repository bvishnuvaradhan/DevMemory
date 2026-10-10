import React from 'react';
import { Terminal } from 'lucide-react';

export default function EmptyState({
  title = 'No records found',
  description = 'Run developer commands with "devmemory run -- <command>" to capture telemetry.',
  icon: Icon = Terminal,
}) {
  return (
    <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-slate-300 bg-white/60 backdrop-blur-md p-8 text-center shadow-xs">
      <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-slate-100 text-slate-500 border border-slate-200 shadow-xs">
        <Icon className="h-6 w-6" />
      </div>
      <h3 className="mt-3 text-sm font-semibold text-slate-800 font-mono">{title}</h3>
      <p className="mt-1 max-w-sm text-xs text-slate-500 leading-relaxed">{description}</p>
    </div>
  );
}
