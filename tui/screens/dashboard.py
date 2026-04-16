"""Main dashboard screen for the TUI.

Displays hosts and their active agent sessions in a
two-tier layout: compact list on top, detail pane below
for the selected agent.
"""

from typing import Dict, List, Optional

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Header, Static

from tui.client import DashboardClient
from tui.widgets.agent_card import AgentCard
from tui.widgets.agent_detail import AgentDetail
from tui.widgets.host_group import HostHeader
from tui.widgets.version_bar import VersionBar


class DashboardScreen(Screen):
    """Main dashboard screen showing hosts and agents.

    Provides keyboard navigation between agent cards with
    a detail pane for the selected agent. Supports live
    telemetry updates via Socket.IO.

    Args:
        client: Connected DashboardClient instance.
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("a", "attach", "Attach"),
        Binding("x", "stop", "Stop"),
        Binding("s", "spawn", "Spawn"),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("down", "cursor_down", "Down", show=False),
        Binding("up", "cursor_up", "Up", show=False),
    ]

    def __init__(self, client: DashboardClient, **kwargs):
        super().__init__(**kwargs)
        self.client = client
        self.hosts: List[Dict] = []
        self.agents: List[Dict] = []
        self._selected_index: int = 0
        self._version_info: Dict = {}
        self._rebuilding = False

    def compose(self) -> ComposeResult:
        """Builds the dashboard layout."""
        yield Header()
        with Vertical():
            with VerticalScroll(id="agent-list"):
                yield Static("  Loading...", id="loading-msg")
            yield AgentDetail(id="detail-pane")
        yield VersionBar(id="version-bar")
        yield Footer()

    def on_screen_resume(self) -> None:
        """Called when the screen regains focus (e.g. after
        returning from a tmux attach). Rebuilds the list
        to fix any rendering issues.
        """
        self._rebuild_list()

    async def on_mount(self) -> None:
        """Called when the screen is mounted. Loads initial
        data and starts background connection.
        """
        # Set up live update callbacks
        self.client.on_agent_telemetry = self._on_agent_telemetry
        self.client.on_agent_status = self._on_agent_status
        self.client.on_host_telemetry = self._on_host_telemetry

        # Load initial data via REST (doesn't need Socket.IO)
        await self._refresh_data()

        # Connect Socket.IO in the background for live
        # updates — this avoids blocking mount if the
        # connection is slow.
        self._connect_socketio()

        # Load version info
        self._load_version()

    @work(thread=False)
    async def _connect_socketio(self) -> None:
        """Connects Socket.IO in the background."""
        try:
            await self.client.connect()
        except Exception as e:
            self.notify(
                f"Live updates unavailable: {e}",
                severity="warning",
            )

    @work(thread=False)
    async def _load_version(self) -> None:
        """Fetches version info in the background."""
        try:
            self._version_info = await self.client.get_version()
            version_bar = self.query_one("#version-bar", VersionBar)
            version_bar.version_info = self._version_info
        except Exception:
            pass

    async def _refresh_data(self) -> None:
        """Fetches hosts and agents from the backend."""
        try:
            self.hosts = await self.client.get_hosts()
            self.agents = await self.client.get_agents()
        except Exception as e:
            self.query_one("#loading-msg", Static).update(f"  Error: {e}")
            return
        self._rebuild_list()

    def _rebuild_list(self) -> None:
        """Rebuilds the agent list from current data.

        Guarded against concurrent calls from telemetry
        updates to prevent DuplicateIds errors.
        """
        if self._rebuilding:
            return
        self._rebuilding = True
        try:
            self._do_rebuild_list()
        finally:
            self._rebuilding = False

    def _do_rebuild_list(self) -> None:
        """Internal list rebuild implementation."""
        container = self.query_one("#agent-list", VerticalScroll)
        # Remove all existing children by querying them
        for child in list(container.children):
            child.remove()

        if not self.agents:
            container.mount(
                Static(
                    "  No active agents. Press [bold]s[/bold] to spawn.",
                    markup=True,
                )
            )
            self._update_detail(None)
            return

        # Sort hosts: online first, then alphabetical
        sorted_hosts = sorted(
            self.hosts,
            key=lambda h: (
                0 if h.get("status") == "online" else 1,
                h.get("name", ""),
            ),
        )

        card_index = 0
        for host in sorted_hosts:
            host_agents = [a for a in self.agents if a.get("host_id") == host.get("id")]
            if not host_agents:
                continue

            container.mount(HostHeader(host))
            for agent in host_agents:
                card = AgentCard(
                    agent,
                    id=f"agent-{card_index}",
                    classes="agent-card",
                )
                if card_index == self._selected_index:
                    card.add_class("selected")
                container.mount(card)
                card_index += 1

        # Update detail pane
        if self.agents and self._selected_index < len(self.agents):
            self._update_detail(self.agents[self._selected_index])
        else:
            self._selected_index = 0
            if self.agents:
                self._update_detail(self.agents[0])

    def _update_detail(self, agent: Optional[Dict]) -> None:
        """Updates the detail pane with the selected agent."""
        detail = self.query_one("#detail-pane", AgentDetail)
        detail.agent = agent or {}

    def _move_selection(self, delta: int) -> None:
        """Moves the selection cursor by delta positions."""
        if not self.agents:
            return
        # Remove old selection
        old_id = f"#agent-{self._selected_index}"
        try:
            old_card = self.query_one(old_id, AgentCard)
            old_card.remove_class("selected")
        except Exception:
            pass

        # Move
        self._selected_index = max(
            0,
            min(
                self._selected_index + delta,
                len(self.agents) - 1,
            ),
        )

        # Add new selection
        new_id = f"#agent-{self._selected_index}"
        try:
            new_card = self.query_one(new_id, AgentCard)
            new_card.add_class("selected")
            new_card.scroll_visible()
        except Exception:
            pass

        # Update detail
        self._update_detail(self.agents[self._selected_index])

    def _get_selected_agent(self) -> Optional[Dict]:
        """Returns the currently selected agent dict."""
        if self.agents and self._selected_index < len(self.agents):
            return self.agents[self._selected_index]
        return None

    # --- Actions ---

    def action_cursor_down(self) -> None:
        """Moves selection down."""
        self._move_selection(1)

    def action_cursor_up(self) -> None:
        """Moves selection up."""
        self._move_selection(-1)

    def action_refresh(self) -> None:
        """Refreshes all data."""
        self.run_worker(self._refresh_data())

    def action_quit(self) -> None:
        """Exits the application."""
        self.app.exit()

    async def action_stop(self) -> None:
        """Stops the selected agent."""
        agent = self._get_selected_agent()
        if not agent:
            return
        agent_id = agent.get("agent_id")
        try:
            await self.client.stop_agent(agent_id)
            await self._refresh_data()
        except Exception as e:
            self.notify(f"Failed to stop: {e}", severity="error")

    async def action_attach(self) -> None:
        """Attaches to the selected agent's terminal."""
        agent = self._get_selected_agent()
        if not agent:
            return
        # Delegate to the app's attach handler
        await self.app.attach_agent(agent)

    def action_spawn(self) -> None:
        """Opens the spawn screen."""
        from tui.screens.spawn import SpawnScreen

        self.app.push_screen(SpawnScreen(self.client, self.hosts))

    # --- Live update handlers ---

    def _on_agent_telemetry(self, agent_id: str, telemetry: Dict) -> None:
        """Handles live telemetry updates.

        Updates the agent data in place and refreshes only
        the affected card and detail pane rather than
        rebuilding the entire list.
        """
        for i, agent in enumerate(self.agents):
            if agent.get("agent_id") == agent_id:
                agent["telemetry"] = {
                    **(agent.get("telemetry") or {}),
                    **telemetry,
                }
                # Update just this card's display
                try:
                    card = self.query_one(f"#agent-{i}", AgentCard)
                    card.agent = agent
                except Exception:
                    pass
                # Update detail pane if this agent is selected
                if i == self._selected_index:
                    self._update_detail(agent)
                break

    def _on_agent_status(self, agent_id: str, status: str) -> None:
        """Handles agent status changes."""
        if status in ("stopped", "closed"):
            self.agents = [a for a in self.agents if a.get("agent_id") != agent_id]
            self._rebuild_list()

    def _on_host_telemetry(self, host_id: int, telemetry: Dict) -> None:
        """Handles host telemetry updates."""
        for host in self.hosts:
            if host.get("id") == host_id:
                host["projects"] = telemetry
                break
