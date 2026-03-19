import React from "react";
import {
  Terminal,
  Activity,
  Square,
  GitBranch,
  Plug,
  Clock,
} from "lucide-react";
import type { Agent } from "../../api";
import {
  getContextWindow,
  getToolColors,
  getProgressColor,
  formatDuration,
} from "./utils";
import StatusIndicator from "./StatusIndicator";
import EditableTaskDescription from "./EditableTaskDescription";

/** Props for the AgentSessionCard component. */
interface AgentSessionCardProps {
  agent: Agent;
  onAttach: (agentId: string) => void;
  onStop: (agentId: string) => void;
}

/**
 * Renders a single active agent session as a card.
 * Displays tool badge, model info, context usage bar,
 * MCP servers, task description, and attach/stop buttons.
 */
const AgentSessionCard: React.FC<AgentSessionCardProps> = ({
  agent,
  onAttach,
  onStop,
}) => {
  const tel = agent.telemetry || {};
  // Use context_tokens (per-call input tokens) for the
  // progress bar -- reflects current context window usage
  // after compression. Fall back to cumulative tokens if
  // context data is not yet available.
  const ctxTokens = tel.context_tokens || tel.tokens || 0;
  const contextMax = getContextWindow(tel.model, ctxTokens);
  const tokenPct = ctxTokens
    ? Math.min((ctxTokens / contextMax) * 100, 100)
    : 0;
  const mcpServers = tel.mcp_servers || [];

  return (
    <div
      className={`bg-slate-800 rounded-2xl p-4 border border-slate-700 ${getToolColors(agent.tool_name).border} transition-all shadow-lg flex flex-col h-full group`}
    >
      <div className="flex justify-between items-start mb-2">
        <div className="overflow-hidden">
          <div className="flex gap-2 items-center">
            <span
              className={`text-[10px] px-2 py-0.5 rounded font-bold uppercase border ${getToolColors(agent.tool_name).badge}`}
            >
              {agent.tool_name || "gemini"}
            </span>
            <h3 className="font-bold text-sm text-slate-50 truncate">
              {tel.git_project || "Agent"}
            </h3>
          </div>
          <div className="flex items-center gap-3 mt-0.5 ml-0.5">
            {tel.git_branch && (
              <span className="flex items-center gap-1.5 text-[10px] text-slate-400 font-mono">
                <GitBranch size={10} /> {tel.git_branch}
              </span>
            )}
            {(tel.run_time_seconds || agent.started_at) && (
              <span
                className="flex items-center gap-1 text-[10px] text-slate-500 font-mono"
                title={
                  tel.run_time_seconds
                    ? "Active time (CLI-reported)"
                    : "Elapsed since spawn"
                }
              >
                <Clock size={10} />{" "}
                {formatDuration(tel.run_time_seconds, agent.started_at)}
              </span>
            )}
          </div>
        </div>
        <StatusIndicator status={tel.agent_status} />
      </div>

      {agent.tool_name !== "bash" && (
        <div className="my-2 border-t border-slate-700/50 pt-2">
          <p className="text-[11px] text-slate-300 font-mono truncate">
            {tel.model || "..."}
          </p>
          <div className="mt-1.5">
            <div className="flex justify-between items-center mb-1">
              <span className="text-[9px] text-slate-500 uppercase font-bold tracking-tight">
                Context
              </span>
              <span className="text-[10px] text-slate-400 font-mono">
                {ctxTokens ? ctxTokens.toLocaleString() : "0"} /{" "}
                {contextMax >= 1000000
                  ? `${(contextMax / 1000000).toFixed(1).replace(".0", "")}M`
                  : `${(contextMax / 1000).toFixed(0)}k`}
              </span>
            </div>
            <div className="w-full h-2.5 bg-slate-700 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all duration-500 ${getProgressColor(tokenPct)}`}
                style={{
                  width: `${Math.max(tokenPct, 1)}%`,
                }}
              />
            </div>
          </div>
        </div>
      )}

      {mcpServers.length > 0 && (
        <div className="flex items-center gap-1.5 text-[10px] text-slate-400 mb-2">
          <Plug size={10} className="text-slate-500 shrink-0" />
          <span className="truncate">MCP: {mcpServers.join(", ")}</span>
        </div>
      )}

      <div className="bg-slate-900/50 p-2 rounded-lg mb-2 border border-slate-700/50">
        <EditableTaskDescription
          agentId={agent.agent_id}
          description={tel.task_description || ""}
        />
        {tel.current_activity && (
          <p
            className={`text-[10px] text-slate-500 font-mono truncate${tel.task_description ? " mt-1 pt-1 border-t border-slate-700/30" : ""}`}
          >
            <Activity size={9} className="inline mr-1 text-slate-500" />
            {tel.current_activity}
          </p>
        )}
      </div>

      <div className="flex gap-2 mt-auto pt-2">
        <button
          onClick={() => onAttach(agent.agent_id)}
          className="flex-1 bg-accent hover:bg-accent-hover text-accent-text font-bold py-2 rounded-xl transition-all shadow-md active:scale-95 flex items-center justify-center gap-2 text-sm cursor-pointer"
        >
          <Terminal size={16} /> Attach
        </button>
        <button
          onClick={(e) => {
            e.preventDefault();
            e.stopPropagation();
            onStop(agent.agent_id);
          }}
          className="w-10 bg-red-600 hover:bg-red-500 text-slate-50 rounded-xl transition-colors flex items-center justify-center shadow-md active:scale-90 cursor-pointer"
          title="Stop Agent"
        >
          <Square size={14} fill="currentColor" />
        </button>
      </div>
    </div>
  );
};

export default AgentSessionCard;
