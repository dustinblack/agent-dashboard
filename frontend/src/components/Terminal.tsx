import React, { useEffect, useRef } from 'react';
import { Terminal as XTerm } from 'xterm';
import { FitAddon } from 'xterm-addon-fit';
import { io, Socket } from 'socket.io-client';
import { ArrowLeft, XCircle } from 'lucide-react';
import 'xterm/css/xterm.css';

interface TerminalProps {
  sessionId: string;
  onClose: () => void;
}

const Terminal: React.FC<TerminalProps> = ({ sessionId, onClose }) => {
  const terminalRef = useRef<HTMLDivElement>(null);
  const xtermRef = useRef<XTerm | null>(null);
  const socketRef = useRef<Socket | null>(null);

  useEffect(() => {
    if (!terminalRef.current) return;

    // Initialize xterm.js
    const term = new XTerm({
      cursorBlink: true,
      theme: {
        background: '#0f172a', // matches slate-900
        foreground: '#f1f5f9', // matches slate-100
        cursor: '#60a5fa',     // matches blue-400
        selectionBackground: '#334155', // matches slate-700
      },
      fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace',
      fontSize: 14,
    });
    const fitAddon = new FitAddon();
    term.loadAddon(fitAddon);
    term.open(terminalRef.current);
    
    // Slight delay to ensure DOM is ready before fitting
    setTimeout(() => {
        fitAddon.fit();
    }, 10);
    xtermRef.current = term;

    // Initialize Socket.IO
    const baseURL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
    const socket = io(`${baseURL}/terminal`, {
      path: '/socket.io',
    });
    socketRef.current = socket;

    socket.on('connect_error', (err) => {
        console.error('Socket.IO Connection Error:', err);
        term.writeln(`\x1b[1;31mConnection error: ${err.message}\x1b[0m`);
    });

    socket.on('connect', () => {
      term.writeln('\x1b[1;32mConnected to session relay...\x1b[0m');
      // Request to join the room for this specific session output
      socket.emit('join_room', { room: sessionId });
    });

    socket.on('terminal_output', (data: { sid: string; output: string }) => {
      if (data.sid === sessionId) {
        term.write(data.output);
      }
    });

    term.onData((data) => {
      socket.emit('terminal_input', { target_sid: sessionId, input: data });
    });

    const handleResize = () => {
        if (fitAddon) {
            fitAddon.fit();
        }
    };
    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      socket.disconnect();
      term.dispose();
    };
  }, [sessionId]);

  return (
    <div className="flex flex-col h-screen w-screen bg-slate-900 overflow-hidden">
      {/* Header Bar */}
      <div className="flex items-center justify-between bg-slate-800 border-b border-slate-700 px-6 py-3 shrink-0">
        <div className="flex items-center gap-4">
            <button 
                onClick={onClose}
                className="flex items-center gap-2 text-slate-400 hover:text-white transition-colors"
                title="Back to Dashboard"
            >
                <ArrowLeft size={20} />
                <span className="font-semibold text-sm">Dashboard</span>
            </button>
            <div className="h-6 w-px bg-slate-700"></div>
            <div className="flex flex-col">
                <span className="text-xs text-slate-400 font-mono">Session ID</span>
                <span className="text-sm font-bold text-white font-mono">{sessionId}</span>
            </div>
        </div>
        
        <button 
          onClick={onClose}
          className="flex items-center gap-2 bg-red-500/10 hover:bg-red-500/20 text-red-400 hover:text-red-300 px-3 py-1.5 rounded-md transition-colors border border-red-500/20"
        >
          <XCircle size={16} />
          <span className="font-semibold text-sm">Disconnect</span>
        </button>
      </div>

      {/* Terminal Container */}
      <div className="flex-1 w-full h-full p-4 overflow-hidden relative">
          <div ref={terminalRef} className="absolute inset-4 rounded-lg overflow-hidden border border-slate-800 shadow-xl" />
      </div>
    </div>
  );
};

export default Terminal;
