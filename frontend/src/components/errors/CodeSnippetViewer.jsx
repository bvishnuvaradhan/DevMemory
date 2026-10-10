import React from 'react';
import { FileCode2, AlertCircle, Copy, Check } from 'lucide-react';

export default function CodeSnippetViewer({ sourceLocation, errorType }) {
  const [copied, setCopied] = React.useState(false);

  if (!sourceLocation || !sourceLocation.file) {
    return (
      <div className="rounded-2xl border border-white/80 bg-white/75 backdrop-blur-md p-5 shadow-glass">
        <div className="flex items-center gap-2 text-xs font-mono text-slate-500">
          <FileCode2 className="h-4 w-4 text-slate-400" />
          <span>Source Code Location</span>
        </div>
        <div className="mt-3 flex items-center gap-2 rounded-xl border border-amber-200 bg-amber-50/70 p-3 text-xs text-amber-900 font-mono">
          <AlertCircle className="h-4 w-4 text-amber-600 shrink-0" />
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
    <div className="overflow-hidden rounded-2xl border border-slate-200/90 bg-white shadow-glass">
      {/* File & Location Header */}
      <div className="flex items-center justify-between border-b border-slate-200 px-4 py-2.5 bg-slate-50/90">
        <div className="flex items-center gap-2 font-mono text-xs">
          <FileCode2 className="h-4 w-4 text-brand-500" />
          <span className="font-semibold text-slate-800">{file}</span>
          <span className="rounded-full bg-rose-50 px-2.5 py-0.5 text-[11px] font-bold text-rose-700 border border-rose-200">
            Line {line}
            {column ? `:${column}` : ''}
          </span>
        </div>

        <button
          onClick={handleCopy}
          className="flex items-center gap-1 text-[11px] font-mono text-slate-500 hover:text-slate-800 transition-colors cursor-pointer"
          title="Copy snippet"
        >
          {copied ? (
            <>
              <Check className="h-3 w-3 text-emerald-600" />
              <span className="text-emerald-600 font-semibold">Copied</span>
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
      <div className="p-4 bg-[#F8FAFC] overflow-x-auto border-t border-slate-100">
        <pre className="font-mono text-xs leading-relaxed text-slate-800">
          {snippet && typeof snippet === 'string' ? (
            snippet.split('\n').map((snipLine, idx) => {
              const isErrorLine = line && snipLine.trim().startsWith(`${line}:`);
              return (
                <div
                  key={idx}
                  className={`py-0.5 px-2 -mx-2 rounded ${
                    isErrorLine
                      ? 'bg-rose-50/90 border-l-4 border-rose-500 text-rose-950 font-bold'
                      : 'hover:bg-slate-200/50'
                  }`}
                >
                  {snipLine}
                </div>
              );
            })
          ) : (
            <span className="text-slate-400 italic">No source snippet captured for this location.</span>
          )}
        </pre>
      </div>
    </div>
  );
}
