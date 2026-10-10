import React, { useState, useEffect } from 'react';
import { Routes, Route, useLocation } from 'react-router-dom';
import Navbar from './components/layout/Navbar';
import Sidebar from './components/layout/Sidebar';
import DemoBanner from './components/common/DemoBanner';
import GlobalDashboard from './pages/GlobalDashboard';
import ProjectWorkspace from './pages/ProjectWorkspace';
import EventsHistory from './pages/EventsHistory';
import { fetchProjects } from './api/devmemoryApi';

export default function App() {
  const [projects, setProjects] = useState([]);
  const [isMock, setIsMock] = useState(true);
  const location = useLocation();

  useEffect(() => {
    async function init() {
      try {
        const res = await fetchProjects();
        setProjects(res.data);
        setIsMock(res.isMock);
      } catch (err) {
        console.error('App init error:', err);
      }
    }
    init();
  }, []);

  const handleDataLoaded = (projs, mockState) => {
    if (projs) setProjects(projs);
    setIsMock(mockState);
  };

  // Determine current active project from URL if in /projects/:id
  const match = location.pathname.match(/\/projects\/([^/]+)/);
  const selectedProjectId = match ? match[1] : null;

  return (
    <div className="flex min-h-screen flex-col bg-[#F4F7FC] text-slate-800 relative">
      {/* Soft background ambient pastel gradients for glassmorphism */}
      <div className="fixed inset-0 pointer-events-none -z-10 overflow-hidden">
        <div className="absolute -top-32 -left-32 w-96 h-96 rounded-full bg-blue-100/70 blur-3xl" />
        <div className="absolute top-1/4 -right-32 w-96 h-96 rounded-full bg-purple-100/70 blur-3xl" />
        <div className="absolute -bottom-32 left-1/3 w-96 h-96 rounded-full bg-emerald-100/50 blur-3xl" />
      </div>

      {/* Demo / Mock banner at top */}
      <DemoBanner isMock={isMock} />

      {/* Top Navbar */}
      <Navbar
        projects={projects}
        selectedProjectId={selectedProjectId}
        isMock={isMock}
      />

      <div className="flex flex-1">
        {/* Persistent Sidebar */}
        <Sidebar projects={projects} />

        {/* Main Content View */}
        <main className="flex-1 overflow-y-auto">
          <Routes>
            <Route
              path="/"
              element={<GlobalDashboard onDataLoaded={handleDataLoaded} />}
            />
            <Route path="/runs" element={<GlobalDashboard onDataLoaded={handleDataLoaded} />} />
            <Route path="/incidents" element={<GlobalDashboard onDataLoaded={handleDataLoaded} />} />
            <Route path="/fixes" element={<GlobalDashboard onDataLoaded={handleDataLoaded} />} />
            <Route path="/performance" element={<GlobalDashboard onDataLoaded={handleDataLoaded} />} />
            <Route path="/events" element={<EventsHistory />} />
            <Route path="/projects/:projectId/*" element={<ProjectWorkspace />} />
            <Route
              path="*"
              element={
                <div className="p-12 text-center">
                  <h2 className="text-lg font-bold text-slate-800 font-mono">Page Not Found</h2>
                  <p className="mt-2 text-xs text-slate-500">
                    The requested view does not exist in DevMemory.
                  </p>
                </div>
              }
            />
          </Routes>
        </main>
      </div>
    </div>
  );
}
