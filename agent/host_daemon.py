#!/usr/bin/env python3
"""Host daemon for the Agent Dashboard.

Runs on each development machine to spawn and manage AI coding
agent sessions (Gemini, Claude, Bash) in pseudo-terminals,
relay I/O via Socket.IO, and receive OpenTelemetry data.
"""

import asyncio
import fcntl
import json
import logging
import os
import pty
import re
import select
import signal
import struct
import subprocess
import sys
import tempfile
import termios
import time
from collections import deque
from typing import Dict, Optional

import socketio
from aiohttp import web

from agent.profiles import load_profiles

logging.basicConfig(
    format="%(asctime)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO,
)
log = logging.getLogger("daemon")

# Default permission patterns — generic prompts that
# apply to all agent tools. Tool-specific patterns are
# loaded from agent profiles and merged at daemon startup.
_DEFAULT_PERMISSION_PATTERNS = [
    r"\[Y/n\]",
    r"\[y/N\]",
    r"\(yes/no\)",
    r"\(y/n\)",
    r"press enter to continue",
    r"Continue\?",
    r"Proceed\?",
]

# Seconds of idle output after a pattern match before
# the status transitions to waiting_permission.
PERMISSION_IDLE_SECONDS = 2

# Regex to strip ANSI escape sequences from terminal
# output before pattern matching.
_ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def _split_utf8(data: bytes) -> tuple:
    """Splits a byte string at the last complete UTF-8 character boundary.

    If the final 1-3 bytes of `data` form an incomplete UTF-8 lead or
    continuation sequence, they are returned separately so they can be
    prepended to the next read.

    Returns:
        A (complete, remainder) tuple of bytes. `remainder` is empty
        when the data ends on a valid character boundary.
    """
    if not data:
        return (b"", b"")

    # Check up to the last 3 bytes for an incomplete sequence.
    # A UTF-8 lead byte tells us how many bytes the character needs:
    #   110xxxxx -> 2 bytes, 1110xxxx -> 3 bytes, 11110xxx -> 4 bytes
    for i in range(1, min(4, len(data) + 1)):
        byte = data[-i]
        if byte < 0x80:
            # ASCII — the string is complete
            return (data, b"")
        if byte >= 0xC0:
            # This is a lead byte. Determine expected length.
            if byte < 0xE0:
                expected = 2
            elif byte < 0xF0:
                expected = 3
            else:
                expected = 4
            if i < expected:
                # Not enough continuation bytes — split here
                return (data[:-i], data[-i:])
            # Enough bytes present — sequence is complete
            return (data, b"")
    # All trailing bytes are continuation bytes with no lead
    # — should not happen in valid UTF-8; pass through as-is.
    return (data, b"")


