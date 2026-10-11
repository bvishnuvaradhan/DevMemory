import React from 'react';
import { History, Share2, ShieldCheck, BookOpen, AlertTriangle, Loader2 } from 'lucide-react';
import Badge from '../common/Badge';

export default function HistoricalIncidentsCard({
  historicalMatches = [],
  currentProjectName,
  isLoading = false,
  error = null,
}) {
  if (isLoading) {
    return (
      <div className="rounded-2xl border border-white/80 bg-white/75 dark:border-slate-800/80 dark:bg-slate-900/75 backdrop-blur-md p-6 text-center text-xs text-slate-500 dark:text-slate-400 font-mono shadow-glass">
        <Loader2 className="h-5 w-5 mx-auto mb-2 text-brand-500 dark:text-brand-400 animate-spin" />
        <span>Searching project memory and curated knowledge bank...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-2xl border border-amber-200/80 bg-amber-50/70 dark:border-amber-900/50 dark:bg-amber-950/30 backdrop-blur-md p-6 text-center text-xs text-amber-800 dark:text-amber-300 font-mono shadow-glass">
        <AlertTriangle className="h-5 w-5 mx-auto mb-2 text-amber-600 dark:text-amber-400" />
        <span className="font-semibold block mb-1">Retrieval Unavailable</span>
        <span className="text-[11px] text-amber-700/80 dark:text-amber-400/80">{String(error)}</span>
      </div>
    );
  }

  const matchesList = Array.isArray(historicalMatches) ? historicalMatches : [];
  const incidentMatches = matchesList.filter(
    (m) => !m.isGeneralKnowledge && m.sourceType !== 'knowledge_base'
  );
  const generalKnowledgeMatches = matchesList.filter(
    (m) => m.isGeneralKnowledge || m.sourceType === 'knowledge_base'
  );

  // State: No relevant results anywhere
  if (incidentMatches.length === 0 && generalKnowledgeMatches.length === 0) {
    return (
      <div className="rounded-2xl border border-white/80 bg-white/75 dark:border-slate-800/80 dark:bg-slate-900/75 backdrop-blur-md p-6 text-center text-xs text-slate-500 dark:text-slate-400 font-mono shadow-glass">
        <History className="h-5 w-5 mx-auto mb-2 text-slate-400 dark:text-slate-500" />
        <span>No previous matching incidents found in project or cross-project memory bank.</span>
      </div>
    );
  }

  return (
    <div className="rounded-2xl border border-white/80 bg-white/75 dark:border-slate-800/80 dark:bg-slate-900/75 backdrop-blur-md p-5 space-y-4 shadow-glass">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-800 pb-3">
        <div className="flex items-center gap-2">
          <History className="h-4 w-4 text-brand-500 dark:text-brand-400" />
          <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100 font-mono">
            {incidentMatches.length > 0
              ? `Related Historical Precedents (${incidentMatches.length})`
              : `Knowledge Base Retrieval (${generalKnowledgeMatches.length})`}
          </h3>
        </div>
        <span className="text-[10px] text-slate-500 dark:text-slate-400 font-mono font-medium">
          Persistent Memory Bank
        </span>
      </div>

      {/* State: No historical incident matches, but general knowledge found */}
      {incidentMatches.length === 0 && generalKnowledgeMatches.length > 0 && (
        <div className="rounded-xl border border-blue-200/80 bg-blue-50/60 dark:border-blue-900/40 dark:bg-blue-950/30 p-3.5 text-xs text-blue-900 dark:text-blue-200 font-mono">
          <div className="flex items-center gap-2 font-semibold">
            <History className="h-4 w-4 text-blue-600 dark:text-blue-400 shrink-0" />
            <span>No previous matching incidents found in project or cross-project memory bank.</span>
          </div>
          <p className="mt-1 text-[11px] text-blue-700 dark:text-blue-300 font-sans leading-relaxed">
            However, relevant troubleshooting guidance was matched from the curated general programming knowledge base:
          </p>
        </div>
      )}

      {/* Historical Incident Matches */}
      {incidentMatches.length > 0 && (
        <div className="space-y-3">
          {incidentMatches.map((match, idx) => {
            const isCrossProject = Boolean(match.isCrossProject);
            const sourceProject = match.sourceProject || (isCrossProject ? 'External Project' : currentProjectName || 'Current Project');

            return (
              <div
                key={match.id || `inc-match-${idx}`}
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
                        Cross-Project Precedent
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1.5 rounded-full bg-slate-100 dark:bg-slate-700/80 px-2.5 py-0.5 text-[11px] font-semibold text-slate-700 dark:text-slate-300 border border-slate-200 dark:border-slate-600">
                        Current Project Memory
                      </span>
                    )}
                    <span className="text-xs font-mono text-slate-700 dark:text-slate-300 font-semibold">
                      Source: {sourceProject}
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
                {match.sanitizedFixSummary && (
                  <div className="mt-3 text-xs">
                    <span className="text-slate-500 dark:text-slate-400 font-mono text-[11px] block mb-0.5 font-medium">
                      Sanitized Fix Outcome:
                    </span>
                    <p className="text-slate-800 dark:text-slate-200 font-sans leading-relaxed">
                      {match.sanitizedFixSummary}
                    </p>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* General Programming Knowledge Matches */}
      {generalKnowledgeMatches.length > 0 && (
        <div className="space-y-3 pt-2">
          {incidentMatches.length > 0 && (
            <div className="flex items-center gap-2 pt-2 border-t border-slate-100 dark:border-slate-800">
              <BookOpen className="h-3.5 w-3.5 text-emerald-600 dark:text-emerald-400" />
              <h4 className="text-xs font-semibold text-slate-800 dark:text-slate-200 font-mono">
                Curated Knowledge Base Guidance ({generalKnowledgeMatches.length})
              </h4>
            </div>
          )}

          {generalKnowledgeMatches.map((match, idx) => (
            <div
              key={match.id || `gk-match-${idx}`}
              className="rounded-xl border border-emerald-200/80 dark:border-emerald-900/50 bg-gradient-to-br from-emerald-50/40 to-white/90 dark:from-emerald-950/20 dark:to-slate-900/90 p-4 transition-all shadow-xs hover:border-emerald-300 dark:hover:border-emerald-700/60"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 dark:bg-emerald-950/60 px-2.5 py-0.5 text-[11px] font-bold text-emerald-700 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800/60 shadow-xs">
                    <BookOpen className="h-3 w-3" />
                    General Knowledge Base
                  </span>
                  <span className="text-xs font-mono text-slate-700 dark:text-slate-300 font-semibold">
                    Source: {match.sourceProject || 'Curated Knowledge Base'}
                  </span>
                </div>
                {match.similarityScore !== undefined && (
                  <span className="text-[10px] font-mono text-emerald-700 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-950/80 px-2 py-0.5 rounded-md border border-emerald-200/60 dark:border-emerald-800/60">
                    Match Score: {(match.similarityScore * 100).toFixed(0)}%
                  </span>
                )}
              </div>

              {match.title && (
                <div className="mt-2 text-xs font-semibold text-slate-900 dark:text-slate-100 font-mono">
                  {match.title}
                </div>
              )}

              {match.matchReason && (
                <div className="mt-2.5 text-xs text-slate-700 dark:text-slate-300">
                  <span className="text-slate-500 dark:text-slate-400 font-mono text-[11px] block mb-0.5 font-medium">
                    Guidance & Diagnostic Rationale:
                  </span>
                  <p className="font-mono text-[11px] text-emerald-950 dark:text-emerald-200 bg-slate-50/90 dark:bg-slate-900/70 p-2 rounded-lg border border-slate-200/70 dark:border-slate-800">
                    {match.matchReason}
                  </p>
                </div>
              )}

              {match.sanitizedFixSummary && (
                <div className="mt-2.5 text-xs">
                  <span className="text-slate-500 dark:text-slate-400 font-mono text-[11px] block mb-0.5 font-medium">
                    Recommended Resolution:
                  </span>
                  <p className="text-slate-800 dark:text-slate-200 font-sans leading-relaxed">
                    {match.sanitizedFixSummary}
                  </p>
                </div>
              )}

              {Array.isArray(match.suggestedResolutions) && match.suggestedResolutions.length > 0 && (
                <div className="mt-2 text-xs">
                  <span className="text-slate-500 dark:text-slate-400 font-mono text-[11px] block mb-0.5 font-medium">
                    Suggested Action Steps:
                  </span>
                  <ul className="list-disc list-inside space-y-1 text-slate-700 dark:text-slate-300 font-sans text-xs">
                    {match.suggestedResolutions.map((step, sIdx) => (
                      <li key={sIdx}>{step}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
