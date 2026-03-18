import React, { useEffect, useState, useRef } from 'react';
import { getHosts, getAgents, spawnAgent, stopAgent, deleteHost } from '../api';
import type { Host, Agent } from '../api';
import { Terminal, Cpu, Activity, PlusCircle, Wifi, WifiOff, Square, GitBranch, Folder, Info, X, ChevronRight, RefreshCw, Trash2, Server, Plug, Clock } from 'lucide-react';
import { io } from 'socket.io-client';

interface DashboardProps {
  onAttach: (agentId: string) => void;
}

interface SpawnModalProps {
    host: Host;
    tool: string;
    onClose: () => void;
    onSpawn: (dir: string, task: string, sessionMode: string) => void;
    onRefresh: () => void;
}

const SpawnModal: React.FC<SpawnModalProps> = ({ host, tool, onClose, onSpawn, onRefresh }) => {
    const projects = host.projects?.available_projects || [];
    const [selectedProject, setSelectedProject] = useState('');
    const [task, setTask] = useState('');
    const [resumeSession, setResumeSession] = useState(true);
    const showResume = tool === 'claude' || tool === 'gemini';

    // Auto-select first project when list arrives
    useEffect(() => {
        if (projects.length > 0 && !selectedProject) {
            setSelectedProject(projects[0]);
        }
    }, [projects, selectedProject]);

    return (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <div className="bg-slate-800 border border-slate-700 rounded-2xl w-full max-w-md shadow-2xl overflow-hidden">
                <div className="flex justify-between items-center p-6 border-b border-slate-700 bg-slate-800/50">
                    <h3 className="text-xl font-bold text-white flex items-center gap-2">
                        <PlusCircle size={24} className="text-blue-400" />
                        Spawn {tool.toUpperCase()}
                    </h3>
                    <button onClick={onClose} className="text-slate-400 hover:text-white transition-colors">
                        <X size={24} />
                    </button>
                </div>
                
                <div className="p-6 space-y-6">
                    <div>
                        <label className="block text-xs font-bold text-slate-400 uppercase tracking-widest mb-2">Host</label>
                        <p className="text-white font-medium bg-slate-900/50 p-3 rounded-lg border border-slate-700">{host.name}</p>
                    </div>

                    <div>
                        <div className="flex justify-between items-center mb-2">
                            <label className="block text-xs font-bold text-slate-400 uppercase tracking-widest text-blue-400">Select Project</label>
                            <button 
                                onClick={onRefresh}
                                className="text-[10px] text-blue-400 hover:text-blue-300 font-bold uppercase tracking-tighter transition-colors flex items-center gap-1"
                            >
                                <RefreshCw size={10} className="animate-spin-slow" /> Force Refresh
                            </button>
                        </div>
                        <div className="relative group">
                            <Folder className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500 group-hover:text-blue-400 transition-colors" size={18} />
                            <select 
                                value={selectedProject}
                                onChange={(e) => setSelectedProject(e.target.value)}
                                className="w-full bg-slate-900 border border-slate-700 rounded-lg py-2.5 pl-10 pr-10 text-white focus:outline-none focus:border-blue-500 appearance-none transition-all cursor-pointer"
                            >
                                {projects.length === 0 && <option value="">Loading projects from {host.projects?.projects_root || '/git'}...</option>}
                                {projects.map(p => (
                                    <option key={p} value={p}>{p}</option>
                                ))}
                            </select>
                            <ChevronRight className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 pointer-events-none group-hover:text-blue-400 rotate-90" size={18} />
                        </div>
                        <p className="text-[10px] text-slate-500 mt-1.5 italic">
                            Projects found in <code className="bg-slate-900 px-1 rounded">{host.projects?.projects_root || '/git'}</code>
                        </p>
                    </div>

                    {showResume && (
                        <div className="flex items-center justify-between">
                            <div>
                                <label className="block text-xs font-bold text-slate-400 uppercase tracking-widest">Session Mode</label>
                                <p className="text-[10px] text-slate-500 mt-0.5">
                                    {resumeSession ? 'Continue the most recent session in this project' : 'Start a fresh session'}
                                </p>
                            </div>
                            <button
                                type="button"
                                onClick={() => setResumeSession(!resumeSession)}
                                className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                                    resumeSession ? 'bg-blue-600' : 'bg-slate-600'
                                }`}
                            >
                                <span className={`inline-block h-4 w-4 rounded-full bg-white transition-transform ${
                                    resumeSession ? 'translate-x-6' : 'translate-x-1'
                                }`} />
                            </button>
                            <span className="text-xs text-slate-300 font-medium ml-2 w-16">
                                {resumeSession ? 'Resume' : 'New'}
                            </span>
                        </div>
                    )}

                    <div>
                        <label className="block text-xs font-bold text-slate-400 uppercase tracking-widest mb-2">Task Description (Optional)</label>
                        <textarea 
                            value={task}
                            onChange={(e) => setTask(e.target.value)}
                            className="w-full bg-slate-900 border border-slate-700 rounded-lg py-2.5 px-4 text-white focus:outline-none focus:border-blue-500 transition-colors min-h-[100px] resize-none"
                            placeholder="Describe the objective for this session..."
                        />
                    </div>
                </div>

                <div className="p-6 bg-slate-900/50 border-t border-slate-700 flex gap-3">
                    <button 
                        onClick={onClose}
                        className="flex-1 px-4 py-2.5 rounded-xl font-bold text-slate-400 hover:text-white transition-colors"
                    >
                        Cancel
                    </button>
                    <button 
                        onClick={() => onSpawn(selectedProject, task, resumeSession ? 'resume' : 'new')}
                        disabled={!selectedProject}
                        className={`flex-1 font-bold py-2.5 rounded-xl transition-all shadow-lg active:scale-95 flex items-center justify-center gap-2 ${
                            selectedProject 
                            ? 'bg-blue-600 hover:bg-blue-500 text-white' 
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

const CONTEXT_TIERS = [8000, 16000, 32000, 64000, 128000, 200000, 500000, 1000000, 2000000, 4000000, 8000000];

const CONTEXT_WINDOWS: Record<string, number> = {
    'claude-3-5': 200000,
    'claude-3': 200000,
    'claude-opus-4': 1000000,
    'claude-sonnet-4': 1000000,
    'claude-haiku-4': 1000000,
    'gemini-1.5-pro': 2000000,
    'gemini-exp': 2000000,
    'gemini-1.5-flash': 1000000,
    'gemini-2.5-pro': 2000000,
    'gemini-2.5-flash': 1000000,
    'gemini-2.0-flash': 1000000,
    'gpt-4': 128000,
    'gpt-4o': 128000,
};

const getContextWindow = (model?: string, tokensUsed: number = 0): number => {
    let baseMax = 200000;
    if (model) {
        const normalizedModel = model.toLowerCase();
        let found = false;
        
        for (const [key, size] of Object.entries(CONTEXT_WINDOWS)) {
            if (normalizedModel.includes(key)) {
                baseMax = size;
                found = true;
                break;
            }
        }
        if (!found) {
            if (normalizedModel.includes('gemini')) baseMax = 1000000;
            else if (normalizedModel.includes('claude')) baseMax = 200000;
        }
    }

    if (!tokensUsed) return baseMax;

    // Expansion: If tokens exceed the hardcoded limit, expand to next tier.
    if (tokensUsed >= baseMax) {
        const higherTiers = CONTEXT_TIERS.filter(t => t > tokensUsed);
        return higherTiers.length > 0 ? higherTiers[0] : Math.ceil(tokensUsed * 1.5);
    }

    // Contraction: If usage is very low compared to the hardcoded baseMax, 
    // dynamically contract the visual maximum so the progress bar remains meaningful.
    const idealMax = Math.max(tokensUsed * 1.5, 32000); 
    if (idealMax < baseMax) {
        const lowerTiers = CONTEXT_TIERS.filter(t => t >= idealMax && t <= baseMax);
        if (lowerTiers.length > 0) {
            return lowerTiers[0];
        }
    }

    return baseMax;
};

/**
 * Returns Tailwind color classes for agent tool type badges.
 * Gemini = blue, Claude = purple, Bash = slate.
 */
const getToolColors = (toolName?: string) => {
    const t = (toolName || '').toLowerCase();
    if (t.includes('claude')) {
        return {
            badge: 'bg-purple-500/20 text-purple-400 border-purple-500/20',
            border: 'hover:border-purple-500/50',
        };
    }
    if (t.includes('bash') || t.includes('shell')) {
        return {
            badge: 'bg-slate-500/20 text-slate-300 border-slate-500/20',
            border: 'hover:border-slate-500/50',
        };
    }
    // Default: gemini / blue
    return {
        badge: 'bg-blue-500/20 text-blue-400 border-blue-500/20',
        border: 'hover:border-blue-500/50',
    };
};

const getProgressColor = (pct: number): string => {
    if (pct > 80) return 'bg-red-500';
    if (pct > 50) return 'bg-amber-500';
    return 'bg-green-500';
};

/**
 * Formats a duration in seconds to a compact human-readable
 * string (e.g. "45s", "12m", "2h 15m", "1d 3h").
 * Falls back to wall-clock elapsed from a start timestamp
 * if seconds is not available.
 */
const formatDuration = (
    seconds?: number,
    startedAt?: string,
): string => {
    let secs = seconds || 0;
    if (!secs && startedAt) {
        const start = new Date(startedAt).getTime();
        if (!isNaN(start)) {
            secs = Math.floor(
                (Date.now() - start) / 1000
            );
        }
    }
    if (secs <= 0) return '';
    if (secs < 60) return `${secs}s`;
    const minutes = Math.floor(secs / 60);
    if (minutes < 60) return `${minutes}m`;
    const hours = Math.floor(minutes / 60);
    const mins = minutes % 60;
    if (hours < 24) return `${hours}h ${mins}m`;
    const days = Math.floor(hours / 24);
    const hrs = hours % 24;
    return `${days}d ${hrs}h`;
};

const StatusIndicator: React.FC<{ status?: string }> = ({ status }) => {
    switch (status) {
        case 'working':
            return (
                <div className="flex items-center gap-1 px-2 py-0.5 bg-green-500/10 rounded-full border border-green-500/20">
                    <div className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse" />
                    <span className="text-green-400 text-[10px] font-bold uppercase tracking-wider">Working</span>
                </div>
            );
        case 'waiting_permission':
            return (
                <div className="flex items-center gap-1 px-2 py-0.5 bg-red-500/15 rounded-full border border-red-500/30 animate-pulse">
                    <div className="w-1.5 h-1.5 rounded-full bg-red-400 animate-pulse" />
                    <span className="text-red-400 text-[10px] font-bold uppercase tracking-wider">Permission</span>
                </div>
            );
        case 'idle':
            return (
                <div className="flex items-center gap-1 px-2 py-0.5 bg-amber-500/10 rounded-full border border-amber-500/20">
                    <div className="w-1.5 h-1.5 rounded-full bg-amber-400" />
                    <span className="text-amber-400 text-[10px] font-bold uppercase tracking-wider">Idle</span>
                </div>
            );
        default:
            return (
                <div className="flex items-center gap-1 px-2 py-0.5 bg-green-500/10 rounded-full border border-green-500/20">
                    <div className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse" />
                    <span className="text-green-400 text-[10px] font-bold uppercase tracking-wider">Live</span>
                </div>
            );
    }
};

const Dashboard: React.FC<DashboardProps> = ({ onAttach }) => {
  const [hosts, setHosts] = useState<Host[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  const [activeSpawn, setActiveSpawn] = useState<{hostId: number, tool: string} | null>(null);

  const projectsCache = useRef<Record<number, any>>({});

  const fetchData = async () => {
    try {
      const [h, a] = await Promise.all([getHosts(), getAgents()]);
      const enrichedHosts = h.map(host => ({
          ...host,
          projects: projectsCache.current[host.id] || host.projects
      }));
      setHosts(enrichedHosts);
      setAgents(a);
      setError(null);
    } catch (err) {
      setError('Failed to fetch dashboard data. Are you logged in?');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleSpawn = async (hostId: number, toolName: string, projectDir?: string, taskDescription?: string, sessionMode?: string) => {
      try {
          const newAgent = await spawnAgent(hostId, toolName, projectDir, taskDescription, sessionMode);
          setActiveSpawn(null);
          await fetchData();
          onAttach(newAgent.agent_id);
      } catch (err) {
          console.error("Failed to spawn agent:", err);
          alert("Failed to spawn agent. Check console for details.");
      }
  };

  const handleStop = async (agentId: string) => {
      if (!window.confirm("Are you sure you want to stop this agent?")) return;
      try {
          await stopAgent(agentId);
          setTimeout(fetchData, 500);
      } catch (err) {
          console.error("Failed to stop agent:", err);
      }
  };

  const handleDeleteHost = async (hostId: number) => {
      if (!window.confirm("Are you sure you want to delete this host? All its agent sessions will also be removed.")) return;
      try {
          await deleteHost(hostId);
          await fetchData();
      } catch (err) {
          console.error("Failed to delete host:", err);
          alert("Failed to delete host. Check console for details.");
      }
  };

  const requestProjects = () => {
      const baseURL = import.meta.env.VITE_API_URL || `http://${window.location.hostname}:8000`;
      const socket = io(`${baseURL}/terminal`, { path: '/socket.io' });
      socket.emit('request_projects', {});
      console.log("Manual project refresh requested.");
      setTimeout(() => socket.disconnect(), 1000);
  };

  useEffect(() => {
    fetchData();
    const baseURL = import.meta.env.VITE_API_URL || `http://${window.location.hostname}:8000`;
    const socket = io(`${baseURL}/terminal`, { path: '/socket.io' });

    socket.on('connect', () => {        socket.emit('request_projects', {});
    });

    socket.on('agent_status_update', (data: { agent_id: string, status: string }) => {
        if (data.status === 'closed') {
            setAgents(prev => prev.filter(a => a.agent_id !== data.agent_id));
        } else {
            setAgents(prev => prev.map(a => 
                a.agent_id === data.agent_id ? { ...a, status: data.status } : a
            ));
        }
    });

    socket.on('agent_telemetry_update', (data: { agent_id: string, telemetry: any }) => {
        setAgents(prev => prev.map(a => 
            a.agent_id === data.agent_id ? { ...a, telemetry: data.telemetry } : a
        ));
    });

    socket.on('host_telemetry_update', (data: { host_id: number, telemetry: any }) => {
        projectsCache.current[data.host_id] = data.telemetry;
        setHosts(prev => prev.map(h => 
            h.id === data.host_id ? { ...h, projects: data.telemetry } : h
        ));
    });

    const interval = setInterval(fetchData, 5000);
    return () => {
        clearInterval(interval);
        socket.disconnect();
    };
  }, []);

  // Set browser window title
  useEffect(() => {
    document.title = 'Agent Dashboard';
  }, []);

  if (loading) return <div className="p-8 text-white">Loading dashboard...</div>;
  if (error) return (
    <div className="p-8">
      <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded relative" role="alert">
        <strong className="font-bold">Error: </strong>
        <span className="block sm:inline">{error}</span>
        <div className="mt-2">
          <a href={import.meta.env.VITE_API_URL ? `${import.meta.env.VITE_API_URL}/login` : `http://${window.location.hostname}:8000/login`} className="underline font-bold">Login via OIDC</a>
        </div>
      </div>
    </div>
  );

  return (
    <div className="max-w-7xl mx-auto p-8">
      <header className="mb-8 flex justify-between items-center">
        <h1 className="text-3xl font-bold flex items-center gap-2 text-white">
          <Terminal size={32} /> Agent Dashboard
        </h1>
        <div className="flex gap-4">
          <div className="bg-slate-800 p-3 rounded-lg flex items-center gap-3">
             <Cpu className="text-blue-400" />
             <div>
                <p className="text-xs text-slate-400">Registered Hosts</p>
                <p className="font-bold text-white">{hosts.length}</p>
             </div>
          </div>
          <div className="bg-slate-800 p-3 rounded-lg flex items-center gap-3">
             <Activity className="text-green-400" />
             <div>
                <p className="text-xs text-slate-400">Active Agents</p>
                <p className="font-bold text-white">{agents.filter(a => a.status === 'active').length}</p>
             </div>
          </div>
        </div>
      </header>

      <section className="mb-12">
        <div className="flex justify-between items-center mb-6">
            <h2 className="text-xl font-semibold text-slate-300">Active Agent Sessions</h2>
            <span className="text-xs text-slate-500 italic">Live telemetry from remote daemons</span>
        </div>
        {agents.filter(a => a.status === 'active').length === 0 ? (
            <div className="py-12 text-center bg-slate-800/30 rounded-2xl border border-dashed border-slate-700">
                <p className="text-slate-500 italic">No active sessions. Spawn one below from an online host.</p>
            </div>
        ) : (
            <div className="space-y-6">
              {(() => {
                const activeAgents = agents.filter(a => a.status === 'active');
                const hostIds = [...new Set(activeAgents.map(a => a.host_id))];
                return hostIds.map(hostId => {
                  const host = hosts.find(h => h.id === hostId);
                  const hostAgents = activeAgents.filter(a => a.host_id === hostId);
                  return (
                    <div key={hostId} className="bg-slate-800/40 rounded-2xl border border-slate-700 overflow-hidden">
                      <div className="flex items-center gap-3 px-6 py-3 bg-slate-800/80 border-b border-slate-700/50">
                        <Server size={16} className="text-slate-400" />
                        <span className="font-semibold text-white text-sm">{host?.name || 'Unknown Host'}</span>
                        {host?.status === 'online' ? (
                          <span className="inline-flex items-center gap-1 text-green-400 text-[10px] font-semibold uppercase">
                            <Wifi size={10} /> Online
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 text-slate-500 text-[10px] font-semibold uppercase">
                            <WifiOff size={10} /> Offline
                          </span>
                        )}
                        <span className="text-[10px] text-slate-500 ml-auto">{hostAgents.length} agent{hostAgents.length !== 1 ? 's' : ''}</span>
                      </div>
                      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 p-4">
                        {hostAgents.map(agent => {
                          const tel = agent.telemetry || {};
                          // Use context_tokens (per-call input tokens)
                          // for the progress bar — reflects current
                          // context window usage after compression.
                          // Fall back to cumulative tokens if context
                          // data is not yet available.
                          const ctxTokens = tel.context_tokens || tel.tokens || 0;
                          const contextMax = getContextWindow(tel.model, ctxTokens);
                          const tokenPct = ctxTokens ? Math.min((ctxTokens / contextMax) * 100, 100) : 0;
                          const mcpServers = tel.mcp_servers || [];
                          return (
                            <div key={agent.id} className={`bg-slate-800 rounded-2xl p-4 border border-slate-700 ${getToolColors(agent.tool_name).border} transition-all shadow-lg flex flex-col h-full group`}>
                              <div className="flex justify-between items-start mb-2">
                                <div className="overflow-hidden">
                                  <div className="flex gap-2 items-center">
                                      <span className={`text-[10px] px-2 py-0.5 rounded font-bold uppercase border ${getToolColors(agent.tool_name).badge}`}>
                                          {agent.tool_name || 'gemini'}
                                      </span>
                                      <h3 className="font-bold text-sm text-white truncate">{tel.git_project || 'Agent'}</h3>
                                  </div>
                                  <div className="flex items-center gap-3 mt-0.5 ml-0.5">
                                      {tel.git_branch && (
                                          <span className="flex items-center gap-1.5 text-[10px] text-slate-400 font-mono">
                                              <GitBranch size={10} /> {tel.git_branch}
                                          </span>
                                      )}
                                      {(tel.run_time_seconds || agent.started_at) && (
                                          <span className="flex items-center gap-1 text-[10px] text-slate-500 font-mono" title={tel.run_time_seconds ? 'Active time (CLI-reported)' : 'Elapsed since spawn'}>
                                              <Clock size={10} /> {formatDuration(tel.run_time_seconds, agent.started_at)}
                                          </span>
                                      )}
                                  </div>
                                </div>
                                <StatusIndicator status={tel.agent_status} />
                              </div>

                              {agent.tool_name !== 'bash' && (
                                  <div className="my-2 border-t border-slate-700/50 pt-2">
                                      <p className="text-[11px] text-slate-300 font-mono truncate">{tel.model || '...'}</p>
                                      <div className="mt-1.5">
                                          <div className="flex justify-between items-center mb-1">
                                              <span className="text-[9px] text-slate-500 uppercase font-bold tracking-tight">Context</span>
                                              <span className="text-[10px] text-slate-400 font-mono">
                                                  {ctxTokens ? ctxTokens.toLocaleString() : '0'} / {contextMax >= 1000000 ? `${(contextMax / 1000000).toFixed(1).replace('.0', '')}M` : `${(contextMax / 1000).toFixed(0)}k`}
                                              </span>
                                          </div>
                                          <div className="w-full h-2.5 bg-slate-700 rounded-full overflow-hidden">
                                              <div
                                                  className={`h-full rounded-full transition-all duration-500 ${getProgressColor(tokenPct)}`}
                                                  style={{ width: `${Math.max(tokenPct, 1)}%` }}
                                              />
                                          </div>
                                      </div>
                                  </div>
                              )}

                              {mcpServers.length > 0 && (
                                  <div className="flex items-center gap-1.5 text-[10px] text-slate-400 mb-2">
                                      <Plug size={10} className="text-slate-500 shrink-0" />
                                      <span className="truncate">MCP: {mcpServers.join(', ')}</span>
                                  </div>
                              )}

                              {(tel.current_activity || tel.task_description) && (
                                  <div className="bg-slate-900/50 p-2 rounded-lg mb-2 border border-slate-700/50">
                                      <p className="text-[11px] text-slate-300 line-clamp-2 leading-relaxed">
                                          <Info size={10} className="inline mr-1 text-slate-500" />
                                          {tel.current_activity || tel.task_description}
                                      </p>
                                  </div>
                              )}

                              <div className="flex gap-2 mt-auto pt-2">
                                  <button
                                      onClick={() => onAttach(agent.agent_id)}
                                      className="flex-1 bg-blue-600 hover:bg-blue-500 text-white font-bold py-2 rounded-xl transition-all shadow-md active:scale-95 flex items-center justify-center gap-2 text-sm cursor-pointer"
                                  >
                                      <Terminal size={16} /> Attach
                                  </button>
                                  <button
                                      onClick={(e) => {
                                          e.preventDefault();
                                          e.stopPropagation();
                                          handleStop(agent.agent_id);
                                      }}
                                      className="w-10 bg-red-600 hover:bg-red-500 text-white rounded-xl transition-colors flex items-center justify-center shadow-md active:scale-90 cursor-pointer"
                                      title="Stop Agent"
                                  >
                                      <Square size={14} fill="currentColor" />
                                  </button>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  );
                });
              })()}
            </div>
        )}
      </section>

      <section>
        <h2 className="text-xl font-semibold mb-4 text-slate-300">Registered Hosts</h2>
        <div className="overflow-x-auto bg-slate-800 rounded-xl border border-slate-700 shadow-xl">
          <table className="w-full text-left">
            <thead>
              <tr className="bg-slate-900/50 text-slate-400 text-[10px] font-bold uppercase tracking-widest border-b border-slate-700">
                <th className="p-4">Name</th>
                <th className="p-4">Status</th>
                <th className="p-4">Registered At</th>
                <th className="p-4">Actions</th>
              </tr>
            </thead>
            <tbody>
              {hosts.map(host => (
                <tr key={host.id} className="border-b border-slate-700/50 text-slate-300 hover:bg-slate-700/30 transition-colors">
                  <td className="p-4 font-medium">{host.name}</td>
                  <td className="p-4">
                      {host.status === 'online' ? (
                          <span className="inline-flex items-center gap-1.5 text-green-400 text-xs font-semibold uppercase">
                              <Wifi size={14} /> Online
                          </span>
                      ) : (
                          <span className="inline-flex items-center gap-1.5 text-slate-500 text-xs font-semibold uppercase">
                              <WifiOff size={14} /> Offline
                          </span>
                      )}
                  </td>
                  <td className="p-4 text-sm">{new Date(host.created_at).toLocaleString()}</td>
                  <td className="p-4">
                      <div className="flex gap-2">
                        <button 
                            onClick={() => setActiveSpawn({hostId: host.id, tool: 'gemini'})}
                            disabled={host.status !== 'online'}
                            className={`text-xs px-3 py-1.5 rounded-md border transition-colors flex items-center gap-1.5 ${
                                host.status === 'online' 
                                ? 'bg-blue-500/20 hover:bg-blue-500/40 text-blue-400 border-blue-500/30 cursor-pointer' 
                                : 'bg-slate-700/50 text-slate-500 border-slate-700 cursor-not-allowed'
                            }`}
                        >
                            <PlusCircle size={14} /> Spawn Gemini
                        </button>
                        <button 
                            onClick={() => setActiveSpawn({hostId: host.id, tool: 'claude'})}
                            disabled={host.status !== 'online'}
                            className={`text-xs px-3 py-1.5 rounded-md border transition-colors flex items-center gap-1.5 ${
                                host.status === 'online' 
                                ? 'bg-purple-500/20 hover:bg-purple-500/40 text-purple-400 border-purple-500/30 cursor-pointer' 
                                : 'bg-slate-700/50 text-slate-500 border-slate-700 cursor-not-allowed'
                            }`}
                        >
                            <PlusCircle size={14} /> Spawn Claude
                        </button>
                        <button 
                            onClick={() => setActiveSpawn({hostId: host.id, tool: 'bash'})}
                            disabled={host.status !== 'online'}
                            className={`text-xs px-3 py-1.5 rounded-md border transition-colors flex items-center gap-1.5 ${
                                host.status === 'online' 
                                ? 'bg-slate-700 hover:bg-slate-600 text-slate-300 border-slate-600 cursor-pointer' 
                                : 'bg-slate-700/50 text-slate-500 border-slate-700 cursor-not-allowed'
                            }`}
                        >
                            <PlusCircle size={14} /> Spawn Bash
                        </button>
                        <button 
                            onClick={() => handleDeleteHost(host.id)}
                            className="text-xs px-3 py-1.5 rounded-md border transition-colors flex items-center gap-1.5 bg-red-500/20 hover:bg-red-500/40 text-red-400 border-red-500/30 cursor-pointer ml-auto"
                            title="Delete Host"
                        >
                            <Trash2 size={14} /> Delete
                        </button>
                      </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {activeSpawn && (
          <SpawnModal 
            host={hosts.find(h => h.id === activeSpawn.hostId)!} 
            tool={activeSpawn.tool} 
            onClose={() => setActiveSpawn(null)}
            onSpawn={(dir, task, sessionMode) => handleSpawn(activeSpawn.hostId, activeSpawn.tool, dir, task, sessionMode)}
            onRefresh={requestProjects}
          />
      )}
    </div>
  );
};

export default Dashboard;
