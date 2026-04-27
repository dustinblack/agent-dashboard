"""Backend client for the Agent Dashboard TUI.

Provides async REST and Socket.IO access to the dashboard
backend. Used by both the dashboard TUI and the standalone
terminal client.
"""

import asyncio
from typing import Any, Callable, Dict, List, Optional

import httpx
import socketio


class DashboardClient:
    """Async client for the Agent Dashboard backend.

    Wraps both REST API calls and Socket.IO real-time events
    into a single interface. The Socket.IO connection is
    optional — call connect() to enable live updates.

    Args:
        base_url: Backend URL (default: http://localhost:8000).
    """

    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url.rstrip("/")
        self._http = httpx.AsyncClient(base_url=self.base_url, timeout=10)
        self._sio = socketio.AsyncClient()
        self._connected = False

        # Callbacks for real-time events. Set these before
        # calling connect() to receive live updates.
        self.on_agent_telemetry: Optional[Callable[[str, Dict], Any]] = None
        self.on_agent_status: Optional[Callable[[str, str], Any]] = None
        self.on_host_telemetry: Optional[Callable[[int, Dict], Any]] = None
        self.on_terminal_output: Optional[Callable[[str, str], Any]] = None
        self.on_history_complete: Optional[Callable[[str], Any]] = None

        self._register_handlers()

    def _register_handlers(self):
        """Registers Socket.IO event handlers that dispatch
        to the configured callbacks.
        """

        @self._sio.on("agent_telemetry_update", namespace="/terminal")
        async def on_telemetry(data):
            if self.on_agent_telemetry:
                await self._call(
                    self.on_agent_telemetry,
                    data.get("agent_id"),
                    data.get("telemetry", {}),
                )

        @self._sio.on("agent_status_update", namespace="/terminal")
        async def on_status(data):
            if self.on_agent_status:
                await self._call(
                    self.on_agent_status,
                    data.get("agent_id"),
                    data.get("status"),
                )

        @self._sio.on("host_telemetry_update", namespace="/terminal")
        async def on_host_tel(data):
            if self.on_host_telemetry:
                await self._call(
                    self.on_host_telemetry,
                    data.get("host_id"),
                    data.get("telemetry", {}),
                )

        @self._sio.on("terminal_output", namespace="/terminal")
        async def on_output(data):
            if self.on_terminal_output:
                await self._call(
                    self.on_terminal_output,
                    data.get("sid"),
                    data.get("output", ""),
                )

        @self._sio.on("history_complete", namespace="/terminal")
        async def on_history(data):
            if self.on_history_complete:
                await self._call(
                    self.on_history_complete,
                    data.get("agent_id"),
                )

    async def _call(self, callback, *args):
        """Calls a callback, handling both sync and async."""
        result = callback(*args)
        if asyncio.iscoroutine(result):
            await result

    # --- REST API methods ---

    async def get_hosts(self) -> List[Dict]:
        """Returns all registered hosts."""
        resp = await self._http.get("/hosts")
        resp.raise_for_status()
        return resp.json()

    async def get_agents(self, status: str = "active") -> List[Dict]:
        """Returns agents filtered by status."""
        resp = await self._http.get("/agents", params={"status": status})
        resp.raise_for_status()
        return resp.json()

    async def get_agent_details(self, agent_id: str) -> Dict:
        """Returns detailed info for a single agent."""
        resp = await self._http.get(f"/agents/{agent_id}/details")
        resp.raise_for_status()
        return resp.json()

    async def get_companions(self, agent_id: str) -> List[Dict]:
        """Returns companion agents for the given agent."""
        resp = await self._http.get(f"/agents/{agent_id}/companions")
        resp.raise_for_status()
        return resp.json()

    async def spawn_agent(
        self,
        host_id: int,
        tool_name: str,
        project_dir: Optional[str] = None,
        task_description: Optional[str] = None,
        session_mode: str = "resume",
        use_worktree: bool = False,
        cols: int = 120,
        rows: int = 40,
    ) -> Dict:
        """Spawns a new agent session on a host."""
        resp = await self._http.post(
            "/agents/spawn",
            json={
                "host_id": host_id,
                "tool_name": tool_name,
                "project_dir": project_dir,
                "task_description": task_description,
                "session_mode": session_mode,
                "use_worktree": use_worktree,
                "cols": cols,
                "rows": rows,
            },
        )
        resp.raise_for_status()
        return resp.json()

    async def stop_agent(self, agent_id: str) -> None:
        """Stops an active agent session."""
        resp = await self._http.post(f"/agents/{agent_id}/stop")
        resp.raise_for_status()

    async def update_task_description(self, agent_id: str, description: str) -> None:
        """Updates an agent's task description."""
        resp = await self._http.patch(
            f"/agents/{agent_id}/task-description",
            json={"task_description": description},
        )
        resp.raise_for_status()

    async def get_version(self) -> Dict:
        """Returns version info including update status."""
        resp = await self._http.get("/version")
        resp.raise_for_status()
        return resp.json()

    # --- Socket.IO methods ---

    async def connect(self):
        """Connects to the backend Socket.IO server."""
        if not self._connected:
            await self._sio.connect(
                self.base_url,
                namespaces=["/terminal"],
                socketio_path="socket.io",
                transports=["websocket", "polling"],
            )
            self._connected = True

    async def disconnect(self):
        """Disconnects from the Socket.IO server."""
        if self._connected:
            try:
                await self._sio.disconnect()
            except Exception:
                pass
            self._connected = False

    async def join_room(self, agent_id: str):
        """Joins an agent's Socket.IO room to receive
        terminal output and telemetry.
        """
        await self._sio.emit(
            "join_room",
            {"room": agent_id},
            namespace="/terminal",
        )

    async def send_input(self, agent_id: str, data: str):
        """Sends terminal input to an agent."""
        await self._sio.emit(
            "terminal_input",
            {"target_sid": agent_id, "input": data},
            namespace="/terminal",
        )

    async def send_resize(self, agent_id: str, cols: int, rows: int):
        """Sends a terminal resize event."""
        await self._sio.emit(
            "terminal_resize",
            {"sid": agent_id, "cols": cols, "rows": rows},
            namespace="/terminal",
        )

    async def close(self):
        """Closes all connections."""
        await self.disconnect()
        await self._http.aclose()
