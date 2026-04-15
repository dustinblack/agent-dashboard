"""Compact one-line agent display for the TUI dashboard.

Shows tool type, project, branch, worktree indicator, status,
and cost in a single line. Task description on a second line
(truncated). Designed for dense list views where many agents
need to be visible simultaneously.
"""

from rich.text import Text
from textual.reactive import reactive
from textual.widgets import Static

# Tool badge colors matching the web UI
_TOOL_COLORS = {
    "claude": "purple",
    "gemini": "blue",
    "bash": "white",
}

# Status indicator styles
_STATUS_STYLES = {
    "working": ("green", "WORKING"),
    "waiting_permission": ("red", "PERMISSION"),
    "idle": ("yellow", "IDLE"),
}


class AgentCard(Static):
    """Compact agent card for list display.

    Renders a one-line summary of an agent session with
    optional task description on the second line.

    Args:
        agent: Agent data dict from the backend API.
    """

    agent = reactive({}, always_update=True)

    def __init__(self, agent: dict, **kwargs):
        super().__init__(**kwargs)
        self.agent = agent

    def render(self) -> Text:
        """Renders the compact agent card."""
        tel = self.agent.get("telemetry") or {}
        tool = self.agent.get("tool_name", "?")
        tool_color = _TOOL_COLORS.get(tool, "white")

        # Build the line
        line = Text()

        # Tool badge
        line.append(f" {tool:8s}", style=f"bold {tool_color}")

        # Project + branch
        project = tel.get("git_project", "")
        branch = tel.get("git_branch", "")
        if project:
            line.append(f" {project}", style="bold white")
        if branch:
            line.append(f"  {branch}", style="green")

        # Worktree indicator
        if tel.get("worktree_path"):
            line.append(" wt", style="yellow")

        # Status
        status = tel.get("agent_status", "")
        style, label = _STATUS_STYLES.get(status, ("dim", status.upper() or "LIVE"))
        line.append(f"  {label}", style=style)

        # Cost
        cost = tel.get("cost_usd")
        if cost and cost > 0:
            line.append(f"  ${cost:.2f}", style="cyan")

        # Task description on second line
        task = tel.get("task_description", "")
        if task:
            # Truncate to fit
            max_len = 60
            desc = task[:max_len]
            if len(task) > max_len:
                desc += "..."
            line.append(f"\n   {desc}", style="dim italic")

        return line
