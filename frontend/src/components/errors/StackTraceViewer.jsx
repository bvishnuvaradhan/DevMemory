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
    <div className="overflow-hidden rounded-2xl border border-slate-200/90 dark:border-slate-800/80 bg-white dark:bg-slate-900 shadow-glass">
      <button
        onClick={() => setIsOpen(!isOpen)}
        aria-expanded={isOpen}
        aria-label={`Full stack trace, ${isOpen ? 'collapse' : 'expand'}`}
        className="w-full flex items-center justify-between px-4 py-3 bg-slate-50/90 dark:bg-slate-800/90 hover:bg-slate-100/80 dark:hover:bg-slate-800 transition-colors text-left cursor-pointer"
      >
        <div className="flex items-center gap-2 font-mono text-xs text-slate-700 dark:text-slate-300">
          <Terminal className="h-4 w-4 text-slate-500 dark:text-slate-400" />
          <span className="font-semibold text-slate-900 dark:text-slate-100">Full Stack Trace</span>
          <span className="text-[10px] text-slate-500 dark:text-slate-400">
            ({stackTrace.split('\n').length} frames)
          </span>
        </div>

        <div className="flex items-center gap-3">
          <span className="text-[10px] text-slate-500 dark:text-slate-400 font-mono">
            {isOpen ? 'Click to collapse' : 'Click to expand'}
          </span>
          {isOpen ? (
            <ChevronDown className="h-4 w-4 text-slate-500 dark:text-slate-400" />
          ) : (
            <ChevronRight className="h-4 w-4 text-slate-500 dark:text-slate-400" />
          )}
        </div>
      </button>

      {isOpen && (
        <div className="relative border-t border-slate-200 dark:border-slate-800 bg-[#F8FAFC] dark:bg-[#0B0F19] p-4">
          <button
            onClick={handleCopy}
            aria-label="Copy stack trace"
            className="absolute top-3 right-3 flex items-center gap-1 rounded-lg bg-white dark:bg-slate-800 px-2 py-1 text-[10px] font-mono text-slate-700 dark:text-slate-200 border border-slate-200 dark:border-slate-700 hover:text-slate-900 dark:hover:text-slate-100 hover:border-slate-300 dark:hover:border-slate-600 shadow-xs transition-colors cursor-pointer"
          >
            {copied ? (
              <>
                <Check className="h-3 w-3 text-emerald-600 dark:text-emerald-400" />
                <span className="text-emerald-600 dark:text-emerald-400 font-semibold">Copied</span>
              </>
            ) : (
              <>
                <Copy className="h-3 w-3" />
                <span>Copy Trace</span>
              </>
            )}
          </button>
          <pre className="font-mono text-xs leading-relaxed text-rose-800/90 dark:text-rose-300 whitespace-pre-wrap overflow-x-auto pr-24">
            {stackTrace}
          </pre>
        </div>
      )}
    </div>
  );
}
