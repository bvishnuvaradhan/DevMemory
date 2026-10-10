import React from 'react';
import { Terminal } from 'lucide-react';

export default function EmptyState({
  title = 'No records found',
  description = 'Run developer commands with "devmemory run -- <command>" to capture telemetry.',
  icon: Icon = Terminal,
}) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-slate-800 bg-slate-900/30 p-8 text-center">
      <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-slate-800/80 text-slate-400">
        <Icon className="h-6 w-6" />
      </div>
      <h3 className="mt-3 text-sm font-semibold text-slate-200">{title}</h3>
      <p className="mt-1 max-w-sm text-xs text-slate-400">{description}</p>
    </div>
  );
}