class HostDaemon:
    """Manages agent sessions on a single development host.

    Connects to the hub via Socket.IO, spawns agent processes
    in PTY sessions, relays I/O, and collects OpenTelemetry data.
    """

    def __init__(self, server_url: str, host_token: str):
        self.server_url = server_url
        self.host_token = host_token
        # Parse PROJECTS_ROOT as a colon-separated list of
        # directories to scan for git repositories. A single
        # path (no colon) works as before.
        roots_str = os.getenv("PROJECTS_ROOT", "/git")
        self.projects_roots = [r.strip() for r in roots_str.split(":") if r.strip()]
        # First root used as default for backward compat
        self.projects_root = self.projects_roots[0]
        # OTLP receiver port — configurable to allow multiple
        # daemons on the same host via Network=host
        self.otlp_port = int(os.getenv("OTLP_PORT", "4318"))
        # Maximum directory depth to scan for git repositories
        # below each PROJECTS_ROOT entry. Default of 6 covers
        # most GitLab org hierarchies without being unlimited.
        self.projects_depth = int(os.getenv("PROJECTS_DEPTH", "6"))
        # Load agent profiles from YAML/JSON configs
        self.profiles = load_profiles()
        # Build OTLP metric lookup tables from profiles
        # for fast matching in handle_otlp().
        self._token_metrics: set = set()
        self._cost_metrics: set = set()
        self._activity_metrics: set = set()
        self._runtime_metrics: dict = {}
        self._excluded_metrics: set = set()
        for prof in self.profiles.values():
            tel = prof.telemetry
            self._token_metrics.update(tel.token_metrics)
            if tel.cost_metric:
                self._cost_metrics.add(tel.cost_metric)
            self._activity_metrics.update(tel.activity_metrics)
            if tel.runtime_metric and tel.runtime_metric.name:
                self._runtime_metrics[tel.runtime_metric.name] = tel.runtime_metric.unit
            self._excluded_metrics.update(tel.excluded_metrics)
        # Merge permission patterns from profiles into
        # the default generic patterns.
        all_patterns = list(_DEFAULT_PERMISSION_PATTERNS)
        for prof in self.profiles.values():
            all_patterns.extend(prof.permission_patterns)
        self.permission_patterns = [re.compile(p, re.IGNORECASE) for p in all_patterns]
        self.sio = socketio.AsyncClient()
        self.agents: Dict[str, Dict] = (
            {}
        )  # agent_id -> {master_fd, pid, tool, history, telemetry}
        self.running = True
        self.cached_projects = []
        self.projects_lock = asyncio.Lock()
        self.otlp_runner = None
        # Event set once the OTLP HTTP server is
        # listening.  spawn_agent() awaits this so
        # pi-otel's 300 ms TCP probe at session_start
        # doesn't race against server startup.
        self._otlp_ready = asyncio.Event()

        @self.sio.on("*", namespace="/terminal")
        async def catch_all(event, data):
            if event in ("terminal_output", "terminal_input"):
                return
            # Summarize large payloads to avoid blocking
            # the event loop with synchronous logging calls.
            if event == "host_telemetry_update":
                tel = data.get("telemetry", {})
                n = len(tel.get("available_projects", []))
                hid = data.get("host_id")
                log.info(f"DEBUG: {event} host_id={hid}" f" projects={n}")
            elif event == "agent_telemetry_update":
                aid = data.get("agent_id", "?")[:8]
                tel = data.get("telemetry", {})
                log.info(
                    f"DEBUG: {event} agent={aid}"
                    f" model={tel.get('model', '?')}"
                    f" status={tel.get('agent_status', '?')}"
                )
            else:
                log.info(f"DEBUG: Received event" f" '{event}' with data: {data}")

        @self.sio.on("connect", namespace="/terminal")
        async def on_connect():
            log.info(f"Connected to dashboard at {self.server_url}")
            # Report available projects immediately on connection
            await self.report_projects()
            # Rejoin agent rooms so the backend can route
            # terminal_input and terminal_resize to us.
            for aid in self.agents:
                await self.sio.emit(
                    "join_room",
                    {"room": aid},
                    namespace="/terminal",
                )
                log.info(f"Rejoined agent room: {aid}")

        @self.sio.on("request_projects", namespace="/terminal")
        async def on_request_projects(data):
            # Force a rescan rather than reporting cached
            # data, so the user gets an up-to-date list.
            await self.scan_and_report_projects()

        @self.sio.on("terminal_resize", namespace="/terminal")
        async def on_terminal_resize(data):
            agent_id = data.get("sid")
            cols = data.get("cols")
            rows = data.get("rows")
            if agent_id in self.agents and cols and rows:
                master_fd = self.agents[agent_id]["master_fd"]
                size = struct.pack("HHHH", rows, cols, 0, 0)
                try:
                    fcntl.ioctl(master_fd, termios.TIOCSWINSZ, size)
                except Exception as e:
                    log.info(f"Failed to resize terminal {agent_id}: {e}")

        @self.sio.on("spawn_agent", namespace="/terminal")
        async def on_spawn_agent(data):
            """
            Triggered by the server to start a new AI agent session.
            data: {'agent_id': '...', 'tool': 'gemini|claude',
                    'project_dir': '...', 'task_description': '...',
                    'session_mode': 'resume'|'new'}
            """
            agent_id = data.get("agent_id")
            tool = data.get("tool", "bash")
            project_dir = data.get("project_dir")
            task_description = data.get("task_description")
            session_mode = data.get("session_mode", "resume")
            use_worktree = data.get("use_worktree", False)
            cols = data.get("cols", 120)
            rows = data.get("rows", 40)
            try:
                await self.spawn_agent(
                    agent_id,
                    tool,
                    project_dir,
                    task_description,
                    session_mode,
                    use_worktree,
                    cols,
                    rows,
                )
            except Exception as e:
                log.info(f"Failed to spawn agent {agent_id}: {e}")
                if self.sio.connected:
                    await self.sio.emit(
                        "agent_status_update",
                        {
                            "agent_id": agent_id,
                            "status": "closed",
                        },
                        namespace="/terminal",
                    )

        @self.sio.on("stop_agent", namespace="/terminal")
        async def on_stop_agent(data):
            agent_id = data.get("agent_id")
            if agent_id in self.agents:
                log.info(f"Stopping agent {agent_id} by request.")
                pid = self.agents[agent_id]["pid"]
                try:
                    os.kill(pid, signal.SIGTERM)
                except OSError:
                    pass
                self.close_agent(agent_id)

        @self.sio.on("update_task_description", namespace="/terminal")
        async def on_update_task_description(data):
            """Syncs a user-edited task description into
            the daemon's local telemetry dict so subsequent
            telemetry emits won't overwrite the edit.
            """
            agent_id = data.get("agent_id")
            desc = data.get("task_description", "")
            if agent_id in self.agents:
                self.agents[agent_id]["telemetry"]["task_description"] = desc

        @self.sio.on("request_history", namespace="/terminal")
        async def on_request_history(data):
            agent_id = data.get("agent_id")
            if agent_id in self.agents and self.sio.connected:
                log.info(f"Replaying history for agent: {agent_id}")
                for chunk in self.agents[agent_id]["history"]:
                    await self.sio.emit(
                        "terminal_output",
                        {"sid": agent_id, "output": chunk},
                        namespace="/terminal",
                    )
                await self.sio.emit(
                    "history_complete", {"agent_id": agent_id}, namespace="/terminal"
                )

        @self.sio.on("terminal_input", namespace="/terminal")
        async def on_terminal_input(data):
            agent_id = data.get("target_sid")
            user_input = data.get("input", "")
            if agent_id in self.agents and user_input:
                # Clear permission state on user input —
                # the user has responded to any prompt.
                info = self.agents[agent_id]
                info["permission_waiting"] = False
                info["permission_candidate"] = 0
                master_fd = info["master_fd"]
                try:
                    os.write(master_fd, user_input.encode("utf-8"))
                except OSError:
                    pass

    def _scan_projects(self) -> list:
        """Scans all PROJECTS_ROOT directories for git repos.

        Synchronous method intended to be called from an
        executor to avoid blocking the event loop. Iterates
        over all configured roots and returns absolute paths.

        Returns:
            Sorted list of absolute project paths.
        """
        projects = []
        for scan_root in self.projects_roots:
            if not os.path.exists(scan_root):
                continue
            try:
                for dirpath, dirs, _files in os.walk(scan_root):
                    rel_path = os.path.relpath(dirpath, scan_root)
                    depth = 0 if rel_path == "." else len(rel_path.split(os.sep))
                    if depth > self.projects_depth:
                        dirs[:] = []
                        continue
                    if ".git" in dirs:
                        if rel_path != ".":
                            projects.append(os.path.join(scan_root, rel_path))
                        dirs[:] = [d for d in dirs if d != ".git"]
            except Exception as e:
                log.info(f"Error scanning projects root {scan_root}: {e}")
        projects.sort()
        return projects

    async def update_projects_cache(self):
        """Continuously updates the project cache in the background every 60 seconds."""
        loop = asyncio.get_running_loop()
        while self.running:
            try:
                new_projects = await loop.run_in_executor(None, self._scan_projects)
                async with self.projects_lock:
                    self.cached_projects = new_projects

                # Immediately report if connected
                if self.sio.connected:
                    await self.report_projects()
            except Exception as e:
                log.info(f"Project cache update failed: {e}")

            await asyncio.sleep(60)

    def _find_project_root(self, project_path: str) -> str:
        """Finds which projects root contains a path.

        Checks each configured root to see if the path
        starts with it. Falls back to the first root if
        no match is found.

        Args:
            project_path: Absolute path to a project.

        Returns:
            The matching root directory path.
        """
        for root in self.projects_roots:
            if project_path.startswith(root + "/") or project_path == root:
                return root
        return self.projects_roots[0]

    def _make_tool_info(self, profile) -> dict:
        """Builds a tool metadata dict from a profile for
        the available_tools payload sent to the frontend.

        Args:
            profile: AgentProfile instance.

        Returns:
            Dict with name, display_name, color,
            supports_resume, and has_model fields.
        """
        return {
            "name": profile.name,
            "display_name": profile.display_name,
            "color": profile.color or "slate",
            "supports_resume": profile.supports_resume,
            "has_model": bool(profile.telemetry.token_metrics),
        }

    def _detect_available_tools(self) -> list:
        """Detects which agent CLI tools are installed and
        configured on this host using agent profiles.

        For each profile, checks if the binary is present
        and if the required auth env vars are set. Profiles
        with always_available=true (e.g. bash) are included
        unconditionally.

        Returns:
            List of tool info dicts with name,
            display_name, color, and supports_resume.
        """
        tools = []
        for profile in self.profiles.values():
            if profile.always_available:
                tools.append(self._make_tool_info(profile))
                continue
            # Check if binary exists. Use a generous
            # timeout because some tools (e.g. Pi) load
            # extensions during --version, which can take
            # several seconds under load.
            try:
                subprocess.run(
                    [profile.binary, "--version"],
                    capture_output=True,
                    timeout=15,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired):
                continue
            # Check auth requirements
            if not profile.auth.env_vars:
                tools.append(self._make_tool_info(profile))
                continue
            if profile.auth.require == "all":
                if all(os.getenv(v) for v in profile.auth.env_vars):
                    tools.append(self._make_tool_info(profile))
                else:
                    log.info(
                        f"{profile.display_name} CLI found "
                        f"but auth not configured — "
                        f"not advertising."
                    )
            else:
                if any(os.getenv(v) for v in profile.auth.env_vars):
                    tools.append(self._make_tool_info(profile))
                else:
                    log.info(
                        f"{profile.display_name} CLI found "
                        f"but auth not configured — "
                        f"not advertising."
                    )
        log.info(f"Available tools: {tools}")
        return tools

    async def scan_and_report_projects(self):
        """Rescans PROJECTS_ROOT and reports the updated
        project list to the Hub. Used for force-refresh
        requests from the UI.
        """
        loop = asyncio.get_running_loop()
        new_projects = await loop.run_in_executor(None, self._scan_projects)
        async with self.projects_lock:
            self.cached_projects = new_projects
        log.info(f"Force rescan: found {len(new_projects)} projects.")
        # Invalidate tool cache so force-refresh re-detects
        self._cached_tools = None
        await self.report_projects()

    async def report_projects(self):
        """Instantly reports cached projects and available
        tools to the Hub.
        """
        async with self.projects_lock:
            projects = list(self.cached_projects)

        # Use cached tools — _detect_available_tools() runs
        # synchronous subprocess calls that block the event
        # loop. Tools don't change at runtime so we detect
        # once at startup and on explicit refresh.
        if not hasattr(self, "_cached_tools") or not self._cached_tools:
            loop = asyncio.get_running_loop()
            self._cached_tools = await loop.run_in_executor(
                None, self._detect_available_tools
            )
        tools = self._cached_tools
        log.info(f"Reporting {len(projects)} projects, {len(tools)} tools to Hub.")
        if self.sio.connected:
            await self.sio.emit(
                "host_telemetry",
                {
                    "projects_root": self.projects_roots,
                    "available_projects": projects,
                    "available_tools": tools,
                },
                namespace="/terminal",
            )

    @staticmethod
    def _remote_to_web_url(remote_url: str) -> str | None:
        """Converts a git remote URL to an HTTPS web URL.

        Handles SSH and HTTPS formats:
        - git@github.com:user/repo.git → https://github.com/user/repo
        - https://github.com/user/repo.git → https://github.com/user/repo
        - git@gitlab.internal:group/repo.git → https://gitlab.internal/group/repo

        Returns None if the URL format is not recognized.
        """
        if not remote_url:
            return None
        url = remote_url.strip()
        # SSH format: git@host:path.git
        if url.startswith("git@"):
            url = url[4:]  # Remove git@
            url = url.replace(":", "/", 1)  # host:path → host/path
            url = "https://" + url
        # Ensure https://
        if not url.startswith("http"):
            return None
        # Remove .git suffix
        if url.endswith(".git"):
            url = url[:-4]
        return url

    def get_git_info(self, path: str):
        """Extracts git branch, project name, and remote web
        URL from a directory.

        The project name is derived from the remote origin URL
        when available, falling back to the git repository's
        root directory name. The web URL is the HTTPS version
        of the remote origin for linking in the UI.

        Returns:
            A (branch, project, remote_url) tuple.
        """
        if not path or not os.path.exists(path):
            return None, None, None

        branch = None
        project = None
        remote_url = None

        try:
            branch = (
                subprocess.check_output(
                    ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                    cwd=path,
                    stderr=subprocess.DEVNULL,
                )
                .decode()
                .strip()
            )
        except Exception:
            pass

        try:
            origin = (
                subprocess.check_output(
                    ["git", "config", "--get", "remote.origin.url"],
                    cwd=path,
                    stderr=subprocess.DEVNULL,
                )
                .decode()
                .strip()
            )
            project = origin.rsplit("/", maxsplit=1)[-1].replace(".git", "")
            remote_url = self._remote_to_web_url(origin)
        except Exception:
            # No remote configured — use the repo root directory name
            try:
                toplevel = (
                    subprocess.check_output(
                        ["git", "rev-parse", "--show-toplevel"],
                        cwd=path,
                        stderr=subprocess.DEVNULL,
                    )
                    .decode()
                    .strip()
                )
                project = os.path.basename(toplevel)
            except Exception:
                pass

        return branch, project, remote_url

    def _detect_mcp_servers(self, project_dir, tool):
        """Detects MCP servers configured for the given tool.

        Uses the agent profile's MCP config to find server
        definitions in project-level and user-level config
        files. Deduplicates server names across files.

        Args:
            project_dir: The project directory path.
            tool: The agent tool name.

        Returns:
            A list of MCP server name strings.
        """
        profile = self.profiles.get(tool)
        if not profile or not profile.mcp:
            return []

        servers = []
        try:
            # Project-level config file
            if profile.mcp.project_file and project_dir:
                mcp_path = os.path.join(project_dir, profile.mcp.project_file)
                if os.path.isfile(mcp_path):
                    with open(mcp_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    mcp_servers = data.get("mcpServers", {})
                    servers.extend(mcp_servers.keys())

            # User-level config files
            for user_file in profile.mcp.user_files:
                path = os.path.expanduser(user_file)
                if os.path.isfile(path):
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    mcp_servers = data.get("mcpServers", {})
                    for name in mcp_servers.keys():
                        if name not in servers:
                            servers.append(name)
        except Exception as e:
            log.info(f"MCP detection error for {tool}: {e}")

        return servers

    async def spawn_agent(
        self,
        agent_id: str,
        tool: str,
        project_dir: Optional[str] = None,
        task: Optional[str] = None,
        session_mode: str = "resume",
        use_worktree: bool = False,
        cols: int = 120,
        rows: int = 40,
    ):
        """Spawns a new process in a pseudo-terminal with environmental context.

        Args:
            agent_id: Unique identifier for the agent session.
            tool: The CLI tool to spawn ('claude', 'gemini', 'bash').
            project_dir: Working directory for the agent.
            task: Optional task description for the session.
            session_mode: 'resume' to continue the latest session
                          (default), or 'new' for a fresh session.
            use_worktree: If True, create a git worktree for
                          isolation from other agents on the same
                          repo.
            cols: Initial terminal width in columns (default 120).
            rows: Initial terminal height in rows (default 40).
        """
        # Resolve full path (handles both absolute and relative from projects_root)
        full_path = project_dir
        if project_dir and not project_dir.startswith("/"):
            full_path = os.path.join(self.projects_root, project_dir)

        # Ensure we use an absolute path for working directory
        if full_path:
            full_path = os.path.abspath(full_path)

        # Create a git worktree for isolation if requested.
        # The worktree is stored under the project's root
        # directory in .agent-worktrees/ to keep the original
        # repo clean. MCP detection and companion matching
        # use the original project_dir.
        original_project_dir = full_path
        worktree_path = None
        worktree_branch = None
        if use_worktree and full_path:
            try:
                project_root = self._find_project_root(full_path)
                project_name = os.path.relpath(full_path, project_root)
                short_id = agent_id[:8]
                worktree_dir = os.path.join(
                    project_root,
                    ".agent-worktrees",
                    project_name,
                    f"agent-{short_id}",
                )
                worktree_branch = f"agent/{tool}-{short_id}"
                os.makedirs(os.path.dirname(worktree_dir), exist_ok=True)
                # Prune stale worktree refs before creating
                subprocess.run(
                    ["git", "worktree", "prune"],
                    cwd=full_path,
                    capture_output=True,
                    check=False,
                )
                subprocess.check_output(
                    [
                        "git",
                        "worktree",
                        "add",
                        "-b",
                        worktree_branch,
                        worktree_dir,
                    ],
                    cwd=full_path,
                    stderr=subprocess.STDOUT,
                )
                worktree_path = worktree_dir
                full_path = worktree_dir
                # Worktrees have no prior session state
                session_mode = "new"
                log.info(
                    f"Created worktree for {agent_id}: "
                    f"{worktree_dir} (branch {worktree_branch})"
                )
            except Exception as e:
                log.info(
                    f"Failed to create worktree for "
                    f"{agent_id}: {e}. "
                    f"Falling back to original directory."
                )
                full_path = original_project_dir
                worktree_path = None
                worktree_branch = None

        # Detect if full_path is inside an existing worktree
        # (e.g. companion session spawned into a parent's
        # worktree). Set worktree_path so the UI shows the
        # worktree indicator, and resolve the original
        # project_dir for MCP detection and companion matching.
        # Check all roots for worktree markers
        in_worktree = False
        if not worktree_path and full_path:
            for rt in self.projects_roots:
                marker = os.path.join(rt, ".agent-worktrees")
                if full_path.startswith(marker):
                    in_worktree = True
                    break
        if in_worktree:
            worktree_path = full_path
            # Resolve original project_dir from the worktree's
            # git configuration.
            try:
                git_common = (
                    subprocess.check_output(
                        ["git", "rev-parse", "--git-common-dir"],
                        cwd=full_path,
                        stderr=subprocess.DEVNULL,
                    )
                    .decode()
                    .strip()
                )
                # git-common-dir returns the .git dir of the
                # parent repo (e.g. /git/project/.git)
                if git_common and not git_common.startswith("/"):
                    git_common = os.path.normpath(os.path.join(full_path, git_common))
                original_project_dir = os.path.dirname(git_common)
            except Exception:
                pass

        # Wait for the OTLP receiver to be listening
        # before spawning the agent process.  pi-otel
        # probes the endpoint with a 300 ms TCP connect
        # at session_start; if the server isn't ready the
        # probe fails and telemetry is silently disabled
        # for the entire session.
        try:
            await asyncio.wait_for(self._otlp_ready.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            log.warning(
                f"OTLP server not ready after 5 s — "
                f"agent {agent_id} may not report "
                f"telemetry"
            )

        log.info(
            f"Spawning agent {agent_id} with tool: {tool} "
            f"mode: {session_mode} in {full_path}"
        )

        # Get git info from the original project directory
        # (not the worktree) so the card shows the real
        # project name and remote URL initially.
        git_info_path = original_project_dir or full_path
        branch, project, remote_url = self.get_git_info(git_info_path)
        mcp_servers = self._detect_mcp_servers(original_project_dir, tool)
        telemetry = {
            "project_dir": original_project_dir,
            "task_description": task,
            "git_branch": branch,
            "git_project": project,
            "git_remote_url": remote_url,
            "model": "detecting...",
            "tokens": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_read_tokens": 0,
            "cache_creation_tokens": 0,
            "cost_usd": 0.0,
            "context_tokens": 0,
            "current_activity": "",
            "agent_status": "idle",
            "mcp_servers": mcp_servers,
            "run_time_seconds": 0,
            "worktree_path": worktree_path,
        }

        # Build command from the agent profile. Resume mode
        # uses a fallback command if defined, otherwise
        # falls back to the new-session command.
        profile = self.profiles.get(tool)
        if profile:
            if session_mode == "resume" and profile.commands.resume:
                cmd = profile.commands.resume
            else:
                cmd = profile.commands.new or [tool]
        else:
            cmd = [tool]

        pid, fd = pty.fork()
        if pid == 0:  # Child process
            if full_path and os.path.exists(full_path):
                os.chdir(full_path)

            env = os.environ.copy()
            env["TERM"] = "xterm-256color"
            env["COLORTERM"] = "truecolor"

            # Inject OpenTelemetry standard configuration
            env["OTEL_EXPORTER_OTLP_ENDPOINT"] = f"http://127.0.0.1:{self.otlp_port}"
            env["OTEL_RESOURCE_ATTRIBUTES"] = f"service.name={agent_id}"

            # Inject profile-specific environment variables.
            # Values can use {otlp_port} and {agent_id}
            # placeholders. Uses .replace() instead of
            # .format() to avoid KeyError if a value
            # contains literal curly braces.
            if profile:
                for key, value in profile.env.items():
                    env[key] = (
                        str(value)
                        .replace("{otlp_port}", str(self.otlp_port))
                        .replace("{agent_id}", agent_id)
                    )

            # Inject sidecar PROMPT_COMMAND if the profile
            # defines one (e.g. bash telemetry collection).
            if profile and profile.sidecar and profile.sidecar.prompt_command:
                sidecar_path = profile.sidecar.file_pattern.format(
                    agent_id=agent_id, tmpdir=tempfile.gettempdir()
                )
                env["PROMPT_COMMAND"] = (
                    f"{profile.sidecar.prompt_command} > {sidecar_path}"
                )

            try:
                os.execvpe(cmd[0], cmd, env)
            except Exception as e:
                log.info(f"Failed to execute {cmd}: {e}")
                os._exit(1)
        else:  # Parent process
            # Set initial PTY dimensions before the agent
            # starts producing output. This avoids the brief
            # period where the PTY defaults to 80x24 while the
            # frontend sends a resize after connecting.
            try:
                size = struct.pack("HHHH", rows, cols, 0, 0)
                fcntl.ioctl(fd, termios.TIOCSWINSZ, size)
            except Exception as e:
                log.info(f"Failed to set initial PTY size " f"for {agent_id}: {e}")

            self.agents[agent_id] = {
                "master_fd": fd,
                "pid": pid,
                "tool": tool,
                "history": deque(maxlen=1000),
                "telemetry": telemetry,
                "last_otlp_time": 0.0,
                "last_output_time": time.monotonic(),
                "permission_waiting": False,
                "permission_candidate": 0,
                "utf8_buffer": b"",
                "worktree_path": worktree_path,
                "worktree_branch": worktree_branch,
                "original_project_dir": original_project_dir,
            }
            if self.sio.connected:
                await self.sio.emit(
                    "agent_telemetry",
                    {
                        "agent_id": agent_id,
                        "telemetry": telemetry,
                    },
                    namespace="/terminal",
                )
                # Join the agent's room so the backend
                # routes terminal_input to this daemon.
                await self.sio.emit(
                    "join_room",
                    {"room": agent_id},
                    namespace="/terminal",
                )
                log.info(f"Joined agent room: {agent_id}")
            os.write(fd, b"\n")

    async def watch_agents(self):
        """Monitors PTY file descriptors and relays agent output."""
        loop = asyncio.get_running_loop()
        while self.running:
            if not self.agents:
                await asyncio.sleep(0.5)
                continue
            fds = [a["master_fd"] for a in self.agents.values()]
            try:
                r, _, _ = await loop.run_in_executor(
                    None, select.select, fds, [], [], 0.1
                )
            except ValueError:
                self.cleanup_closed_agents()
                continue
            for fd in r:
                agent_entry = next(
                    (
                        item
                        for item in self.agents.items()
                        if item[1]["master_fd"] == fd
                    ),
                    None,
                )
                if not agent_entry:
                    continue
                agent_id, info = agent_entry
                try:
                    # Drain all available data from the PTY
                    # in a tight loop so that rapid bursts of
                    # output (e.g. Claude updating multiple
                    # status lines with cursor-movement escape
                    # sequences) are coalesced into a single
                    # socket emit.  This reduces partial escape
                    # sequence chunks reaching the frontend,
                    # which cause visible terminal jumping.
                    raw = os.read(fd, 65536)
                    if not raw:
                        self.close_agent(agent_id)
                        continue
                    while True:
                        rd, _, _ = select.select([fd], [], [], 0)
                        if not rd:
                            break
                        chunk = os.read(fd, 65536)
                        if not chunk:
                            break
                        raw += chunk
                    if self.sio.connected:
                        # Prepend any leftover bytes from a
                        # previously split UTF-8 character.
                        buf = info.get("utf8_buffer", b"")
                        data = buf + raw
                        complete, remainder = _split_utf8(data)
                        info["utf8_buffer"] = remainder
                        if not complete:
                            continue
                        decoded_data = complete.decode("utf-8", errors="replace")
                        self.agents[agent_id]["history"].append(decoded_data)
                        self.agents[agent_id]["last_output_time"] = time.monotonic()

                        # Check for permission prompts.
                        # Strip ANSI escapes before matching to
                        # avoid false positives on escape codes.
                        # A match sets a candidate timestamp;
                        # the status poll promotes it to
                        # permission_waiting after the agent
                        # has been idle for PERMISSION_IDLE_SECONDS.
                        stripped = _ANSI_ESCAPE.sub("", decoded_data)
                        now = time.monotonic()
                        if any(p.search(stripped) for p in self.permission_patterns):
                            info["permission_candidate"] = now
                        # New output clears permission_waiting
                        # since the agent is actively producing
                        # output (not waiting for input).
                        if info.get("permission_waiting"):
                            info["permission_waiting"] = False

                        try:
                            await self.sio.emit(
                                "terminal_output",
                                {
                                    "sid": agent_id,
                                    "output": decoded_data,
                                },
                                namespace="/terminal",
                            )
                        except Exception:
                            pass
                except OSError:
                    self.close_agent(agent_id)
            await asyncio.sleep(0.01)

    def close_agent(self, agent_id: str):
        """Closes the PTY fd and removes an agent from tracking."""
        if agent_id in self.agents:
            log.info(f"Closing agent {agent_id}")
            fd = self.agents[agent_id]["master_fd"]
            try:
                os.close(fd)
            except OSError:
                pass
            # Clean up sidecar telemetry file if the
            # profile defines one
            tool_name = self.agents[agent_id].get("tool")
            profile = self.profiles.get(tool_name)
            if profile and profile.sidecar:
                sidecar = profile.sidecar.file_pattern.format(
                    agent_id=agent_id, tmpdir=tempfile.gettempdir()
                )
                try:
                    os.unlink(sidecar)
                except OSError:
                    pass
            # Clean up git worktree if one was created
            wt_path = self.agents[agent_id].get("worktree_path")
            wt_branch = self.agents[agent_id].get("worktree_branch")
            orig_dir = self.agents[agent_id].get("original_project_dir")
            if wt_path and orig_dir:
                try:
                    subprocess.run(
                        ["git", "worktree", "remove", "--force", wt_path],
                        cwd=orig_dir,
                        capture_output=True,
                        check=False,
                    )
                    log.info(f"Removed worktree {wt_path}")
                except Exception as e:
                    log.info(f"Failed to remove worktree {wt_path}: {e}")
                if wt_branch:
                    try:
                        subprocess.run(
                            ["git", "branch", "-D", wt_branch],
                            cwd=orig_dir,
                            capture_output=True,
                            check=False,
                        )
                    except Exception as e:
                        log.info(f"Failed to delete branch {wt_branch}: {e}")
                # Clean up empty parent directories
                try:
                    parent = os.path.dirname(wt_path)
                    if os.path.isdir(parent) and not os.listdir(parent):
                        os.rmdir(parent)
                except OSError:
                    pass
            del self.agents[agent_id]
            if self.sio.connected:
                asyncio.create_task(
                    self.sio.emit(
                        "agent_exit", {"agent_id": agent_id}, namespace="/terminal"
                    )
                )

    def cleanup_closed_agents(self):
        """Removes agents whose PTY file descriptors are closed."""
        to_delete = []
        for aid, info in self.agents.items():
            try:
                os.fstat(info["master_fd"])
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
        for key in ("stringValue", "intValue", "doubleValue", "boolValue"):
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
            key = attr.get("key", "")
            value = attr.get("value", {})
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
        for key in ("model", "gen_ai.request.model", "gen_ai.response.model"):
            model = attrs.get(key)
            if model and isinstance(model, str) and tel.get("model") != model:
                tel["model"] = model
                changed = True
                break

        # Token detection — try common attribute names
        input_tokens = None
        output_tokens = None
        cache_tokens = None
        for key in ("input_token_count", "input_tokens", "gen_ai.usage.input_tokens"):
            val = attrs.get(key)
            if val is not None:
                input_tokens = int(val)
                break
        for key in (
            "output_token_count",
            "output_tokens",
            "gen_ai.usage.output_tokens",
        ):
            val = attrs.get(key)
            if val is not None:
                output_tokens = int(val)
                break
        # Cache tokens — check both short names (Claude)
        # and GenAI semconv names (pi-otel).
        cache_read = None
        cache_creation = None
        for key in (
            "cache_read_tokens",
            "gen_ai.usage.cache_read_input_tokens",
        ):
            val = attrs.get(key)
            if val is not None:
                cache_read = int(val)
                break
        for key in (
            "cache_creation_tokens",
            "gen_ai.usage.cache_creation_input_tokens",
        ):
            val = attrs.get(key)
            if val is not None:
                cache_creation = int(val)
                break
        if cache_read is not None or cache_creation is not None:
            cache_tokens = (cache_read or 0) + (cache_creation or 0)
        else:
            cache_tokens = None

        if input_tokens is not None or output_tokens is not None:
            total = (input_tokens or 0) + (output_tokens or 0) + (cache_tokens or 0)
            if total > tel.get("tokens", 0):
                tel["tokens"] = total
                changed = True

        # Track input_tokens as context_tokens — this is
        # the per-API-call value representing current context
        # window usage (accounts for compression/eviction).
        # Always overwrite with the latest value so it can
        # decrease after context compression.
        if input_tokens is not None and input_tokens > 0:
            tel["context_tokens"] = input_tokens
            changed = True

        # Cost — pi-otel puts cumulative session cost on
        # pi.llm_request span attributes as pi.cost.usd.
        cost = attrs.get("pi.cost.usd")
        if cost is not None:
            cost_f = float(cost)
            if cost_f > tel.get("cost_usd", 0.0):
                tel["cost_usd"] = cost_f
                changed = True

        # Current activity — extract the latest tool/function
        # name from span or log attributes.  Gemini uses
        # 'function_name', Claude uses 'tool_name', pi-otel
        # uses 'gen_ai.tool.name'.
        activity = None
        for key in (
            "function_name",
            "tool_name",
            "gen_ai.tool.name",
            "gen_ai.operation.name",
        ):
            val = attrs.get(key)
            if val and isinstance(val, str):
                activity = val
                break

        # Fall back to event.name for log records
        if not activity:
            event_name = attrs.get("event.name")
            if (
                event_name
                and isinstance(event_name, str)
                and event_name not in ("gen_ai_operation_details",)
            ):
                activity = event_name

        if activity:
            tel["current_activity"] = activity
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
        agent_id = res_attrs.get("service.name")
        if agent_id and agent_id in self.agents:
            return agent_id

        # Fallback: infer tool type from resource attributes and
        # match to an active agent of that type.
        tool_hint = None
        svc = res_attrs.get("service.name", "") or ""
        all_vals = " ".join(str(v) for v in res_attrs.values() if v).lower()

        if "gemini" in svc.lower() or "gemini" in all_vals:
            tool_hint = "gemini"
        elif "claude" in svc.lower() or "claude" in all_vals:
            tool_hint = "claude"
        elif "pi" == svc.lower() or "pi-otel" in all_vals:
            tool_hint = "pi"

        if tool_hint:
            candidates = [
                (aid, info)
                for aid, info in self.agents.items()
                if info.get("tool") == tool_hint
            ]
            if len(candidates) == 1:
                return candidates[0][0]
            elif len(candidates) > 1:
                # Multiple agents of same type — use the most
                # recently spawned (highest last_output_time as
                # proxy for recency)
                return max(
                    candidates,
                    key=lambda c: c[1].get("last_output_time", 0),
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
            # Identify signal types present in the payload
            # for clearer logging (especially when requests
            # arrive on the root-path compatibility route).
            signals = [
                k.replace("resource", "").lower()
                for k in data
                if k.startswith("resource")
            ]
            log.info(
                f"OTLP received on {request.path}"
                f" signals={signals or list(data.keys())}"
            )

            # Optional verbose debug mode for inspecting
            # raw OTLP payloads from agent tools.
            if os.getenv("OTLP_DEBUG"):
                log.info(
                    f"OTLP DEBUG {request.path}:\n"
                    f"{json.dumps(data, indent=2, default=str)}"
                )

            # Process OTLP Logs (resourceLogs → scopeLogs → logRecords)
            for res_log in data.get("resourceLogs", []):
                resource = res_log.get("resource", {})
                res_attrs = self._process_otel_attributes(
                    resource.get("attributes", [])
                )
                agent_id = self._resolve_agent_id(res_attrs)

                if not agent_id:
                    log.info(
                        f"OTLP: no agent match for resource " f"attrs: {res_attrs}"
                    )
                    continue
                tel = self.agents[agent_id]["telemetry"]
                changed = False

                for scope_log in res_log.get("scopeLogs", []):
                    for record in scope_log.get("logRecords", []):
                        attrs = self._process_otel_attributes(
                            record.get("attributes", [])
                        )
                        if self._update_telemetry_from_attrs(tel, attrs):
                            changed = True

                if changed:
                    self.agents[agent_id]["last_otlp_time"] = time.monotonic()
                    if self.sio.connected:
                        await self.sio.emit(
                            "agent_telemetry",
                            {"agent_id": agent_id, "telemetry": tel},
                            namespace="/terminal",
                        )

            # Process OTLP Traces (resourceSpans → scopeSpans → spans)
            for res_span in data.get("resourceSpans", []):
                resource = res_span.get("resource", {})
                res_attrs = self._process_otel_attributes(
                    resource.get("attributes", [])
                )
                agent_id = self._resolve_agent_id(res_attrs)

                if not agent_id:
                    log.info("OTLP: no agent match for trace" f" resource: {res_attrs}")
                    continue
                tel = self.agents[agent_id]["telemetry"]
                changed = False

                # Keywords that indicate the agent is
                # waiting for user input / permission.
                _wait_keywords = (
                    "permission",
                    "user_input",
                    "approval",
                    "confirm",
                    "waiting",
                )

                for scope_span in res_span.get("scopeSpans", []):
                    for span in scope_span.get("spans", []):
                        attrs = self._process_otel_attributes(
                            span.get("attributes", [])
                        )
                        if self._update_telemetry_from_attrs(tel, attrs):
                            changed = True

                        # Extract activity from span names like
                        # "pi.tool.bash", "pi.tool.read", etc.
                        # when attributes didn't provide it.
                        span_name = span.get("name") or ""
                        if span_name.startswith("pi.tool."):
                            tool = span_name[len("pi.tool.") :]
                            if tool and tel.get("current_activity") != tool:
                                tel["current_activity"] = tool
                                changed = True

                        # Check span name for permission /
                        # waiting signals (future-proofing for
                        # when tools emit these via OTLP).
                        span_name = span_name.lower()
                        if any(kw in span_name for kw in _wait_keywords):
                            info = self.agents[agent_id]
                            info["permission_candidate"] = time.monotonic()
                            changed = True

                        # Check span events for waiting
                        # indicators.
                        for event in span.get("events", []):
                            event_name = (event.get("name") or "").lower()
                            if any(kw in event_name for kw in _wait_keywords):
                                info = self.agents[agent_id]
                                info["permission_candidate"] = time.monotonic()
                                changed = True

                if changed:
                    self.agents[agent_id]["last_otlp_time"] = time.monotonic()
                    if self.sio.connected:
                        await self.sio.emit(
                            "agent_telemetry",
                            {"agent_id": agent_id, "telemetry": tel},
                            namespace="/terminal",
                        )

            # Process OTLP Metrics
            # (resourceMetrics → scopeMetrics → metrics → dataPoints)
            # Claude Code sends token usage as counter metrics with
            # 'model' and 'type' (input/output) attributes.
            for res_metric in data.get("resourceMetrics", []):
                resource = res_metric.get("resource", {})
                res_attrs = self._process_otel_attributes(
                    resource.get("attributes", [])
                )
                agent_id = self._resolve_agent_id(res_attrs)

                if not agent_id:
                    log.info(
                        "OTLP: no agent match for metric" f" resource: {res_attrs}"
                    )
                    continue
                tel = self.agents[agent_id]["telemetry"]
                changed = False

                for scope_metric in res_metric.get("scopeMetrics", []):
                    for metric in scope_metric.get("metrics", []):
                        name = metric.get("name", "")

                        # Collect data points from sum, gauge, or
                        # histogram structures
                        data_points = []
                        for container in ("sum", "gauge", "histogram"):
                            section = metric.get(container, {})
                            data_points.extend(section.get("dataPoints", []))

                        for dp in data_points:
                            dp_attrs = self._process_otel_attributes(
                                dp.get("attributes", [])
                            )

                            # Model detection from any metric with a
                            # 'model' attribute. GenAI conventions
                            # also use gen_ai.response.model.
                            model = (
                                dp_attrs.get("model")
                                or dp_attrs.get("gen_ai.response.model")
                                or dp_attrs.get("gen_ai.request.model")
                            )
                            if (
                                model
                                and isinstance(model, str)
                                and tel.get("model") != model
                            ):
                                tel["model"] = model
                                changed = True

                            # Extract the data point value. Sum and
                            # Gauge metrics use asInt/asDouble.
                            # Histogram metrics store cumulative
                            # totals in the "sum" field instead.
                            dp_value = (
                                dp.get("asInt")
                                or dp.get("asDouble")
                                or dp.get("sum")
                                or 0
                            )

                            # Token, cost, activity, and runtime
                            # metrics are matched against the
                            # lookup tables built from agent
                            # profiles at startup. Metric names
                            # are defined in the profile YAML
                            # files under agent/profiles/.
                            #
                            # Token metrics may be OTLP cumulative
                            # Sum counters or Histograms (pi-otel
                            # uses histograms). Use max() not +=.
                            if (
                                name in self._token_metrics
                                and name not in self._excluded_metrics
                            ):
                                if dp_value:
                                    int_value = int(dp_value)
                                    # Claude uses "type", GenAI
                                    # semconv uses "gen_ai.token.type"
                                    token_type = (
                                        dp_attrs.get("type")
                                        or dp_attrs.get("gen_ai.token.type")
                                        or ""
                                    )
                                    if token_type == "input":
                                        tel["input_tokens"] = max(
                                            tel.get("input_tokens", 0),
                                            int_value,
                                        )
                                    elif token_type == "output":
                                        tel["output_tokens"] = max(
                                            tel.get("output_tokens", 0),
                                            int_value,
                                        )
                                    elif token_type == "cacheRead":
                                        tel["cache_read_tokens"] = max(
                                            tel.get("cache_read_tokens", 0),
                                            int_value,
                                        )
                                    elif token_type in (
                                        "cacheCreation",
                                        "cache",
                                    ):
                                        tel["cache_creation_tokens"] = max(
                                            tel.get("cache_creation_tokens", 0),
                                            int_value,
                                        )
                                    tel["tokens"] = (
                                        tel.get("input_tokens", 0)
                                        + tel.get("output_tokens", 0)
                                        + tel.get("cache_read_tokens", 0)
                                        + tel.get("cache_creation_tokens", 0)
                                    )
                                    changed = True

                            # Cost metrics (cumulative Sum, USD)
                            if name in self._cost_metrics:
                                if dp_value:
                                    tel["cost_usd"] = max(
                                        tel.get("cost_usd", 0.0),
                                        float(dp_value),
                                    )
                                    changed = True

                            # Activity metrics (tool/function name)
                            if name in self._activity_metrics:
                                fn = (
                                    dp_attrs.get("function_name")
                                    or dp_attrs.get("tool_name")
                                    or dp_attrs.get("gen_ai.tool.name")
                                )
                                if fn and isinstance(fn, str):
                                    tel["current_activity"] = fn
                                    changed = True

                            # Runtime duration metrics
                            if name in self._runtime_metrics:
                                if dp_value:
                                    unit = self._runtime_metrics[name]
                                    if unit == "milliseconds":
                                        tel["run_time_seconds"] = int(dp_value / 1000)
                                    else:
                                        tel["run_time_seconds"] = int(dp_value)
                                    changed = True

                if changed:
                    self.agents[agent_id]["last_otlp_time"] = time.monotonic()
                    if self.sio.connected:
                        await self.sio.emit(
                            "agent_telemetry",
                            {"agent_id": agent_id, "telemetry": tel},
                            namespace="/terminal",
                        )

            return web.Response(
                status=200,
                text="{}",
                content_type="application/json",
                headers={"Connection": "close"},
            )
        except Exception as e:
            log.info(f"OTLP Error: {e}")
            return web.Response(status=400)

    async def start_otlp_server(self):
        """Starts a local HTTP server for OpenTelemetry data."""
        app = web.Application()
        app.router.add_post("/v1/logs", self.handle_otlp)
        app.router.add_post("/v1/traces", self.handle_otlp)
        app.router.add_post("/v1/metrics", self.handle_otlp)
        # Compatibility route: accept OTLP payloads on the
        # root path for clients that send to the endpoint URL
        # directly instead of appending /v1/{signal}.  This is
        # harmless and keeps the receiver resilient regardless
        # of client implementation details.
        # History: https://github.com/NikiforovAll/pi-otel/issues/4
        app.router.add_post("/", self.handle_otlp)
        self.otlp_runner = web.AppRunner(app)
        await self.otlp_runner.setup()
        site = web.TCPSite(self.otlp_runner, "127.0.0.1", self.otlp_port)
        await site.start()
        self._otlp_ready.set()
        log.info(f"OTLP Receiver listening on " f"http://127.0.0.1:{self.otlp_port}")

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
                try:
                    tel = info["telemetry"]
                    old_status = tel.get("agent_status")

                    # Promote permission candidate to
                    # permission_waiting if the agent has
                    # been idle (no output) since the match.
                    candidate_time = info.get("permission_candidate", 0)
                    if candidate_time > 0:
                        idle_since = now - info.get("last_output_time", 0)
                        if idle_since >= PERMISSION_IDLE_SECONDS:
                            info["permission_waiting"] = True

                    if info.get("permission_waiting"):
                        new_status = "waiting_permission"
                    elif (now - info.get("last_otlp_time", 0)) < 15:
                        new_status = "working"
                    elif (now - info.get("last_output_time", 0)) < 15:
                        new_status = "working"
                    else:
                        new_status = "idle"

                    if new_status != old_status:
                        tel["agent_status"] = new_status
                        if self.sio.connected:
                            await self.sio.emit(
                                "agent_telemetry",
                                {
                                    "agent_id": agent_id,
                                    "telemetry": tel,
                                },
                                namespace="/terminal",
                            )
                except Exception:
                    pass
            await asyncio.sleep(5)

    async def update_agents_git_info(self):
        """Periodically checks the current working directory
        of each agent and updates git info."""
        while self.running:
            for agent_id, info in list(self.agents.items()):
                try:
                    pid = info["pid"]
                    if not pid:
                        continue
                    # Try to read the cwd of the child process.
                    # For worktree agents, use the original
                    # project dir for project name and remote
                    # URL so the card doesn't show the worktree
                    # directory name.
                    cwd = os.readlink(f"/proc/{pid}/cwd")
                    orig = info.get("original_project_dir")
                    branch, project, remote_url = self.get_git_info(cwd)
                    if orig and orig != cwd:
                        _, orig_project, orig_url = self.get_git_info(orig)
                        if orig_project:
                            project = orig_project
                        if orig_url:
                            remote_url = orig_url

                    tel = info["telemetry"]
                    changed = False
                    if branch and tel.get("git_branch") != branch:
                        tel["git_branch"] = branch
                        changed = True
                    if project and tel.get("git_project") != project:
                        tel["git_project"] = project
                        changed = True
                    if remote_url and tel.get("git_remote_url") != remote_url:
                        tel["git_remote_url"] = remote_url
                        changed = True

                    # Read sidecar telemetry file if the
                    # profile defines one (e.g. bash uses
                    # PROMPT_COMMAND to write cwd, exit code,
                    # and last command to a JSON file).
                    tool_name = info.get("tool")
                    profile = self.profiles.get(tool_name)
                    if profile and profile.sidecar:
                        sidecar = profile.sidecar.file_pattern.format(
                            agent_id=agent_id, tmpdir=tempfile.gettempdir()
                        )
                        try:
                            with open(sidecar, "r", encoding="utf-8") as f:
                                sc_data = json.loads(f.read().strip())
                            # Map sidecar fields to telemetry
                            # using the profile's field mapping
                            for tel_key, sc_key in profile.sidecar.fields.items():
                                val = sc_data.get(sc_key)
                                if val is not None and tel.get(tel_key) != val:
                                    tel[tel_key] = val
                                    changed = True
                        except (FileNotFoundError, json.JSONDecodeError):
                            # Sidecar not yet written —
                            # fall back to /proc cwd
                            if cwd and tel.get("current_activity") != cwd:
                                tel["current_activity"] = cwd
                                changed = True

                    if changed and self.sio.connected:
                        await self.sio.emit(
                            "agent_telemetry",
                            {"agent_id": agent_id, "telemetry": tel},
                            namespace="/terminal",
                        )
                except Exception:
                    pass  # Process might have died or no permission
            await asyncio.sleep(5)

    async def _run_task(self, name, coro):
        """Runs a background task with error recovery.

        Catches exceptions and restarts the task instead of
        letting failures propagate through asyncio.gather()
        and crash the entire daemon.

        Args:
            name: Human-readable task name for logging.
            coro: Async callable (unbound method) to run.
        """
        while self.running:
            try:
                await coro()
                return
            except asyncio.CancelledError:
                return
            except Exception as e:
                log.info(f"Background task '{name}' failed: {e}")
                log.info(f"Restarting '{name}' in 5 seconds...")
                await asyncio.sleep(5)

    async def run(self):
        """Connects to the hub and starts all background tasks."""
        try:
            await self.sio.connect(
                self.server_url,
                namespaces=["/terminal"],
                headers={"X-Host-Token": self.host_token},
            )
            # Start background tasks with error recovery.
            # Each task is wrapped in _run_task so a failure
            # in one doesn't crash the entire daemon. The
            # OTLP server uses aiohttp's own error handling.
            self.watcher_task = asyncio.create_task(
                self._run_task("watcher", self.watch_agents)
            )
            self.cache_task = asyncio.create_task(
                self._run_task("cache", self.update_projects_cache)
            )
            self.otlp_task = asyncio.create_task(self.start_otlp_server())
            self.git_task = asyncio.create_task(
                self._run_task("git_info", self.update_agents_git_info)
            )
            self.status_task = asyncio.create_task(
                self._run_task("status", self.update_agent_status)
            )

            await asyncio.gather(
                self.watcher_task,
                self.cache_task,
                self.otlp_task,
                self.git_task,
                self.status_task,
            )
        except asyncio.CancelledError:
            pass
        except Exception as e:
            log.info(f"Daemon error: {e}")
        finally:
            self.running = False
            if self.otlp_runner:
                await self.otlp_runner.cleanup()
            for agent_id in list(self.agents.keys()):
                self.close_agent(agent_id)
            if self.sio.connected:
                await self.sio.disconnect()
            log.info("Daemon stopped.")

    def stop(self):
        """Signals all background tasks to stop."""
        log.info("\nShutting down daemon...")
        self.running = False
        if hasattr(self, "watcher_task") and not self.watcher_task.done():
            self.watcher_task.cancel()
        if hasattr(self, "cache_task") and not self.cache_task.done():
            self.cache_task.cancel()
        if hasattr(self, "git_task") and not self.git_task.done():
            self.git_task.cancel()
        if hasattr(self, "status_task") and not self.status_task.done():
            self.status_task.cancel()


async def main():
    """Entry point: reads config from env vars and runs the daemon."""
    server_url = os.getenv("DASHBOARD_URL", "http://localhost:8000")
    host_token = os.getenv("HOST_TOKEN")
    if not host_token:
        log.info("Error: HOST_TOKEN environment variable is required.")
        sys.exit(1)
    daemon = HostDaemon(server_url, host_token)
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, daemon.stop)
    await daemon.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
