"""Spawn screen for the TUI dashboard.

Full-screen flow for spawning a new agent session.
The user selects host, tool, project, session mode,
worktree isolation, and optionally a task description.
"""

from typing import Dict, List

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    Label,
    Select,
    Static,
    Switch,
)

from tui.client import DashboardClient


class SpawnScreen(Screen):
    """Screen for spawning a new agent session.

    Provides selectors for host, tool, project, session
    mode, worktree isolation, and task description.

    Args:
        client: Connected DashboardClient instance.
        hosts: List of host dicts from the backend.
        agents: List of active agent dicts for smart
            worktree default.
    """

    BINDINGS = [
        Binding("escape", "cancel", "Back"),
    ]

    def __init__(
        self,
        client: DashboardClient,
        hosts: List[Dict],
        agents: List[Dict] | None = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.client = client
        self.hosts = hosts
        self.agents = agents or []
        self._selected_host_id: int | None = None
        self._projects: List[str] = []

    def compose(self) -> ComposeResult:
        """Builds the spawn screen layout."""
        yield Header()
        with Vertical(id="spawn-form"):
            yield Label("Spawn New Agent", id="spawn-title")

            # Host selector
            yield Label("Host", classes="field-label")
            online_hosts = [h for h in self.hosts if h.get("status") == "online"]
            host_options = [
                (h.get("name", "Unknown"), h.get("id")) for h in online_hosts
            ]
            yield Select(
                host_options,
                id="host-select",
                prompt="Select a host",
            )

            # Tool selector
            yield Label("Tool", classes="field-label")
            yield Select(
                [
                    ("Claude", "claude"),
                    ("Gemini", "gemini"),
                    ("Bash", "bash"),
                ],
                id="tool-select",
                prompt="Select a tool",
            )

            # Project selector
            yield Label("Project", classes="field-label")
            yield Select(
                [],
                id="project-select",
                prompt="Select host first",
            )

            # Session mode
            yield Label("Resume Session", classes="field-label")
            yield Switch(value=True, id="resume-switch")

            # Worktree isolation
            yield Label("Worktree Isolation", classes="field-label")
            yield Switch(value=False, id="worktree-switch")

            # Task description
            yield Label(
                "Task Description (optional)",
                classes="field-label",
            )
            yield Input(
                placeholder="Describe the objective...",
                id="task-input",
            )

            # Spawn button
            yield Button(
                "Spawn Agent",
                id="spawn-btn",
                variant="primary",
            )

            yield Static("", id="spawn-status")

        yield Footer()

    def on_select_changed(self, event: Select.Changed) -> None:
        """Handles host selection to populate projects."""
        if event.select.id == "host-select":
            host_id = event.value
            if host_id is Select.BLANK:
                return
            self._selected_host_id = host_id
            # Find the host and its projects
            host = None
            for h in self.hosts:
                if h.get("id") == host_id:
                    host = h
                    break
            if host and host.get("projects"):
                projects = host["projects"].get("available_projects", [])
            else:
                projects = []
            self._projects = projects

            # Update project selector
            project_select = self.query_one("#project-select", Select)
            if projects:
                project_select.set_options([(p, p) for p in projects])
            else:
                project_select.set_options([])

            # Smart worktree default: enable if another
            # agent is active on the selected project
            self._update_worktree_default()

        elif event.select.id == "project-select":
            self._update_worktree_default()

    def _update_worktree_default(self) -> None:
        """Sets worktree toggle based on whether another
        agent is already active on the selected project.
        """
        project_select = self.query_one("#project-select", Select)
        selected_project = project_select.value
        if selected_project is Select.BLANK:
            return

        # Check if any active agent is on this project
        # on the selected host
        host = None
        for h in self.hosts:
            if h.get("id") == self._selected_host_id:
                host = h
                break
        if not host:
            return
        projects_root = ""
        if host.get("projects"):
            projects_root = host["projects"].get("projects_root", "/git")
        full_path = f"{projects_root}/{selected_project}"

        has_active = any(
            a.get("host_id") == self._selected_host_id
            and (a.get("telemetry") or {}).get("project_dir") == full_path
            for a in self.agents
        )
        worktree_switch = self.query_one("#worktree-switch", Switch)
        worktree_switch.value = has_active

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handles the spawn button press."""
        if event.button.id != "spawn-btn":
            return

        host_select = self.query_one("#host-select", Select)
        tool_select = self.query_one("#tool-select", Select)
        project_select = self.query_one("#project-select", Select)
        resume_switch = self.query_one("#resume-switch", Switch)
        worktree_switch = self.query_one("#worktree-switch", Switch)
        task_input = self.query_one("#task-input", Input)
        status = self.query_one("#spawn-status", Static)

        # Validate
        host_id = host_select.value
        tool = tool_select.value
        project = project_select.value

        if host_id is Select.BLANK:
            status.update("  Select a host")
            return
        if tool is Select.BLANK:
            status.update("  Select a tool")
            return
        if project is Select.BLANK:
            status.update("  Select a project")
            return

        session_mode = "resume" if resume_switch.value else "new"
        use_worktree = worktree_switch.value
        task = task_input.value.strip() or None

        # Force new session for worktree
        if use_worktree:
            session_mode = "new"

        status.update("  Spawning...")
        try:
            await self.client.spawn_agent(
                host_id=host_id,
                tool_name=tool,
                project_dir=project,
                task_description=task,
                session_mode=session_mode,
                use_worktree=use_worktree,
            )
            self.app.pop_screen()
        except Exception as e:
            status.update(f"  Failed: {e}")

    def action_cancel(self) -> None:
        """Returns to the dashboard."""
        self.app.pop_screen()
