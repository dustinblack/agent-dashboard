import React, { useEffect, useRef, useState, useCallback } from 'react';
import { Terminal as XTerm } from '@xterm/xterm';
import { FitAddon } from '@xterm/addon-fit';
import { io, Socket } from 'socket.io-client';
import {
  XCircle,
  GitBranch,
  GitFork,
  Monitor,
  TerminalSquare,
  ExternalLink,
  RefreshCw,
} from 'lucide-react';
import '@xterm/xterm/css/xterm.css';
import type { AgentDetail, Agent, ToolInfo } from '../api';
import {
  getAgentDetails,
  getCompanions,
  spawnAgent,
  stopAgent,
  normalizeToolInfo,
} from '../api';
import { getToolColorsByKeyword } from './dashboard/utils';

interface TerminalProps {
  agentId: string;
  onClose: () => void;
}

/** Canonical tool type buckets */
type ToolCategory = 'gemini' | 'claude' | 'bash' | 'unknown';

function categorize(toolName?: string): ToolCategory {
  if (!toolName) return 'unknown';
  const t = toolName.toLowerCase();
  if (t.includes('gemini')) return 'gemini';
  if (t.includes('claude')) return 'claude';
  if (t.includes('bash') || t.includes('shell')) return 'bash';
  return 'unknown';
}

const TOOL_COLORS: Record<ToolCategory, string> = {
  gemini: 'bg-blue-500',
  claude: 'bg-purple-500',
  bash: 'bg-slate-500',
  unknown: 'bg-slate-500',
};

const TOOL_LABELS: Record<ToolCategory, string> = {
  gemini: 'Gemini',
  claude: 'Claude',
  bash: 'Bash',
  unknown: 'Agent',
};

/** Open (or focus) a terminal popup window for the given agent. */
function openTerminalWindow(agentId: string) {
  const width = 1024;
  const height = 768;
  const left = (window.screen.width - width) / 2;
  const top = (window.screen.height - height) / 2;
  window.open(
    `/terminal/${agentId}`,
    `agent_${agentId}`,
    `width=${width},height=${height},left=${left},top=${top},menubar=no,toolbar=no,location=no,status=no,personalbar=no`,
  );
}

