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
        self._strip_prefix: str = ""

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

            # Tool selector — populated dynamically when
            # a host is selected based on its available_tools.
            yield Label("Tool", classes="field-label")
            yield Select(
                [],
                id="tool-select",
                prompt="Select host first",
            )

            # Project search and selector
            yield Label("Project", classes="field-label")
            yield Input(
                placeholder="Search projects...",
                id="project-search",
            )
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
                raw_tools = host["projects"].get("available_tools", [])
                pr = host["projects"].get("projects_root", "/git")
                roots = pr if isinstance(pr, list) else [pr]
                self._strip_prefix = roots[0] + "/" if len(roots) == 1 else ""
            else:
                projects = []
                raw_tools = []
                self._strip_prefix = ""
            self._projects = projects

            # Update tool selector from host's profiles
            tool_select = self.query_one("#tool-select", Select)
            if raw_tools and isinstance(raw_tools[0], dict):
                tool_options = [
                    (t.get("display_name", t["name"]), t["name"]) for t in raw_tools
                ]
            elif raw_tools and isinstance(raw_tools[0], str):
                tool_options = [(t.capitalize(), t) for t in raw_tools]
            else:
                tool_options = [
                    ("Claude", "claude"),
                    ("Gemini", "gemini"),
                    ("Bash", "bash"),
                ]
            tool_select.set_options(tool_options)

            # Update project selector and clear search
            project_select = self.query_one("#project-select", Select)
            project_select.set_options(self._project_options(projects))
            search_input = self.query_one("#project-search", Input)
            search_input.value = ""

            # Smart worktree default: enable if another
            # agent is active on the selected project
            self._update_worktree_default()

        elif event.select.id == "project-select":
            self._update_worktree_default()

    def on_input_changed(self, event: Input.Changed) -> None:
        """Filters the project list as the user types."""
        if event.input.id != "project-search":
            return
        query = event.value.strip().lower()
        project_select = self.query_one("#project-select", Select)
        if not query:
            project_select.set_options(self._project_options(self._projects))
        else:
            filtered = [p for p in self._projects if query in p.lower()]
            project_select.set_options(self._project_options(filtered))

    def _project_options(self, projects):
        """Builds Select options from project paths.

        Strips the common root prefix for single-root
        configs to keep labels readable.
        """
        if not projects:
            return []
        prefix = self._strip_prefix or ""
        return [
            (
                p[len(prefix) :] if prefix and p.startswith(prefix) else p,
                p,
            )
            for p in projects
        ]

    def _update_worktree_default(self) -> None:
        """Sets worktree toggle based on whether another
        agent is already active on the selected project.
        Projects are absolute paths so direct comparison
        works without joining with projects_root.
        """
        project_select = self.query_one("#project-select", Select)
        selected_project = project_select.value
        if selected_project is Select.BLANK:
            return

        has_active = any(
            a.get("host_id") == self._selected_host_id
            and (a.get("telemetry") or {}).get("project_dir") == selected_project
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
