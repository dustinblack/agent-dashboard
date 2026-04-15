"""Standalone terminal client for Agent Dashboard.

Connects to the backend via Socket.IO and provides raw
PTY passthrough to a remote agent session. Handles history
replay, resize propagation, and DA response filtering.

Usage:
    python -m tui.terminal_client <agent-id> [--url URL]

Can be run standalone or invoked by the dashboard TUI
when attaching to an agent via tmux.
"""

import argparse
import asyncio
import os
import re
import signal
import sys
import termios
import tty
from typing import Optional

from tui.client import DashboardClient

# Filter Device Attributes responses from terminal output
# before relaying to prevent "1;2c" appearing in agent
# input on some CLIs (e.g. Gemini).
_DA_RESPONSE = re.compile(r"\x1b\[\?[\d;]*c")

# Stale session timeout — if history_complete is not
# received within this many seconds, the session is
# considered stale and we exit.
_STALE_TIMEOUT = 5.0


class TerminalClient:
    """Raw terminal passthrough to a remote agent session.

    Connects to the dashboard backend, joins the agent's
    Socket.IO room, replays history, and relays I/O between
    the local terminal and the remote agent PTY.

    Args:
        base_url: Backend URL.
        agent_id: UUID of the agent session to attach to.
    """

    def __init__(self, base_url: str, agent_id: str):
        self.base_url = base_url
        self.agent_id = agent_id
        self.client = DashboardClient(base_url)
        self._replaying = True
        self._history_buf: list[str] = []
        self._old_settings: Optional[list] = None
        self._running = False
        self._stale_timer: Optional[asyncio.TimerHandle] = None

    async def run(self):
        """Main entry point. Connects, replays history,
        then relays I/O until the session ends or the
        user presses Ctrl+C.
        """
        # Set up callbacks
        self.client.on_terminal_output = self._on_output
        self.client.on_history_complete = self._on_history_complete
        self.client.on_agent_status = self._on_status

        # Connect and join the agent room
        try:
            await self.client.connect()
        except Exception as e:
            print(
                f"Failed to connect to {self.base_url}: {e}",
                file=sys.stderr,
            )
            return 1

        await self.client.join_room(self.agent_id)

        # Start stale session timer
        loop = asyncio.get_running_loop()
        self._stale_timer = loop.call_later(_STALE_TIMEOUT, self._on_stale)

        # Send initial resize
        rows, cols = self._get_terminal_size()
        await self.client.send_resize(self.agent_id, cols, rows)

        # Set terminal to raw mode for passthrough
        self._enter_raw_mode()
        self._running = True

        # Handle SIGWINCH for terminal resize
        loop.add_signal_handler(
            signal.SIGWINCH,
            lambda: asyncio.ensure_future(self._handle_resize()),
        )

        try:
            # Start reading stdin in background
            stdin_task = asyncio.create_task(self._read_stdin())
            # Wait until session ends
            while self._running:
                await asyncio.sleep(0.1)
            stdin_task.cancel()
        except asyncio.CancelledError:
            pass
        finally:
            self._restore_terminal()
            await self.client.close()

        return 0

    def _on_output(self, agent_id: str, output: str):
        """Handles terminal output from the agent."""
        if agent_id != self.agent_id:
            return
        if self._replaying:
            self._history_buf.append(output)
        else:
            # Filter DA responses
            filtered = _DA_RESPONSE.sub("", output)
            if filtered:
                sys.stdout.write(filtered)
                sys.stdout.flush()

    def _on_history_complete(self, agent_id: str):
        """Handles history replay completion."""
        if agent_id != self.agent_id:
            return
        # Cancel stale timer
        if self._stale_timer:
            self._stale_timer.cancel()
            self._stale_timer = None
        # Flush buffered history
        for chunk in self._history_buf:
            filtered = _DA_RESPONSE.sub("", chunk)
            if filtered:
                sys.stdout.write(filtered)
        sys.stdout.flush()
        self._history_buf.clear()
        self._replaying = False

    def _on_status(self, agent_id: str, status: str):
        """Handles agent status changes."""
        if agent_id != self.agent_id:
            return
        if status in ("stopped", "closed"):
            self._running = False
            print(
                f"\r\nAgent session {status}.\r\n",
                file=sys.stderr,
            )

    def _on_stale(self):
        """Called when history_complete is not received
        within the timeout. The session is stale.
        """
        self._running = False
        self._restore_terminal()
        print(
            "\r\nSession is stale — the agent may no longer be running.\r\n",
            file=sys.stderr,
        )

    async def _read_stdin(self):
        """Reads stdin in raw mode and sends to the agent."""
        loop = asyncio.get_running_loop()
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        await loop.connect_read_pipe(lambda: protocol, sys.stdin)
        while self._running:
            try:
                data = await asyncio.wait_for(reader.read(4096), timeout=0.1)
                if not data:
                    break
                text = data.decode("utf-8", errors="replace")
                # Filter DA responses from input
                filtered = _DA_RESPONSE.sub("", text)
                if filtered:
                    await self.client.send_input(self.agent_id, filtered)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

    async def _handle_resize(self):
        """Sends terminal resize to the agent."""
        rows, cols = self._get_terminal_size()
        await self.client.send_resize(self.agent_id, cols, rows)

    def _get_terminal_size(self) -> tuple:
        """Returns (rows, cols) of the current terminal."""
        try:
            size = os.get_terminal_size()
            return (size.lines, size.columns)
        except OSError:
            return (40, 120)

    def _enter_raw_mode(self):
        """Sets stdin to raw mode for character-by-character
        input without echo.
        """
        if sys.stdin.isatty():
            self._old_settings = termios.tcgetattr(sys.stdin.fileno())
            tty.setraw(sys.stdin.fileno())

    def _restore_terminal(self):
        """Restores the terminal to its original mode."""
        if self._old_settings is not None:
            termios.tcsetattr(
                sys.stdin.fileno(),
                termios.TCSADRAIN,
                self._old_settings,
            )
            self._old_settings = None


def main():
    """CLI entry point for the terminal client."""
    parser = argparse.ArgumentParser(description="Attach to an Agent Dashboard session")
    parser.add_argument("agent_id", help="UUID of the agent session")
    parser.add_argument(
        "--url",
        default=os.getenv("DASHBOARD_URL", "http://localhost:8000"),
        help=("Backend URL " "(default: $DASHBOARD_URL or localhost:8000)"),
    )
    args = parser.parse_args()

    client = TerminalClient(args.url, args.agent_id)
    try:
        exit_code = asyncio.run(client.run())
    except KeyboardInterrupt:
        exit_code = 0
    finally:
        # Ensure terminal is restored on any exit
        client._restore_terminal()  # pylint: disable=protected-access
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
