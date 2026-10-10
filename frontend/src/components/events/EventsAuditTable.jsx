import React, { useState, useEffect, useMemo } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  History,
  Search,
  Filter,
  Terminal,
  AlertTriangle,
  Sparkles,
  ShieldCheck,
  TrendingUp,
  Clock,
  ArrowUpDown,
  ExternalLink,
  FileCode2,
  Database,
  CheckCircle2,
  XCircle,
  HelpCircle,
  Layers,
} from 'lucide-react';
import Badge from '../common/Badge';
import EmptyState from '../common/EmptyState';

const EVENT_TYPE_OPTIONS = [
  { value: 'ALL', label: 'All Event Types' },
  { value: 'COMMAND_RUN', label: 'Command Run' },
  { value: 'ERROR_INCIDENT', label: 'Error Incident' },
  { value: 'AI_DIAGNOSIS', label: 'AI Diagnosis' },
  { value: 'FIX_VERIFICATION', label: 'Fix Verification' },
  { value: 'PERFORMANCE_REGRESSION', label: 'Performance Regression' },
];

const STATUS_OPTIONS = [
  { value: 'ALL', label: 'All Statuses' },
  { value: 'SUCCESS', label: 'Success' },
  { value: 'FAILED', label: 'Failed' },
  { value: 'VERIFIED', label: 'Verified' },
  { value: 'FLAGGED', label: 'Flagged' },
  { value: 'RESOLVED', label: 'Resolved' },
  { value: 'RECURRING', label: 'Recurring' },
];

function getEventTypeBadge(type) {
  const norm = (type || '').toUpperCase();
  switch (norm) {
    case 'COMMAND_RUN':
      return (
        <span className="inline-flex items-center gap-1.5 rounded-full bg-slate-100 px-2.5 py-0.5 text-[11px] font-mono text-slate-700 border border-slate-200 font-medium">
          <Terminal className="h-3 w-3 text-sky-500" />
          <span>Command</span>
        </span>
      );
    case 'ERROR_INCIDENT':
      return (
        <span className="inline-flex items-center gap-1.5 rounded-full bg-rose-50 px-2.5 py-0.5 text-[11px] font-mono text-rose-700 border border-rose-200 font-medium">
          <AlertTriangle className="h-3 w-3 text-rose-500" />
          <span>Incident</span>
        </span>
      );
    case 'AI_DIAGNOSIS':
      return (
        <span className="inline-flex items-center gap-1.5 rounded-full bg-indigo-50 px-2.5 py-0.5 text-[11px] font-mono text-indigo-700 border border-indigo-200 font-medium">
          <Sparkles className="h-3 w-3 text-indigo-500" />
          <span>AI Diagnosis</span>
        </span>
      );
    case 'FIX_VERIFICATION':
      return (
        <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-2.5 py-0.5 text-[11px] font-mono text-emerald-700 border border-emerald-200 font-medium">
          <ShieldCheck className="h-3 w-3 text-emerald-600" />
          <span>Fix Verification</span>
        </span>
      );
    case 'PERFORMANCE_REGRESSION':
      return (
        <span className="inline-flex items-center gap-1.5 rounded-full bg-amber-50 px-2.5 py-0.5 text-[11px] font-mono text-amber-800 border border-amber-200 font-medium">
          <TrendingUp className="h-3 w-3 text-amber-600" />
          <span>Regression</span>
        </span>
      );
    default:
      return (
        <span className="inline-flex items-center gap-1.5 rounded-full bg-slate-100 px-2.5 py-0.5 text-[11px] font-mono text-slate-600 border border-slate-200">
          <HelpCircle className="h-3 w-3 text-slate-400" />
          <span>{type || 'Event'}</span>
        </span>
      );
  }
}

function getStatusBadge(status) {
  const norm = (status || '').toUpperCase();
  if (norm === 'SUCCESS' || norm === 'VERIFIED' || norm === 'RESOLVED') {
    return (
      <Badge variant="success" size="xs" dot>
        {status}
      </Badge>
    );
  }
  if (norm === 'FAILED') {
    return (
      <Badge variant="danger" size="xs" dot>
        {status}
      </Badge>
    );
  }
  if (norm === 'FLAGGED' || norm === 'RECURRING') {
    return (
      <Badge variant="warning" size="xs" dot>
        {status}
      </Badge>
    );
  }
  return (
    <Badge variant="neutral" size="xs">
      {status || 'UNKNOWN'}
    </Badge>
  );
}

