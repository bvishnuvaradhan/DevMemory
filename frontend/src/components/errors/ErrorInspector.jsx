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
          <span className="text-xs font-mono text-slate-500 uppercase shrink-0">
            Select Incident:
          </span>
          {incidents.map((inc) => {
            const isSelected = inc.incidentId === activeIncident.incidentId;
            return (
              <button
                key={inc.incidentId}
                onClick={() => setSelectedId(inc.incidentId)}
                className={`flex items-center gap-2 rounded-lg px-3 py-1.5 text-xs font-mono transition-colors cursor-pointer shrink-0 border ${
                  isSelected
                    ? 'bg-rose-500/20 text-rose-300 border-rose-500/40 font-semibold'
                    : 'bg-slate-900/60 text-slate-400 border-slate-800 hover:text-white hover:bg-slate-800'
                }`}
              >
                <AlertTriangle className="h-3 w-3 text-rose-400" />
                <span>{inc.errorType}</span>
                <span className="text-[10px] text-slate-500">({inc.incidentId})</span>
              </button>
            );
          })}
        </div>
      )}

      {/* Main Incident Card */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-6 space-y-6 shadow-sm">
        {/* Incident Summary Header */}
        <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-4 border-b border-slate-800/80 pb-6">
          <div className="space-y-2">
            <div className="flex flex-wrap items-center gap-2.5">
              <span className="flex items-center gap-1.5 rounded bg-rose-500/10 px-2.5 py-1 text-xs font-mono font-bold text-rose-400 border border-rose-500/30">
                <AlertTriangle className="h-3.5 w-3.5" />
                {activeIncident.errorType}
              </span>
              <Badge variant="neutral" size="xs">
                Exit Code: {activeIncident.exitCode}
              </Badge>
              <span className="text-xs font-mono text-slate-500">
                Event: {activeIncident.eventId}
              </span>
            </div>

            <h2 className="text-base font-semibold text-white font-mono break-all leading-snug">
              {activeIncident.errorMessage}
            </h2>

            <div className="flex items-center gap-2 text-xs font-mono text-slate-400 pt-1">
              <Terminal className="h-3.5 w-3.5 text-slate-500" />
              <code className="bg-black/50 px-2 py-0.5 rounded text-slate-300 border border-slate-800/80">
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
                <span className="text-[11px] font-mono text-slate-500 flex items-center gap-1">
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
          <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-5 space-y-3">
            <div className="flex items-center justify-between border-b border-slate-800/80 pb-2.5">
              <span className="text-xs font-mono font-semibold text-white uppercase tracking-wider flex items-center gap-1.5">
                <CheckCircle2 className="h-4 w-4 text-emerald-400" />
                Fix Verification Tracking
              </span>
              <FixVerificationBadge
                status={activeIncident.fixOutcome.status}
                recurrenceCount={activeIncident.fixOutcome.recurrenceAfterFix}
              />
            </div>

            <div className="space-y-2 text-xs">
              <div>
                <span className="text-slate-500 font-mono text-[11px] block">
                  Proposed Solution:
                </span>
                <p className="text-slate-200 font-sans mt-0.5">
                  {activeIncident.fixOutcome.proposedSolution}
                </p>
              </div>

              <div className="rounded bg-slate-900/80 p-2.5 font-mono text-[11px] text-slate-300 border border-slate-800/60">
                <span className="text-slate-500 block text-[10px] uppercase mb-1">
                  Verification Execution:
                </span>
                <code className="text-emerald-300 block break-all">
                  {activeIncident.fixOutcome.verificationMethod}
                </code>
                {activeIncident.fixOutcome.testResult && (
                  <span className="text-slate-400 block mt-1.5 text-[10px]">
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
