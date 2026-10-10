import React from 'react';
import { Sparkles, Eye, Lightbulb, CheckCircle2, ShieldAlert } from 'lucide-react';
import Badge from '../common/Badge';

export default function AIDiagnosisCard({ aiDiagnosis, errorType }) {
  if (!aiDiagnosis) {
    return (
      <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-5 text-center text-xs text-slate-400">
        <Sparkles className="h-5 w-5 text-slate-500 mx-auto mb-2" />
        <span>AI diagnosis pending or unavailable for this incident.</span>
      </div>
    );
  }

  const evidenceList = Array.isArray(aiDiagnosis.observedEvidence)
    ? aiDiagnosis.observedEvidence
    : typeof aiDiagnosis.observedEvidence === 'string'
    ? [aiDiagnosis.observedEvidence]
    : [];

  const hypothesesList = Array.isArray(aiDiagnosis.hypotheses)
    ? aiDiagnosis.hypotheses
    : typeof aiDiagnosis.hypotheses === 'string'
    ? [aiDiagnosis.hypotheses]
    : [];

  const recommendationsList = Array.isArray(aiDiagnosis.recommendations)
    ? aiDiagnosis.recommendations
    : typeof aiDiagnosis.recommendations === 'string'
    ? [aiDiagnosis.recommendations]
    : [];

  const { confidence } = aiDiagnosis;

  return (
    <div className="rounded-2xl border border-indigo-100 dark:border-indigo-900/60 bg-gradient-to-br from-indigo-50/70 via-purple-50/30 to-white/90 dark:from-slate-900/90 dark:via-indigo-950/40 dark:to-slate-900/90 backdrop-blur-md p-5 shadow-glass space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-indigo-100/80 dark:border-indigo-900/60 pb-3">
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-xl bg-indigo-100 dark:bg-indigo-950/80 text-indigo-600 dark:text-indigo-400 border border-indigo-200/80 dark:border-indigo-800/60 shadow-xs">
            <Sparkles className="h-4 w-4" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100 font-mono">
              AI Diagnostic Reasoning
            </h3>
            <span className="text-[10px] text-indigo-700 dark:text-indigo-300 font-mono font-medium">
              Structured Evidence-Hypothesis Breakdown
            </span>
          </div>
        </div>

        {confidence && (
          <Badge variant="purple" size="xs">
            Confidence: {confidence}
          </Badge>
        )}
      </div>

      {/* Two-Column Grid: Evidence vs Hypotheses */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Column 1: Observed Evidence (Concrete facts) */}
        <div className="rounded-xl border border-slate-200/90 dark:border-slate-800 bg-white/90 dark:bg-slate-800/80 p-4 shadow-xs">
          <div className="flex items-center gap-2 text-xs font-semibold text-sky-700 dark:text-sky-300 font-mono mb-2.5">
            <Eye className="h-4 w-4 text-sky-500 dark:text-sky-400" />
            <span>Observed Evidence (Facts)</span>
          </div>
          <ul className="space-y-2 text-xs text-slate-700 dark:text-slate-300">
            {evidenceList.map((ev, idx) => (
              <li key={idx} className="flex items-start gap-2">
                <span className="h-1.5 w-1.5 rounded-full bg-sky-500 dark:bg-sky-400 mt-1.5 shrink-0" />
                <span className="leading-relaxed">{ev}</span>
              </li>
            ))}
          </ul>
        </div>

        {/* Column 2: AI Hypotheses (Conjectures) */}
        <div className="rounded-xl border border-indigo-100 dark:border-indigo-900/50 bg-white/90 dark:bg-slate-800/80 p-4 shadow-xs">
          <div className="flex items-center gap-2 text-xs font-semibold text-indigo-700 dark:text-indigo-300 font-mono mb-2.5">
            <Lightbulb className="h-4 w-4 text-indigo-500 dark:text-indigo-400" />
            <span>AI-Generated Hypotheses</span>
          </div>
          <ul className="space-y-2 text-xs text-slate-700 dark:text-slate-300">
            {hypothesesList.map((hyp, idx) => (
              <li key={idx} className="flex items-start gap-2">
                <span className="h-1.5 w-1.5 rounded-full bg-indigo-500 dark:bg-indigo-400 mt-1.5 shrink-0" />
                <span className="leading-relaxed">{hyp}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>

      {/* Recommended Fix / Remediation Steps */}
      {recommendationsList.length > 0 && (
        <div className="rounded-xl border border-emerald-100 dark:border-emerald-900/50 bg-emerald-50/60 dark:bg-emerald-950/30 p-4 shadow-xs">
          <div className="flex items-center gap-2 text-xs font-semibold text-emerald-800 dark:text-emerald-300 font-mono mb-2.5">
            <CheckCircle2 className="h-4 w-4 text-emerald-600 dark:text-emerald-400" />
            <span>Actionable Remediation Guidance</span>
          </div>
          <ol className="space-y-2 text-xs text-slate-800 dark:text-slate-200 list-decimal list-inside">
            {recommendationsList.map((rec, idx) => (
              <li key={idx} className="leading-relaxed font-sans pl-1">
                <span className="font-mono text-emerald-900 dark:text-emerald-300 font-medium">{rec}</span>
              </li>
            ))}
          </ol>
        </div>
      )}

      {/* Epistemic disclaimer */}
      <div className="flex items-center gap-2 text-[11px] text-slate-500 dark:text-slate-400 italic pt-1">
        <ShieldAlert className="h-3.5 w-3.5 shrink-0 text-slate-400 dark:text-slate-500" />
        <span>
          AI recommendations are hypotheses based on current logs and historical precedents. They are not treated as verified fixes until verified with a passing command.
        </span>
      </div>
    </div>
  );
}
