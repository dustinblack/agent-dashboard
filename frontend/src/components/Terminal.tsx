import React, { useEffect, useRef, useState, useCallback } from 'react';
import { Terminal as XTerm } from '@xterm/xterm';
import { FitAddon } from '@xterm/addon-fit';
import { io, Socket } from 'socket.io-client';
import {
  XCircle,
  GitBranch,
  Monitor,
  TerminalSquare,
  ExternalLink,
} from 'lucide-react';
import '@xterm/xterm/css/xterm.css';
import type { AgentDetail, Agent } from '../api';
import { getAgentDetails, getCompanions, spawnAgent } from '../api';

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
        .catch((err) =>
          console.error('Failed to fetch companions:', err),
        );
    };
    fetchCompanions();
    const interval = setInterval(fetchCompanions, 10_000);
    return () => clearInterval(interval);
  }, [agentId]);

  // Listen for live telemetry updates to keep header fresh
  useEffect(() => {
    if (!socketRef.current) return;
    const handler = (data: { agent_id: string; telemetry: Record<string, unknown> }) => {
      if (data.agent_id === agentId && agentDetail) {
        setAgentDetail((prev) =>
          prev ? { ...prev, telemetry: { ...prev.telemetry, ...data.telemetry } } : prev,
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
      const existing = companions.find(
        (c) => categorize(c.tool_name) === targetTool,
      );
      if (existing) {
        openTerminalWindow(existing.agent_id);
        return;
      }

      if (!agentDetail || spawning) return;
      setSpawning(true);
      try {
        const projectDir = agentDetail.telemetry?.project_dir;
        const spawned = await spawnAgent(
          agentDetail.host_id,
          targetTool,
          projectDir,
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

    const performFit = () => {
      if (terminalRef.current) {
        try {
          fitAddon.fit();
          term.focus();
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
      }
    };

    const handleResize = () => performFit();
    window.addEventListener('resize', handleResize);

    // Debounce ResizeObserver to avoid rapid-fire resize
    // events during layout transitions or animations.
    let resizeTimer: ReturnType<typeof setTimeout> | null =
      null;
    let resizeObserver: ResizeObserver | null = null;
    if (terminalRef.current) {
      resizeObserver = new ResizeObserver(() => {
        if (resizeTimer) clearTimeout(resizeTimer);
        resizeTimer = setTimeout(performFit, 150);
      });
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
      terminalRef.current?.querySelector<HTMLElement>(
        '.xterm-screen',
      );
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
    // flush them in a single term.write() per animation frame
    // to prevent visible scroll jumping during fast output.
    let outputBuffer = '';
    let rafId: number | null = null;
    const flushOutput = () => {
      rafId = null;
      if (outputBuffer) {
        term.write(outputBuffer);
        outputBuffer = '';
      }
    };

    // Buffer history chunks and write them all at once on
    // history_complete to avoid per-chunk scroll jumping
    // during replay.
    let historyBuffer: string[] = [];

    // Socket.IO
    const baseURL =
      import.meta.env.VITE_API_URL ||
      `http://${window.location.hostname}:8000`;
    const socket = io(`${baseURL}/terminal`, {
      path: '/socket.io',
    });
    socketRef.current = socket;

    socket.on('connect', () => {
      isReplaying.current = true;
      historyBuffer = [];
      socket.emit('join_room', { room: agentId });
      performFit();
    });

    socket.on(
      'history_complete',
      (data: { agent_id: string }) => {
        if (data.agent_id === agentId) {
          // Write all buffered history in one call
          if (historyBuffer.length > 0) {
            term.write(historyBuffer.join(''));
            historyBuffer = [];
          }
          isReplaying.current = false;
          performFit();
        }
      },
    );

    socket.on(
      'terminal_output',
      (data: { sid: string; output: string }) => {
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
      },
    );

    term.onData((data) => {
      if (!isReplaying.current) {
        socket.emit('terminal_input', {
          target_sid: agentId,
          input: data,
        });
      }
    });

    return () => {
      window.removeEventListener('resize', handleResize);
      if (resizeTimer) clearTimeout(resizeTimer);
      if (rafId !== null) cancelAnimationFrame(rafId);
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

  // Update browser window title with host / project / branch
  useEffect(() => {
    const parts = [TOOL_LABELS[category]];
    if (hostName) parts.push(hostName);
    if (gitProject) parts.push(gitProject);
    if (gitBranch) parts.push(gitBranch);
    document.title = parts.join(' · ');
    return () => { document.title = 'Agent Dashboard'; };
  }, [category, hostName, gitProject, gitBranch]);

  // Build companion buttons based on current tool type
  const companionButtons: { label: string; tool: ToolCategory }[] = [];
  if (category === 'bash') {
    companionButtons.push({ label: 'Gemini', tool: 'gemini' });
    companionButtons.push({ label: 'Claude', tool: 'claude' });
  } else if (category === 'gemini' || category === 'claude') {
    companionButtons.push({ label: 'Bash', tool: 'bash' });
  }

  return (
    <div className="flex-1 flex flex-col h-full w-full bg-black overflow-hidden">
      {/* Header Bar */}
      <div className="h-12 flex items-center justify-between bg-slate-800 border-b border-slate-700 px-4 shrink-0">
        {/* Left side: tool badge + context */}
        <div className="flex items-center gap-3 min-w-0">
          {/* Tool badge */}
          <span
            className={`${TOOL_COLORS[category]} text-white text-[10px] font-bold uppercase px-2 py-0.5 rounded tracking-wider shrink-0`}
          >
            {TOOL_LABELS[category]}
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
                <span className="text-white font-semibold">
                  {gitProject}
                </span>
              </>
            )}
            {gitBranch && (
              <>
                <GitBranch
                  size={12}
                  className="text-emerald-400 shrink-0 ml-1"
                />
                <span className="text-emerald-300">{gitBranch}</span>
              </>
            )}
          </div>
        </div>

        {/* Right side: companion + close buttons */}
        <div className="flex items-center gap-2 shrink-0">
          {companionButtons.map((btn) => {
            const existing = companions.find(
              (c) => categorize(c.tool_name) === btn.tool,
            );
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
      <div className="flex-1 flex flex-col h-full min-h-0 bg-black p-2 overflow-hidden">
        <div className="flex-1 h-full min-h-0">
          <div
            id="terminal"
            ref={terminalRef}
            className="terminal xterm"
            style={{ height: '100%' }}
          />
        </div>
      </div>
    </div>
  );
};

export default Terminal;
