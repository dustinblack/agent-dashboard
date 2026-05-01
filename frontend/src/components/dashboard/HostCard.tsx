import React from 'react';
import { Server, Wifi, WifiOff, PlusCircle, Trash2 } from 'lucide-react';
import type { Host, Agent } from '../../api';
import { normalizeToolInfo } from '../../api';
import AgentSessionCard from './AgentSessionCard';
import { getToolColorsByKeyword } from './utils';

/** Props for the HostCard component. */
interface HostCardProps {
  host: Host;
  /** Pre-filtered active agents for this host. */
  agents: Agent[];
  onAttach: (agentId: string) => void;
  onStop: (agentId: string) => void;
  onSpawnClick: (hostId: number, tool: string) => void;
  onDeleteHost: (hostId: number) => void;
}

/**
 * Unified host card that combines host info, spawn/delete
 * controls, and active agent session cards in one view.
 * Offline hosts are muted with disabled spawn buttons.
 */
const HostCard: React.FC<HostCardProps> = ({
  host,
  agents,
  onAttach,
  onStop,
  onSpawnClick,
  onDeleteHost,
}) => {
  const isOnline = host.status === 'online';
  const availableTools = (host.projects?.available_tools || []).map(
    normalizeToolInfo,
  );

  return (
    <div
      className={`bg-slate-800/40 rounded-2xl border border-slate-700 overflow-hidden${isOnline ? '' : ' opacity-60'}`}
    >
      {/* Header */}
      <div className="px-6 py-3 bg-slate-800/80 border-b border-slate-700/50">
        {/* Row 1: Host info */}
        <div className="flex items-center gap-3">
          <Server size={16} className="text-slate-400" />
          <span className="font-semibold text-slate-50 text-sm">
            {host.name}
          </span>
          {isOnline ? (
            <span className="inline-flex items-center gap-1 text-green-400 text-[10px] font-semibold uppercase">
              <Wifi size={10} /> Online
            </span>
          ) : (
            <span className="inline-flex items-center gap-1 text-slate-500 text-[10px] font-semibold uppercase">
              <WifiOff size={10} /> Offline
            </span>
          )}
          <span className="text-[10px] text-slate-500">
            Registered: {new Date(host.created_at).toLocaleDateString()}
          </span>
          <span className="text-[10px] text-slate-500 ml-auto">
            {agents.length} agent
            {agents.length !== 1 ? 's' : ''}
          </span>
        </div>

        {/* Row 2: Spawn + Delete buttons */}
        <div className="flex items-center gap-2 mt-2">
          {availableTools.map((tool) => {
            const colors = getToolColorsByKeyword(tool.color);
            return (
              <button
                key={tool.name}
                onClick={() => onSpawnClick(host.id, tool.name)}
                disabled={!isOnline}
                className={`text-xs px-3 py-1.5 rounded-md border transition-colors flex items-center gap-1.5 ${
                  isOnline
                    ? `${colors.button} ${colors.buttonHover} cursor-pointer`
                    : 'bg-slate-700/50 text-slate-500 border-slate-700 cursor-not-allowed'
                }`}
              >
                <PlusCircle size={14} /> Spawn {tool.display_name}
              </button>
            );
          })}
          <button
            onClick={() => onDeleteHost(host.id)}
            className="text-xs px-3 py-1.5 rounded-md border transition-colors flex items-center gap-1.5 bg-red-500/20 hover:bg-red-500/40 text-red-400 border-red-500/30 cursor-pointer ml-auto"
            title="Delete Host"
          >
            <Trash2 size={14} /> Delete
          </button>
        </div>
      </div>

      {/* Body: Agent session cards or empty state */}
      {agents.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 p-4">
          {agents.map((agent) => (
            <AgentSessionCard
              key={agent.id}
              agent={agent}
              availableTools={availableTools}
              onAttach={onAttach}
              onStop={onStop}
            />
          ))}
        </div>
      ) : (
        <div className="px-6 py-3 text-sm text-slate-500 italic">
          No active sessions
        </div>
      )}
    </div>
  );
};

export default HostCard;
