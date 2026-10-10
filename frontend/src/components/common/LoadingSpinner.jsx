import React from 'react';
import { Loader2 } from 'lucide-react';

export default function LoadingSpinner({ label = 'Loading DevMemory telemetry...' }) {
  return (
    <div className="flex flex-col items-center justify-center p-12 text-slate-400">
      <Loader2 className="h-8 w-8 animate-spin text-brand-400" />
      <p className="mt-3 text-xs font-mono">{label}</p>
    </div>
  );
}
