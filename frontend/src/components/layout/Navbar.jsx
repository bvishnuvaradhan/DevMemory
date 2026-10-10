import React from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Cpu, Github, Activity, ChevronDown } from 'lucide-react';
import Badge from '../common/Badge';

export default function Navbar({ projects = [], selectedProjectId, onSelectProject, isMock = true }) {
  const navigate = useNavigate();

  const handleProjectChange = (e) => {
    const val = e.target.value;
    if (val === 'all') {
      navigate('/');
    } else {
      navigate(`/projects/${val}`);
    }
    if (onSelectProject) onSelectProject(val);
  };

  return (
    <header className="sticky top-0 z-30 flex h-16 w-full items-center justify-between border-b border-slate-800/80 bg-slate-950/80 px-6 backdrop-blur">
      <div className="flex items-center gap-6">
        <Link to="/" className="flex items-center gap-3 group">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-brand-500 to-indigo-700 shadow-lg shadow-brand-500/20 group-hover:scale-105 transition-transform">
            <Cpu className="h-5 w-5 text-white" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-base font-bold tracking-tight text-white font-mono">
                DevMemory
              </span>
              <Badge variant="brand" size="xs">Track 3</Badge>
            </div>
            <p className="text-[10px] text-slate-400 font-mono -mt-0.5">Persistent Troubleshooting</p>
          </div>
        </Link>

        {/* Project Selector Dropdown */}
        <div className="hidden sm:flex items-center gap-2 ml-4 pl-4 border-l border-slate-800">
          <label htmlFor="project-select" className="text-xs text-slate-400 font-mono">
            Scope:
          </label>
          <div className="relative">
            <select
              id="project-select"
              value={selectedProjectId || 'all'}
              onChange={handleProjectChange}
              className="appearance-none rounded-lg border border-slate-700/80 bg-slate-900/90 py-1.5 pl-3 pr-8 text-xs font-mono text-slate-200 focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500 cursor-pointer"
            >
              <option value="all">⚡ All Projects (Global)</option>
              {projects.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name} ({p.language})
                </option>
              ))}
            </select>
            <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-400" />
          </div>
        </div>
      </div>

      <div className="flex items-center gap-4">
        {/* Connection status */}
        <div className="flex items-center gap-2 text-xs font-mono">
          <span className={`h-2 w-2 rounded-full animate-pulse ${isMock ? 'bg-amber-400' : 'bg-emerald-400'}`} />
          <span className="text-slate-400 hidden md:inline">
            {isMock ? 'Demo Mode' : 'Live Gateway'}
          </span>
        </div>

        <a
          href="https://github.com/bvishnuvaradhan/DevMemory"
          target="_blank"
          rel="noreferrer"
          className="flex h-8 w-8 items-center justify-center rounded-lg border border-slate-800 bg-slate-900 text-slate-400 hover:text-white hover:border-slate-700 transition-colors"
          title="GitHub Repository"
        >
          <Github className="h-4 w-4" />
        </a>
      </div>
    </header>
  );
}
