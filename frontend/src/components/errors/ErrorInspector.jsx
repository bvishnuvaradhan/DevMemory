import React, { useState } from 'react';
import {
  AlertTriangle,
  Terminal,
  Clock,
  CheckCircle2,
  FileCode2,
  Activity,
  Layers,
  ChevronRight,
} from 'lucide-react';
import Badge from '../common/Badge';
import CodeSnippetViewer from './CodeSnippetViewer';
import StackTraceViewer from './StackTraceViewer';
import AIDiagnosisCard from './AIDiagnosisCard';
import HistoricalIncidentsCard from './HistoricalIncidentsCard';
import FixVerificationBadge from './FixVerificationBadge';
import EmptyState from '../common/EmptyState';

export default function ErrorInspector({ incidents = [], currentProjectName }) {
  const [selectedId, setSelectedId] = useState(
    incidents.length > 0 ? incidents[0].incidentId : null
  );

  if (!incidents || incidents.length === 0) {
    return (
      <EmptyState
        title="No Errors or Incidents Recorded"
        description="All command runs in this workspace have passed with exit code 0."
        icon={CheckCircle2}
      />
    );
  }

  const activeIncident =
    incidents.find((i) => i.incidentId === selectedId) || incidents[0];

  return (
    <div className="space-y-6">
      {/* Incident Switcher Pills (if multiple) */}
      {incidents.length > 1 && (
        <div className="flex items-center gap-2 overflow-x-auto pb-1">
          <span className="text-xs font-mono text-slate-500 dark:text-slate-400 uppercase shrink-0 font-medium">
            Select Incident:
          </span>
          {incidents.map((inc) => {
            const isSelected = inc.incidentId === activeIncident.incidentId;
            return (
              <button
                key={inc.incidentId}
                onClick={() => setSelectedId(inc.incidentId)}
                aria-pressed={isSelected}
                aria-label={`Select incident ${inc.incidentId}: ${inc.errorType}`}
                className={`flex items-center gap-2 rounded-xl px-3 py-1.5 text-xs font-mono transition-all cursor-pointer shrink-0 border ${
                  isSelected
                    ? 'bg-rose-50 dark:bg-rose-950/60 text-rose-700 dark:text-rose-300 border-rose-300 dark:border-rose-800/60 font-semibold shadow-xs'
                    : 'bg-white/80 dark:bg-slate-800/80 text-slate-600 dark:text-slate-300 border-slate-200 dark:border-slate-700 hover:text-slate-900 dark:hover:text-slate-100 hover:bg-white dark:hover:bg-slate-800 shadow-xs'
                }`}
              >
                <AlertTriangle className="h-3 w-3 text-rose-500 dark:text-rose-400" />
                <span>{inc.errorType}</span>
                <span className="text-[10px] text-slate-400 dark:text-slate-500">({inc.incidentId})</span>
              </button>
            );
          })}
        </div>
      )}

      {/* Main Incident Card */}
      <div className="rounded-2xl border border-white/80 bg-white/75 dark:border-slate-800/80 dark:bg-slate-900/75 backdrop-blur-md p-4 sm:p-6 space-y-6 shadow-glass">
        {/* Incident Summary Header */}
        <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-4 border-b border-slate-100 dark:border-slate-800 pb-6">
          <div className="space-y-2">
            <div className="flex flex-wrap items-center gap-2.5">
              <span className="flex items-center gap-1.5 rounded-full bg-rose-50 dark:bg-rose-950/60 px-2.5 py-1 text-xs font-mono font-bold text-rose-700 dark:text-rose-300 border border-rose-200 dark:border-rose-800/60 shadow-xs">
                <AlertTriangle className="h-3.5 w-3.5 text-rose-500 dark:text-rose-400" />
                {activeIncident.errorType}
              </span>
              <Badge variant="neutral" size="xs">
                Exit Code: {activeIncident.exitCode}
              </Badge>
              <span className="text-xs font-mono text-slate-400 dark:text-slate-500">
                Event: {activeIncident.eventId}
              </span>
            </div>

            <h2 className="text-base font-semibold text-slate-900 dark:text-slate-100 font-mono break-all leading-snug">
              {activeIncident.errorMessage}
            </h2>

            <div className="flex items-center gap-2 text-xs font-mono text-slate-500 dark:text-slate-400 pt-1">
              <Terminal className="h-3.5 w-3.5 text-slate-400 dark:text-slate-500" />
              <code className="bg-slate-100 dark:bg-slate-800 px-2 py-0.5 rounded-lg text-slate-800 dark:text-slate-200 border border-slate-200/80 dark:border-slate-700">
                {activeIncident.command}
              </code>
            </div>
          </div>

          {/* Verification Badge */}
          <div className="shrink-0 flex lg:flex-col items-center lg:items-end justify-between gap-2">
            <FixVerificationBadge
              status={activeIncident.fixOutcome?.status}
              recurrenceCount={activeIncident.fixOutcome?.recurrenceAfterFix}
            />
            {activeIncident.timestamp && (() => {
              const d = new Date(activeIncident.timestamp);
              const valid = !isNaN(d.getTime());
              return (
                <span className="text-[11px] font-mono text-slate-400 dark:text-slate-500 flex items-center gap-1">
                  <Clock className="h-3 w-3" />
                  {valid ? d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : String(activeIncident.timestamp)}
                </span>
              );
            })()}
          </div>
        </div>

        {/* 1. Source-Aware Code Snippet Viewer */}
        <CodeSnippetViewer
          sourceLocation={activeIncident.sourceLocation}
          errorType={activeIncident.errorType}
        />

        {/* 2. Full Stack Trace Viewer */}
        <StackTraceViewer stackTrace={activeIncident.stackTrace} />

        {/* 3. AI Diagnosis: Evidence vs Hypotheses */}
        <AIDiagnosisCard
          aiDiagnosis={activeIncident.aiDiagnosis}
          errorType={activeIncident.errorType}
        />

        {/* 4. Fix Outcome & Verification Section */}
        {activeIncident.fixOutcome && (
          <div className="rounded-2xl border border-emerald-100 dark:border-emerald-900/50 bg-emerald-50/40 dark:bg-emerald-950/30 p-5 space-y-3 shadow-xs">
            <div className="flex items-center justify-between border-b border-emerald-100 dark:border-emerald-900/60 pb-2.5">
              <span className="text-xs font-mono font-semibold text-emerald-900 dark:text-emerald-300 uppercase tracking-wider flex items-center gap-1.5">
                <CheckCircle2 className="h-4 w-4 text-emerald-600 dark:text-emerald-400" />
                Fix Verification Tracking
              </span>
              <FixVerificationBadge
                status={activeIncident.fixOutcome.status}
                recurrenceCount={activeIncident.fixOutcome.recurrenceAfterFix}
              />
            </div>

            <div className="space-y-2 text-xs">
              <div>
                <span className="text-slate-500 dark:text-slate-400 font-mono text-[11px] block font-medium">
                  Proposed Solution:
                </span>
                <p className="text-slate-800 dark:text-slate-200 font-sans mt-0.5 leading-relaxed">
                  {activeIncident.fixOutcome.proposedSolution}
                </p>
              </div>

              <div className="rounded-xl bg-white/90 dark:bg-slate-800/80 p-3 font-mono text-[11px] text-slate-700 dark:text-slate-300 border border-emerald-200/60 dark:border-emerald-800/60 shadow-xs">
                <span className="text-slate-500 dark:text-slate-400 block text-[10px] uppercase font-semibold mb-1">
                  Verification Execution:
                </span>
                <code className="text-emerald-800 dark:text-emerald-300 block break-all font-semibold">
                  {activeIncident.fixOutcome.verificationMethod}
                </code>
                {activeIncident.fixOutcome.testResult && (
                  <span className="text-slate-500 dark:text-slate-400 block mt-1.5 text-[10px]">
                    Result: {activeIncident.fixOutcome.testResult}
                  </span>
                )}
              </div>
            </div>
          </div>
        )}

        {/* 5. Historical Precedents & Cross-Project Memory */}
        <HistoricalIncidentsCard
          historicalMatches={activeIncident.historicalMatches}
          currentProjectName={currentProjectName}
        />
      </div>
    </div>
  );
}
