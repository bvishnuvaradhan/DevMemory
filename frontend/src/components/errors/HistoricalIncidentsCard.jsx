import React from 'react';
import { History, Share2, ShieldCheck, ArrowRight, ExternalLink } from 'lucide-react';
import Badge from '../common/Badge';

export default function HistoricalIncidentsCard({ historicalMatches = [], currentProjectName }) {
  if (!Array.isArray(historicalMatches) || historicalMatches.length === 0) {
    return (
      <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-5 text-center text-xs text-slate-500 font-mono">
        <History className="h-5 w-5 mx-auto mb-2 text-slate-600" />
        <span>No previous matching incidents found in project or cross-project memory bank.</span>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-5 space-y-4">
      <div className="flex items-center justify-between border-b border-slate-800/80 pb-3">
        <div className="flex items-center gap-2">
          <History className="h-4 w-4 text-brand-400" />
          <h3 className="text-sm font-semibold text-white font-mono">
            Related Historical Precedents ({historicalMatches.length})
          </h3>
        </div>
        <span className="text-[10px] text-slate-400 font-mono">
          Persistent Memory Bank
        </span>
      </div>

      <div className="space-y-3">
        {historicalMatches.map((match, idx) => {
          const isCrossProject = match.isCrossProject;
          return (
            <div
              key={idx}
              className={`rounded-lg border p-4 transition-colors ${
                isCrossProject
                  ? 'border-indigo-500/40 bg-indigo-950/20 hover:border-indigo-500/60'
                  : 'border-slate-800 bg-slate-950/60 hover:border-slate-700'
              }`}
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  {isCrossProject ? (
                    <span className="inline-flex items-center gap-1.5 rounded-full bg-indigo-500/20 px-2.5 py-0.5 text-[11px] font-bold text-indigo-300 border border-indigo-500/40">
                      <Share2 className="h-3 w-3" />
                      Cross-Project Match
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1.5 rounded-full bg-slate-800 px-2.5 py-0.5 text-[11px] font-semibold text-slate-300">
                      Current Project Memory
                    </span>
                  )}
                  <span className="text-xs font-mono text-slate-300 font-semibold">
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
              <div className="mt-2.5 text-xs text-slate-300">
                <span className="text-slate-500 font-mono text-[11px] block mb-0.5">
                  Why this precedent applies:
                </span>
                <p className="font-mono text-[11px] text-indigo-200/90 bg-slate-950/80 p-2 rounded border border-slate-800/60">
                  {match.matchReason}
                </p>
              </div>

              {/* Sanitized Fix Summary */}
              <div className="mt-3 text-xs">
                <span className="text-slate-500 font-mono text-[11px] block mb-0.5">
                  Sanitized Fix Outcome:
                </span>
                <p className="text-slate-200 font-sans leading-relaxed">
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
