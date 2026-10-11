import React, { useState, useEffect } from 'react';
import {
  ShieldCheck,
  X,
  AlertTriangle,
  CheckCircle2,
  Terminal,
  FileText,
  Clock,
  Layers,
  ArrowRight,
  Info,
} from 'lucide-react';
import { verifyFix, createIncidentFix, fetchProjectRuns } from '../../api/devmemoryApi';

export default function VerifyFixModal({
  isOpen,
  onClose,
  fix,
  incident,
  projectId,
  onVerified,
}) {
  const [evidenceMode, setEvidenceMode] = useState('command'); // 'command' | 'event'
  const [command, setCommand] = useState('');
  const [details, setDetails] = useState('');
  const [exitCode, setExitCode] = useState(0);
  const [source, setSource] = useState('user_confirmation');
  const [availableRuns, setAvailableRuns] = useState([]);
  // New state declarations to fix ReferenceError and handle UI feedback
  const [errorMsg, setErrorMsg] = useState(null);
  const [successMsg, setSuccessMsg] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [eventId, setEventId] = useState('');

  // Load recent runs for the current project when using event evidence mode
  useEffect(() => {
    if (isOpen && evidenceMode === 'event' && projectId) {
      fetchProjectRuns(projectId).then((res) => {
        if (res && res.data) {
          setAvailableRuns(res.data);
        }
      });
    }
    // Clear runs when switching away from event mode
    if (evidenceMode !== 'event') {
      setAvailableRuns([]);
    }
  }, [isOpen, evidenceMode, projectId]);

  // Pre-fill fields from fix or incident recommendations when modal opens
  useEffect(() => {
    if (isOpen) {
      setErrorMsg(null);
      setSuccessMsg(null);
      setSubmitting(false);

      const defaultCmd =
        fix?.verificationMethod && fix.verificationMethod !== 'Manual Verification' && fix.verificationMethod !== 'devmemory verify'
          ? fix.verificationMethod
          : incident?.command
          ? incident.command
          : '';
      setCommand(defaultCmd);

      const defaultDetails =
        fix?.testResult && fix.testResult !== 'Verified successfully' && fix.testResult !== 'Pending verification'
          ? fix.testResult
          : '';
      setDetails(defaultDetails);

      setExitCode(0);
      setSource('user_confirmation');
      setEventId('');
      setEvidenceMode('command');
    }
  }, [isOpen, fix, incident]);

  if (!isOpen) return null;

  const fixId = fix?.id || fix?.fixId || fix?.fix_id;
  const targetProjectId = projectId || fix?.projectId || incident?.projectId;
  const isRecurring =
    Boolean(fix?.status === 'RECURRING' || (fix?.recurrenceCountAfterFix || 0) > 0 || (fix?.recurrenceAfterFix || 0) > 0);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setErrorMsg(null);
    setSuccessMsg(null);

    if (isRecurring) {
      setErrorMsg('This fix has recurred after initial deployment and is invalidated per accuracy guarantees. It cannot be verified.');
      return;
    }

    // Client-side verification evidence check matching backend contract
    if (evidenceMode === 'command') {
      const trimmedCmd = command.trim();
      const trimmedDetails = details.trim();
      if (exitCode === 0 && !trimmedCmd && !trimmedDetails) {
        setErrorMsg('Verification evidence required: Provide the executed command or test outcome details per DevMemory verification rules.');
        return;
      }
    } else if (evidenceMode === 'event') {
      if (!eventId.trim()) {
        setErrorMsg('Please select or specify a valid command run event_id.');
        return;
      }
    }

    setSubmitting(true);

    try {
      let activeFixId = fixId;

      // If no fix_id exists yet (e.g. verifying an incident before a fix document is created),
      // first register the proposed fix outcome in the backend
      if (!activeFixId && incident?.incidentId) {
        const proposedDescription =
          fix?.solutionSummary ||
          fix?.description ||
          incident?.aiDiagnosis?.recommendations?.[0] ||
          incident?.aiDiagnosis?.summary ||
          `Proposed fix for ${incident.errorType}`;

        const createRes = await createIncidentFix(
          incident.incidentId,
          {
            description: proposedDescription,
            diagnosis_id: incident?.aiDiagnosis?.diagnosisId || undefined,
          },
          targetProjectId
        );

        if (!createRes.success || !createRes.data) {
          setErrorMsg(createRes.error || 'Failed to register fix proposal before verification.');
          setSubmitting(false);
          return;
        }

        activeFixId = createRes.data.id || createRes.data.fixId;
      }

      if (!activeFixId) {
        setErrorMsg('Cannot determine target fix ID for verification.');
        setSubmitting(false);
        return;
      }

      // Build verification payload
      const payload = {
        exit_code: Number(exitCode),
        source: evidenceMode === 'event' ? 'devmemory_runner' : source,
      };

      if (evidenceMode === 'event') {
        payload.event_id = eventId.trim();
      } else {
        if (command.trim()) payload.command = command.trim();
        if (details.trim()) payload.details = details.trim();
      }

      const verifyRes = await verifyFix(activeFixId, payload, targetProjectId);

      if (!verifyRes.success || !verifyRes.data) {
        setErrorMsg(verifyRes.error || 'Fix verification was rejected by backend.');
        setSubmitting(false);
        return;
      }

      const updatedFix = verifyRes.data;
      setSuccessMsg(`Fix ${activeFixId} successfully marked as ${updatedFix.status.toUpperCase()} in MongoDB!`);

      setTimeout(() => {
        if (onVerified) {
          onVerified(updatedFix);
        }
        onClose();
      }, 700);
    } catch (err) {
      setErrorMsg(err.message || 'An unexpected error occurred during verification.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="verify-modal-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 dark:bg-black/70 p-3 sm:p-4 backdrop-blur-xs overflow-y-auto animate-in fade-in duration-200"
    >
      <div className="relative w-full max-w-xl rounded-2xl border border-white/90 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-2xl p-5 sm:p-6 space-y-5 my-8">
        {/* Header */}
        <div className="flex items-start justify-between border-b border-slate-100 dark:border-slate-800 pb-4">
          <div className="flex items-center gap-2.5">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-50 dark:bg-emerald-950/60 text-emerald-600 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-800/60 shadow-xs">
              <ShieldCheck className="h-5 w-5" />
            </div>
            <div>
              <h2 id="verify-modal-title" className="text-base font-bold text-slate-900 dark:text-slate-100 font-mono">
                Verify Fix Outcome
              </h2>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                Submit authenticated evidence to verify and persist fix resolution in DevMemory.
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            aria-label="Close verification modal"
            className="rounded-lg p-1.5 text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Recurrence Warning */}
        {isRecurring && (
          <div className="rounded-xl border border-rose-200 dark:border-rose-900/60 bg-rose-50/90 dark:bg-rose-950/50 p-3.5 text-xs text-rose-800 dark:text-rose-300 flex items-start gap-2.5">
            <AlertTriangle className="h-4 w-4 shrink-0 text-rose-600 dark:text-rose-400 mt-0.5" />
            <div>
              <strong className="font-bold">Fix Recurrence Invalidation: </strong>
              This issue recurred after fix deployment. DevMemory integrity rules forbid verifying invalidated fixes.
            </div>
          </div>
        )}

        {/* Target Solution Summary */}
        <div className="rounded-xl border border-slate-200/80 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-800/50 p-3.5 space-y-1.5 text-xs font-mono">
          <div className="flex items-center justify-between text-[11px] text-slate-500 dark:text-slate-400">
            <span>Target: <strong>{fixId || 'Proposed Solution'}</strong></span>
            <span>Project: <strong>{targetProjectId || 'General'}</strong></span>
          </div>
          <p className="text-slate-800 dark:text-slate-200 line-clamp-3 font-sans text-xs leading-relaxed">
            {fix?.solutionSummary ||
              fix?.description ||
              incident?.aiDiagnosis?.recommendations?.[0] ||
              incident?.aiDiagnosis?.summary ||
              'Proposed resolution for reported incident.'}
          </p>
        </div>

        {/* Error / Success Notifications */}
        {errorMsg && (
          <div className="rounded-xl border border-rose-200 dark:border-rose-900/60 bg-rose-50/90 dark:bg-rose-950/60 p-3 text-xs text-rose-700 dark:text-rose-300 font-mono flex items-start gap-2">
            <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
            <span className="break-all">{errorMsg}</span>
          </div>
        )}

        {successMsg && (
          <div className="rounded-xl border border-emerald-200 dark:border-emerald-900/60 bg-emerald-50/90 dark:bg-emerald-950/60 p-3 text-xs text-emerald-700 dark:text-emerald-300 font-mono flex items-center gap-2">
            <CheckCircle2 className="h-4 w-4 shrink-0" />
            <span>{successMsg}</span>
          </div>
        )}

        {/* Form */}
        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Mode Switcher */}
          <div>
            <label className="block text-xs font-mono font-medium text-slate-700 dark:text-slate-300 mb-1.5">
              Verification Evidence Type
            </label>
            <div className="grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={() => setEvidenceMode('command')}
                className={`flex items-center justify-center gap-2 py-2 px-3 rounded-xl text-xs font-mono font-medium border transition-colors cursor-pointer ${
                  evidenceMode === 'command'
                    ? 'bg-emerald-50/80 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-300 border-emerald-300 dark:border-emerald-800/60 font-semibold'
                    : 'bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-400 border-slate-200 dark:border-slate-700 hover:bg-slate-50'
                }`}
              >
                <Terminal className="h-3.5 w-3.5" />
                <span>Command Execution / Attestation</span>
              </button>
              <button
                type="button"
                onClick={() => setEvidenceMode('event')}
                className={`flex items-center justify-center gap-2 py-2 px-3 rounded-xl text-xs font-mono font-medium border transition-colors cursor-pointer ${
                  evidenceMode === 'event'
                    ? 'bg-emerald-50/80 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-300 border-emerald-300 dark:border-emerald-800/60 font-semibold'
                    : 'bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-400 border-slate-200 dark:border-slate-700 hover:bg-slate-50'
                }`}
              >
                <Layers className="h-3.5 w-3.5" />
                <span>Recorded Command Run (event_id)</span>
              </button>
            </div>
          </div>

          {evidenceMode === 'command' ? (
            <>
              {/* Verification Command */}
              <div>
                <label htmlFor="verify-command-input" className="block text-xs font-mono font-medium text-slate-700 dark:text-slate-300 mb-1">
                  Verification Command Executed
                </label>
                <div className="relative">
                  <input
                    id="verify-command-input"
                    type="text"
                    value={command}
                    onChange={(e) => setCommand(e.target.value)}
                    placeholder="e.g. devmemory run -- pytest tests/ -k test_auth"
                    className="w-full rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 py-2 pl-3 pr-3 text-xs font-mono text-slate-800 dark:text-slate-200 shadow-xs focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
                  />
                </div>
              </div>

              {/* Execution Details / Test Results */}
              <div>
                <label htmlFor="verify-details-input" className="block text-xs font-mono font-medium text-slate-700 dark:text-slate-300 mb-1">
                  Test Results & Evidence Details <span className="text-slate-400 text-[11px] font-normal">(Required if command is omitted)</span>
                </label>
                <textarea
                  id="verify-details-input"
                  rows={3}
                  value={details}
                  onChange={(e) => setDetails(e.target.value)}
                  placeholder="e.g. 5 passed in 0.42s; verified fix handles empty lists without raising IndexError."
                  className="w-full rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-3 text-xs font-mono text-slate-800 dark:text-slate-200 shadow-xs focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
                />
              </div>

              {/* Exit Code & Attestation Source */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label htmlFor="verify-exit-code-select" className="block text-xs font-mono font-medium text-slate-700 dark:text-slate-300 mb-1">
                    Outcome Status
                  </label>
                  <select
                    id="verify-exit-code-select"
                    value={exitCode}
                    onChange={(e) => setExitCode(Number(e.target.value))}
                    className="w-full rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 py-2 px-3 text-xs font-mono text-slate-800 dark:text-slate-200 shadow-xs focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
                  >
                    <option value={0}>✅ Success / Passing (Exit Code 0)</option>
                    <option value={1}>❌ Failure / Failed (Exit Code 1)</option>
                  </select>
                </div>

                <div>
                  <label htmlFor="verify-source-select" className="block text-xs font-mono font-medium text-slate-700 dark:text-slate-300 mb-1">
                    Evidence Source
                  </label>
                  <select
                    id="verify-source-select"
                    value={source}
                    onChange={(e) => setSource(e.target.value)}
                    className="w-full rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 py-2 px-3 text-xs font-mono text-slate-800 dark:text-slate-200 shadow-xs focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
                  >
                    <option value="user_confirmation">Developer Manual Confirmation</option>
                    <option value="automated_command">Automated CI/Command Run</option>
                    <option value="test_runner">Local Test Runner Suite</option>
                  </select>
                </div>
              </div>
            </>
          ) : (
            /* Mode B: Event ID Mode */
            <div className="space-y-3">
              <div>
                <label htmlFor="verify-event-id-input" className="block text-xs font-mono font-medium text-slate-700 dark:text-slate-300 mb-1">
                  Recorded Command Run Event ID
                </label>
                <input
                  id="verify-event-id-input"
                  type="text"
                  value={eventId}
                  onChange={(e) => setEventId(e.target.value)}
                  placeholder="e.g. evt_run_01"
                  className="w-full rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 py-2 px-3 text-xs font-mono text-slate-800 dark:text-slate-200 shadow-xs focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
                />
              </div>

              {availableRuns.length > 0 && (
                <div>
                  <span className="block text-[11px] font-mono text-slate-500 dark:text-slate-400 mb-1">
                    Select from recent workspace runs:
                  </span>
                  <div className="max-h-32 overflow-y-auto space-y-1 pr-1">
                    {availableRuns.map((r) => (
                      <button
                        key={r.eventId || r.id}
                        type="button"
                        onClick={() => setEventId(r.eventId || r.id)}
                        className={`w-full text-left p-2 rounded-lg text-xs font-mono flex items-center justify-between border transition-colors cursor-pointer ${
                          eventId === (r.eventId || r.id)
                            ? 'bg-emerald-50 dark:bg-emerald-950/60 border-emerald-300 dark:border-emerald-800 text-emerald-800 dark:text-emerald-300'
                            : 'bg-white dark:bg-slate-800 border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-300 hover:bg-slate-50'
                        }`}
                      >
                        <span className="truncate max-w-[280px]">{r.command || r.eventId}</span>
                        <span className={`text-[10px] px-1.5 py-0.5 rounded font-bold ${r.exitCode === 0 ? 'bg-emerald-100 text-emerald-700' : 'bg-rose-100 text-rose-700'}`}>
                          code {r.exitCode ?? 0}
                        </span>
                      </button>
                    ))}
                  </div>
                </div>
              )}

              <div className="rounded-xl border border-sky-200 dark:border-sky-900/60 bg-sky-50/70 dark:bg-sky-950/30 p-3 text-xs text-sky-800 dark:text-sky-300 flex items-start gap-2">
                <Info className="h-4 w-4 shrink-0 mt-0.5" />
                <span>
                  The backend resolves the recorded run directly from the database and uses its actual exit code to guarantee authenticity.
                </span>
              </div>
            </div>
          )}

          {/* Action Buttons */}
          <div className="flex items-center justify-end gap-3 pt-3 border-t border-slate-100 dark:border-slate-800">
            <button
              type="button"
              onClick={onClose}
              disabled={submitting}
              className="rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-4 py-2 text-xs font-mono font-medium text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700 transition-colors cursor-pointer"
            >
              Cancel
            </button>

            <button
              type="submit"
              disabled={submitting || isRecurring}
              className="inline-flex items-center gap-1.5 rounded-xl bg-emerald-600 hover:bg-emerald-700 disabled:bg-slate-300 dark:disabled:bg-slate-700 text-white px-4 py-2 text-xs font-mono font-bold shadow-xs transition-colors cursor-pointer disabled:cursor-not-allowed"
            >
              <ShieldCheck className="h-4 w-4" />
              <span>{submitting ? 'Persisting to Backend...' : exitCode === 0 ? 'Mark as Verified' : 'Record Verification Failure'}</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
