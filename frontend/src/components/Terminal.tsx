import React, { useEffect, useRef } from 'react';
import { Terminal as XTerm } from '@xterm/xterm';
import { FitAddon } from '@xterm/addon-fit';
import { io, Socket } from 'socket.io-client';
import { XCircle } from 'lucide-react';
import '@xterm/xterm/css/xterm.css';

interface TerminalProps {
  agentId: string;
  onClose: () => void;
}

const Terminal: React.FC<TerminalProps> = ({ agentId, onClose }) => {
  const terminalRef = useRef<HTMLDivElement>(null);
  const xtermRef = useRef<XTerm | null>(null);
  const socketRef = useRef<Socket | null>(null);
  const isReplaying = useRef<boolean>(false);

  useEffect(() => {
    if (!terminalRef.current) return;

    // Initialize xterm.js
    const term = new XTerm({
      cursorBlink: true,
      theme: {
        background: '#000000',
        foreground: '#f1f5f9',
        cursor: '#60a5fa',
        selectionBackground: '#334155',
      },
      fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace',
      fontSize: 14,
      allowProposedApi: true
    });
    
    const fitAddon = new FitAddon();
    term.loadAddon(fitAddon);
    
    // 1. Open the terminal in your div
    term.open(terminalRef.current);
    
    // 2. IMPORTANT: You must call fit() AFTER opening the terminal
    // This tells xterm to look at the h-full div and fill it with rows.
    fitAddon.fit();
    
    const performFit = () => {
        if (terminalRef.current) {
            try {
                // 2. IMPORTANT: You must call fit() AFTER opening the terminal
                // This tells xterm to look at the h-full div and fill it with rows.
                fitAddon.fit();
                term.focus();
                
                if (socketRef.current?.connected) {
                    socketRef.current.emit('terminal_resize', {
                        sid: agentId,
                        cols: term.cols,
                        rows: term.rows
                    });
                }
            } catch (e) {
                console.error("Fit failed:", e);
            }
        }
    };

    // 3. Keep it full-screen when the window or container resizes
    const handleResize = () => {
        performFit();
    };
    window.addEventListener('resize', handleResize);

    // Use ResizeObserver on the container for robust resize detection
    // (catches cases window.resize misses, e.g. layout reflows)
    let resizeObserver: ResizeObserver | null = null;
    if (terminalRef.current) {
        resizeObserver = new ResizeObserver(() => {
            performFit();
        });
        resizeObserver.observe(terminalRef.current);
    }

    // Initial fit after the browser has a chance to compute layout
    requestAnimationFrame(performFit);

    xtermRef.current = term;

    // Initialize Socket.IO
    const baseURL = import.meta.env.VITE_API_URL || `http://${window.location.hostname}:8000`;
    const socket = io(`${baseURL}/terminal`, { path: '/socket.io' });
    socketRef.current = socket;

    socket.on('connect', () => {
      isReplaying.current = true;
      socket.emit('join_room', { room: agentId });
      performFit();
    });

    socket.on('history_complete', (data: { agent_id: string }) => {
        if (data.agent_id === agentId) {
            isReplaying.current = false;
            performFit();
        }
    });

    socket.on('terminal_output', (data: { sid: string; output: string }) => {
      if (data.sid === agentId) {
        term.write(data.output);
      }
    });

    term.onData((data) => {
      if (!isReplaying.current) {
          socket.emit('terminal_input', { target_sid: agentId, input: data });
      }
    });

    return () => {
      window.removeEventListener('resize', handleResize);
      resizeObserver?.disconnect();
      socket.disconnect();
      term.dispose();
    };
  }, [agentId]);

  return (
    <div className="flex-1 flex flex-col h-full w-full bg-black overflow-hidden">
      {/* Header Bar - Fixed Height */}
      <div className="h-12 flex items-center justify-between bg-slate-800 border-b border-slate-700 px-4 shrink-0">
        <div className="flex items-center gap-4">
            <div className="flex flex-col">
                <span className="text-[10px] text-slate-400 font-mono uppercase tracking-tight leading-none mb-1">Agent ID</span>
                <span className="text-xs font-bold text-white font-mono leading-none">{agentId}</span>
            </div>
        </div>
        
        <button 
          onClick={onClose}
          className="flex items-center gap-2 bg-red-500/10 hover:bg-red-500/20 text-red-400 px-3 py-1.5 rounded-md transition-colors border border-red-500/20 cursor-pointer"
        >
          <XCircle size={14} />
          <span className="font-semibold text-xs">Close Window</span>
        </button>
      </div>

      {/* Terminal Container - Following user instruction exactly */}
      <div className="flex-1 flex flex-col h-full min-h-0 bg-black p-2 overflow-hidden">
          <div className="flex-1 h-full min-h-0">
              <div id="terminal" ref={terminalRef} className="terminal xterm" style={{ height: '100%' }} />
          </div>
      </div>
    </div>
  );
};

export default Terminal;
