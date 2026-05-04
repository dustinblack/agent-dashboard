import React from 'react';
import {
  Terminal,
  Activity,
  Square,
  GitBranch,
  Plug,
  Clock,
  FolderOpen,
  ChevronRight,
  GitFork,
  TriangleAlert,
} from 'lucide-react';
import type { Agent, ToolInfo } from '../../api';
import {
  getContextWindow,
  getToolColors,
  getToolColorsByKeyword,
  getProgressColor,
  formatDuration,
  estimateCost,
  formatCost,
  formatTokenCount,
  isModelRecognized,
} from './utils';
import StatusIndicator from './StatusIndicator';
import EditableTaskDescription from './EditableTaskDescription';

/** Props for the AgentSessionCard component. */
interface AgentSessionCardProps {
  agent: Agent;
  /** Tool metadata from the host's available_tools list. */
  availableTools?: ToolInfo[];
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
  availableTools,
  onAttach,
  onStop,
}) => {
  const tel = agent.telemetry || {};
  // Prefer profile color from available_tools metadata,
  // falling back to name-based inference.
  const toolInfo = availableTools?.find((t) => t.name === agent.tool_name);
  const toolColors = toolInfo?.color
    ? getToolColorsByKeyword(toolInfo.color)
    : getToolColors(agent.tool_name);
  // Use context_tokens (per-call input tokens) for the
  // progress bar — reflects current context window usage
  // after compression. Do NOT fall back to cumulative
  // tokens, which would cause the dynamic scaling to keep
  // expanding and make the bar useless.
  const ctxTokens = tel.context_tokens || 0;
  const contextMax = getContextWindow(tel.model, ctxTokens);
  const tokenPct = ctxTokens
    ? Math.min((ctxTokens / contextMax) * 100, 100)
    : 0;
  const totalTokens = tel.tokens || 0;
  // Use OTLP-reported cost (Claude) or estimate from
  // pricing tables (Gemini / other).
  const displayCost =
    tel.cost_usd && tel.cost_usd > 0
      ? tel.cost_usd
      : estimateCost(
          tel.model,
          tel.input_tokens,
          tel.output_tokens,
          tel.cache_read_tokens,
          tel.cache_creation_tokens,
        );
  const costSource =
    tel.cost_usd && tel.cost_usd > 0
      ? 'Reported by CLI'
      : 'Estimated from token usage';
  const mcpServers = tel.mcp_servers || [];

  return (
    <div
      className={`bg-slate-800 rounded-2xl p-4 border border-slate-700 ${toolColors.border} transition-all shadow-lg flex flex-col h-full group`}
    >
      <div className="flex justify-between items-start mb-2">
        <div className="overflow-hidden">
          <div className="flex gap-2 items-center">
            <span
              className={`text-[10px] px-2 py-0.5 rounded font-bold uppercase border ${toolColors.badge}`}
            >
              {agent.tool_name || 'agent'}
            </span>
            {tel.git_remote_url ? (
              <a
                href={tel.git_remote_url}
                target="_blank"
                rel="noopener noreferrer"
                className="font-bold text-sm text-slate-50 truncate hover:underline"
              >
                {tel.git_project || 'Agent'}
              </a>
            ) : (
              <h3 className="font-bold text-sm text-slate-50 truncate">
                {tel.git_project || 'Agent'}
              </h3>
            )}
          </div>
          <div className="flex items-center gap-3 mt-0.5 ml-0.5">
            {tel.git_branch && (
              <span className="flex items-center gap-1.5 text-[10px] text-slate-400 font-mono">
                <GitBranch size={10} /> {tel.git_branch}
              </span>
            )}
            {tel.worktree_path && (
              <span
                className="flex items-center gap-1 text-[10px] text-amber-400/70 font-mono"
                title={`Worktree: ${tel.worktree_path}`}
              >
                <GitFork size={10} /> worktree
              </span>
            )}
            {(tel.run_time_seconds || agent.started_at) && (
              <span
                className="flex items-center gap-1 text-[10px] text-slate-500 font-mono"
                title={
                  tel.run_time_seconds
                    ? 'Active time (CLI-reported)'
                    : 'Elapsed since spawn'
                }
              >
                <Clock size={10} />{' '}
                {formatDuration(tel.run_time_seconds, agent.started_at)}
              </span>
            )}
          </div>
        </div>
        <StatusIndicator status={tel.agent_status} />
      </div>

      {tel.model && tel.model !== 'detecting...' && (
        <div className="my-2 border-t border-slate-700/50 pt-2">
          <div className="flex items-center gap-1">
            <p className="text-[11px] text-slate-300 font-mono truncate">
              {tel.model || '...'}
            </p>
            {tel.model && !isModelRecognized(tel.model) && (
              <span title="Unrecognized model — context window and pricing may be inaccurate">
                <TriangleAlert size={12} className="text-amber-400 shrink-0" />
              </span>
            )}
          </div>
          <div className="mt-1.5">
            <div className="flex justify-between items-center mb-1">
              <span className="text-[9px] text-slate-500 uppercase font-bold tracking-tight">
                Context
              </span>
              <span className="text-[10px] text-slate-400 font-mono">
                {ctxTokens ? ctxTokens.toLocaleString() : '0'} /{' '}
                {contextMax >= 1000000
                  ? `${(contextMax / 1000000).toFixed(1).replace('.0', '')}M`
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
          {/* Total tokens + cost row */}
          <div className="flex justify-between items-center mt-2 pt-1.5 border-t border-slate-700/30">
            <span
              className="text-[10px] text-slate-400 font-mono"
              title={costSource}
            >
              {formatCost(displayCost)}
            </span>
            <span className="text-[10px] text-slate-400 font-mono">
              {totalTokens
                ? `${formatTokenCount(totalTokens)} tokens`
                : '0 tokens'}
            </span>
          </div>
          {/* Input/output breakdown */}
          {tel.input_tokens || tel.output_tokens ? (
            <p className="text-[9px] text-slate-500 font-mono text-right mt-0.5">
              {tel.input_tokens
                ? formatTokenCount(tel.input_tokens) + ' in'
                : ''}
              {tel.input_tokens && tel.output_tokens ? ' / ' : ''}
              {tel.output_tokens
                ? formatTokenCount(tel.output_tokens) + ' out'
                : ''}
            </p>
          ) : null}
        </div>
      )}

      {mcpServers.length > 0 && (
        <div className="flex items-center gap-1.5 text-[10px] text-slate-400 mb-2">
          <Plug size={10} className="text-slate-500 shrink-0" />
          <span className="truncate">MCP: {mcpServers.join(', ')}</span>
        </div>
      )}

      <div className="bg-slate-900/50 p-2 rounded-lg mb-2 border border-slate-700/50 mt-auto">
        <EditableTaskDescription
          agentId={agent.agent_id}
          description={tel.task_description || ''}
        />
        {tel.last_cmd !== undefined || tel.last_exit_code !== undefined ? (
          <>
            {tel.current_activity && (
              <p
                className={`text-[10px] text-slate-500 font-mono truncate${tel.task_description ? ' mt-1 pt-1 border-t border-slate-700/30' : ''}`}
              >
                <FolderOpen size={9} className="inline mr-1" />
                {tel.current_activity}
              </p>
            )}
            {tel.last_cmd && (
              <p className="text-[10px] text-slate-500 font-mono truncate mt-0.5 flex items-center gap-0.5">
                <ChevronRight size={9} className="shrink-0" />
                <span className="truncate">{tel.last_cmd}</span>
                {tel.last_exit_code != null && tel.last_exit_code !== 0 && (
                  <span className="ml-1 px-1 py-px bg-red-500/20 text-red-400 text-[9px] font-bold rounded shrink-0">
                    E{tel.last_exit_code}
                  </span>
                )}
              </p>
            )}
          </>
        ) : (
          tel.current_activity && (
            <p
              className={`text-[10px] text-slate-500 font-mono truncate${tel.task_description ? ' mt-1 pt-1 border-t border-slate-700/30' : ''}`}
            >
              <Activity size={9} className="inline mr-1 text-slate-500" />
              {tel.current_activity}
            </p>
          )
        )}
      </div>

      <div className="flex gap-2 pt-2">
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
