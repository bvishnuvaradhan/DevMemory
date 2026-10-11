import React from 'react';
import { Sparkles, Eye, Lightbulb, CheckCircle2, ShieldAlert, Zap, Clock, AlertCircle } from 'lucide-react';
import Badge from '../common/Badge';

export default function AIDiagnosisCard({ aiDiagnosis, errorType, diagnosisStatus, incident }) {
  if (!aiDiagnosis) {
    const isPending = diagnosisStatus === 'pending';
    const isFailed = diagnosisStatus === 'failed';

    return (
      <div className="rounded-2xl border border-white/80 bg-white/75 dark:border-slate-800/80 dark:bg-slate-900/75 backdrop-blur-md p-6 text-center shadow-glass space-y-2">
        {isPending ? (
          <>
            <Clock className="h-6 w-6 text-amber-500 dark:text-amber-400 mx-auto animate-pulse" />
            <h4 className="text-xs font-mono font-semibold text-slate-800 dark:text-slate-200">
              AI Diagnosis Pending
            </h4>
            <p className="text-[11px] text-slate-500 dark:text-slate-400 font-sans max-w-sm mx-auto">
              Incident logs have been captured. AI diagnostic reasoning will generate on background worker execution.
            </p>
          </>
        ) : isFailed ? (
          <>
            <AlertCircle className="h-6 w-6 text-rose-500 dark:text-rose-400 mx-auto" />
            <h4 className="text-xs font-mono font-semibold text-rose-700 dark:text-rose-300">
              AI Diagnosis Unavailable
            </h4>
            <p className="text-[11px] text-slate-500 dark:text-slate-400 font-sans max-w-sm mx-auto">
              Inference was offline or unavailable during command execution.
            </p>
          </>
        ) : (
          <>
            <Sparkles className="h-6 w-6 text-slate-400 dark:text-slate-500 mx-auto" />
            <h4 className="text-xs font-mono font-semibold text-slate-700 dark:text-slate-300">
              No Diagnosis Recorded
            </h4>
            <p className="text-[11px] text-slate-500 dark:text-slate-400 font-sans max-w-sm mx-auto">
              Diagnosis has not been triggered or requested for this incident.
            </p>
          </>
        )}
      </div>
    );
  }

  const evidenceList = Array.isArray(aiDiagnosis.observedEvidence)
    ? aiDiagnosis.observedEvidence
    : typeof aiDiagnosis.observedEvidence === 'string'
    ? [aiDiagnosis.observedEvidence]
    : [];

  const rawHypotheses = aiDiagnosis.hypotheses ?? [];
  const hypothesesList = Array.isArray(rawHypotheses)
    ? rawHypotheses.map((h) =>
        typeof h === 'object' && h !== null ? h.cause || h.details || JSON.stringify(h) : String(h)
      )
    : typeof rawHypotheses === 'string'
    ? [rawHypotheses]
    : [];

  const rawRecs = aiDiagnosis.recommendations ?? [];
  const recommendationsList = Array.isArray(rawRecs)
    ? rawRecs
    : typeof rawRecs === 'string'
    ? [rawRecs]
    : [];

  const { confidence, llmSkipped, decisionReason, source, summary, isVerifiedFix } = aiDiagnosis;
  const formattedConfidence =
    confidence !== undefined && confidence !== null
      ? typeof confidence === 'number' && confidence <= 1
        ? `${Math.round(confidence * 100)}%`
        : String(confidence)
      : '90%';

  return (
    <div className="rounded-2xl border border-indigo-100 dark:border-indigo-900/60 bg-gradient-to-br from-indigo-50/70 via-purple-50/30 to-white/90 dark:from-slate-900/90 dark:via-indigo-950/40 dark:to-slate-900/90 backdrop-blur-md p-5 shadow-glass space-y-5">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between border-b border-indigo-100/80 dark:border-indigo-900/60 pb-3 gap-3">
        <div className="flex items-center gap-2.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-indigo-100 dark:bg-indigo-950/80 text-indigo-600 dark:text-indigo-400 border border-indigo-200/80 dark:border-indigo-800/60 shadow-xs shrink-0">
            {llmSkipped ? <Zap className="h-4 w-4 text-emerald-600 dark:text-emerald-400" /> : <Sparkles className="h-4 w-4" />}
          </div>
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100 font-mono">
                {llmSkipped
                  ? isVerifiedFix
                    ? 'Verified Fix Reused'
                    : 'Memory Bank Diagnosis'
                  : 'AI Diagnostic Reasoning'}
              </h3>
              {llmSkipped && (
                <Badge variant="success" size="xs">
                  Inference Bypassed (Decision Gate)
                </Badge>
              )}
            </div>
            <div className="flex items-center gap-2 mt-0.5 text-[10px] font-mono text-slate-500 dark:text-slate-400">
              <span>Source: {source || 'AI Diagnosis Engine'}</span>
              {decisionReason && (
                <>
                  <span>•</span>
                  <span className="text-emerald-700 dark:text-emerald-400 font-medium">
                    Gate: {decisionReason.replace(/_/g, ' ')}
                  </span>
                </>
              )}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2 self-start sm:self-auto">
          {confidence && (
            <Badge variant="purple" size="xs">
              Confidence: {formattedConfidence}
            </Badge>
          )}
        </div>
      </div>

      {/* Summary Box */}
      {summary && (
        <div className="rounded-xl border border-indigo-200/70 dark:border-indigo-800/50 bg-white/90 dark:bg-slate-850 p-3.5 shadow-xs">
          <span className="text-[10px] uppercase font-mono text-indigo-700 dark:text-indigo-400 font-bold block mb-1">
            Diagnosis Summary
          </span>
          <p className="text-xs text-slate-800 dark:text-slate-200 font-mono leading-relaxed">
            {summary}
          </p>
        </div>
      )}

      {/* Two-Column Grid: Evidence vs Hypotheses */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Column 1: Observed Evidence (Concrete facts) */}
        <div className="rounded-xl border border-slate-200/90 dark:border-slate-800 bg-white/90 dark:bg-slate-800/80 p-4 shadow-xs">
          <div className="flex items-center gap-2 text-xs font-semibold text-sky-700 dark:text-sky-300 font-mono mb-2.5">
            <Eye className="h-4 w-4 text-sky-500 dark:text-sky-400" />
            <span>Observed Evidence (Facts)</span>
          </div>
          <ul className="space-y-2 text-xs text-slate-700 dark:text-slate-300">
            {evidenceList.length > 0 ? (
              evidenceList.map((ev, idx) => (
                <li key={idx} className="flex items-start gap-2">
                  <span className="h-1.5 w-1.5 rounded-full bg-sky-500 dark:bg-sky-400 mt-1.5 shrink-0" />
                  <span className="leading-relaxed">{ev}</span>
                </li>
              ))
            ) : (
              <li className="text-slate-400 dark:text-slate-500 italic text-[11px]">
                No structured evidence items recorded.
              </li>
            )}
          </ul>
        </div>

        {/* Column 2: AI Hypotheses (Conjectures) */}
        <div className="rounded-xl border border-indigo-100 dark:border-indigo-900/50 bg-white/90 dark:bg-slate-800/80 p-4 shadow-xs">
          <div className="flex items-center gap-2 text-xs font-semibold text-indigo-700 dark:text-indigo-300 font-mono mb-2.5">
            <Lightbulb className="h-4 w-4 text-indigo-500 dark:text-indigo-400" />
            <span>AI-Generated Hypotheses</span>
          </div>
          <ul className="space-y-2 text-xs text-slate-700 dark:text-slate-300">
            {hypothesesList.length > 0 ? (
              hypothesesList.map((hyp, idx) => (
                <li key={idx} className="flex items-start gap-2">
                  <span className="h-1.5 w-1.5 rounded-full bg-indigo-500 dark:bg-indigo-400 mt-1.5 shrink-0" />
                  <span className="leading-relaxed">{hyp}</span>
                </li>
              ))
            ) : (
              <li className="text-slate-400 dark:text-slate-500 italic text-[11px]">
                No separate hypotheses generated.
              </li>
            )}
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
