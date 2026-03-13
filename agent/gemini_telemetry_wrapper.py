#!/usr/bin/env python3
import os
import pty
import sys
import asyncio
import socketio
import termios
import tty
import select
from typing import Optional

# Socket.IO Client
sio: Optional[socketio.AsyncClient] = None

# Global reference to the pty master fd
master_fd: Optional[int] = None

def get_sio():
    global sio
    if sio is None:
        sio = socketio.AsyncClient()
        
        @sio.event(namespace='/terminal')
        async def connect():
            """Event handler for successful connection to the dashboard."""
            pass

        @sio.event(namespace='/terminal')
        async def disconnect():
            """Event handler for disconnection."""
            pass

        @sio.on('terminal_input', namespace='/terminal')
        async def on_terminal_input(data):
            """Receive keystrokes from the dashboard and write to the pty."""
            global master_fd
            if master_fd is not None:
                user_input = data.get('input', '')
                if user_input:
                    os.write(master_fd, user_input.encode('utf-8'))
    return sio

async def main():
    global master_fd
    
    sio_client = get_sio()
    
    DASHBOARD_URL = os.getenv("DASHBOARD_URL", "http://localhost:8000")
    MACHINE_TOKEN = os.getenv("MACHINE_TOKEN")

    if not MACHINE_TOKEN:
        print("Error: MACHINE_TOKEN environment variable is required to authenticate with the dashboard.")
        sys.exit(1)
        
    cmd = sys.argv[1:]
    if not cmd:
        cmd = ["bash"]

    try:
        await sio_client.connect(
            DASHBOARD_URL, 
            namespaces=['/terminal'],
            headers={'X-Machine-Token': MACHINE_TOKEN}
        )
    except Exception as e:
        print(f"Warning: Failed to connect to telemetry dashboard at {DASHBOARD_URL}: {e}")
        print("Continuing local execution without telemetry...")

    pid, fd = pty.fork()
    if pid == 0:
        try:
            os.execvp(cmd[0], cmd)
        except Exception as e:
            print(f"Failed to execute {cmd}: {e}")
            sys.exit(1)
    else:
        master_fd = fd
        old_tty = None
        if sys.stdin.isatty():
            old_tty = termios.tcgetattr(sys.stdin)
            tty.setraw(sys.stdin.fileno())
            
        try:
            loop = asyncio.get_running_loop()
            while True:
                r, w, e = await loop.run_in_executor(None, select.select, [sys.stdin, master_fd], [], [], 0.1)
                
                if sys.stdin in r:
                    data = os.read(sys.stdin.fileno(), 1024)
                    if not data:
                        break
                    os.write(master_fd, data)
                    
                if master_fd in r:
                    try:
                        data = os.read(master_fd, 1024)
                    except OSError:
                        break
                    if not data:
                        break
                        
                    os.write(sys.stdout.fileno(), data)
                    
                    if sio_client.connected:
                        try:
                            decoded_data = data.decode('utf-8', errors='replace')
                            asyncio.create_task(sio_client.emit('terminal_output', {'output': decoded_data}, namespace='/terminal'))
                        except Exception:
                            pass

            await loop.run_in_executor(None, os.waitpid, pid, 0)
            
        finally:
            if old_tty:
                termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_tty)
            if sio_client.connected:
                await sio_client.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
