import React from 'react';
import { History, Share2, ShieldCheck, ArrowRight, ExternalLink } from 'lucide-react';
import Badge from '../common/Badge';

export default function HistoricalIncidentsCard({ historicalMatches = [], currentProjectName }) {
  if (!Array.isArray(historicalMatches) || historicalMatches.length === 0) {
    return (
      <div className="rounded-2xl border border-white/80 bg-white/75 dark:border-slate-800/80 dark:bg-slate-900/75 backdrop-blur-md p-6 text-center text-xs text-slate-500 dark:text-slate-400 font-mono shadow-glass">
        <History className="h-5 w-5 mx-auto mb-2 text-slate-400 dark:text-slate-500" />
        <span>No previous matching incidents found in project or cross-project memory bank.</span>
      </div>
    );
  }

  return (
    <div className="rounded-2xl border border-white/80 bg-white/75 dark:border-slate-800/80 dark:bg-slate-900/75 backdrop-blur-md p-5 space-y-4 shadow-glass">
      <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-800 pb-3">
        <div className="flex items-center gap-2">
          <History className="h-4 w-4 text-brand-500 dark:text-brand-400" />
          <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100 font-mono">
            Related Historical Precedents ({historicalMatches.length})
          </h3>
        </div>
        <span className="text-[10px] text-slate-500 dark:text-slate-400 font-mono font-medium">
          Persistent Memory Bank
        </span>
      </div>

      <div className="space-y-3">
        {historicalMatches.map((match, idx) => {
          const isCrossProject = match.isCrossProject;
          return (
            <div
              key={idx}
              className={`rounded-xl border p-4 transition-all shadow-xs ${
                isCrossProject
                  ? 'border-indigo-200/80 dark:border-indigo-900/50 bg-gradient-to-br from-indigo-50/50 to-white/90 dark:from-indigo-950/30 dark:to-slate-900/90 hover:border-indigo-300 dark:hover:border-indigo-700/60'
                  : 'border-slate-200/80 dark:border-slate-800 bg-white/90 dark:bg-slate-800/80 hover:border-slate-300 dark:hover:border-slate-700'
              }`}
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  {isCrossProject ? (
                    <span className="inline-flex items-center gap-1.5 rounded-full bg-indigo-50 dark:bg-indigo-950/60 px-2.5 py-0.5 text-[11px] font-bold text-indigo-700 dark:text-indigo-300 border border-indigo-200 dark:border-indigo-800/60 shadow-xs">
                      <Share2 className="h-3 w-3" />
                      Cross-Project Match
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1.5 rounded-full bg-slate-100 dark:bg-slate-700/80 px-2.5 py-0.5 text-[11px] font-semibold text-slate-700 dark:text-slate-300 border border-slate-200 dark:border-slate-600">
                      Current Project Memory
                    </span>
                  )}
                  <span className="text-xs font-mono text-slate-700 dark:text-slate-300 font-semibold">
                    Source: {match.sourceProject}
                  </span>
                </div>

                {match.verified && (
                  <Badge variant="success" size="xs" dot>
                    Verified in Source
                  </Badge>
                )}
              </div>

              {/* Match Rationale */}
              <div className="mt-2.5 text-xs text-slate-700 dark:text-slate-300">
                <span className="text-slate-500 dark:text-slate-400 font-mono text-[11px] block mb-0.5 font-medium">
                  Why this precedent applies:
                </span>
                <p className="font-mono text-[11px] text-indigo-950 dark:text-indigo-200 bg-slate-50/90 dark:bg-slate-900/70 p-2 rounded-lg border border-slate-200/70 dark:border-slate-800">
                  {match.matchReason}
                </p>
              </div>

              {/* Sanitized Fix Summary */}
              <div className="mt-3 text-xs">
                <span className="text-slate-500 dark:text-slate-400 font-mono text-[11px] block mb-0.5 font-medium">
                  Sanitized Fix Outcome:
                </span>
                <p className="text-slate-800 dark:text-slate-200 font-sans leading-relaxed">
                  {match.sanitizedFixSummary}
                </p>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
