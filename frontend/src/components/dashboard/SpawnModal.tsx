import React, { useEffect, useMemo, useState } from 'react';
import {
  PlusCircle,
  X,
  ChevronRight,
  RefreshCw,
  Folder,
  GitFork,
} from 'lucide-react';
import type { Agent, Host } from '../../api';

/** Props for the SpawnModal component. */
export interface SpawnModalProps {
  host: Host;
  tool: string;
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
  activeAgents = [],
  onClose,
  onSpawn,
  onRefresh,
}) => {
  const projects = useMemo(
    () => host.projects?.available_projects || [],
    [host.projects?.available_projects],
  );
  const [selectedProject, setSelectedProject] = useState('');
  const [task, setTask] = useState('');
  const [resumeSession, setResumeSession] = useState(true);
  const [useWorktree, setUseWorktree] = useState(false);
  const showResume = tool === 'claude' || tool === 'gemini';

  // Auto-select first project when list arrives
  useEffect(() => {
    if (projects.length > 0 && !selectedProject) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- initialize from async data
      setSelectedProject(projects[0]);
    }
  }, [projects, selectedProject]);

  // Smart default: enable worktree isolation when another
  // agent is already active on the selected project.
  // Uses the original project_dir for matching so
  // worktree-isolated agents are counted too.
  useEffect(() => {
    if (!selectedProject) return;
    const projectsRoot = host.projects?.projects_root || '/git';
    const fullPath = `${projectsRoot}/${selectedProject}`;
    const hasActiveAgent = activeAgents.some(
      (a) => a.telemetry?.project_dir === fullPath,
    );
    // eslint-disable-next-line react-hooks/set-state-in-effect -- derive from props
    setUseWorktree(hasActiveAgent);
  }, [selectedProject, activeAgents, host.projects?.projects_root]);

  // When worktree is enabled, force session mode to "new"
  // since the worktree has no prior session state.
  const effectiveResume = useWorktree ? false : resumeSession;

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-slate-800 border border-slate-700 rounded-2xl w-full max-w-md shadow-2xl overflow-hidden">
        <div className="flex justify-between items-center p-6 border-b border-slate-700 bg-slate-800/50">
          <h3 className="text-xl font-bold text-slate-50 flex items-center gap-2">
            <PlusCircle size={24} className="text-accent" />
            Spawn {tool.toUpperCase()}
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
            <div className="relative group">
              <Folder
                className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500 group-hover:text-accent transition-colors"
                size={18}
              />
              <select
                value={selectedProject}
                onChange={(e) => setSelectedProject(e.target.value)}
                className="w-full bg-slate-900 border border-slate-700 rounded-lg py-2.5 pl-10 pr-10 text-slate-50 focus:outline-none focus:border-accent appearance-none transition-all cursor-pointer"
              >
                {projects.length === 0 && (
                  <option value="">
                    Loading projects from{' '}
                    {host.projects?.projects_root || '/git'}
                    ...
                  </option>
                )}
                {projects.map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </select>
              <ChevronRight
                className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 pointer-events-none group-hover:text-accent rotate-90"
                size={18}
              />
            </div>
            <p className="text-[10px] text-slate-500 mt-1.5 italic">
              Projects found in{' '}
              <code className="bg-slate-900 px-1 rounded">
                {host.projects?.projects_root || '/git'}
              </code>
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
