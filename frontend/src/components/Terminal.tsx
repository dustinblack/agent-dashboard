import React, { useEffect, useRef } from 'react';
import { Terminal as XTerm } from 'xterm';
import { FitAddon } from 'xterm-addon-fit';
import { io, Socket } from 'socket.io-client';
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
        background: '#1a1b26',
        foreground: '#a9b1d6',
      },
    });
    const fitAddon = new FitAddon();
    term.loadAddon(fitAddon);
    term.open(terminalRef.current);
    fitAddon.fit();
    xtermRef.current = term;

    // Initialize Socket.IO
    const socket = io(import.meta.env.VITE_API_URL || 'http://localhost:8000', {
      path: '/socket.io',
      namespace: '/terminal',
      transports: ['websocket'],
    });
    socketRef.current = socket;

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

    const handleResize = () => fitAddon.fit();
    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      socket.disconnect();
      term.dispose();
    };
  }, [sessionId]);

  return (
    <div className="terminal-container" style={{ height: '100%', width: '100%', position: 'relative' }}>
      <div style={{ position: 'absolute', top: 10, right: 10, zIndex: 10 }}>
        <button 
          onClick={onClose}
          style={{ padding: '4px 8px', background: '#f44336', color: 'white', border: 'none', cursor: 'pointer' }}
        >
          Close
        </button>
      </div>
      <div ref={terminalRef} style={{ height: '100%', width: '100%' }} />
    </div>
  );
};

export default Terminal;
