import React, { useState, useEffect } from 'react';
import { Link, NavLink, useNavigate, useLocation } from 'react-router-dom';
import {
  Cpu,
  Github,
  ChevronDown,
  Menu,
  X,
  LayoutDashboard,
  TerminalSquare,
  AlertTriangle,
  CheckCircle,
  TrendingUp,
  History,
  FolderGit2,
  Database,
  BrainCircuit,
  Sun,
  Moon,
} from 'lucide-react';
import Badge from '../common/Badge';
import { useTheme } from '../../context/ThemeContext';

export default function Navbar({ projects = [], selectedProjectId, onSelectProject, isMock = true }) {
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const { isDark, toggleTheme } = useTheme();
  const navigate = useNavigate();
  const location = useLocation();

  // Close mobile menu on route change
  useEffect(() => {
    setIsMobileMenuOpen(false);
  }, [location.pathname]);

  // Close mobile menu on Escape key press
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape' && isMobileMenuOpen) {
        setIsMobileMenuOpen(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isMobileMenuOpen]);

  const handleProjectChange = (e) => {
    const val = e.target.value;
    if (val === 'all') {
      navigate('/');
    } else {
      navigate(`/projects/${val}`);
    }
    if (onSelectProject) onSelectProject(val);
    setIsMobileMenuOpen(false);
  };

  const navItemClass = ({ isActive }) =>
    `flex items-center gap-3 px-3 py-2 text-xs font-medium rounded-xl transition-all duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 ${
      isActive
        ? 'bg-indigo-50/90 dark:bg-indigo-950/60 text-indigo-600 dark:text-indigo-400 font-semibold border border-indigo-200/80 dark:border-indigo-800/60 shadow-xs'
        : 'text-slate-600 dark:text-slate-300 hover:text-slate-900 dark:hover:text-white hover:bg-white/80 dark:hover:bg-slate-800/80'
    }`;

  return (
    <>
      <nav
        aria-label="Global application navigation"
        className="flex h-16 w-full items-center justify-between border-b border-slate-200/80 dark:border-slate-800/80 bg-white/75 dark:bg-slate-900/80 px-3 sm:px-6 backdrop-blur-md relative z-30 transition-colors"
      >
        <div className="flex items-center gap-2 sm:gap-6">
          {/* Mobile hamburger menu toggle */}
          <button
            type="button"
            onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
            aria-label={isMobileMenuOpen ? 'Close navigation menu' : 'Open navigation menu'}
            aria-expanded={isMobileMenuOpen}
            className="flex h-9 w-9 items-center justify-center rounded-xl border border-slate-200 dark:border-slate-700 bg-white/80 dark:bg-slate-800/80 text-slate-700 dark:text-slate-200 hover:bg-white dark:hover:bg-slate-700 hover:text-slate-900 dark:hover:text-white md:hidden shadow-xs cursor-pointer transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500"
          >
            {isMobileMenuOpen ? (
              <X className="h-5 w-5 text-slate-700 dark:text-slate-200" />
            ) : (
              <Menu className="h-5 w-5 text-slate-700 dark:text-slate-200" />
            )}
          </button>

          <Link
            to="/"
            aria-label="DevMemory Platform Home"
            className="flex items-center gap-2.5 sm:gap-3 group focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 rounded-xl p-1"
          >
            <div className="flex h-8 w-8 sm:h-9 sm:w-9 items-center justify-center rounded-xl bg-gradient-to-br from-brand-500 to-indigo-600 shadow-md shadow-brand-500/20 group-hover:scale-105 transition-transform shrink-0">
              <Cpu className="h-4 w-4 sm:h-5 sm:w-5 text-white" />
            </div>
            <div>
              <div className="flex items-center gap-1.5 sm:gap-2">
                <span className="text-sm sm:text-base font-bold tracking-tight text-slate-900 dark:text-white font-mono">
                  DevMemory
                </span>
                <Badge variant="brand" size="xs">Track 3</Badge>
              </div>
              <p className="text-[9px] sm:text-[10px] text-slate-500 dark:text-slate-400 font-mono -mt-0.5 hidden xs:block">
                Persistent Troubleshooting
              </p>
            </div>
          </Link>

          {/* Project Selector Dropdown on Desktop */}
          <div className="hidden sm:flex items-center gap-2 ml-2 sm:ml-4 pl-2 sm:pl-4 border-l border-slate-200 dark:border-slate-800">
            <label htmlFor="project-select" className="text-xs text-slate-500 dark:text-slate-400 font-mono">
              Scope:
            </label>
            <div className="relative">
              <select
                id="project-select"
                aria-label="Select active project scope"
                value={selectedProjectId || 'all'}
                onChange={handleProjectChange}
                className="appearance-none rounded-lg border border-slate-200 dark:border-slate-700 bg-white/90 dark:bg-slate-800 py-1.5 pl-3 pr-8 text-xs font-mono text-slate-700 dark:text-slate-200 focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500 cursor-pointer shadow-xs focus-visible:ring-2 focus-visible:ring-indigo-500"
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

        <div className="flex items-center gap-2 sm:gap-3">
          {/* Connection status indicator */}
          <div className="flex items-center gap-1.5 sm:gap-2 text-xs font-mono" title={isMock ? 'Running with local demo dataset' : 'Connected to live FastAPI backend'}>
            <span
              aria-hidden="true"
              className={`h-2 w-2 rounded-full ${isMock ? 'bg-amber-500 animate-pulse' : 'bg-emerald-500'}`}
            />
            <span className="text-slate-600 dark:text-slate-400 hidden md:inline font-medium">
              {isMock ? 'Demo Mode' : 'Live Gateway'}
            </span>
          </div>

          {/* Light / Dark Mode Toggle */}
          <button
            type="button"
            onClick={toggleTheme}
            aria-label={`Switch to ${isDark ? 'light' : 'dark'} mode`}
            title={`Switch to ${isDark ? 'light' : 'dark'} mode`}
            className="flex h-8 w-8 items-center justify-center rounded-lg border border-slate-200 dark:border-slate-700 bg-white/80 dark:bg-slate-800/80 text-slate-600 dark:text-amber-400 hover:text-slate-900 dark:hover:text-amber-300 hover:border-slate-300 dark:hover:border-slate-600 shadow-xs transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 cursor-pointer"
          >
            {isDark ? (
              <Sun className="h-4 w-4 text-amber-400 transition-transform duration-200 hover:rotate-45" />
            ) : (
              <Moon className="h-4 w-4 text-slate-600 transition-transform duration-200 hover:-rotate-12" />
            )}
          </button>

          <a
            href="https://github.com/bvishnuvaradhan/DevMemory"
            target="_blank"
            rel="noreferrer"
            aria-label="GitHub Repository (opens in new tab)"
            className="flex h-8 w-8 items-center justify-center rounded-lg border border-slate-200 dark:border-slate-700 bg-white/80 dark:bg-slate-800/80 text-slate-600 dark:text-slate-300 hover:text-slate-900 dark:hover:text-white hover:border-slate-300 dark:hover:border-slate-600 shadow-xs transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500"
            title="GitHub Repository"
          >
            <Github className="h-4 w-4" />
          </a>
        </div>
      </nav>

      {/* Mobile Slide-Down Navigation Drawer (Visible on <md screens when toggled) */}
      {isMobileMenuOpen && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Mobile Navigation Menu"
          className="fixed inset-x-0 top-16 bottom-0 z-40 bg-slate-900/40 backdrop-blur-sm md:hidden flex flex-col justify-start"
          onClick={(e) => {
            if (e.target === e.currentTarget) setIsMobileMenuOpen(false);
          }}
        >
          <div className="w-full max-h-[85vh] flex flex-col overflow-hidden bg-white/95 dark:bg-slate-900/95 backdrop-blur-xl border-b border-slate-200 dark:border-slate-800 p-4 shadow-2xl space-y-4 animate-in slide-in-from-top-2 duration-150">
            {/* Scope Selector on Mobile: Stationary */}
            <div className="shrink-0">
              <label htmlFor="mobile-project-select" className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500 block mb-1.5 font-mono">
                Active Project Scope
              </label>
              <div className="relative">
                <select
                  id="mobile-project-select"
                  aria-label="Select active project scope on mobile"
                  value={selectedProjectId || 'all'}
                  onChange={handleProjectChange}
                  className="w-full appearance-none rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 py-2 pl-3 pr-8 text-xs font-mono text-slate-800 dark:text-slate-200 shadow-xs focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
                >
                  <option value="all">⚡ All Projects (Global Scope)</option>
                  {projects.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name} ({p.language})
                    </option>
                  ))}
                </select>
                <ChevronDown className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
              </div>
            </div>

            {/* Platform Navigation: Stationary */}
            <div className="shrink-0">
              <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500 block mb-1.5 font-mono">
                Platform Features
              </span>
              <nav aria-label="Mobile platform features" className="space-y-1">
                <NavLink to="/" end className={navItemClass}>
                  <LayoutDashboard className="h-4 w-4 text-indigo-500" />
                  <span>Global Dashboard</span>
                </NavLink>
                <NavLink to="/runs" className={navItemClass}>
                  <TerminalSquare className="h-4 w-4 text-sky-500" />
                  <span>Command Runs</span>
                </NavLink>
                <NavLink to="/incidents" className={navItemClass}>
                  <AlertTriangle className="h-4 w-4 text-rose-500" />
                  <span>Errors & Diagnoses</span>
                </NavLink>
                <NavLink to="/fixes" className={navItemClass}>
                  <CheckCircle className="h-4 w-4 text-emerald-500" />
                  <span>Verified Fixes</span>
                </NavLink>
                <NavLink to="/performance" className={navItemClass}>
                  <TrendingUp className="h-4 w-4 text-indigo-500" />
                  <span>Performance Lab</span>
                </NavLink>
                <NavLink to="/events" className={navItemClass}>
                  <History className="h-4 w-4 text-purple-500" />
                  <span>Events & Audit</span>
                </NavLink>
              </nav>
            </div>

            {/* Project Workspaces list: Stationary heading + Scrollable list */}
            <div className="flex-1 min-h-0 flex flex-col overflow-hidden">
              <span className="shrink-0 text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500 block mb-1.5 font-mono">
                Workspaces ({projects.length})
              </span>
              <nav
                aria-label="Mobile workspaces navigation"
                className="flex-1 min-h-0 max-h-48 overflow-y-auto overflow-x-hidden space-y-1 pr-1.5"
              >
                {projects.map((p) => (
                  <NavLink
                    key={p.id}
                    to={`/projects/${p.id}`}
                    className={({ isActive }) =>
                      `flex items-center justify-between px-3 py-1.5 text-xs rounded-xl transition-all duration-150 ${
                        isActive
                          ? 'bg-indigo-50 dark:bg-indigo-950/60 text-indigo-700 dark:text-indigo-400 font-semibold border border-indigo-200 dark:border-indigo-800/60'
                          : 'text-slate-600 dark:text-slate-300 hover:text-slate-900 dark:hover:text-white hover:bg-slate-50 dark:hover:bg-slate-800'
                      }`
                    }
                  >
                    <div className="flex items-center gap-2 truncate">
                      <FolderGit2 className="h-3.5 w-3.5 text-brand-500 shrink-0" />
                      <span className="truncate">{p.name}</span>
                    </div>
                    {p.failureCount > 0 && (
                      <span className="rounded-full bg-rose-50 dark:bg-rose-950/50 px-2 py-0.5 text-[10px] font-mono text-rose-600 dark:text-rose-400 font-semibold border border-rose-200 dark:border-rose-800">
                        {p.failureCount}
                      </span>
                    )}
                  </NavLink>
                ))}
              </nav>
            </div>

            {/* Theme Toggle Row on Mobile: Stationary */}
            <div className="shrink-0 pt-2 border-t border-slate-200/80 dark:border-slate-800/80 flex items-center justify-between">
              <span className="text-xs font-mono text-slate-600 dark:text-slate-400 font-medium">
                Interface Theme:
              </span>
              <button
                type="button"
                onClick={toggleTheme}
                aria-label={`Switch to ${isDark ? 'light' : 'dark'} mode`}
                className="flex items-center gap-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-1.5 text-xs font-mono text-slate-700 dark:text-slate-200 shadow-xs cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-700"
              >
                {isDark ? (
                  <>
                    <Sun className="h-3.5 w-3.5 text-amber-400" />
                    <span>Dark Theme</span>
                  </>
                ) : (
                  <>
                    <Moon className="h-3.5 w-3.5 text-slate-600" />
                    <span>Light Theme</span>
                  </>
                )}
              </button>
            </div>

            {/* Memory indicator box */}
            <div className="rounded-xl border border-indigo-100 dark:border-indigo-900/60 bg-indigo-50/50 dark:bg-indigo-950/40 p-3 text-xs font-mono text-indigo-900 dark:text-indigo-200 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <BrainCircuit className="h-4 w-4 text-indigo-600 dark:text-indigo-400" />
                <span className="font-semibold">3-Tier Dev Memory</span>
              </div>
              <div className="flex items-center gap-1 text-[11px] text-indigo-600 dark:text-indigo-400">
                <Database className="h-3 w-3" />
                <span>MongoDB</span>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
