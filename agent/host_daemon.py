#!/usr/bin/env python3
import os
import pty
import sys
import asyncio
import socketio
import select
import signal
import subprocess
import re
from typing import Dict, Optional, List
from collections import deque

class HostDaemon:
    def __init__(self, server_url: str, host_token: str):
        self.server_url = server_url
        self.host_token = host_token
        self.projects_root = os.getenv("PROJECTS_ROOT", "/git")
        self.sio = socketio.AsyncClient()
        self.agents: Dict[str, Dict] = {} # agent_id -> {master_fd, pid, tool, history, telemetry}
        self.running = True

        @self.sio.on('*', namespace='/terminal')
        async def catch_all(event, data):
            # Suppress noisy heartbeat/terminal output logs in debug
            if event not in ['terminal_output', 'terminal_input']:
                print(f"DEBUG: Received event '{event}' with data: {data}")

        @self.sio.on('connect', namespace='/terminal')
        async def on_connect():
            print(f"Connected to dashboard at {self.server_url}")
            # Report available projects immediately on connection
            await self.report_projects()

        @self.sio.on('request_projects', namespace='/terminal')
        async def on_request_projects(data):
            await self.report_projects()

        @self.sio.on('spawn_agent', namespace='/terminal')
        async def on_spawn_agent(data):
            """
            Triggered by the server to start a new AI agent session.
            data: {'agent_id': '...', 'tool': 'gemini|claude', 'project_dir': '...', 'task_description': '...'}
            """
            agent_id = data.get('agent_id')
            tool = data.get('tool', 'bash')
            project_dir = data.get('project_dir')
            task_description = data.get('task_description')
            await self.spawn_agent(agent_id, tool, project_dir, task_description)

        @self.sio.on('stop_agent', namespace='/terminal')
        async def on_stop_agent(data):
            agent_id = data.get('agent_id')
            if agent_id in self.agents:
                print(f"Stopping agent {agent_id} by request.")
                pid = self.agents[agent_id]['pid']
                try:
                    os.kill(pid, signal.SIGTERM)
                except OSError:
                    pass
                self.close_agent(agent_id)

        @self.sio.on('request_history', namespace='/terminal')
        async def on_request_history(data):
            agent_id = data.get('agent_id')
            if agent_id in self.agents and self.sio.connected:
                print(f"Replaying history for agent: {agent_id}")
                for chunk in self.agents[agent_id]['history']:
                    await self.sio.emit('terminal_output', {
                        'sid': agent_id, 
                        'output': chunk
                    }, namespace='/terminal')
                await self.sio.emit('history_complete', {'agent_id': agent_id}, namespace='/terminal')

        @self.sio.on('terminal_input', namespace='/terminal')
        async def on_terminal_input(data):
            agent_id = data.get('target_sid')
            user_input = data.get('input', '')
            if agent_id in self.agents and user_input:
                master_fd = self.agents[agent_id]['master_fd']
                try:
                    os.write(master_fd, user_input.encode('utf-8'))
                except OSError:
                    pass

    async def report_projects(self):
        """Scans PROJECTS_ROOT and reports available subdirectories to the Hub."""
        projects = []
        if os.path.exists(self.projects_root):
            try:
                # Only list directories
                projects = [d for d in os.listdir(self.projects_root) 
                            if os.path.isdir(os.path.join(self.projects_root, d))]
                projects.sort()
            except Exception as e:
                print(f"Error scanning projects root {self.projects_root}: {e}")
        
        if self.sio.connected:
            await self.sio.emit('host_telemetry', {
                'projects_root': self.projects_root,
                'available_projects': projects
            }, namespace='/terminal')

    def get_git_info(self, path: str):
        """Extracts git branch and project name from a directory."""
        if not path or not os.path.exists(path):
            return None, None
        try:
            branch = subprocess.check_output(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"], 
                cwd=path, stderr=subprocess.DEVNULL
            ).decode().strip()
            
            origin = subprocess.check_output(
                ["git", "config", "--get", "remote.origin.url"], 
                cwd=path, stderr=subprocess.DEVNULL
            ).decode().strip()
            project = origin.split("/")[-1].replace(".git", "")
            return branch, project
        except Exception:
            return None, None

    async def spawn_agent(self, agent_id: str, tool: str, project_dir: Optional[str] = None, task: Optional[str] = None):
        """Spawns a new process in a pseudo-terminal with environmental context."""
        # Resolve full path if only relative project name provided
        full_path = project_dir
        if project_dir and not project_dir.startswith('/'):
            full_path = os.path.join(self.projects_root, project_dir)

        print(f"Spawning agent {agent_id} with tool: {tool} in {full_path}")
        
        branch, project = self.get_git_info(full_path)
        telemetry = {
            "project_dir": full_path,
            "task_description": task,
            "git_branch": branch,
            "git_project": project,
            "model": "detecting...",
            "tokens": 0
        }

        cmd_map = {'gemini': ['gemini'], 'claude': ['claude'], 'bash': ['bash']}
        cmd = cmd_map.get(tool, [tool])

        pid, fd = pty.fork()
        if pid == 0: # Child process
            if full_path and os.path.exists(full_path):
                os.chdir(full_path)
            
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
                'history': deque(maxlen=1000),
                'telemetry': telemetry
            }
            if self.sio.connected:
                await self.sio.emit('agent_telemetry', {'agent_id': agent_id, 'telemetry': telemetry}, namespace='/terminal')
            os.write(fd, b'\n')

    def parse_telemetry(self, agent_id: str, text: str):
        changed = False
        tel = self.agents[agent_id]['telemetry']
        model_match = re.search(r"model:?\s*([a-zA-Z0-9\-\.]+)", text, re.IGNORECASE)
        if model_match:
            new_model = model_match.group(1)
            if tel.get('model') != new_model:
                tel['model'] = new_model
                changed = True
        token_match = re.search(r"(?:tokens|usage):?\s*(\d+)", text, re.IGNORECASE)
        if token_match:
            new_tokens = int(token_match.group(1))
            if tel.get('tokens') != new_tokens:
                tel['tokens'] = new_tokens
                changed = True
        return changed

    async def watch_agents(self):
        loop = asyncio.get_running_loop()
        while self.running:
            if not self.agents:
                await asyncio.sleep(0.5)
                continue
            fds = [a['master_fd'] for a in self.agents.values()]
            try:
                r, _, _ = await loop.run_in_executor(None, select.select, fds, [], [], 0.1)
            except ValueError:
                self.cleanup_closed_agents()
                continue
            for fd in r:
                agent_entry = next((item for item in self.agents.items() if item[1]['master_fd'] == fd), None)
                if not agent_entry: continue
                agent_id, info = agent_entry
                try:
                    data = os.read(fd, 1024)
                    if not data:
                        self.close_agent(agent_id)
                        continue
                    if self.sio.connected:
                        decoded_data = data.decode('utf-8', errors='replace')
                        self.agents[agent_id]['history'].append(decoded_data)
                        if self.parse_telemetry(agent_id, decoded_data):
                            await self.sio.emit('agent_telemetry', {'agent_id': agent_id, 'telemetry': self.agents[agent_id]['telemetry']}, namespace='/terminal')
                        await self.sio.emit('terminal_output', {'sid': agent_id, 'output': decoded_data}, namespace='/terminal')
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
