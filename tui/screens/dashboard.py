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
        # Track selection by agent_id, not positional index
        self._selected_id: Optional[str] = None
        # Ordered list of agent_ids matching display order
        self._display_order: List[str] = []
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
        returning from a tmux attach). Refreshes data and
        rebuilds the list.
        """
        self.run_worker(self._refresh_data())

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
        await self._rebuild_list()

    async def _rebuild_list(self) -> None:
        """Rebuilds the agent list from current data.

        Uses await on remove() to ensure widgets are fully
        removed before mounting new ones, preventing
        DuplicateIds errors.
        """
        if self._rebuilding:
            return
        self._rebuilding = True
        try:
            container = self.query_one("#agent-list", VerticalScroll)
            # Await removal of each child to ensure
            # widget IDs are freed before remounting.
            for child in list(container.children):
                await child.remove()

            if not self.agents:
                await container.mount(
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

            self._display_order = []
            for host in sorted_hosts:
                host_agents = [
                    a for a in self.agents if a.get("host_id") == host.get("id")
                ]
                if not host_agents:
                    continue

                await container.mount(HostHeader(host))
                for agent in host_agents:
                    aid = agent.get("agent_id", "")
                    widget_id = f"agent-{aid.replace('-', '')}"
                    card = AgentCard(
                        agent,
                        id=widget_id,
                        classes="agent-card",
                    )
                    if aid == self._selected_id:
                        card.add_class("selected")
                    await container.mount(card)
                    self._display_order.append(aid)

            # Update selection
            if self._selected_id not in self._display_order and self._display_order:
                self._selected_id = self._display_order[0]
            if self._selected_id:
                self._update_detail(self._agent_by_id(self._selected_id))
            else:
                self._update_detail(None)
        finally:
            self._rebuilding = False

    def _agent_by_id(self, agent_id: str) -> Optional[Dict]:
        """Finds an agent dict by agent_id."""
        for a in self.agents:
            if a.get("agent_id") == agent_id:
                return a
        return None

    def _widget_id(self, agent_id: str) -> str:
        """Returns the Textual widget ID for an agent."""
        return f"agent-{agent_id.replace('-', '')}"

    def _update_detail(self, agent: Optional[Dict]) -> None:
        """Updates the detail pane with the selected agent."""
        detail = self.query_one("#detail-pane", AgentDetail)
        detail.agent = agent or {}

    def _move_selection(self, delta: int) -> None:
        """Moves the selection cursor by delta positions."""
        if not self._display_order:
            return
        # Find current position in display order
        try:
            idx = self._display_order.index(self._selected_id)
        except ValueError:
            idx = 0
        # Remove old selection highlight
        try:
            old_card = self.query_one(
                f"#{self._widget_id(self._selected_id)}",
                AgentCard,
            )
            old_card.remove_class("selected")
        except Exception:
            pass
        # Move
        idx = max(0, min(idx + delta, len(self._display_order) - 1))
        self._selected_id = self._display_order[idx]
        # Add new selection highlight
        try:
            new_card = self.query_one(
                f"#{self._widget_id(self._selected_id)}",
                AgentCard,
            )
            new_card.add_class("selected")
            new_card.scroll_visible()
        except Exception:
            pass
        # Update detail
        self._update_detail(self._agent_by_id(self._selected_id))

    def _get_selected_agent(self) -> Optional[Dict]:
        """Returns the currently selected agent dict."""
        if self._selected_id:
            return self._agent_by_id(self._selected_id)
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
        agent = self._agent_by_id(agent_id)
        if not agent:
            return
        agent["telemetry"] = {
            **(agent.get("telemetry") or {}),
            **telemetry,
        }
        # Update this card's display
        try:
            card = self.query_one(f"#{self._widget_id(agent_id)}", AgentCard)
            card.agent = agent
        except Exception:
            pass
        # Update detail pane if this agent is selected
        if agent_id == self._selected_id:
            self._update_detail(agent)

    def _on_agent_status(self, agent_id: str, status: str) -> None:
        """Handles agent status changes.

        Removes the agent from the data and removes its
        card widget directly rather than rebuilding the
        entire list.
        """
        if status in ("stopped", "closed"):
            self.agents = [a for a in self.agents if a.get("agent_id") != agent_id]
            if agent_id in self._display_order:
                self._display_order.remove(agent_id)
            # Remove the specific card widget
            try:
                card = self.query_one(
                    f"#{self._widget_id(agent_id)}",
                    AgentCard,
                )
                card.remove()
            except Exception:
                pass
            # Update selection
            if self._selected_id == agent_id:
                if self._display_order:
                    self._selected_id = self._display_order[0]
                    self._update_detail(self._agent_by_id(self._selected_id))
                else:
                    self._selected_id = None
                    self._update_detail(None)

    def _on_host_telemetry(self, host_id: int, telemetry: Dict) -> None:
        """Handles host telemetry updates."""
        for host in self.hosts:
            if host.get("id") == host_id:
                host["projects"] = telemetry
                break
