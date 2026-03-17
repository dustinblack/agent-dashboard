import React, { useEffect, useState, useRef } from 'react';
import { getHosts, getAgents, spawnAgent, stopAgent, deleteHost } from '../api';
import type { Host, Agent } from '../api';
import { Terminal, Cpu, Activity, PlusCircle, Wifi, WifiOff, Square, GitBranch, Folder, Info, X, ChevronRight, RefreshCw, Trash2, Server } from 'lucide-react';
import { io } from 'socket.io-client';

interface DashboardProps {
  onAttach: (agentId: string) => void;
}

interface SpawnModalProps {
    host: Host;
    tool: string;
    onClose: () => void;
    onSpawn: (dir: string, task: string) => void;
    onRefresh: () => void;
}

const SpawnModal: React.FC<SpawnModalProps> = ({ host, tool, onClose, onSpawn, onRefresh }) => {
    const projects = host.projects?.available_projects || [];
    const [selectedProject, setSelectedProject] = useState('');
    const [task, setTask] = useState('');

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
                        onClick={() => onSpawn(selectedProject, task)}
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

  const handleSpawn = async (hostId: number, toolName: string, projectDir?: string, taskDescription?: string) => {
      try {
          const newAgent = await spawnAgent(hostId, toolName, projectDir, taskDescription);
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
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {agents.filter(a => a.status === 'active').length === 0 && (
            <div className="col-span-full py-12 text-center bg-slate-800/30 rounded-2xl border border-dashed border-slate-700">
                <p className="text-slate-500 italic">No active sessions. Spawn one below from an online host.</p>
            </div>
          )}
          {agents.filter(a => a.status === 'active').map(agent => {
            const host = hosts.find(h => h.id === agent.host_id);
            const tel = agent.telemetry || {};
            return (
              <div key={agent.id} className="bg-slate-800 rounded-2xl p-6 border border-slate-700 hover:border-blue-500/50 transition-all shadow-lg flex flex-col group">
                <div className="flex justify-between items-start mb-4">
                  <div className="overflow-hidden">
                    <h3 className="font-bold text-lg text-white truncate">{tel.git_project || host?.name || 'Agent'}</h3>
                    <div className="flex gap-2 items-center mt-1">
                        <span className="text-[10px] px-2 py-0.5 bg-blue-500/20 text-blue-400 rounded font-bold uppercase border border-blue-500/20">
                            {agent.tool_name || 'gemini'}
                        </span>
                        <span className="flex items-center gap-1 text-[10px] text-slate-400 font-mono" title="Host">
                            <Server size={10} /> {host?.name || 'Unknown Host'}
                        </span>
                        {tel.git_branch && (
                            <span className="flex items-center gap-1 text-[10px] text-slate-400 font-mono">
                                <GitBranch size={10} /> {tel.git_branch}
                            </span>
                        )}
                    </div>
                  </div>
                  <div className="flex items-center gap-1 px-2 py-0.5 bg-green-500/10 rounded-full border border-green-500/20">
                    <div className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse"></div>
                    <span className="text-green-400 text-[10px] font-bold uppercase tracking-wider">Live</span>
                  </div>
                </div>

                {tel.task_description && (
                    <div className="bg-slate-900/50 p-3 rounded-lg mb-4 border border-slate-700/50">
                        <p className="text-xs text-slate-300 line-clamp-3 leading-relaxed">
                            <Info size={12} className="inline mr-1.5 text-slate-500" />
                            {tel.task_description}
                        </p>
                    </div>
                )}

                {agent.tool_name !== 'bash' && (
                    <div className="grid grid-cols-2 gap-3 mb-6">
                        <div className="bg-slate-900/30 p-2 rounded border border-slate-700/30">
                            <p className="text-[9px] text-slate-500 uppercase font-bold tracking-tight">Model</p>
                            <p className="text-[11px] text-slate-200 font-mono truncate">{tel.model || '...'}</p>
                        </div>
                        <div className="bg-slate-900/30 p-2 rounded border border-slate-700/30">
                            <p className="text-[9px] text-slate-500 uppercase font-bold tracking-tight">Context Usage</p>
                            <p className="text-[11px] text-slate-200 font-mono truncate">{tel.tokens ? `${tel.tokens.toLocaleString()} tokens` : '...'}</p>
                        </div>
                    </div>
                )}
                
                <div className="flex gap-2 mt-auto">
                    <button 
                        onClick={() => onAttach(agent.agent_id)}
                        className="flex-1 bg-blue-600 hover:bg-blue-500 text-white font-bold py-2.5 rounded-xl transition-all shadow-md active:scale-95 flex items-center justify-center gap-2 text-sm cursor-pointer"
                    >
                        <Terminal size={18} /> Attach
                    </button>
                    <button 
                        onClick={(e) => {
                            e.preventDefault();
                            e.stopPropagation();
                            handleStop(agent.agent_id);
                        }}
                        className="w-12 bg-red-600 hover:bg-red-500 text-white rounded-xl transition-colors flex items-center justify-center shadow-md active:scale-90 cursor-pointer"
                        title="Stop Agent"
                    >
                        <Square size={16} fill="currentColor" />
                    </button>
                </div>
              </div>
            );
          })}
        </div>
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
            onSpawn={(dir, task) => handleSpawn(activeSpawn.hostId, activeSpawn.tool, dir, task)}
            onRefresh={requestProjects}
          />
      )}
    </div>
  );
};

export default Dashboard;