const Terminal: React.FC<TerminalProps> = ({ agentId, onClose }) => {
  const terminalRef = useRef<HTMLDivElement>(null);
  const xtermRef = useRef<XTerm | null>(null);
  const socketRef = useRef<Socket | null>(null);
  const isReplaying = useRef<boolean>(false);

  const [agentDetail, setAgentDetail] = useState<AgentDetail | null>(null);
  const [companions, setCompanions] = useState<Agent[]>([]);
  const [spawning, setSpawning] = useState(false);

  // Stale session reconnect state
  const [sessionLost, setSessionLost] = useState(false);
  const [reconnecting, setReconnecting] = useState(false);
  const [reconnectError, setReconnectError] = useState<string | null>(null);
  const reconnectingRef = useRef(false);
  const historyTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Fetch agent details on mount
  useEffect(() => {
    getAgentDetails(agentId)
      .then(setAgentDetail)
      .catch((err) => console.error('Failed to fetch agent details:', err));
  }, [agentId]);

  // Fetch companions on mount + poll every 10s
  useEffect(() => {
    const fetchCompanions = () => {
      getCompanions(agentId)
        .then(setCompanions)
        .catch((err) => console.error('Failed to fetch companions:', err));
    };
    fetchCompanions();
    const interval = setInterval(fetchCompanions, 10_000);
    return () => clearInterval(interval);
  }, [agentId]);

  // Auto-reconnect when a stale session is detected:
  // stop the old agent record, spawn a replacement with
  // resume mode, and navigate to the new terminal.
  useEffect(() => {
    if (!sessionLost || reconnecting || reconnectError) return;
    if (!agentDetail) return;

    const reconnect = async () => {
      setReconnecting(true);
      reconnectingRef.current = true;
      try {
        // Stop the stale agent record (ignore errors —
        // it may already be cleaned up)
        await stopAgent(agentId).catch(() => {});

        // Spawn a new agent with the same parameters,
        // using resume mode for session continuity.
        // If the stale session was in a worktree, use
        // the worktree path so the agent resumes in the
        // same isolated directory with its branch and
        // uncommitted work intact.
        const projectDir =
          agentDetail.telemetry?.worktree_path ||
          agentDetail.telemetry?.project_dir;
        const newAgent = await spawnAgent(
          agentDetail.host_id,
          agentDetail.tool_name || 'bash',
          projectDir,
          agentDetail.telemetry?.task_description,
          'resume',
        );

        // Navigate to the new agent's terminal and update
        // the window name so the dashboard's window.open()
        // can find and focus this popup instead of opening
        // a duplicate
        window.name = `agent_${newAgent.agent_id}`;
        window.location.replace(`/terminal/${newAgent.agent_id}`);
      } catch (err) {
        console.error('Reconnect failed:', err);
        setReconnectError('Failed to reconnect — the host may be offline.');
        setReconnecting(false);
      }
    };
    reconnect();
  }, [agentId, sessionLost, agentDetail, reconnecting, reconnectError]);

  // Listen for live telemetry updates to keep header fresh
  useEffect(() => {
    if (!socketRef.current) return;
    const handler = (data: {
      agent_id: string;
      telemetry: Record<string, unknown>;
    }) => {
      if (data.agent_id === agentId && agentDetail) {
        setAgentDetail((prev) =>
          prev
            ? { ...prev, telemetry: { ...prev.telemetry, ...data.telemetry } }
            : prev,
        );
      }
    };
    socketRef.current.on('agent_telemetry_update', handler);
    return () => {
      socketRef.current?.off('agent_telemetry_update', handler);
    };
  }, [agentId, agentDetail]);

  // Companion button handler
  const handleOpenCompanion = useCallback(
    async (targetTool: string) => {
      // Check existing companions for matching tool
      const existing = companions.find((c) => c.tool_name === targetTool);
      if (existing) {
        openTerminalWindow(existing.agent_id);
        return;
      }

      if (!agentDetail || spawning) return;
      setSpawning(true);
      try {
        // Use the worktree path if present so the
        // companion inherits the same working directory
        // as the parent agent (worktree or original).
        const projectDir =
          agentDetail.telemetry?.worktree_path ||
          agentDetail.telemetry?.project_dir;
        const spawned = await spawnAgent(
          agentDetail.host_id,
          targetTool,
          projectDir,
          undefined, // taskDescription
          undefined, // sessionMode
          false, // useWorktree — share parent's directory
        );
        openTerminalWindow(spawned.agent_id);
      } catch (err) {
        console.error('Failed to spawn companion:', err);
      } finally {
        setSpawning(false);
      }
    },
    [companions, agentDetail, spawning],
  );

  // xterm + socket setup
  useEffect(() => {
    if (!terminalRef.current) return;

    const term = new XTerm({
      cursorBlink: true,
      // Cap scrollback to limit memory growth in long
      // sessions. Agent output with heavy escape sequences
      // (cursor movement, progress bars, color codes) can
      // consume orders of magnitude more memory per line
      // than plain text.
      scrollback: 2000,
      theme: {
        background: '#000000',
        foreground: '#f1f5f9',
        cursor: '#60a5fa',
        selectionBackground: '#334155',
      },
      fontFamily:
        'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace',
      fontSize: 14,
      allowProposedApi: true,
    });

    const fitAddon = new FitAddon();
    term.loadAddon(fitAddon);
    term.open(terminalRef.current);
    fitAddon.fit();
    term.focus();

    // --- Scroll position tracking ---
    // Track whether the viewport is scrolled to the bottom
    // so we can restore position after fitAddon.fit()
    // reflows the buffer.
    let isAtBottom = true;
    term.onScroll(() => {
      const buf = term.buffer.active;
      isAtBottom = buf.viewportY >= buf.baseY;
    });

    // --- Resize handling ---
    // Debounce fitAddon.fit() to prevent rapid-fire calls
    // during layout transitions. The fit runs immediately
    // after the debounce settles — no streaming deferral,
    // which could block fits indefinitely under high
    // latency and cause black screens.
    const performFit = () => {
      if (!terminalRef.current) return;
      try {
        const wasAtBottom = isAtBottom;
        fitAddon.fit();
        if (wasAtBottom) {
          term.scrollToBottom();
        }
        if (socketRef.current?.connected) {
          socketRef.current.emit('terminal_resize', {
            sid: agentId,
            cols: term.cols,
            rows: term.rows,
          });
        }
      } catch (e) {
        console.error('Fit failed:', e);
      }
    };

    let resizeTimer: ReturnType<typeof setTimeout> | null = null;
    const RESIZE_DEBOUNCE_MS = 150;
    const debouncedFit = () => {
      if (resizeTimer) clearTimeout(resizeTimer);
      resizeTimer = setTimeout(performFit, RESIZE_DEBOUNCE_MS);
    };

    window.addEventListener('resize', debouncedFit);

    // Re-render the terminal when the tab/window regains
    // focus — xterm.js canvas may not update while hidden.
    const onVisibilityChange = () => {
      if (!document.hidden) {
        requestAnimationFrame(performFit);
      }
    };
    document.addEventListener('visibilitychange', onVisibilityChange);
    window.addEventListener('focus', () => {
      requestAnimationFrame(performFit);
    });

    let resizeObserver: ResizeObserver | null = null;
    if (terminalRef.current) {
      resizeObserver = new ResizeObserver(debouncedFit);
      resizeObserver.observe(terminalRef.current);
    }

    requestAnimationFrame(performFit);
    xtermRef.current = term;

    // --- Touch scrolling ---
    // xterm.js intercepts touch events with {passive: false}
    // and calls preventDefault(), blocking the browser's
    // native scroll.  We attach our own handler on the
    // xterm-screen element (capture phase) to translate
    // vertical swipe gestures into term.scrollLines() calls.
    let touchStartY: number | null = null;
    let touchAccum = 0;
    const LINE_HEIGHT_PX = 18; // approx pixel height per row

    const onTouchStart = (e: TouchEvent) => {
      if (e.touches.length === 1) {
        touchStartY = e.touches[0].clientY;
        touchAccum = 0;
      }
    };
    const onTouchMove = (e: TouchEvent) => {
      if (touchStartY === null || e.touches.length !== 1) return;
      const deltaY = touchStartY - e.touches[0].clientY;
      touchStartY = e.touches[0].clientY;
      touchAccum += deltaY;

      const lines = Math.trunc(touchAccum / LINE_HEIGHT_PX);
      if (lines !== 0) {
        term.scrollLines(lines);
        touchAccum -= lines * LINE_HEIGHT_PX;
      }
      // Prevent the page itself from scrolling
      e.preventDefault();
    };
    const onTouchEnd = () => {
      touchStartY = null;
      touchAccum = 0;
    };

    // Attach to the .xterm-screen element inside our
    // container so we capture touches before xterm's own
    // handler can preventDefault() on them.
    const screenEl =
      terminalRef.current?.querySelector<HTMLElement>('.xterm-screen');
    if (screenEl) {
      screenEl.addEventListener('touchstart', onTouchStart, {
        passive: true,
      });
      screenEl.addEventListener('touchmove', onTouchMove, {
        passive: false,
      });
      screenEl.addEventListener('touchend', onTouchEnd, {
        passive: true,
      });
    }

    // --- Output batching ---
    // Buffer rapid successive terminal_output events and
    // flush them in a single term.write() per animation
    // frame. Uses the write callback so xterm signals
    // when processing is complete.
    let outputBuffer = '';
    let rafId: number | null = null;
    const flushOutput = () => {
      rafId = null;
      if (outputBuffer) {
        const chunk = outputBuffer;
        outputBuffer = '';
        term.write(chunk);
      }
    };

    // Buffer history chunks and write them all at once on
    // history_complete to avoid per-chunk scroll jumping
    // during replay.
    let historyBuffer: string[] = [];

    // Socket.IO
    const baseURL =
      import.meta.env.VITE_API_URL || `http://${window.location.hostname}:8000`;
    const socket = io(`${baseURL}/terminal`, {
      path: '/socket.io',
    });
    socketRef.current = socket;

    socket.on('connect', () => {
      isReplaying.current = true;
      historyBuffer = [];
      socket.emit('join_room', { room: agentId });
      performFit();

      // Detect stale sessions: if history never completes
      // within 5s, the daemon likely no longer has this agent
      if (historyTimeoutRef.current) clearTimeout(historyTimeoutRef.current);
      historyTimeoutRef.current = setTimeout(() => {
        if (isReplaying.current) {
          setSessionLost(true);
          isReplaying.current = false;
        }
      }, 5000);
    });

    socket.on('history_complete', (data: { agent_id: string }) => {
      if (data.agent_id === agentId) {
        // History arrived — session is alive, cancel
        // the stale detection timeout
        if (historyTimeoutRef.current) clearTimeout(historyTimeoutRef.current);

        // Write all buffered history in one call
        if (historyBuffer.length > 0) {
          term.write(historyBuffer.join(''));
          historyBuffer = [];
        }
        isReplaying.current = false;
        performFit();
      }
    });

    socket.on('terminal_output', (data: { sid: string; output: string }) => {
      if (data.sid !== agentId) return;
      if (isReplaying.current) {
        // Collect history chunks for batched write
        historyBuffer.push(data.output);
      } else {
        // Buffer live output and flush per animation frame
        outputBuffer += data.output;
        if (rafId === null) {
          rafId = requestAnimationFrame(flushOutput);
        }
      }
    });

    // Handle agent lifecycle events. "stopped" means the
    // user intentionally stopped the agent — close the
    // terminal window. "closed" means a daemon-side
    // disconnect — trigger auto-reconnect.
    socket.on(
      'agent_status_update',
      (data: { agent_id: string; status: string }) => {
        if (data.agent_id !== agentId) return;
        if (data.status === 'stopped' && !reconnectingRef.current) {
          // User-initiated stop — close the window
          // instead of auto-reconnecting. Skip if
          // we're reconnecting (our own stopAgent call
          // triggers this event).
          window.close();
        } else if (data.status === 'closed') {
          setSessionLost(true);
          isReplaying.current = false;
        }
      },
    );

    // Filter terminal responses (like DA — Device Attributes)
    // from user input before relaying to the daemon. xterm.js
    // responds to DA queries (ESC [ c) from the remote process
    // with ESC [ ? ... c, which flows back through onData.
    // Some CLIs (Gemini) capture this response as stdin input,
    // showing "1;2c" in the prompt.
    // eslint-disable-next-line no-control-regex
    const DA_RESPONSE = /\x1b\[\?[\d;]*c/;
    term.onData((data) => {
      if (!isReplaying.current) {
        const filtered = data.replace(DA_RESPONSE, '');
        if (filtered) {
          socket.emit('terminal_input', {
            target_sid: agentId,
            input: filtered,
          });
        }
      }
    });

    return () => {
      window.removeEventListener('resize', debouncedFit);
      document.removeEventListener('visibilitychange', onVisibilityChange);
      if (resizeTimer) clearTimeout(resizeTimer);
      if (rafId !== null) cancelAnimationFrame(rafId);
      if (historyTimeoutRef.current) clearTimeout(historyTimeoutRef.current);
      resizeObserver?.disconnect();
      if (screenEl) {
        screenEl.removeEventListener('touchstart', onTouchStart);
        screenEl.removeEventListener('touchmove', onTouchMove);
        screenEl.removeEventListener('touchend', onTouchEnd);
      }
      socket.disconnect();
      term.dispose();
    };
  }, [agentId]);

  // Derived header values
  const category = categorize(agentDetail?.tool_name);
  const hostName = agentDetail?.host_name;
  const gitProject = agentDetail?.telemetry?.git_project;
  const gitBranch = agentDetail?.telemetry?.git_branch;
  const gitRemoteUrl = agentDetail?.telemetry?.git_remote_url;
  const worktreePath = agentDetail?.telemetry?.worktree_path;

  // Build tool info from available_tools on this host.
  const allTools: ToolInfo[] = (agentDetail?.available_tools || []).map(
    normalizeToolInfo,
  );

  // Prefer display_name from profile metadata over the
  // hardcoded label map for the tool badge and title.
  const profileInfo = allTools.find((t) => t.name === agentDetail?.tool_name);
  const toolLabel = profileInfo?.display_name || TOOL_LABELS[category];
  const toolBadgeColor = profileInfo?.color
    ? getToolColorsByKeyword(profileInfo.color).solid
    : TOOL_COLORS[category];

  // Companion buttons: all other tools on this host.
  const companionButtons = allTools
    .filter((t) => t.name !== agentDetail?.tool_name)
    .map((t) => ({ label: t.display_name, tool: t.name, color: t.color }));

  // Update browser window title with host / project / branch
  useEffect(() => {
    const parts = [toolLabel];
    if (hostName) parts.push(hostName);
    if (gitProject) parts.push(gitProject);
    if (gitBranch) parts.push(gitBranch);
    if (worktreePath) parts.push('worktree');
    document.title = parts.join(' · ');
    return () => {
      document.title = 'Agent Dashboard';
    };
  }, [toolLabel, hostName, gitProject, gitBranch, worktreePath]);

  return (
    <div className="flex-1 flex flex-col h-full w-full bg-black overflow-hidden">
      {/* Header Bar */}
      <div className="h-12 flex items-center justify-between bg-slate-800 border-b border-slate-700 px-4 shrink-0 overflow-hidden">
        {/* Left side: tool badge + context */}
        <div className="flex items-center gap-3 min-w-0">
          {/* Tool badge */}
          <span
            className={`${toolBadgeColor} text-white text-[10px] font-bold uppercase px-2 py-0.5 rounded tracking-wider shrink-0`}
          >
            {toolLabel}
          </span>

          {/* Host / project / branch */}
          <div className="flex items-center gap-2 text-xs text-slate-300 font-mono truncate">
            {hostName && (
              <>
                <Monitor size={12} className="text-slate-400 shrink-0" />
                <span className="text-slate-200">{hostName}</span>
              </>
            )}
            {gitProject && (
              <>
                <span className="text-slate-600">/</span>
                {gitRemoteUrl ? (
                  <a
                    href={gitRemoteUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-white font-semibold hover:underline"
                  >
                    {gitProject}
                  </a>
                ) : (
                  <span className="text-white font-semibold">{gitProject}</span>
                )}
              </>
            )}
            {gitBranch && (
              <>
                <GitBranch
                  size={12}
                  className="text-emerald-400 shrink-0 ml-1"
                />
                {gitRemoteUrl ? (
                  <a
                    href={`${gitRemoteUrl}/tree/${gitBranch}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-emerald-300 hover:underline"
                  >
                    {gitBranch}
                  </a>
                ) : (
                  <span className="text-emerald-300">{gitBranch}</span>
                )}
              </>
            )}
            {worktreePath && (
              <>
                <GitFork size={12} className="text-amber-400 shrink-0 ml-1" />
                <span className="text-amber-300">worktree</span>
              </>
            )}
          </div>
        </div>

        {/* Right side: companion + close buttons */}
        <div className="flex items-center gap-2 shrink-0">
          {companionButtons.map((btn) => {
            const existing = companions.find((c) => c.tool_name === btn.tool);
            return (
              <button
                key={btn.tool}
                onClick={() => handleOpenCompanion(btn.tool)}
                disabled={spawning}
                className="flex items-center gap-1.5 bg-slate-700/60 hover:bg-slate-600 text-slate-200 px-2.5 py-1.5 rounded-md transition-colors border border-slate-600/40 cursor-pointer text-xs font-medium disabled:opacity-50"
                title={
                  existing
                    ? `Attach to existing ${btn.label} session`
                    : `Open new ${btn.label} session`
                }
              >
                {existing ? (
                  <ExternalLink size={12} />
                ) : (
                  <TerminalSquare size={12} />
                )}
                <span>
                  {existing ? `Attach ${btn.label}` : `Open ${btn.label}`}
                </span>
              </button>
            );
          })}

          <button
            onClick={onClose}
            className="flex items-center gap-2 bg-red-500/10 hover:bg-red-500/20 text-red-400 px-3 py-1.5 rounded-md transition-colors border border-red-500/20 cursor-pointer"
          >
            <XCircle size={14} />
            <span className="font-semibold text-xs">Close Window</span>
          </button>
        </div>
      </div>

      {/* Terminal Container */}
      <div className="flex-1 flex flex-col h-full min-h-0 bg-black p-2 overflow-hidden relative">
        <div className="flex-1 h-full min-h-0">
          <div
            id="terminal"
            ref={terminalRef}
            className="terminal xterm"
            style={{ height: '100%' }}
          />
        </div>

        {/* Reconnecting overlay shown when a stale session
            is detected and auto-reconnect is in progress */}
        {(reconnecting || reconnectError) && (
          <div className="absolute inset-0 flex items-center justify-center bg-black/80 z-10">
            <div className="text-center space-y-4 max-w-sm">
              {reconnectError ? (
                <>
                  <p className="text-red-400 text-sm">{reconnectError}</p>
                  <button
                    onClick={onClose}
                    className="text-slate-400 hover:text-slate-50 px-4 py-2 rounded-xl border border-slate-700 transition-colors text-sm"
                  >
                    Close
                  </button>
                </>
              ) : (
                <p className="text-slate-300 text-sm flex items-center gap-2">
                  <RefreshCw size={14} className="animate-spin" />
                  Reconnecting session...
                </p>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default Terminal;
