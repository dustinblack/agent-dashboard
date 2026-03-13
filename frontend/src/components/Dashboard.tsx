import React, { useEffect, useState } from 'react';
import { getMachines, getSessions } from '../api';
import type { Machine, Session } from '../api';
import { Terminal, Cpu, Clock, Activity } from 'lucide-react';

interface DashboardProps {
  onAttach: (sessionId: string) => void;
}

const Dashboard: React.FC<DashboardProps> = ({ onAttach }) => {
  const [machines, setMachines] = useState<Machine[]>([]);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = async () => {
    try {
      const [m, s] = await Promise.all([getMachines(), getSessions()]);
      setMachines(m);
      setSessions(s);
      setError(null);
    } catch (err) {
      setError('Failed to fetch dashboard data. Are you logged in?');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 5000); // Refresh every 5s
    return () => clearInterval(interval);
  }, []);

  if (loading) return <div className="p-8">Loading dashboard...</div>;
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
                <p className="text-xs text-slate-400">Machines</p>
                <p className="font-bold text-white">{machines.length}</p>
             </div>
          </div>
          <div className="bg-slate-800 p-3 rounded-lg flex items-center gap-3">
             <Activity className="text-green-400" />
             <div>
                <p className="text-xs text-slate-400">Active Sessions</p>
                <p className="font-bold text-white">{sessions.filter(s => s.status === 'active').length}</p>
             </div>
          </div>
        </div>
      </header>

      <section className="mb-8">
        <h2 className="text-xl font-semibold mb-4 text-slate-300">Active Sessions</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {sessions.filter(s => s.status === 'active').length === 0 && (
            <p className="text-slate-500 italic">No active sessions found.</p>
          )}
          {sessions.filter(s => s.status === 'active').map(session => {
            const machine = machines.find(m => m.id === session.machine_id);
            return (
              <div key={session.id} className="bg-slate-800 rounded-xl p-5 border border-slate-700 hover:border-blue-500 transition-colors">
                <div className="flex justify-between items-start mb-4">
                  <div>
                    <h3 className="font-bold text-lg text-white">{machine?.name || 'Unknown Machine'}</h3>
                    <p className="text-xs text-slate-400 font-mono">ID: {session.session_id.substring(0, 8)}...</p>
                  </div>
                  <span className="bg-green-500/10 text-green-400 text-xs px-2 py-1 rounded-full border border-green-500/20">
                    Active
                  </span>
                </div>
                <div className="flex items-center gap-2 text-slate-400 text-sm mb-4">
                  <Clock size={14} />
                  <span>Started: {new Date(session.started_at).toLocaleTimeString()}</span>
                </div>
                <button 
                  onClick={() => onAttach(session.session_id)}
                  className="w-full bg-blue-600 hover:bg-blue-500 text-white font-semibold py-2 rounded-lg transition-colors flex items-center justify-center gap-2"
                >
                  <Terminal size={18} /> Attach Terminal
                </button>
              </div>
            );
          })}
        </div>
      </section>

      <section>
        <h2 className="text-xl font-semibold mb-4 text-slate-300">Registered Machines</h2>
        <div className="overflow-x-auto bg-slate-800 rounded-xl border border-slate-700">
          <table className="w-full text-left">
            <thead>
              <tr className="border-b border-slate-700 text-slate-400 text-sm">
                <th className="p-4 font-semibold">Name</th>
                <th className="p-4 font-semibold">ID</th>
                <th className="p-4 font-semibold">Registered At</th>
              </tr>
            </thead>
            <tbody>
              {machines.map(machine => (
                <tr key={machine.id} className="border-b border-slate-700/50 text-slate-300 hover:bg-slate-700/30 transition-colors">
                  <td className="p-4 font-medium">{machine.name}</td>
                  <td className="p-4 font-mono text-xs">{machine.id}</td>
                  <td className="p-4 text-sm">{new Date(machine.created_at).toLocaleString()}</td>
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
