"""Spawn screen placeholder for the TUI dashboard.

Will be implemented in Phase 4 with host/tool/project
selection, session mode, worktree toggle, and task input.
"""

from typing import Dict, List

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Footer, Header, Static

from tui.client import DashboardClient


class SpawnScreen(Screen):
    """Modal screen for spawning a new agent session.

    Args:
        client: Connected DashboardClient instance.
        hosts: List of host dicts from the backend.
    """

    BINDINGS = [
        Binding("escape", "cancel", "Back"),
    ]

    def __init__(
        self,
        client: DashboardClient,
        hosts: List[Dict],
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.client = client
        self.hosts = hosts

    def compose(self) -> ComposeResult:
        """Builds the spawn screen layout."""
        yield Header()
        yield Static(
            "  Spawn screen — coming soon.\n  Press [bold]Escape[/bold] to go back.",
            markup=True,
        )
        yield Footer()

    def action_cancel(self) -> None:
        """Returns to the dashboard."""
        self.app.pop_screen()
