#!/usr/bin/env python3
import os
import pty
import sys
import asyncio
import socketio
import select
import signal
from typing import Dict, Optional

class HostDaemon:
    def __init__(self, server_url: str, host_token: str):
        self.server_url = server_url
        self.host_token = host_token
        self.sio = socketio.AsyncClient()
        self.agents: Dict[str, Dict] = {} # agent_id -> {master_fd, pid, tool}
        self.running = True

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

        @self.sio.on('terminal_input', namespace='/terminal')
        async def on_terminal_input(data):
            """
            Receives keystrokes from the UI and writes them to the pty.
            data: {'target_sid': '...', 'input': '...'}
            """
            # Note: in this new model, target_sid is the agent_id
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
            try:
                os.execvp(cmd[0], cmd)
            except Exception as e:
                print(f"Failed to execute {cmd}: {e}")
                sys.exit(1)
        else: # Parent process
            self.agents[agent_id] = {
                'master_fd': fd,
                'pid': pid,
                'tool': tool
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
                # Find which agent this FD belongs to
                agent_id = next(aid for aid, info in self.agents.items() if info['master_fd'] == fd)
                
                try:
                    data = os.read(fd, 1024)
                    if not data:
                        self.close_agent(agent_id)
                        continue
                        
                    if self.sio.connected:
                        decoded_data = data.decode('utf-8', errors='replace')
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
            watcher_task = asyncio.create_task(self.watch_agents())
            await watcher_task
        except Exception as e:
            print(f"Daemon error: {e}")
        finally:
            self.running = False
            if self.sio.connected:
                await self.sio.disconnect()

async def main():
    SERVER_URL = os.getenv("DASHBOARD_URL", "http://localhost:8000")
    HOST_TOKEN = os.getenv("HOST_TOKEN")

    if not HOST_TOKEN:
        print("Error: HOST_TOKEN environment variable is required.")
        sys.exit(1)

    daemon = HostDaemon(SERVER_URL, HOST_TOKEN)
    
    # Handle termination signals
    def stop_daemon(*args):
        daemon.running = False
        sys.exit(0)

    signal.signal(signal.SIGINT, stop_daemon)
    signal.signal(signal.SIGTERM, stop_daemon)

    await daemon.run()

if __name__ == '__main__':
    asyncio.run(main())
