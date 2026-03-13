import React, { useEffect, useRef } from 'react';
import { Terminal as XTerm } from 'xterm';
import { FitAddon } from 'xterm-addon-fit';
import { io, Socket } from 'socket.io-client';
import { XCircle } from 'lucide-react';
import 'xterm/css/xterm.css';

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
    });
    const fitAddon = new FitAddon();
    term.loadAddon(fitAddon);
    term.open(terminalRef.current);
    
    // Reliable fitting and focusing
    const performFit = () => {
        try {
            fitAddon.fit();
            term.focus();
        } catch (e) {
            console.error("Fit failed:", e);
        }
    };

    setTimeout(performFit, 50);
    setTimeout(performFit, 250);
    
    xtermRef.current = term;

    // Initialize Socket.IO
    const baseURL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
    const socket = io(`${baseURL}/terminal`, { path: '/socket.io' });
    socketRef.current = socket;

    socket.on('connect_error', (err) => {
        term.writeln(`\x1b[1;31mConnection error: ${err.message}\x1b[0m`);
    });

    socket.on('connect', () => {
      term.writeln('\x1b[1;32mConnected to session relay...\x1b[0m');
      
      // Block automatic responses during history replay
      isReplaying.current = true;
      socket.emit('join_room', { room: agentId });
      
      setTimeout(() => {
          isReplaying.current = false;
      }, 1000); // 1 second input lock
    });

    socket.on('terminal_output', (data: { sid: string; output: string }) => {
      if (data.sid === agentId) {
        term.write(data.output);
      }
    });

    term.onData((data) => {
      // Discard all input (including automatic DSR responses) during the replay window
      if (isReplaying.current) return;
      
      socket.emit('terminal_input', { target_sid: agentId, input: data });
    });

    const handleResize = () => performFit();
    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      socket.disconnect();
      term.dispose();
    };
  }, [agentId]);

  return (
    <div className="flex flex-col h-screen w-screen bg-black overflow-hidden">
      <div className="flex items-center justify-between bg-slate-800 border-b border-slate-700 px-4 py-2 shrink-0">
        <div className="flex items-center gap-4">
            <div className="flex flex-col">
                <span className="text-[10px] text-slate-400 font-mono uppercase tracking-tight">Agent ID</span>
                <span className="text-xs font-bold text-white font-mono">{agentId}</span>
            </div>
        </div>
        <button 
          onClick={onClose}
          className="flex items-center gap-2 bg-red-500/10 hover:bg-red-500/20 text-red-400 hover:text-red-300 px-3 py-1 rounded-md transition-colors border border-red-500/20 cursor-pointer"
        >
          <XCircle size={14} />
          <span className="font-semibold text-xs">Close Window</span>
        </button>
      </div>
      <div className="flex-1 w-full h-full overflow-hidden relative">
          <div ref={terminalRef} className="absolute inset-0" />
      </div>
    </div>
  );
};

export default Terminal;
