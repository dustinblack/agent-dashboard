import React, { useEffect, useState } from 'react';
import { getHosts, getAgents, spawnAgent, stopAgent } from '../api';
import type { Host, Agent } from '../api';
import { Terminal, Cpu, Clock, Activity, PlusCircle, Wifi, WifiOff, Square } from 'lucide-react';
import { io } from 'socket.io-client';

interface DashboardProps {
  onAttach: (agentId: string) => void;
}

const Dashboard: React.FC<DashboardProps> = ({ onAttach }) => {
  const [hosts, setHosts] = useState<Host[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = async () => {
    try {
      const [h, a] = await Promise.all([getHosts(), getAgents()]);
      setHosts(h);
      setAgents(a);
      setError(null);
    } catch (err) {
      setError('Failed to fetch dashboard data. Are you logged in?');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleSpawn = async (hostId: number, toolName: string) => {
      try {
          const newAgent = await spawnAgent(hostId, toolName);
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
          // Give the system a moment to sync before refreshing the UI
          setTimeout(fetchData, 500);
      } catch (err) {
          console.error("Failed to stop agent:", err);
      }
  };

  useEffect(() => {
    fetchData();
    
    // Set up Socket.IO listener for real-time status updates
    const baseURL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
    const socket = io(`${baseURL}/terminal`, { path: '/socket.io' });
    
    socket.on('agent_status_update', (data: { agent_id: string, status: string }) => {
        if (data.status === 'closed') {
            setAgents(prev => prev.filter(a => a.agent_id !== data.agent_id));
        } else {
            setAgents(prev => prev.map(a => 
                a.agent_id === data.agent_id ? { ...a, status: data.status } : a
            ));
        }
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
          <a href="http://localhost:8000/login" className="underline font-bold">Login via OIDC</a>
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

      <section className="mb-8">
        <div className="flex justify-between items-center mb-4">
            <h2 className="text-xl font-semibold text-slate-300">Active Agents</h2>
            <span className="text-xs text-slate-500 italic">Multiplexed across connected hosts</span>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {agents.filter(a => a.status === 'active').length === 0 && (
            <p className="text-slate-500 italic">No active agents found. Spawn one below from an online host.</p>
          )}
          {agents.filter(a => a.status === 'active').map(agent => {
            const host = hosts.find(h => h.id === agent.host_id);
            return (
              <div key={agent.id} className="bg-slate-800 rounded-xl p-5 border border-slate-700 hover:border-blue-500 transition-colors flex flex-col">
                <div className="flex justify-between items-start mb-4">
                  <div>
                    <h3 className="font-bold text-lg text-white">{host?.name || 'Unknown Host'}</h3>
                    <div className="flex gap-2 items-center mt-1">
                        <span className="text-xs px-2 py-0.5 bg-slate-700 text-slate-300 rounded font-mono uppercase">
                            {agent.tool_name || 'gemini'}
                        </span>
                        <p className="text-xs text-slate-400 font-mono">ID: {agent.agent_id.substring(0, 8)}...</p>
                    </div>
                  </div>
                  <span className="bg-green-500/10 text-green-400 text-xs px-2 py-1 rounded-full border border-green-500/20">
                    Active
                  </span>
                </div>
                <div className="flex items-center gap-2 text-slate-400 text-sm mb-4">
                  <Clock size={14} />
                  <span>Started: {new Date(agent.started_at).toLocaleTimeString()}</span>
                </div>
                <div className="flex gap-2 mt-auto">
                    <button 
                        onClick={() => onAttach(agent.agent_id)}
                        className="flex-1 bg-blue-600 hover:bg-blue-500 text-white font-semibold py-2 rounded-lg transition-colors flex items-center justify-center gap-2 cursor-pointer"
                    >
                        <Terminal size={18} /> Attach
                    </button>
                    <button 
                        onClick={(e) => {
                            e.preventDefault();
                            e.stopPropagation();
                            handleStop(agent.agent_id);
                        }}
                        className="px-4 bg-red-600 hover:bg-red-500 text-white rounded-lg transition-colors flex items-center justify-center cursor-pointer"
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
        <div className="overflow-x-auto bg-slate-800 rounded-xl border border-slate-700">
          <table className="w-full text-left">
            <thead>
              <tr className="border-b border-slate-700 text-slate-400 text-sm">
                <th className="p-4 font-semibold">Name</th>
                <th className="p-4 font-semibold">Status</th>
                <th className="p-4 font-semibold">Registered At</th>
                <th className="p-4 font-semibold">Actions</th>
              </tr>
            </thead>
            <tbody>
              {hosts.map(host => (
                <tr key={host.id} className="border-b border-slate-700/50 text-slate-300 hover:bg-slate-700/30 transition-colors">
                  <td className="p-4 font-medium">{host.name}</td>
                  <td className="p-4">
                      {host.status === 'online' ? (
                          <span className="flex items-center gap-1.5 text-green-400 text-xs font-semibold uppercase">
                              <Wifi size={14} /> Online
                          </span>
                      ) : (
                          <span className="flex items-center gap-1.5 text-slate-500 text-xs font-semibold uppercase">
                              <WifiOff size={14} /> Offline
                          </span>
                      )}
                  </td>
                  <td className="p-4 text-sm">{new Date(host.created_at).toLocaleString()}</td>
                  <td className="p-4">
                      <div className="flex gap-2">
                        <button 
                            onClick={() => handleSpawn(host.id, 'gemini')}
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
                            onClick={() => handleSpawn(host.id, 'claude')}
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
                            onClick={() => handleSpawn(host.id, 'bash')}
                            disabled={host.status !== 'online'}
                            className={`text-xs px-3 py-1.5 rounded-md border transition-colors flex items-center gap-1.5 ${
                                host.status === 'online' 
                                ? 'bg-slate-700 hover:bg-slate-600 text-slate-300 border-slate-600 cursor-pointer' 
                                : 'bg-slate-700/50 text-slate-500 border-slate-700 cursor-not-allowed'
                            }`}
                        >
                            <PlusCircle size={14} /> Spawn Bash
                        </button>
                      </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
};

export default Dashboard;
