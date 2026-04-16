"""Main TUI application for Agent Dashboard.

Launches a Textual-based terminal UI that connects to the
dashboard backend and provides keyboard-driven management
of AI coding agent sessions. Supports tmux integration for
multi-pane terminal layouts.

Usage:
    python -m tui.app [--url URL]
"""

import argparse
import os
import subprocess
import sys
from typing import Dict

from textual.app import App

from tui.client import DashboardClient
from tui.screens.dashboard import DashboardScreen


class AgentDashboardApp(App):
    """Textual application for the Agent Dashboard TUI.

    Connects to the backend on startup and displays the
    main dashboard screen. Supports attaching to agent
    sessions via tmux panes or foreground terminal client.

    Args:
        base_url: Backend URL.
    """

    TITLE = "Agent Dashboard"
    CSS = """
    #agent-list {
        height: 1fr;
        border-bottom: solid $accent;
    }

    #detail-pane {
        height: auto;
        max-height: 12;
        padding: 0;
    }

    #version-bar {
        height: 1;
        dock: bottom;
        background: $surface;
    }

    .agent-card {
        height: auto;
        padding: 0;
        margin: 0;
    }

    .agent-card.selected {
        background: $accent 20%;
    }
    """

    def __init__(self, base_url: str, **kwargs):
        super().__init__(**kwargs)
        self.base_url = base_url
        self.client = DashboardClient(base_url)
        self._in_tmux = bool(os.environ.get("TMUX"))
        self._attach_cmd: str | None = None

    def on_mount(self) -> None:
        """Pushes the main dashboard screen on startup."""
        self.push_screen(DashboardScreen(self.client))

    async def attach_agent(self, agent: Dict) -> None:
        """Attaches to an agent session.

        If running inside tmux, opens a new tmux window
        with the terminal client. Otherwise, suspends the
        TUI and runs the terminal client in the foreground.

        Args:
            agent: Agent data dict with agent_id, telemetry.
        """
        agent_id = agent.get("agent_id", "")
        tel = agent.get("telemetry") or {}
        tool = agent.get("tool_name", "agent")
        project = tel.get("git_project", "")
        branch = tel.get("git_branch", "")

        # Build a descriptive window/session name
        parts = [tool]
        if project:
            parts.append(project)
        if branch:
            parts.append(branch)
        window_name = ":".join(parts)

        # Build the terminal client command. Use the
        # current working directory to ensure the tui
        # package is importable in the tmux subprocess.
        # Build the terminal client command. Use the
        # current working directory to ensure the tui
        # package is importable in the tmux subprocess.
        # Add a read prompt on exit so error messages
        # are visible before the tmux window closes.
        cwd = os.getcwd()
        # Ensure the tmux subprocess uses the same Python
        # environment (venv, PYTHONPATH) as the TUI.
        venv = os.environ.get("VIRTUAL_ENV", "")
        activate = f"source {venv}/bin/activate && " if venv else ""
        client_cmd = (
            f"cd {cwd} && {activate}"
            f"PYTHONPATH={cwd}:$PYTHONPATH "
            f"{sys.executable} -m tui.terminal_client "
            f"{agent_id} --url {self.base_url}"
        )

        if self._in_tmux:
            # Open a new tmux window with the terminal client
            subprocess.run(
                [
                    "tmux",
                    "new-window",
                    "-n",
                    window_name,
                    client_cmd,
                ],
                check=False,
            )
            self.notify(f"Attached in tmux window: {window_name}")
        else:
            # Not in tmux — exit the TUI and run the
            # terminal client directly. The user can
            # relaunch the TUI after disconnecting.
            self._attach_cmd = client_cmd
            self.exit()

    async def on_unmount(self) -> None:
        """Clean up client connections on exit."""
        await self.client.close()


def main():
    """CLI entry point for the TUI dashboard."""
    parser = argparse.ArgumentParser(description="Agent Dashboard TUI")
    parser.add_argument(
        "--url",
        default=os.getenv("DASHBOARD_URL", "http://localhost:8000"),
        help=("Backend URL " "(default: $DASHBOARD_URL or localhost:8000)"),
    )
    args = parser.parse_args()

    app = AgentDashboardApp(args.url)
    app.run()

    # If the user pressed attach without tmux, the TUI
    # exits and we run the terminal client directly.
    if app._attach_cmd:  # pylint: disable=protected-access
        subprocess.run(
            app._attach_cmd,  # pylint: disable=protected-access
            shell=True,
            check=False,
        )


if __name__ == "__main__":
    main()
