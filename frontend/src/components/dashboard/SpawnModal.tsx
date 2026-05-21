import React, { useEffect, useMemo, useState } from 'react';
import {
  PlusCircle,
  X,
  RefreshCw,
  Folder,
  GitFork,
  Search,
} from 'lucide-react';
import type { Agent, Host } from '../../api';

/** Props for the SpawnModal component. */
export interface SpawnModalProps {
  host: Host;
  tool: string;
  /** Human-readable tool name from the profile. */
  displayName?: string;
  /** Whether the tool supports resuming sessions. */
  supportsResume?: boolean;
  /** Active agents on this host, used to compute the
   *  smart default for the worktree isolation toggle. */
  activeAgents?: Agent[];
  onClose: () => void;
  onSpawn: (
    dir: string,
    task: string,
    sessionMode: string,
    useWorktree: boolean,
  ) => void;
  onRefresh: () => void;
}

/**
 * Modal dialog for spawning a new agent session on a host.
 * Allows selecting a project directory, entering a task
 * description, choosing resume vs. new session mode, and
 * optionally isolating the session in a git worktree.
 */
const SpawnModal: React.FC<SpawnModalProps> = ({
  host,
  tool,
  displayName,
  supportsResume: supportsResumeProp,
  activeAgents = [],
  onClose,
  onSpawn,
  onRefresh,
}) => {
  const projects = useMemo(
    () => host.projects?.available_projects || [],
    [host.projects?.available_projects],
  );

  // Compute display labels by stripping the common prefix
  // from absolute paths for readability.
  const projectsRoot = host.projects?.projects_root;
  const roots = useMemo(
    () =>
      Array.isArray(projectsRoot)
        ? projectsRoot
        : projectsRoot
          ? [projectsRoot]
          : ['/git'],
    [projectsRoot],
  );
  const stripPrefix = useMemo(() => {
    if (roots.length === 1) return roots[0] + '/';
    return '';
  }, [roots]);
  const displayLabel = (p: string) =>
    stripPrefix && p.startsWith(stripPrefix) ? p.slice(stripPrefix.length) : p;

  const [selectedProject, setSelectedProject] = useState('');
  const [projectSearch, setProjectSearch] = useState('');
  const [task, setTask] = useState('');
  const [resumeSession, setResumeSession] = useState(true);
  const [useWorktree, setUseWorktree] = useState(false);
  const showResume = supportsResumeProp ?? false;

  // Filter projects by search query (case-insensitive
  // substring match against the full path).
  const filteredProjects = useMemo(() => {
    if (!projectSearch) return projects;
    const q = projectSearch.toLowerCase();
    return projects.filter((p) => p.toLowerCase().includes(q));
  }, [projects, projectSearch]);

  // Auto-select first project when list arrives
  useEffect(() => {
    if (projects.length > 0 && !selectedProject) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- initialize from async data
      setSelectedProject(projects[0]);
    }
  }, [projects, selectedProject]);

  // Smart default: enable worktree isolation when another
  // agent is already active on the selected project.
  // Only runs when the project selection changes — not
  // on activeAgents updates — so it doesn't override
  // user manual toggles.
  useEffect(() => {
    if (!selectedProject) return;
    const fullPath = selectedProject.startsWith('/')
      ? selectedProject
      : `${roots[0]}/${selectedProject}`;
    const hasActiveAgent = activeAgents.some(
      (a) =>
        a.telemetry?.project_dir === selectedProject ||
        a.telemetry?.project_dir === fullPath,
    );
    // eslint-disable-next-line react-hooks/set-state-in-effect -- derive from props
    setUseWorktree(hasActiveAgent);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- intentionally omit activeAgents to avoid overriding user toggles
  }, [selectedProject, roots]);

  // When worktree is enabled, force session mode to "new"
  // since the worktree has no prior session state.
  const effectiveResume = useWorktree ? false : resumeSession;

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-slate-800 border border-slate-700 rounded-2xl w-full max-w-md shadow-2xl overflow-hidden">
        <div className="flex justify-between items-center p-6 border-b border-slate-700 bg-slate-800/50">
          <h3 className="text-xl font-bold text-slate-50 flex items-center gap-2">
            <PlusCircle size={24} className="text-accent" />
            Spawn {displayName || tool.toUpperCase()}
          </h3>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-50 transition-colors"
          >
            <X size={24} />
          </button>
        </div>

        <div className="p-6 space-y-6">
          <div>
            <label className="block text-xs font-bold text-slate-400 uppercase tracking-widest mb-2">
              Host
            </label>
            <p className="text-slate-50 font-medium bg-slate-900/50 p-3 rounded-lg border border-slate-700">
              {host.name}
            </p>
          </div>

          <div>
            <div className="flex justify-between items-center mb-2">
              <label className="block text-xs font-bold uppercase tracking-widest text-accent">
                Select Project
              </label>
              <button
                onClick={onRefresh}
                className="text-[10px] text-accent font-bold uppercase tracking-tighter transition-colors flex items-center gap-1 cursor-pointer hover:text-accent-hover hover:underline"
              >
                <RefreshCw size={10} className="animate-spin-slow" /> Force
                Refresh
              </button>
            </div>
            <div className="relative">
              <Search
                className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500"
                size={14}
              />
              <input
                autoFocus
                type="text"
                value={projectSearch}
                onChange={(e) => setProjectSearch(e.target.value)}
                placeholder="Search projects..."
                className="w-full bg-slate-900 border border-slate-700 rounded-lg py-2 pl-9 pr-4 text-sm text-slate-50 focus:outline-none focus:border-accent transition-colors"
              />
            </div>
            <div className="mt-1.5 max-h-48 overflow-y-auto bg-slate-900 border border-slate-700 rounded-lg">
              {projects.length === 0 ? (
                <p className="text-sm text-slate-500 px-3 py-2 italic">
                  Loading projects from {roots.join(', ')}...
                </p>
              ) : filteredProjects.length === 0 ? (
                <p className="text-sm text-slate-500 px-3 py-2 italic">
                  No projects match &ldquo;{projectSearch}&rdquo;
                </p>
              ) : (
                filteredProjects.map((p) => (
                  <button
                    key={p}
                    type="button"
                    onClick={() => setSelectedProject(p)}
                    className={`w-full text-left px-3 py-1.5 text-sm font-mono flex items-center gap-2 transition-colors ${
                      selectedProject === p
                        ? 'bg-accent/20 text-accent'
                        : 'text-slate-300 hover:bg-slate-800'
                    }`}
                  >
                    <Folder size={12} className="shrink-0" />
                    {displayLabel(p)}
                  </button>
                ))
              )}
            </div>
            <p className="text-[10px] text-slate-500 mt-1 italic">
              {roots.length === 1 ? (
                <>
                  Projects from{' '}
                  <code className="bg-slate-900 px-1 rounded">{roots[0]}</code>
                </>
              ) : (
                <>Projects from {roots.length} directories</>
              )}
            </p>
          </div>

          {showResume && (
            <div
              className={`flex items-center justify-between ${useWorktree ? 'opacity-50' : ''}`}
            >
              <div>
                <label className="block text-xs font-bold text-slate-400 uppercase tracking-widest">
                  Session Mode
                </label>
                <p className="text-[10px] text-slate-500 mt-0.5">
                  {useWorktree
                    ? 'New session (required for worktree isolation)'
                    : effectiveResume
                      ? 'Continue the most recent session in this project'
                      : 'Start a fresh session'}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setResumeSession(!resumeSession)}
                disabled={useWorktree}
                className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                  effectiveResume ? 'bg-accent' : 'bg-slate-600'
                } ${useWorktree ? 'cursor-not-allowed' : ''}`}
              >
                <span
                  className={`inline-block h-4 w-4 rounded-full bg-white transition-transform ${
                    effectiveResume ? 'translate-x-6' : 'translate-x-1'
                  }`}
                />
              </button>
              <span className="text-xs text-slate-300 font-medium ml-2 w-16">
                {effectiveResume ? 'Resume' : 'New'}
              </span>
            </div>
          )}

          <div className="flex items-center justify-between">
            <div>
              <label className="block text-xs font-bold text-slate-400 uppercase tracking-widest flex items-center gap-1.5">
                <GitFork size={12} />
                Worktree Isolation
              </label>
              <p className="text-[10px] text-slate-500 mt-0.5">
                {useWorktree
                  ? 'Create a separate working copy for this agent'
                  : 'Agent works directly in the project directory'}
              </p>
            </div>
            <button
              type="button"
              onClick={() => setUseWorktree(!useWorktree)}
              className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                useWorktree ? 'bg-accent' : 'bg-slate-600'
              }`}
            >
              <span
                className={`inline-block h-4 w-4 rounded-full bg-white transition-transform ${
                  useWorktree ? 'translate-x-6' : 'translate-x-1'
                }`}
              />
            </button>
            <span className="text-xs text-slate-300 font-medium ml-2 w-16">
              {useWorktree ? 'Isolated' : 'Shared'}
            </span>
          </div>

          <div>
            <label className="block text-xs font-bold text-slate-400 uppercase tracking-widest mb-2">
              Task Description (Optional)
            </label>
            <textarea
              value={task}
              onChange={(e) => setTask(e.target.value)}
              className="w-full bg-slate-900 border border-slate-700 rounded-lg py-2.5 px-4 text-slate-50 focus:outline-none focus:border-accent transition-colors min-h-[100px] resize-none"
              placeholder="Describe the objective for this session..."
            />
          </div>
        </div>

        <div className="p-6 bg-slate-900/50 border-t border-slate-700 flex gap-3">
          <button
            onClick={onClose}
            className="flex-1 px-4 py-2.5 rounded-xl font-bold text-slate-400 hover:text-slate-50 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={() =>
              onSpawn(
                selectedProject,
                task,
                effectiveResume ? 'resume' : 'new',
                useWorktree,
              )
            }
            disabled={!selectedProject}
            className={`flex-1 font-bold py-2.5 rounded-xl transition-all shadow-lg active:scale-95 flex items-center justify-center gap-2 ${
              selectedProject
                ? 'bg-accent hover:bg-accent-hover text-accent-text'
                : 'bg-slate-700 text-slate-500 cursor-not-allowed border border-slate-600'
            }`}
          >
            Initialize Agent
          </button>
        </div>
      </div>
    </div>
  );
};

export default SpawnModal;
