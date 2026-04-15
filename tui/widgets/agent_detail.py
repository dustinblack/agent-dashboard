"""Detail pane for the selected agent in the TUI dashboard.

Shows full telemetry information for the currently focused
agent: model, context bar, token breakdown, cost, activity,
MCP servers, and task description.
"""

from rich.text import Text
from textual.reactive import reactive
from textual.widgets import Static


def _format_tokens(n: int) -> str:
    """Formats a token count compactly (1.2k, 1.2M)."""
    if n >= 1_000_000:
        v = n / 1_000_000
        return f"{v:.1f}M".replace(".0M", "M")
    if n >= 1_000:
        v = n / 1_000
        return f"{v:.1f}k".replace(".0k", "k")
    return str(n)


def _context_bar(used: int, total: int, width: int = 20) -> str:
    """Renders an ASCII context usage bar."""
    if total <= 0:
        return "░" * width
    pct = min(used / total, 1.0)
    filled = int(pct * width)
    return "█" * filled + "░" * (width - filled)


# Status display styles
_STATUS_STYLES = {
    "working": ("green", "Working"),
    "waiting_permission": ("bold red", "Permission"),
    "idle": ("yellow", "Idle"),
}


class AgentDetail(Static):
    """Detail pane showing full telemetry for one agent.

    Updates reactively when the agent data changes.

    Args:
        agent: Agent data dict from the backend API.
    """

    agent = reactive({}, always_update=True)

    def render(self) -> Text:
        """Renders the full detail view."""
        if not self.agent:
            return Text(
                "  Select an agent to view details",
                style="dim italic",
            )

        tel = self.agent.get("telemetry") or {}
        text = Text()

        # Model + Status
        model = tel.get("model", "detecting...")
        status = tel.get("agent_status", "")
        s_style, s_label = _STATUS_STYLES.get(status, ("dim", status or "Live"))
        text.append("  Model:    ", style="dim")
        text.append(model, style="bold")
        text.append("     Status:  ", style="dim")
        text.append(s_label, style=s_style)
        text.append("\n")

        # Context bar
        ctx = tel.get("context_tokens", 0)
        # Use a reasonable default for context max
        ctx_max = 200_000
        if model:
            m = model.lower()
            if "gemini" in m:
                ctx_max = 1_048_576
            elif "[1m]" in m:
                ctx_max = 1_000_000
        ctx_bar = _context_bar(ctx, ctx_max)
        text.append("  Context:  ", style="dim")
        # Color the bar based on usage
        pct = (ctx / ctx_max * 100) if ctx_max > 0 else 0
        bar_style = "green"
        if pct > 80:
            bar_style = "red"
        elif pct > 50:
            bar_style = "yellow"
        text.append(ctx_bar, style=bar_style)
        text.append(
            f"  {_format_tokens(ctx)}/{_format_tokens(ctx_max)}",
            style="dim",
        )
        text.append("\n")

        # Cost + Tokens
        cost = tel.get("cost_usd", 0)
        tokens = tel.get("tokens", 0)
        text.append("  Cost:     ", style="dim")
        if cost and cost > 0:
            text.append(f"${cost:.2f}", style="cyan bold")
        else:
            text.append("—", style="dim")
        text.append("            Tokens:  ", style="dim")
        text.append(_format_tokens(tokens), style="bold")

        # Input/output breakdown
        inp = tel.get("input_tokens", 0)
        out = tel.get("output_tokens", 0)
        if inp or out:
            text.append(
                f" ({_format_tokens(inp)} in" f" / {_format_tokens(out)} out)",
                style="dim",
            )
        text.append("\n")

        # Activity
        activity = tel.get("current_activity", "")
        if activity:
            text.append("  Activity: ", style="dim")
            text.append(activity, style="italic")
            text.append("\n")

        # MCP servers
        mcp = tel.get("mcp_servers", [])
        if mcp:
            text.append("  MCP:      ", style="dim")
            text.append(", ".join(mcp))
            text.append("\n")

        # Task description
        task = tel.get("task_description", "")
        if task:
            text.append("  Task:     ", style="dim")
            text.append(task, style="italic")
            text.append("\n")

        # Worktree
        wt = tel.get("worktree_path")
        if wt:
            text.append("  Worktree: ", style="dim")
            text.append(wt, style="yellow")
            text.append("\n")

        # Run time
        run_time = tel.get("run_time_seconds", 0)
        if run_time:
            mins = run_time // 60
            secs = run_time % 60
            if mins >= 60:
                hours = mins // 60
                mins = mins % 60
                time_str = f"{hours}h {mins}m"
            elif mins > 0:
                time_str = f"{mins}m {secs}s"
            else:
                time_str = f"{secs}s"
            text.append("  Runtime:  ", style="dim")
            text.append(time_str)
            text.append("\n")

        return text
