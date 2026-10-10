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
    <nav className="flex h-16 w-full items-center justify-between border-b border-slate-200/80 bg-white/75 px-6 backdrop-blur-md">
      <div className="flex items-center gap-6">
        <Link to="/" className="flex items-center gap-3 group">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-brand-500 to-indigo-600 shadow-md shadow-brand-500/20 group-hover:scale-105 transition-transform">
            <Cpu className="h-5 w-5 text-white" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-base font-bold tracking-tight text-slate-900 font-mono">
                DevMemory
              </span>
              <Badge variant="brand" size="xs">Track 3</Badge>
            </div>
            <p className="text-[10px] text-slate-500 font-mono -mt-0.5">Persistent Troubleshooting</p>
          </div>
        </Link>

        {/* Project Selector Dropdown */}
        <div className="hidden sm:flex items-center gap-2 ml-4 pl-4 border-l border-slate-200">
          <label htmlFor="project-select" className="text-xs text-slate-500 font-mono">
            Scope:
          </label>
          <div className="relative">
            <select
              id="project-select"
              value={selectedProjectId || 'all'}
              onChange={handleProjectChange}
              className="appearance-none rounded-lg border border-slate-200 bg-white/90 py-1.5 pl-3 pr-8 text-xs font-mono text-slate-700 focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500 cursor-pointer shadow-xs"
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
          <span className={`h-2 w-2 rounded-full ${isMock ? 'bg-amber-500 animate-pulse' : 'bg-emerald-500'}`} />
          <span className="text-slate-600 hidden md:inline font-medium">
            {isMock ? 'Demo Mode' : 'Live Gateway'}
          </span>
        </div>

        <a
          href="https://github.com/bvishnuvaradhan/DevMemory"
          target="_blank"
          rel="noreferrer"
          className="flex h-8 w-8 items-center justify-center rounded-lg border border-slate-200 bg-white/80 text-slate-600 hover:text-slate-900 hover:border-slate-300 shadow-xs transition-colors"
          title="GitHub Repository"
        >
          <Github className="h-4 w-4" />
        </a>
      </div>
    </nav>
  );
}
