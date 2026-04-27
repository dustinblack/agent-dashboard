import React, { useEffect, useState, useRef } from 'react';
import {
  getHosts,
  getAgents,
  spawnAgent,
  stopAgent,
  deleteHost,
  getVersion,
} from '../api';
import type { Host, Agent, VersionInfo } from '../api';
import { Cpu, Activity } from 'lucide-react';
import { io } from 'socket.io-client';
import LogoSvg from './LogoSvg';
import ThemeSelector from './ThemeSelector';
import SpawnModal from './dashboard/SpawnModal';
import HostCard from './dashboard/HostCard';

interface DashboardProps {
  onAttach: (agentId: string) => void;
}

const Dashboard: React.FC<DashboardProps> = ({ onAttach }) => {
  const [hosts, setHosts] = useState<Host[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [activeSpawn, setActiveSpawn] = useState<{
    hostId: number;
    tool: string;
  } | null>(null);
  const [versionInfo, setVersionInfo] = useState<VersionInfo | null>(null);
  const socketRef = useRef<ReturnType<typeof io> | null>(null);

  // Fetch version info on mount
  const appVersion = import.meta.env.VITE_APP_VERSION || 'dev';
  useEffect(() => {
    getVersion()
      .then(setVersionInfo)
      .catch(() => {}); // Degrade gracefully
  }, []);

  const projectsCache = useRef<Record<number, Host['projects']>>({});

  const fetchData = async () => {
    try {
      const [h, a] = await Promise.all([getHosts(), getAgents()]);
      const enrichedHosts = h.map((host) => ({
        ...host,
        projects: projectsCache.current[host.id] || host.projects,
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

  const handleSpawn = async (
    hostId: number,
    toolName: string,
    projectDir?: string,
    taskDescription?: string,
    sessionMode?: string,
    useWorktree?: boolean,
  ) => {
    try {
      const newAgent = await spawnAgent(
        hostId,
        toolName,
        projectDir,
        taskDescription,
        sessionMode,
        useWorktree,
      );
      setActiveSpawn(null);
      await fetchData();
      onAttach(newAgent.agent_id);
    } catch (err) {
      console.error('Failed to spawn agent:', err);
      alert('Failed to spawn agent. Check console for details.');
    }
  };

  const handleStop = async (agentId: string) => {
    if (!window.confirm('Are you sure you want to stop this agent?')) return;
    try {
      // Close the terminal popup window if it's open, before
      // stopping the agent, to prevent the auto-reconnect
      // from respawning it.
      const popup = window.open('', `agent_${agentId}`);
      if (popup && !popup.closed) {
        popup.close();
      }
      await stopAgent(agentId);
      setTimeout(fetchData, 500);
    } catch (err) {
      console.error('Failed to stop agent:', err);
    }
  };

  const handleDeleteHost = async (hostId: number) => {
    if (
      !window.confirm(
        'Are you sure you want to delete this host? All its agent sessions will also be removed.',
      )
    )
      return;
    try {
      await deleteHost(hostId);
      await fetchData();
    } catch (err) {
      console.error('Failed to delete host:', err);
      alert('Failed to delete host. Check console for details.');
    }
  };

  const requestProjects = () => {
    if (socketRef.current?.connected) {
      socketRef.current.emit('request_projects', {});
    }
  };

  useEffect(() => {
    fetchData();
    const baseURL =
      import.meta.env.VITE_API_URL || `http://${window.location.hostname}:8000`;
    const socket = io(`${baseURL}/terminal`, {
      path: '/socket.io',
    });
    socketRef.current = socket;

    socket.on('connect', () => {
      socket.emit('request_projects', {});
    });

    socket.on(
      'agent_status_update',
      (data: { agent_id: string; status: string }) => {
        if (data.status === 'closed' || data.status === 'stopped') {
          setAgents((prev) => prev.filter((a) => a.agent_id !== data.agent_id));
        } else {
          setAgents((prev) =>
            prev.map((a) =>
              a.agent_id === data.agent_id ? { ...a, status: data.status } : a,
            ),
          );
        }
      },
    );

    socket.on(
      'agent_telemetry_update',
      (data: { agent_id: string; telemetry: Agent['telemetry'] }) => {
        setAgents((prev) =>
          prev.map((a) =>
            a.agent_id === data.agent_id
              ? { ...a, telemetry: data.telemetry }
              : a,
          ),
        );
      },
    );

    socket.on(
      'host_telemetry_update',
      (data: { host_id: number; telemetry: Host['projects'] }) => {
        projectsCache.current[data.host_id] = data.telemetry;
        setHosts((prev) =>
          prev.map((h) =>
            h.id === data.host_id ? { ...h, projects: data.telemetry } : h,
          ),
        );
      },
    );

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

  // Sort hosts: online first, then alphabetical by name
  const activeAgents = agents.filter((a) => a.status === 'active');
  const sortedHosts = [...hosts].sort((a, b) => {
    if (a.status === 'online' && b.status !== 'online') return -1;
    if (a.status !== 'online' && b.status === 'online') return 1;
    return a.name.localeCompare(b.name);
  });

  if (loading)
    return <div className="p-8 text-slate-50">Loading dashboard...</div>;
  if (error)
    return (
      <div className="p-8">
        <div
          className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded relative"
          role="alert"
        >
          <strong className="font-bold">Error: </strong>
          <span className="block sm:inline">{error}</span>
          <div className="mt-2">
            <a
              href={
                import.meta.env.VITE_API_URL
                  ? `${import.meta.env.VITE_API_URL}/login`
                  : `http://${window.location.hostname}:8000/login`
              }
              className="underline font-bold"
            >
              Login via OIDC
            </a>
          </div>
        </div>
      </div>
    );

  return (
    <div className="max-w-7xl mx-auto p-8">
      <header className="mb-8 flex justify-between items-center">
        <h1 className="text-3xl font-bold flex items-center gap-3 text-slate-50">
          <LogoSvg className="w-9 h-9" />
          Agent Dashboard
          <span className="text-xs font-normal text-slate-500 font-mono self-end mb-0.5">
            {appVersion}
            {versionInfo?.update_available && versionInfo.latest && (
              <>
                {' '}
                <span className="text-slate-600">→</span>{' '}
                <a
                  href={versionInfo.latest_url || '#'}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-accent hover:underline"
                >
                  {versionInfo.latest} available
                </a>
              </>
            )}
            {!versionInfo?.update_available &&
              versionInfo?.is_dev &&
              versionInfo?.latest && (
                <>
                  {' '}
                  <span className="text-slate-600">·</span>{' '}
                  <a
                    href={versionInfo.latest_url || '#'}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-slate-500 hover:underline"
                  >
                    latest: {versionInfo.latest}
                  </a>
                </>
              )}
          </span>
        </h1>
        <div className="flex items-center gap-4">
          <ThemeSelector />
          <div className="bg-slate-800 p-3 rounded-lg flex items-center gap-3">
            <Cpu className="text-accent" />
            <div>
              <p className="text-xs text-slate-400">Registered Hosts</p>
              <p className="font-bold text-slate-50">{hosts.length}</p>
            </div>
          </div>
          <div className="bg-slate-800 p-3 rounded-lg flex items-center gap-3">
            <Activity className="text-green-400" />
            <div>
              <p className="text-xs text-slate-400">Active Agents</p>
              <p className="font-bold text-slate-50">{activeAgents.length}</p>
            </div>
          </div>
        </div>
      </header>

      <section>
        <div className="flex justify-between items-center mb-6">
          <h2 className="text-xl font-semibold text-slate-300">
            Registered Hosts & Active Sessions
          </h2>
          <span className="text-xs text-slate-500 italic">
            Live telemetry from remote daemons
          </span>
        </div>
        <div className="space-y-6">
          {sortedHosts.map((host) => (
            <HostCard
              key={host.id}
              host={host}
              agents={activeAgents.filter((a) => a.host_id === host.id)}
              onAttach={onAttach}
              onStop={handleStop}
              onSpawnClick={(hostId, tool) => setActiveSpawn({ hostId, tool })}
              onDeleteHost={handleDeleteHost}
            />
          ))}
        </div>
      </section>

      {activeSpawn && (
        <SpawnModal
          host={hosts.find((h) => h.id === activeSpawn.hostId)!}
          tool={activeSpawn.tool}
          activeAgents={activeAgents.filter(
            (a) => a.host_id === activeSpawn.hostId,
          )}
          onClose={() => setActiveSpawn(null)}
          onSpawn={(dir, task, sessionMode, useWorktree) =>
            handleSpawn(
              activeSpawn.hostId,
              activeSpawn.tool,
              dir,
              task,
              sessionMode,
              useWorktree,
            )
          }
          onRefresh={requestProjects}
        />
      )}
    </div>
  );
};

export default Dashboard;
