import React from 'react';

/**
 * Displays a colored status badge for an agent session.
 * Renders working (green pulse), waiting_permission (red pulse),
 * idle (amber), or default live (green pulse) states.
 */
const StatusIndicator: React.FC<{ status?: string }> = ({ status }) => {
  switch (status) {
    case 'working':
      return (
        <div className="flex items-center gap-1 px-2 py-0.5 bg-green-500/10 rounded-full border border-green-500/20">
          <div className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse" />
          <span className="text-green-400 text-[10px] font-bold uppercase tracking-wider">
            Working
          </span>
        </div>
      );
    case 'waiting_permission':
      return (
        <div className="flex items-center gap-1 px-2 py-0.5 bg-red-500/15 rounded-full border border-red-500/30 animate-pulse">
          <div className="w-1.5 h-1.5 rounded-full bg-red-400 animate-pulse" />
          <span className="text-red-400 text-[10px] font-bold uppercase tracking-wider">
            Permission
          </span>
        </div>
      );
    case 'idle':
      return (
        <div className="flex items-center gap-1 px-2 py-0.5 bg-amber-500/10 rounded-full border border-amber-500/20">
          <div className="w-1.5 h-1.5 rounded-full bg-amber-400" />
          <span className="text-amber-400 text-[10px] font-bold uppercase tracking-wider">
            Idle
          </span>
        </div>
      );
    default:
      return (
        <div className="flex items-center gap-1 px-2 py-0.5 bg-green-500/10 rounded-full border border-green-500/20">
          <div className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse" />
          <span className="text-green-400 text-[10px] font-bold uppercase tracking-wider">
            Live
          </span>
        </div>
      );
  }
};

export default StatusIndicator;
