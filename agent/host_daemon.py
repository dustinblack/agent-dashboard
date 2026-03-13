#!/usr/bin/env python3
import os
import pty
import sys
import asyncio
import socketio
import select
import signal
from typing import Dict, Optional
from collections import deque

class HostDaemon:
    def __init__(self, server_url: str, host_token: str):
        self.server_url = server_url
        self.host_token = host_token
        self.sio = socketio.AsyncClient()
        self.agents: Dict[str, Dict] = {} # agent_id -> {master_fd, pid, tool, history}
        self.running = True

        @self.sio.on('*', namespace='/terminal')
        async def catch_all(event, data):
            print(f"DEBUG: Received event '{event}' with data: {data}")

        @self.sio.on('connect', namespace='/terminal')
        async def on_connect():
            print(f"Connected to dashboard at {self.server_url}")

        @self.sio.on('spawn_agent', namespace='/terminal')
        async def on_spawn_agent(data):
            """
            Triggered by the server to start a new AI agent session.
            data: {'agent_id': '...', 'tool': 'gemini|claude'}
            """
            agent_id = data.get('agent_id')
            tool = data.get('tool', 'bash')
            await self.spawn_agent(agent_id, tool)

        @self.sio.on('stop_agent', namespace='/terminal')
        async def on_stop_agent(data):
            """
            Triggered by the server to stop an active AI agent session.
            data: {'agent_id': '...'}
            """
            agent_id = data.get('agent_id')
            print(f"Received remote stop request for agent: {agent_id}")
            if agent_id in self.agents:
                print(f"Stopping agent {agent_id} by request.")
                pid = self.agents[agent_id]['pid']
                try:
                    os.kill(pid, signal.SIGTERM)
                    print(f"Killed process {pid}")
                except OSError as e:
                    print(f"Failed to kill process {pid}: {e}")
                self.close_agent(agent_id)
            else:
                print(f"Agent {agent_id} not found in active agents list.")

        @self.sio.on('request_history', namespace='/terminal')
        async def on_request_history(data):
            """
            Triggered when a UI client joins an agent room and needs past output.
            data: {'agent_id': '...'}
            """
            agent_id = data.get('agent_id')
            if agent_id in self.agents and self.sio.connected:
                print(f"Replaying history for agent: {agent_id}")
                for chunk in self.agents[agent_id]['history']:
                    await self.sio.emit('terminal_output', {
                        'sid': agent_id, 
                        'output': chunk
                    }, namespace='/terminal')

        @self.sio.on('terminal_input', namespace='/terminal')
        async def on_terminal_input(data):
            """
            Receives keystrokes from the UI and writes them to the pty.
            data: {'target_sid': '...', 'input': '...'}
            """
            agent_id = data.get('target_sid')
            user_input = data.get('input', '')
            
            if agent_id in self.agents and user_input:
                master_fd = self.agents[agent_id]['master_fd']
                try:
                    os.write(master_fd, user_input.encode('utf-8'))
                except OSError:
                    pass

    async def spawn_agent(self, agent_id: str, tool: str):
        """Spawns a new process in a pseudo-terminal."""
        print(f"Spawning agent {agent_id} with tool: {tool}")
        
        # Mapping tool names to actual commands
        cmd_map = {
            'gemini': ['gemini'],
            'claude': ['claude'],
            'bash': ['bash']
        }
        cmd = cmd_map.get(tool, [tool])

        pid, fd = pty.fork()
        if pid == 0: # Child process
            # Ensure the child inherits the daemon's environment variables (including API keys)
            # Inject terminal capabilities for full color support
            env = os.environ.copy()
            env['TERM'] = 'xterm-256color'
            env['COLORTERM'] = 'truecolor'
            try:
                os.execvpe(cmd[0], cmd, env)
            except Exception as e:
                print(f"Failed to execute {cmd}: {e}")
                os._exit(1)
        else: # Parent process
            self.agents[agent_id] = {
                'master_fd': fd,
                'pid': pid,
                'tool': tool,
                'history': deque(maxlen=1000) # Store last 1000 chunks of output
            }
            # Force an initial newline to trigger prompt rendering
            os.write(fd, b'\n')

    async def watch_agents(self):
        """Continuously polls all active agent FDs for output."""
        loop = asyncio.get_running_loop()
        while self.running:
            if not self.agents:
                await asyncio.sleep(0.5)
                continue

            fds = [a['master_fd'] for a in self.agents.values()]
            
            # Non-blocking select
            try:
                r, _, _ = await loop.run_in_executor(None, select.select, fds, [], [], 0.1)
            except ValueError: # Occurs if an FD was closed
                self.cleanup_closed_agents()
                continue

            for fd in r:
                # Find which agent this FD belongs to safely
                agent_entry = next((item for item in self.agents.items() if item[1]['master_fd'] == fd), None)
                if not agent_entry:
                    continue
                
                agent_id, info = agent_entry
                
                try:
                    data = os.read(fd, 1024)
                    if not data:
                        self.close_agent(agent_id)
                        continue
                        
                    if self.sio.connected:
                        decoded_data = data.decode('utf-8', errors='replace')
                        # Save to history buffer
                        self.agents[agent_id]['history'].append(decoded_data)
                        
                        await self.sio.emit('terminal_output', {
                            'sid': agent_id, 
                            'output': decoded_data
                        }, namespace='/terminal')
                except OSError:
                    self.close_agent(agent_id)

            await asyncio.sleep(0.01)

    def close_agent(self, agent_id: str):
        if agent_id in self.agents:
            print(f"Closing agent {agent_id}")
            fd = self.agents[agent_id]['master_fd']
            try:
                os.close(fd)
            except OSError:
                pass
            del self.agents[agent_id]
            # Notify the server that this agent process has ended
            if self.sio.connected:
                asyncio.create_task(self.sio.emit('agent_exit', {'agent_id': agent_id}, namespace='/terminal'))

    def cleanup_closed_agents(self):
        to_delete = []
        for aid, info in self.agents.items():
            try:
                os.fstat(info['master_fd'])
            except OSError:
                to_delete.append(aid)
        for aid in to_delete:
            self.close_agent(aid)

    async def run(self):
        try:
            await self.sio.connect(
                self.server_url,
                namespaces=['/terminal'],
                headers={'X-Host-Token': self.host_token}
            )
            # Run the output watcher as a background task
            self.watcher_task = asyncio.create_task(self.watch_agents())
            await self.watcher_task
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"Daemon error: {e}")
        finally:
            self.running = False
            for agent_id in list(self.agents.keys()):
                self.close_agent(agent_id)
            if self.sio.connected:
                await self.sio.disconnect()
            print("Daemon stopped.")

    def stop(self):
        print("\nShutting down daemon...")
        self.running = False
        if hasattr(self, 'watcher_task') and not self.watcher_task.done():
            self.watcher_task.cancel()

async def main():
    SERVER_URL = os.getenv("DASHBOARD_URL", "http://localhost:8000")
    HOST_TOKEN = os.getenv("HOST_TOKEN")

    if not HOST_TOKEN:
        print("Error: HOST_TOKEN environment variable is required.")
        sys.exit(1)

    daemon = HostDaemon(SERVER_URL, HOST_TOKEN)
    
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, daemon.stop)

    await daemon.run()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
