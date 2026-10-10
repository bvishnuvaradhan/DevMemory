import React, { useState, useEffect } from 'react';
import { History, RefreshCw } from 'lucide-react';
import EventsAuditTable from '../components/events/EventsAuditTable';
import LoadingSpinner from '../components/common/LoadingSpinner';
import { fetchGlobalEvents, fetchProjects } from '../api/devmemoryApi';

export default function EventsHistory() {
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [events, setEvents] = useState([]);
  const [projects, setProjects] = useState([]);
  const [isMock, setIsMock] = useState(true);

  const loadData = async (isManual = false) => {
    if (isManual) setRefreshing(true);
    try {
      const [eventsRes, projsRes] = await Promise.all([
        fetchGlobalEvents(),
        fetchProjects(),
      ]);
      setEvents(eventsRes.data);
      setProjects(projsRes.data);
      setIsMock(eventsRes.isMock);
    } catch (err) {
      console.error('Failed to load events audit stream:', err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  if (loading) {
    return <LoadingSpinner label="Loading telemetry audit event stream..." />;
  }

  return (
    <div className="space-y-6 p-3 sm:p-6 max-w-7xl mx-auto">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white font-mono flex items-center gap-2">
            <History className="h-6 w-6 text-brand-500" />
            Events & Audit History
          </h1>
          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
            Immutable chronological audit stream of commands, error incidents, AI diagnoses, and fix-verification events.
          </p>
        </div>

        <button
          onClick={() => loadData(true)}
          disabled={refreshing}
          className="inline-flex items-center gap-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-white/80 dark:bg-slate-800/80 px-3.5 py-2 text-xs font-mono text-slate-700 dark:text-slate-200 hover:bg-white dark:hover:bg-slate-700 hover:text-slate-900 dark:hover:text-white shadow-xs hover:border-slate-300 dark:hover:border-slate-600 transition-all cursor-pointer self-start sm:self-auto"
        >
          <RefreshCw className={`h-3.5 w-3.5 text-indigo-500 ${refreshing ? 'animate-spin' : ''}`} />
          <span>Refresh Stream</span>
        </button>
      </div>

      {/* Events Table */}
      <EventsAuditTable
        events={events}
        projects={projects}
        isMock={isMock}
      />
    </div>
  );
}
