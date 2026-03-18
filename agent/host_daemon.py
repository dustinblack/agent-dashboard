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
import json
import time
import asyncio
import aiohttp
from aiohttp import web
from typing import Dict, Optional, List
from collections import deque

# Terminal patterns that indicate the agent is waiting for user input
PERMISSION_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r'\[Y/n\]', r'\[y/N\]', r'Do you want to proceed',
        r'Allow\s', r'waiting for your', r'press enter',
        r'approve|deny|permission', r'\(yes/no\)',
    ]
]

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
            data: {'agent_id': '...', 'tool': 'gemini|claude',
                    'project_dir': '...', 'task_description': '...',
                    'session_mode': 'resume'|'new'}
            """
            agent_id = data.get('agent_id')
            tool = data.get('tool', 'bash')
            project_dir = data.get('project_dir')
            task_description = data.get('task_description')
            session_mode = data.get('session_mode', 'resume')
            await self.spawn_agent(
                agent_id, tool, project_dir,
                task_description, session_mode
            )

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

    def _detect_mcp_servers(self, project_dir, tool):
        """Detects MCP servers configured for the given tool and project.

        For Claude, reads .mcp.json in the project directory and
        ~/.claude.json for global MCP server configuration.
        For Gemini, reads ~/.gemini/settings.json.

        Args:
            project_dir: The project directory path.
            tool: The agent tool name ('claude', 'gemini', etc.).

        Returns:
            A list of MCP server name strings.
        """
        servers = []
        try:
            if tool == 'claude':
                # Project-level .mcp.json
                if project_dir:
                    mcp_path = os.path.join(project_dir, '.mcp.json')
                    if os.path.isfile(mcp_path):
                        with open(mcp_path, 'r') as f:
                            data = json.load(f)
                        mcp_servers = data.get('mcpServers', {})
                        servers.extend(mcp_servers.keys())

                # User-level ~/.claude.json
                home_claude = os.path.expanduser('~/.claude.json')
                if os.path.isfile(home_claude):
                    with open(home_claude, 'r') as f:
                        data = json.load(f)
                    mcp_servers = data.get('mcpServers', {})
                    for name in mcp_servers.keys():
                        if name not in servers:
                            servers.append(name)

            elif tool == 'gemini':
                settings_path = os.path.expanduser(
                    '~/.gemini/settings.json'
                )
                if os.path.isfile(settings_path):
                    with open(settings_path, 'r') as f:
                        data = json.load(f)
                    mcp_servers = data.get('mcpServers', {})
                    servers.extend(mcp_servers.keys())
        except Exception as e:
            print(f"MCP detection error for {tool}: {e}")

        return servers

    async def spawn_agent(
        self, agent_id: str, tool: str,
        project_dir: Optional[str] = None,
        task: Optional[str] = None,
        session_mode: str = "resume"
    ):
        """Spawns a new process in a pseudo-terminal with environmental context.

        Args:
            agent_id: Unique identifier for the agent session.
            tool: The CLI tool to spawn ('claude', 'gemini', 'bash').
            project_dir: Working directory for the agent.
            task: Optional task description for the session.
            session_mode: 'resume' to continue the latest session
                          (default), or 'new' for a fresh session.
        """
        # Resolve full path (handles both absolute and relative from projects_root)
        full_path = project_dir
        if project_dir and not project_dir.startswith('/'):
            full_path = os.path.join(self.projects_root, project_dir)

        # Ensure we use an absolute path for working directory
        if full_path:
            full_path = os.path.abspath(full_path)

        print(
            f"Spawning agent {agent_id} with tool: {tool} "
            f"mode: {session_mode} in {full_path}"
        )

        branch, project = self.get_git_info(full_path)
        mcp_servers = self._detect_mcp_servers(full_path, tool)
        telemetry = {
            "project_dir": full_path,
            "task_description": task,
            "git_branch": branch,
            "git_project": project,
            "model": "detecting...",
            "tokens": 0,
            "agent_status": "idle",
            "mcp_servers": mcp_servers,
        }

        # Build command based on session_mode
        if session_mode == "resume":
            cmd_map = {
                'gemini': ['gemini', '--resume', 'latest'],
                'claude': ['claude', '--continue'],
                'bash': ['bash'],
            }
        else:
            cmd_map = {
                'gemini': ['gemini'],
                'claude': ['claude'],
                'bash': ['bash'],
            }
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
            # Gemini SDK appends /v1/{traces,logs,metrics} to
            # this base URL — do NOT include a path suffix.
            env['GEMINI_TELEMETRY_OTLP_ENDPOINT'] = (
                'http://127.0.0.1:4318'
            )
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
                'telemetry': telemetry,
                'last_otlp_time': 0.0,
                'last_output_time': time.monotonic(),
                'permission_waiting': False,
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
                        self.agents[agent_id]['last_output_time'] = (
                            time.monotonic()
                        )

                        # Check for permission prompts
                        if any(p.search(decoded_data)
                               for p in PERMISSION_PATTERNS):
                            self.agents[agent_id][
                                'permission_waiting'] = True
                        else:
                            self.agents[agent_id][
                                'permission_waiting'] = False

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

    def _resolve_agent_id(self, res_attrs):
        """Resolves an agent_id from OTLP resource attributes.

        First checks for the standard 'service.name' attribute (set
        via OTEL_RESOURCE_ATTRIBUTES for tools like Claude Code that
        use the standard OTEL SDK).  If not found, falls back to
        matching by tool type — Gemini CLI uses its own telemetry
        implementation and does not honour OTEL_RESOURCE_ATTRIBUTES.

        The fallback inspects the 'service.name' value and all
        resource attributes for tool-type hints, then matches to
        any active agent of that tool type.  When multiple agents of
        the same tool type are running, falls back to the most
        recently spawned one.

        Args:
            res_attrs: Flat dict of parsed OTLP resource attributes.

        Returns:
            A matching agent_id string, or None.
        """
        # Direct match via injected service.name (Claude Code path)
        agent_id = res_attrs.get('service.name')
        if agent_id and agent_id in self.agents:
            return agent_id

        # Fallback: infer tool type from resource attributes and
        # match to an active agent of that type.
        tool_hint = None
        svc = res_attrs.get('service.name', '') or ''
        all_vals = ' '.join(
            str(v) for v in res_attrs.values() if v
        ).lower()

        if 'gemini' in svc.lower() or 'gemini' in all_vals:
            tool_hint = 'gemini'
        elif 'claude' in svc.lower() or 'claude' in all_vals:
            tool_hint = 'claude'

        if tool_hint:
            candidates = [
                (aid, info) for aid, info in self.agents.items()
                if info.get('tool') == tool_hint
            ]
            if len(candidates) == 1:
                return candidates[0][0]
            elif len(candidates) > 1:
                # Multiple agents of same type — use the most
                # recently spawned (highest last_output_time as
                # proxy for recency)
                return max(
                    candidates,
                    key=lambda c: c[1].get(
                        'last_output_time', 0
                    ),
                )[0]

        # Last resort: if there is exactly one agent, use it
        if len(self.agents) == 1:
            return next(iter(self.agents))

        return None

    async def handle_otlp(self, request):
        """Standardized OTLP HTTP receiver (JSON format).

        Handles logs (/v1/logs), traces (/v1/traces), and metrics
        (/v1/metrics). Extracts agent_id from the resource
        'service.name' attribute (injected at spawn time) and looks
        for model/token info in record or span attributes.  Falls
        back to tool-type matching for CLIs (like Gemini) that do
        not respect OTEL_RESOURCE_ATTRIBUTES.
        """
        try:
            data = await request.json()
            print(f"OTLP received on {request.path}: {list(data.keys())}")

            # Process OTLP Logs (resourceLogs → scopeLogs → logRecords)
            for res_log in data.get('resourceLogs', []):
                resource = res_log.get('resource', {})
                res_attrs = self._process_otel_attributes(
                    resource.get('attributes', []))
                agent_id = self._resolve_agent_id(res_attrs)

                if not agent_id:
                    print(
                        f"OTLP: no agent match for resource "
                        f"attrs: {res_attrs}"
                    )
                    continue
                self.agents[agent_id]['last_otlp_time'] = (
                    time.monotonic()
                )
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
                agent_id = self._resolve_agent_id(res_attrs)

                if not agent_id:
                    continue
                self.agents[agent_id]['last_otlp_time'] = (
                    time.monotonic()
                )
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
                agent_id = self._resolve_agent_id(res_attrs)

                if not agent_id:
                    continue
                self.agents[agent_id]['last_otlp_time'] = (
                    time.monotonic()
                )
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

                            # Token accumulation from tool-
                            # specific usage counters.
                            # Claude: claude_code.token.usage
                            # Gemini: gemini_cli.token.usage
                            # Note: Gemini also emits
                            # gen_ai.client.token.usage with
                            # identical values — intentionally
                            # excluded to avoid double-counting.
                            token_metrics = (
                                'claude_code.token.usage',
                                'gemini_cli.token.usage',
                            )
                            if name in token_metrics:
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

    async def update_agent_status(self):
        """Periodically derives agent_status from OTLP and output activity.

        Runs every 5 seconds. Status logic:
        - permission_waiting flag set -> 'waiting_permission'
        - OTLP data received within last 15s -> 'working'
        - No recent activity -> 'idle'
        Emits agent_telemetry on status change.
        """
        while self.running:
            now = time.monotonic()
            for agent_id, info in list(self.agents.items()):
                tel = info['telemetry']
                old_status = tel.get('agent_status')

                if info.get('permission_waiting'):
                    new_status = 'waiting_permission'
                elif (now - info.get('last_otlp_time', 0)) < 15:
                    new_status = 'working'
                elif (now - info.get('last_output_time', 0)) < 15:
                    new_status = 'working'
                else:
                    new_status = 'idle'

                if new_status != old_status:
                    tel['agent_status'] = new_status
                    if self.sio.connected:
                        await self.sio.emit(
                            'agent_telemetry',
                            {
                                'agent_id': agent_id,
                                'telemetry': tel,
                            },
                            namespace='/terminal',
                        )
            await asyncio.sleep(5)

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
            self.status_task = asyncio.create_task(
                self.update_agent_status()
            )

            await asyncio.gather(
                self.watcher_task, self.cache_task,
                self.otlp_task, self.git_task,
                self.status_task,
            )
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
        if hasattr(self, 'status_task') and not self.status_task.done():
            self.status_task.cancel()

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