function formatSafeTimestamp(ts) {
  if (!ts) return '—';
  const d = new Date(ts);
  if (isNaN(d.getTime())) return String(ts);
  return d.toLocaleString([], {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

export default function EventsAuditTable({
  events = [],
  projects = [],
  scopedProjectId = null,
  isMock = true,
}) {
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedType, setSelectedType] = useState('ALL');
  const [selectedStatus, setSelectedStatus] = useState('ALL');
  const [selectedProject, setSelectedProject] = useState(scopedProjectId || 'ALL');
  const [sortOrder, setSortOrder] = useState('NEWEST'); // 'NEWEST' | 'OLDEST'
  const [selectedEventModal, setSelectedEventModal] = useState(null);
  const navigate = useNavigate();

  // Escape key closes details modal
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape' && selectedEventModal) {
        setSelectedEventModal(null);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [selectedEventModal]);

  // Filter and sort events
  const filteredEvents = useMemo(() => {
    let result = Array.isArray(events) ? [...events] : [];

    // Filter by project
    if (selectedProject !== 'ALL') {
      result = result.filter(
        (e) => (e.projectId || e.project_id) === selectedProject
      );
    }

    // Filter by event type
    if (selectedType !== 'ALL') {
      result = result.filter(
        (e) => (e.eventType || '').toUpperCase() === selectedType
      );
    }

    // Filter by status
    if (selectedStatus !== 'ALL') {
      result = result.filter(
        (e) => (e.status || '').toUpperCase() === selectedStatus
      );
    }

    // Search query
    if (searchTerm.trim()) {
      const q = searchTerm.toLowerCase().trim();
      result = result.filter((e) => {
        const idMatch = (e.eventId || '').toLowerCase().includes(q);
        const cmdMatch = (e.relatedCommand || '').toLowerCase().includes(q);
        const incMatch = (e.relatedIncidentId || '').toLowerCase().includes(q);
        const projMatch = (e.projectName || e.projectId || '')
          .toLowerCase()
          .includes(q);
        const summaryMatch = (e.summary || '').toLowerCase().includes(q);
        const detailsMatch = (e.details || '').toLowerCase().includes(q);
        const fileMatch = (e.sourceLocation?.file || '').toLowerCase().includes(q);
        return (
          idMatch ||
          cmdMatch ||
          incMatch ||
          projMatch ||
          summaryMatch ||
          detailsMatch ||
          fileMatch
        );
      });
    }

    // Sort
    result.sort((a, b) => {
      const dateA = new Date(a.timestamp || 0).getTime() || 0;
      const dateB = new Date(b.timestamp || 0).getTime() || 0;
      return sortOrder === 'NEWEST' ? dateB - dateA : dateA - dateB;
    });

    return result;
  }, [events, selectedProject, selectedType, selectedStatus, searchTerm, sortOrder]);

  return (
    <div className="space-y-4">
      {/* Demonstration Banner */}
      {isMock && (
        <div className="rounded-2xl border border-amber-200 bg-amber-50/80 px-4 py-2.5 text-xs text-amber-900 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 font-mono shadow-xs">
          <div className="flex items-center gap-2">
            <Database className="h-4 w-4 text-amber-600 shrink-0" />
            <span>
              <strong>Demonstration Event Stream:</strong> Audited telemetry records shown below represent simulated command lifecycles.
            </span>
          </div>
          <span className="rounded-full bg-amber-100 px-2.5 py-0.5 text-[10px] text-amber-900 border border-amber-300 uppercase shrink-0 font-semibold">
            MOCK AUDIT LOG
          </span>
        </div>
      )}

      {/* Filter and Search Bar */}
      <div className="rounded-2xl border border-white/80 bg-white/75 backdrop-blur-md p-4 space-y-3 shadow-glass">
        <div className="flex flex-col lg:flex-row gap-3">
          {/* Search Box */}
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-400" />
            <input
              type="text"
              aria-label="Search audit events"
              placeholder="Search by Event ID, command, incident ID, project, or file..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full rounded-xl border border-slate-200 bg-white py-2 pl-9 pr-3 text-xs font-mono text-slate-800 placeholder-slate-400 focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500 shadow-xs"
            />
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {/* Type Filter */}
            <select
              value={selectedType}
              onChange={(e) => setSelectedType(e.target.value)}
              aria-label="Filter events by type"
              className="w-full sm:w-auto rounded-xl border border-slate-200 bg-white py-2 px-3 text-xs font-mono text-slate-700 focus:border-brand-500 focus:outline-none shadow-xs"
            >
              {EVENT_TYPE_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>

            {/* Status Filter */}
            <select
              value={selectedStatus}
              onChange={(e) => setSelectedStatus(e.target.value)}
              aria-label="Filter events by status"
              className="w-full sm:w-auto rounded-xl border border-slate-200 bg-white py-2 px-3 text-xs font-mono text-slate-700 focus:border-brand-500 focus:outline-none shadow-xs"
            >
              {STATUS_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>

            {/* Project Filter (if not scoped to single project) */}
            {!scopedProjectId && projects.length > 0 && (
              <select
                value={selectedProject}
                onChange={(e) => setSelectedProject(e.target.value)}
                aria-label="Filter events by project"
                className="w-full sm:w-auto rounded-xl border border-slate-200 bg-white py-2 px-3 text-xs font-mono text-slate-700 focus:border-brand-500 focus:outline-none shadow-xs"
              >
                <option value="ALL">All Projects ({projects.length})</option>
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            )}

            {/* Sort Order Toggle */}
            <button
              onClick={() =>
                setSortOrder((prev) => (prev === 'NEWEST' ? 'OLDEST' : 'NEWEST'))
              }
              aria-label={`Toggle sort order, current: ${sortOrder === 'NEWEST' ? 'Newest First' : 'Oldest First'}`}
              className="w-full sm:w-auto flex items-center justify-center gap-1.5 rounded-xl border border-slate-200 bg-white py-2 px-3 text-xs font-mono text-slate-700 hover:text-slate-900 hover:bg-slate-50 transition-colors cursor-pointer shrink-0 shadow-xs font-medium"
              title="Toggle Sort Order"
            >
              <ArrowUpDown className="h-3.5 w-3.5 text-brand-500" />
              <span>{sortOrder === 'NEWEST' ? 'Newest First' : 'Oldest First'}</span>
            </button>
          </div>
        </div>

        {/* Filter Summary & Result Count */}
        <div className="flex items-center justify-between text-xs font-mono text-slate-500 pt-1 border-t border-slate-100">
          <span>
            Showing <strong>{filteredEvents.length}</strong> of{' '}
            <strong>{events.length}</strong> events
          </span>
          {(searchTerm ||
            selectedType !== 'ALL' ||
            selectedStatus !== 'ALL' ||
            (!scopedProjectId && selectedProject !== 'ALL')) && (
            <button
              onClick={() => {
                setSearchTerm('');
                setSelectedType('ALL');
                setSelectedStatus('ALL');
                if (!scopedProjectId) setSelectedProject('ALL');
              }}
              className="text-brand-600 hover:text-brand-700 cursor-pointer font-medium"
            >
              Clear filters
            </button>
          )}
        </div>
      </div>

      {/* Events Audit Table */}
      {filteredEvents.length === 0 ? (
        <EmptyState
          title="No Events Found"
          description="No telemetry audit records matched the active filters and search criteria."
          icon={History}
        />
      ) : (
        <div className="overflow-hidden rounded-2xl border border-white/80 bg-white/75 backdrop-blur-md shadow-glass">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs font-mono">
              <thead className="bg-slate-50/80 text-slate-500 border-b border-slate-200/80">
                <tr>
                  <th className="px-4 py-3 uppercase tracking-wider text-[10px]">Event ID</th>
                  <th className="px-4 py-3 uppercase tracking-wider text-[10px]">Timestamp</th>
                  <th className="px-4 py-3 uppercase tracking-wider text-[10px]">Type</th>
                  <th className="px-4 py-3 uppercase tracking-wider text-[10px]">Status</th>
                  <th className="px-4 py-3 uppercase tracking-wider text-[10px]">Project</th>
                  <th className="px-4 py-3 uppercase tracking-wider text-[10px]">Command / Target</th>
                  <th className="px-4 py-3 uppercase tracking-wider text-[10px]">Evidence / Source</th>
                  <th className="px-4 py-3 uppercase tracking-wider text-[10px] text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 text-slate-700">
                {filteredEvents.map((evt) => {
                  return (
                    <tr
                      key={evt.eventId}
                      className="hover:bg-slate-50/60 transition-colors"
                    >
                      {/* Event ID */}
                      <td className="px-4 py-3 whitespace-nowrap">
                        <span className="font-semibold text-brand-700 bg-brand-50 px-2 py-0.5 rounded-lg border border-brand-200">
                          {evt.eventId}
                        </span>
                      </td>

                      {/* Timestamp */}
                      <td className="px-4 py-3 whitespace-nowrap text-slate-500">
                        <span className="flex items-center gap-1.5 text-[11px]">
                          <Clock className="h-3 w-3 text-slate-400" />
                          {formatSafeTimestamp(evt.timestamp)}
                        </span>
                      </td>

                      {/* Event Type */}
                      <td className="px-4 py-3 whitespace-nowrap">
                        {getEventTypeBadge(evt.eventType)}
                      </td>

                      {/* Status */}
                      <td className="px-4 py-3 whitespace-nowrap">
                        {getStatusBadge(evt.status)}
                      </td>

                      {/* Project */}
                      <td className="px-4 py-3 whitespace-nowrap">
                        <Link
                          to={`/projects/${evt.projectId}`}
                          className="hover:text-brand-600 transition-colors flex items-center gap-1 text-slate-800 font-medium"
                        >
                          <Layers className="h-3 w-3 text-brand-500" />
                          <span>{evt.projectName || evt.projectId}</span>
                        </Link>
                      </td>

                      {/* Command / Summary */}
                      <td className="px-4 py-3 max-w-xs md:max-w-sm">
                        {evt.relatedCommand ? (
                          <div className="truncate text-slate-800 bg-slate-100 px-2 py-0.5 rounded-lg border border-slate-200/80 text-[11px]">
                            {evt.relatedCommand}
                          </div>
                        ) : (
                          <span className="text-slate-600 truncate block">
                            {evt.summary || '—'}
                          </span>
                        )}
                        {evt.summary && evt.relatedCommand && (
                          <span className="text-[10px] text-slate-400 block truncate mt-0.5">
                            {evt.summary}
                          </span>
                        )}
                      </td>

                      {/* Source Location */}
                      <td className="px-4 py-3 whitespace-nowrap">
                        {evt.sourceLocation?.file ? (
                          <span className="inline-flex items-center gap-1 text-rose-700 text-[11px] bg-rose-50 px-2 py-0.5 rounded-md border border-rose-200 font-medium">
                            <FileCode2 className="h-3 w-3" />
                            {evt.sourceLocation.file}:{evt.sourceLocation.line || 0}
                          </span>
                        ) : evt.relatedIncidentId ? (
                          <span className="text-[11px] text-amber-800 bg-amber-50 px-2 py-0.5 rounded-md border border-amber-200 font-medium">
                            {evt.relatedIncidentId}
                          </span>
                        ) : (
                          <span className="text-slate-400">—</span>
                        )}
                      </td>

                      {/* Actions */}
                      <td className="px-4 py-3 whitespace-nowrap text-right">
                        <div className="flex items-center justify-end gap-2">
                          {evt.relatedIncidentId && (
                            <Link
                              to={`/projects/${evt.projectId}/errors`}
                              className="text-[11px] text-rose-600 hover:text-rose-700 hover:underline flex items-center gap-0.5 font-medium"
                              title="Inspect Incident"
                            >
                              <span>Incident</span>
                              <ExternalLink className="h-2.5 w-2.5" />
                            </Link>
                          )}
                          <button
                            onClick={() => setSelectedEventModal(evt)}
                            className="rounded-lg bg-slate-100 px-2.5 py-1 text-[11px] text-slate-700 hover:bg-slate-200 hover:text-slate-900 border border-slate-200/80 transition-colors cursor-pointer shadow-xs font-medium"
                          >
                            Details
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Event Details Modal */}
      {selectedEventModal && (
        <div
          onClick={(e) => {
            if (e.target === e.currentTarget) setSelectedEventModal(null);
          }}
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4 backdrop-blur-sm"
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="audit-event-modal-title"
            className="w-full max-w-xl max-h-[90vh] overflow-y-auto rounded-2xl border border-white/90 bg-white/95 backdrop-blur-md p-6 shadow-2xl space-y-4 text-slate-800"
          >
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <div className="flex items-center gap-2">
                <History className="h-4 w-4 text-brand-500" />
                <h3 id="audit-event-modal-title" className="text-sm font-semibold text-slate-900 font-mono">
                  Event Record: {selectedEventModal.eventId}
                </h3>
              </div>
              <button
                onClick={() => setSelectedEventModal(null)}
                aria-label="Close event details modal"
                className="text-slate-400 hover:text-slate-700 text-xs font-mono cursor-pointer transition-colors"
              >
                ✕ Close
              </button>
            </div>

            <div className="space-y-3 text-xs font-mono">
              <div className="grid grid-cols-2 gap-2 bg-slate-50 p-3.5 rounded-xl border border-slate-200/80">
                <div>
                  <span className="text-slate-400 text-[10px] uppercase font-semibold">Type</span>
                  <div className="mt-0.5">{getEventTypeBadge(selectedEventModal.eventType)}</div>
                </div>
                <div>
                  <span className="text-slate-400 text-[10px] uppercase font-semibold">Status</span>
                  <div className="mt-0.5">{getStatusBadge(selectedEventModal.status)}</div>
                </div>
                <div>
                  <span className="text-slate-400 text-[10px] uppercase font-semibold">Timestamp</span>
                  <div className="text-slate-700 mt-0.5 font-medium">
                    {formatSafeTimestamp(selectedEventModal.timestamp)}
                  </div>
                </div>
                <div>
                  <span className="text-slate-400 text-[10px] uppercase font-semibold">Project</span>
                  <div className="text-slate-700 mt-0.5 font-medium">
                    {selectedEventModal.projectName} ({selectedEventModal.projectId})
                  </div>
                </div>
              </div>

              {selectedEventModal.summary && (
                <div>
                  <span className="text-slate-400 text-[10px] uppercase font-semibold">Summary</span>
                  <p className="mt-1 text-slate-800 bg-slate-50 p-2.5 rounded-xl border border-slate-200">
                    {selectedEventModal.summary}
                  </p>
                </div>
              )}

              {selectedEventModal.relatedCommand && (
                <div>
                  <span className="text-slate-400 text-[10px] uppercase font-semibold">Command</span>
                  <code className="block mt-1 text-brand-700 bg-slate-100 p-2.5 rounded-xl border border-slate-200 break-all font-mono font-medium">
                    {selectedEventModal.relatedCommand}
                  </code>
                </div>
              )}

              {selectedEventModal.sourceLocation && (
                <div>
                  <span className="text-slate-400 text-[10px] uppercase font-semibold">Source Code Location</span>
                  <div className="mt-1 text-rose-700 bg-rose-50 p-2.5 rounded-xl border border-rose-200 flex items-center gap-1.5 font-medium">
                    <FileCode2 className="h-3.5 w-3.5" />
                    <span>
                      {selectedEventModal.sourceLocation.file}:
                      {selectedEventModal.sourceLocation.line || 0}
                    </span>
                  </div>
                </div>
              )}

              {selectedEventModal.details && (
                <div>
                  <span className="text-slate-400 text-[10px] uppercase font-semibold">Audit Details</span>
                  <p className="mt-1 text-slate-700 bg-slate-50 p-2.5 rounded-xl border border-slate-200 leading-relaxed font-sans text-xs">
                    {selectedEventModal.details}
                  </p>
                </div>
              )}
            </div>

            <div className="flex items-center justify-between pt-3 border-t border-slate-100">
              <Link
                to={`/projects/${selectedEventModal.projectId}`}
                className="text-xs font-mono text-brand-600 hover:text-brand-700 flex items-center gap-1 font-medium"
                onClick={() => setSelectedEventModal(null)}
              >
                <span>Go to Project Workspace</span>
                <ExternalLink className="h-3 w-3" />
              </Link>
              <button
                onClick={() => setSelectedEventModal(null)}
                className="rounded-xl bg-slate-100 px-3.5 py-1.5 text-xs font-mono text-slate-700 hover:bg-slate-200 hover:text-slate-900 border border-slate-200 transition-colors shadow-xs cursor-pointer font-medium"
              >
                Done
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
