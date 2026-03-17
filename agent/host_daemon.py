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
import asyncio
import aiohttp
from aiohttp import web
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
        self.cached_projects = []
        self.projects_lock = asyncio.Lock()
        self.otlp_runner = None

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

        @self.sio.on('terminal_resize', namespace='/terminal')
        async def on_terminal_resize(data):
            agent_id = data.get('sid')
            cols = data.get('cols')
            rows = data.get('rows')
            if agent_id in self.agents and cols and rows:
                master_fd = self.agents[agent_id]['master_fd']
                import fcntl, termios, struct
                size = struct.pack('HHHH', rows, cols, 0, 0)
                try:
                    fcntl.ioctl(master_fd, termios.TIOCSWINSZ, size)
                except Exception as e:
                    print(f"Failed to resize terminal {agent_id}: {e}")

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

    async def update_projects_cache(self):
        """Continuously updates the project cache in the background every 60 seconds."""
        loop = asyncio.get_running_loop()
        while self.running:
            def _scan():
                projects = []
                if os.path.exists(self.projects_root):
                    try:
                        for root, dirs, files in os.walk(self.projects_root):
                            rel_path = os.path.relpath(root, self.projects_root)
                            depth = 0 if rel_path == "." else len(rel_path.split(os.sep))
                            if depth > 2:
                                dirs[:] = [] 
                                continue
                            if ".git" in dirs:
                                if rel_path != ".":
                                    projects.append(rel_path)
                                dirs[:] = [d for d in dirs if d != ".git"]
                        projects.sort()
                    except Exception as e:
                        print(f"Error scanning projects root {self.projects_root}: {e}")
                return projects
                
            new_projects = await loop.run_in_executor(None, _scan)
            async with self.projects_lock:
                self.cached_projects = new_projects
            
            # Immediately report if connected
            if self.sio.connected:
                await self.report_projects()
                
            await asyncio.sleep(60)

    async def report_projects(self):
        """Instantly reports cached projects to the Hub."""
        async with self.projects_lock:
            projects = list(self.cached_projects)
            
        print(f"Reporting {len(projects)} available projects to Hub.")
        if self.sio.connected:
            await self.sio.emit('host_telemetry', {
                'projects_root': self.projects_root,
                'available_projects': projects
            }, namespace='/terminal')

    def get_git_info(self, path: str):
        """Extracts git branch and project name from a directory.

        The project name is derived from the remote origin URL when
        available, falling back to the git repository's root directory
        name (e.g. a repo at /git/agent-dashboard yields
        "agent-dashboard").
        """
        if not path or not os.path.exists(path):
            return None, None

        branch = None
        project = None

        try:
            branch = subprocess.check_output(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=path, stderr=subprocess.DEVNULL
            ).decode().strip()
        except Exception:
            pass

        try:
            origin = subprocess.check_output(
                ["git", "config", "--get", "remote.origin.url"],
                cwd=path, stderr=subprocess.DEVNULL
            ).decode().strip()
            project = origin.split("/")[-1].replace(".git", "")
        except Exception:
            # No remote configured — use the repo root directory name
            try:
                toplevel = subprocess.check_output(
                    ["git", "rev-parse", "--show-toplevel"],
                    cwd=path, stderr=subprocess.DEVNULL
                ).decode().strip()
                project = os.path.basename(toplevel)
            except Exception:
                pass

        return branch, project

    async def spawn_agent(self, agent_id: str, tool: str, project_dir: Optional[str] = None, task: Optional[str] = None):
        """Spawns a new process in a pseudo-terminal with environmental context."""
        # Resolve full path (handles both absolute and relative from projects_root)
        full_path = project_dir
        if project_dir and not project_dir.startswith('/'):
            full_path = os.path.join(self.projects_root, project_dir)
        
        # Ensure we use an absolute path for working directory
        if full_path:
            full_path = os.path.abspath(full_path)

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

            # Inject OpenTelemetry standard configuration
            env['OTEL_EXPORTER_OTLP_ENDPOINT'] = "http://127.0.0.1:4318"
            env['OTEL_RESOURCE_ATTRIBUTES'] = f"service.name={agent_id}"

            # Tool-specific OTel enablement
            env['CLAUDE_CODE_ENABLE_TELEMETRY'] = '1'
            env['OTEL_METRICS_EXPORTER'] = 'otlp'
            env['OTEL_LOGS_EXPORTER'] = 'otlp'
            env['OTEL_EXPORTER_OTLP_PROTOCOL'] = 'http/json'
            env['GEMINI_CLI_TELEMETRY_ENABLED'] = 'true'
            env['GEMINI_TELEMETRY_ENABLED'] = 'true'
            env['GEMINI_TELEMETRY_OTLP_ENDPOINT'] = 'http://127.0.0.1:4318/v1/logs'
            env['GEMINI_TELEMETRY_OTLP_PROTOCOL'] = 'http'
            env['GEMINI_TELEMETRY_USE_COLLECTOR'] = 'true'
            env['GEMINI_TELEMETRY_TARGET'] = 'local'

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
                    data = os.read(fd, 65536)
                    if not data:
                        self.close_agent(agent_id)
                        continue
                    if self.sio.connected:
                        decoded_data = data.decode('utf-8', errors='replace')
                        self.agents[agent_id]['history'].append(decoded_data)
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

    def _extract_otel_value(self, value_obj):
        """Extracts the actual value from an OTLP attribute value object.

        OTLP attribute values are wrapped in type-specific keys like
        'stringValue', 'intValue', 'doubleValue', etc. This helper
        returns the first non-None value found.
        """
        for key in ('stringValue', 'intValue', 'doubleValue', 'boolValue'):
            if key in value_obj:
                return value_obj[key]
        return None

    def _process_otel_attributes(self, attrs_list):
        """Converts a list of OTLP key/value attributes to a flat dict.

        Args:
            attrs_list: List of dicts with 'key' and 'value' fields
                        in OTLP attribute format.

        Returns:
            A dict mapping attribute keys to their extracted values.
        """
        result = {}
        for attr in attrs_list:
            key = attr.get('key', '')
            value = attr.get('value', {})
            result[key] = self._extract_otel_value(value)
        return result

    def _update_telemetry_from_attrs(self, tel, attrs):
        """Updates agent telemetry dict from parsed OTLP attributes.

        Looks for model name and token usage attributes using multiple
        naming conventions (Gemini and Claude use different schemas).

        Args:
            tel: The agent's telemetry dict to update in place.
            attrs: Flat dict of parsed OTLP attributes.

        Returns:
            True if any telemetry value was updated, False otherwise.
        """
        changed = False

        # Model detection — try common attribute names
        for key in ('model', 'gen_ai.request.model',
                     'gen_ai.response.model'):
            model = attrs.get(key)
            if model and isinstance(model, str) and tel.get('model') != model:
                tel['model'] = model
                changed = True
                break

        # Token detection — try common attribute names
        input_tokens = None
        output_tokens = None
        cache_tokens = None
        for key in ('input_token_count', 'input_tokens',
                     'gen_ai.usage.input_tokens'):
            val = attrs.get(key)
            if val is not None:
                input_tokens = int(val)
                break
        for key in ('output_token_count', 'output_tokens',
                     'gen_ai.usage.output_tokens'):
            val = attrs.get(key)
            if val is not None:
                output_tokens = int(val)
                break
        for key in ('cache_read_tokens', 'cache_creation_tokens'):
            val = attrs.get(key)
            if val is not None:
                cache_tokens = (cache_tokens or 0) + int(val)

        if input_tokens is not None or output_tokens is not None:
            total = ((input_tokens or 0) + (output_tokens or 0)
                     + (cache_tokens or 0))
            if total > tel.get('tokens', 0):
                tel['tokens'] = total
                changed = True

        return changed

    async def handle_otlp(self, request):
        """Standardized OTLP HTTP receiver (JSON format).

        Handles logs (/v1/logs), traces (/v1/traces), and metrics
        (/v1/metrics). Extracts agent_id from the resource
        'service.name' attribute (injected at spawn time) and looks
        for model/token info in record or span attributes.
        """
        try:
            data = await request.json()
            print(f"OTLP received on {request.path}: {list(data.keys())}")

            # Process OTLP Logs (resourceLogs → scopeLogs → logRecords)
            for res_log in data.get('resourceLogs', []):
                resource = res_log.get('resource', {})
                res_attrs = self._process_otel_attributes(
                    resource.get('attributes', []))
                agent_id = res_attrs.get('service.name')

                if not agent_id or agent_id not in self.agents:
                    continue
                tel = self.agents[agent_id]['telemetry']
                changed = False

                for scope_log in res_log.get('scopeLogs', []):
                    for record in scope_log.get('logRecords', []):
                        attrs = self._process_otel_attributes(
                            record.get('attributes', []))
                        if self._update_telemetry_from_attrs(tel, attrs):
                            changed = True

                if changed and self.sio.connected:
                    await self.sio.emit(
                        'agent_telemetry',
                        {'agent_id': agent_id, 'telemetry': tel},
                        namespace='/terminal')

            # Process OTLP Traces (resourceSpans → scopeSpans → spans)
            for res_span in data.get('resourceSpans', []):
                resource = res_span.get('resource', {})
                res_attrs = self._process_otel_attributes(
                    resource.get('attributes', []))
                agent_id = res_attrs.get('service.name')

                if not agent_id or agent_id not in self.agents:
                    continue
                tel = self.agents[agent_id]['telemetry']
                changed = False

                for scope_span in res_span.get('scopeSpans', []):
                    for span in scope_span.get('spans', []):
                        attrs = self._process_otel_attributes(
                            span.get('attributes', []))
                        if self._update_telemetry_from_attrs(tel, attrs):
                            changed = True

                if changed and self.sio.connected:
                    await self.sio.emit(
                        'agent_telemetry',
                        {'agent_id': agent_id, 'telemetry': tel},
                        namespace='/terminal')

            # Process OTLP Metrics
            # (resourceMetrics → scopeMetrics → metrics → dataPoints)
            # Claude Code sends token usage as counter metrics with
            # 'model' and 'type' (input/output) attributes.
            for res_metric in data.get('resourceMetrics', []):
                resource = res_metric.get('resource', {})
                res_attrs = self._process_otel_attributes(
                    resource.get('attributes', []))
                agent_id = res_attrs.get('service.name')

                if not agent_id or agent_id not in self.agents:
                    continue
                tel = self.agents[agent_id]['telemetry']
                changed = False

                for scope_metric in res_metric.get('scopeMetrics', []):
                    for metric in scope_metric.get('metrics', []):
                        name = metric.get('name', '')

                        # Collect data points from sum, gauge, or
                        # histogram structures
                        data_points = []
                        for container in ('sum', 'gauge', 'histogram'):
                            section = metric.get(container, {})
                            data_points.extend(
                                section.get('dataPoints', []))

                        for dp in data_points:
                            dp_attrs = self._process_otel_attributes(
                                dp.get('attributes', []))

                            # Model detection from any metric with a
                            # 'model' attribute
                            model = dp_attrs.get('model')
                            if (model and isinstance(model, str)
                                    and tel.get('model') != model):
                                tel['model'] = model
                                changed = True

                            # Token accumulation from
                            # claude_code.token.usage counters
                            if name == 'claude_code.token.usage':
                                value = (dp.get('asInt')
                                         or dp.get('asDouble')
                                         or 0)
                                if value:
                                    tel['tokens'] = (
                                        tel.get('tokens', 0)
                                        + int(value))
                                    changed = True

                if changed and self.sio.connected:
                    await self.sio.emit(
                        'agent_telemetry',
                        {'agent_id': agent_id, 'telemetry': tel},
                        namespace='/terminal')

            return web.Response(status=200)
        except Exception as e:
            print(f"OTLP Error: {e}")
            return web.Response(status=400)

    async def start_otlp_server(self):
        """Starts a local HTTP server for OpenTelemetry data."""
        app = web.Application()
        app.router.add_post('/v1/logs', self.handle_otlp)
        app.router.add_post('/v1/traces', self.handle_otlp)
        app.router.add_post('/v1/metrics', self.handle_otlp)
        self.otlp_runner = web.AppRunner(app)
        await self.otlp_runner.setup()
        site = web.TCPSite(self.otlp_runner, '127.0.0.1', 4318)
        print("OTLP Receiver listening on http://127.0.0.1:4318")
        await site.start()

    async def update_agents_git_info(self):
        """Periodically checks the current working directory of each agent and updates git info."""
        while self.running:
            for agent_id, info in list(self.agents.items()):
                try:
                    pid = info['pid']
                    if not pid: continue
                    # Try to read the cwd of the child process
                    cwd = os.readlink(f'/proc/{pid}/cwd')
                    branch, project = self.get_git_info(cwd)
                    
                    tel = info['telemetry']
                    changed = False
                    if branch and tel.get('git_branch') != branch:
                        tel['git_branch'] = branch
                        changed = True
                    if project and tel.get('git_project') != project:
                        tel['git_project'] = project
                        changed = True
                    
                    if changed and self.sio.connected:
                        await self.sio.emit('agent_telemetry', {'agent_id': agent_id, 'telemetry': tel}, namespace='/terminal')
                except Exception:
                    pass # Process might have died or no permission
            await asyncio.sleep(5)

    async def run(self):
        try:
            await self.sio.connect(
                self.server_url,
                namespaces=['/terminal'],
                headers={'X-Host-Token': self.host_token}
            )
            # Start background tasks
            self.watcher_task = asyncio.create_task(self.watch_agents())
            self.cache_task = asyncio.create_task(self.update_projects_cache())
            self.otlp_task = asyncio.create_task(self.start_otlp_server())
            self.git_task = asyncio.create_task(self.update_agents_git_info())
            
            await asyncio.gather(self.watcher_task, self.cache_task, self.otlp_task, self.git_task)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"Daemon error: {e}")
        finally:
            self.running = False
            if self.otlp_runner:
                await self.otlp_runner.cleanup()
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
        if hasattr(self, 'cache_task') and not self.cache_task.done():
            self.cache_task.cancel()
        if hasattr(self, 'git_task') and not self.git_task.done():
            self.git_task.cancel()

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
