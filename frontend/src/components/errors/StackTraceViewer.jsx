import React, { useState } from 'react';
import { ChevronDown, ChevronRight, Terminal, Copy, Check } from 'lucide-react';

export default function StackTraceViewer({ stackTrace }) {
  const [isOpen, setIsOpen] = useState(false);
  const [copied, setCopied] = useState(false);

  if (!stackTrace || typeof stackTrace !== 'string' || stackTrace.trim().length === 0) {
    return null;
  }

  const handleCopy = () => {
    navigator.clipboard.writeText(stackTrace);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="overflow-hidden rounded-xl border border-slate-800 bg-slate-900/60 shadow-sm">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center justify-between px-4 py-3 bg-slate-950/80 hover:bg-slate-900/80 transition-colors text-left cursor-pointer"
      >
        <div className="flex items-center gap-2 font-mono text-xs text-slate-300">
          <Terminal className="h-4 w-4 text-slate-400" />
          <span className="font-semibold text-white">Full Stack Trace</span>
          <span className="text-[10px] text-slate-500">
            ({stackTrace.split('\n').length} frames)
          </span>
        </div>

        <div className="flex items-center gap-3">
          <span className="text-[10px] text-slate-500 font-mono">
            {isOpen ? 'Click to collapse' : 'Click to expand'}
          </span>
          {isOpen ? (
            <ChevronDown className="h-4 w-4 text-slate-400" />
          ) : (
            <ChevronRight className="h-4 w-4 text-slate-400" />
          )}
        </div>
      </button>

      {isOpen && (
        <div className="relative border-t border-slate-800 bg-slate-950 p-4">
          <button
            onClick={handleCopy}
            className="absolute top-3 right-3 flex items-center gap-1 rounded bg-slate-800/80 px-2 py-1 text-[10px] font-mono text-slate-300 hover:text-white hover:bg-slate-700 transition-colors cursor-pointer"
          >
            {copied ? (
              <>
                <Check className="h-3 w-3 text-emerald-400" />
                <span className="text-emerald-400">Copied</span>
              </>
            ) : (
              <>
                <Copy className="h-3 w-3" />
                <span>Copy Trace</span>
              </>
            )}
          </button>
          <pre className="font-mono text-xs leading-relaxed text-rose-300/90 whitespace-pre-wrap overflow-x-auto pr-16">
            {stackTrace}
          </pre>
        </div>
      )}
    </div>
  );
}
