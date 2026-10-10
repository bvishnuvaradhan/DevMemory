import React from 'react';
import { FileCode2, AlertCircle, Copy, Check } from 'lucide-react';

export default function CodeSnippetViewer({ sourceLocation, errorType }) {
  const [copied, setCopied] = React.useState(false);

  if (!sourceLocation || !sourceLocation.file) {
    return (
      <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-4">
        <div className="flex items-center gap-2 text-xs font-mono text-slate-400">
          <FileCode2 className="h-4 w-4 text-slate-500" />
          <span>Source Code Location</span>
        </div>
        <div className="mt-3 flex items-center gap-2 rounded-lg border border-slate-800/80 bg-slate-950/60 p-3 text-xs text-slate-400 font-mono">
          <AlertCircle className="h-4 w-4 text-amber-400/80 shrink-0" />
          <span>
            Source location unavailable. The command failed due to an OS-level signal, external environment error, or compiled binary crash without file traces.
          </span>
        </div>
      </div>
    );
  }

  const { file, line, column, snippet } = sourceLocation;

  const handleCopy = () => {
    if (snippet) {
      navigator.clipboard.writeText(snippet);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div className="overflow-hidden rounded-xl border border-slate-800 bg-slate-900/60 shadow-sm">
      {/* File & Location Header */}
      <div className="flex items-center justify-between border-b border-slate-800 px-4 py-2.5 bg-slate-950/80">
        <div className="flex items-center gap-2 font-mono text-xs">
          <FileCode2 className="h-4 w-4 text-brand-400" />
          <span className="font-semibold text-white">{file}</span>
          <span className="rounded bg-rose-500/20 px-2 py-0.5 text-[11px] font-bold text-rose-300 border border-rose-500/30">
            Line {line}
            {column ? `:${column}` : ''}
          </span>
        </div>

        <button
          onClick={handleCopy}
          className="flex items-center gap-1 text-[11px] font-mono text-slate-400 hover:text-white transition-colors cursor-pointer"
          title="Copy snippet"
        >
          {copied ? (
            <>
              <Check className="h-3 w-3 text-emerald-400" />
              <span className="text-emerald-400">Copied</span>
            </>
          ) : (
            <>
              <Copy className="h-3 w-3" />
              <span>Copy</span>
            </>
          )}
        </button>
      </div>

      {/* Code Snippet Box */}
      <div className="p-4 bg-slate-950 overflow-x-auto">
        <pre className="font-mono text-xs leading-relaxed text-slate-200">
          {snippet && typeof snippet === 'string' ? (
            snippet.split('\n').map((snipLine, idx) => {
              const isErrorLine = line && snipLine.trim().startsWith(`${line}:`);
              return (
                <div
                  key={idx}
                  className={`py-0.5 px-2 -mx-2 rounded ${
                    isErrorLine
                      ? 'bg-rose-950/50 border-l-2 border-rose-500 text-rose-200 font-semibold'
                      : 'hover:bg-slate-900/60'
                  }`}
                >
                  {snipLine}
                </div>
              );
            })
          ) : (
            <span className="text-slate-500 italic">No source snippet captured for this location.</span>
          )}
        </pre>
      </div>
    </div>
  );
}
