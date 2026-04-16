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
_STALE_TIMEOUT = 10.0


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
        self._defer_flush = False

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
            print(
                f"Connecting to {self.base_url}...",
                file=sys.stderr,
            )
            await self.client.connect()
            print("Connected.", file=sys.stderr)
        except Exception as e:
            print(
                f"Failed to connect to {self.base_url}: {e}",
                file=sys.stderr,
            )
            return 1

        print(
            f"Joining room {self.agent_id}...",
            file=sys.stderr,
        )
        await self.client.join_room(self.agent_id)
        print("Joined. Waiting for history...", file=sys.stderr)

        # Wait for history_complete before entering raw
        # mode. History chunks are buffered (not flushed)
        # during this wait. The timeout resets whenever a
        # new chunk arrives, so large histories (1000
        # chunks) don't falsely trigger stale detection.
        self._defer_flush = True
        last_chunk_count = 0
        idle_ticks = 0
        while self._replaying:
            await asyncio.sleep(0.1)
            current_count = len(self._history_buf)
            if current_count > last_chunk_count:
                # Chunks are still arriving — reset timer
                last_chunk_count = current_count
                idle_ticks = 0
            else:
                idle_ticks += 1
            # Only consider stale if no chunks arrived for
            # the full timeout AND we never got any chunks
            if idle_ticks >= int(_STALE_TIMEOUT * 10):
                print(
                    f"Timeout: chunks={last_chunk_count} "
                    f"replaying={self._replaying}",
                    file=sys.stderr,
                )
                if last_chunk_count == 0:
                    # No chunks at all — try auto-reconnect
                    new_id = await self._auto_reconnect()
                    if new_id:
                        # Restart with the new agent
                        self.agent_id = new_id
                        self._replaying = True
                        self._history_buf.clear()
                        await self.client.join_room(new_id)
                        last_chunk_count = 0
                        idle_ticks = 0
                        continue
                    await self.client.close()
                    return 1
                # Got chunks but no history_complete —
                # proceed anyway (daemon might have a bug)
                break

        # Send initial resize
        loop = asyncio.get_running_loop()
        rows, cols = self._get_terminal_size()
        await self.client.send_resize(self.agent_id, cols, rows)

        # Enter raw mode BEFORE flushing history so that
        # escape sequences in the history don't corrupt
        # the outer terminal/tmux.
        self._enter_raw_mode()
        self._running = True

        # Now flush buffered history
        for chunk in self._history_buf:
            filtered = _DA_RESPONSE.sub("", chunk)
            if filtered:
                self._write_output(filtered)
        self._history_buf.clear()
        self._defer_flush = False

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
                self._write_output(filtered)

    def _write_output(self, data: str):
        """Writes output to stdout, retrying on
        BlockingIOError. In raw mode, the PTY output
        buffer can fill up during rapid output bursts.
        """
        encoded = data.encode("utf-8", errors="replace")
        fd = sys.stdout.fileno()
        while encoded:
            try:
                written = os.write(fd, encoded)
                encoded = encoded[written:]
            except BlockingIOError:
                # Buffer full — brief yield then retry
                import time

                time.sleep(0.001)  # 1ms backoff

    def _on_history_complete(self, agent_id: str):
        """Handles history replay completion.

        If _defer_flush is True (during initial connect),
        just marks replay done — the caller will flush
        after entering raw mode. Otherwise flushes
        immediately (for reconnect scenarios).
        """
        if agent_id != self.agent_id:
            return
        if not self._defer_flush:
            for chunk in self._history_buf:
                filtered = _DA_RESPONSE.sub("", chunk)
                if filtered:
                    self._write_output(filtered)
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

    async def _auto_reconnect(self) -> str | None:
        """Attempts to reconnect a stale session by stopping
        the old agent record and spawning a replacement with
        resume mode, similar to the web UI's auto-reconnect.

        Returns the new agent_id if successful, None if failed.
        """
        print(
            "Session appears stale, attempting reconnect...",
            file=sys.stderr,
        )
        try:
            # Get the stale agent's details for respawning
            details = await self.client.get_agent_details(self.agent_id)
            tel = details.get("telemetry") or {}
            host_id = details.get("host_id")
            tool = details.get("tool_name", "gemini")
            project_dir = tel.get("worktree_path") or tel.get("project_dir")
            task = tel.get("task_description")

            # Stop the stale record
            try:
                await self.client.stop_agent(self.agent_id)
            except Exception:
                pass

            # Spawn a replacement with resume mode
            new_agent = await self.client.spawn_agent(
                host_id=host_id,
                tool_name=tool,
                project_dir=project_dir,
                task_description=task,
                session_mode="resume",
            )
            new_id = new_agent.get("agent_id")
            print(
                f"Reconnected as {new_id}",
                file=sys.stderr,
            )
            return new_id
        except Exception as e:
            print(
                f"Reconnect failed: {e}",
                file=sys.stderr,
            )
            return None

    async def _read_stdin(self):
        """Reads stdin in raw mode and sends to the agent.

        Detach sequence: press Enter then ~. (tilde-dot)
        to disconnect from the session, similar to SSH.
        Ctrl+C (0x03) also triggers a clean disconnect.
        """
        loop = asyncio.get_running_loop()
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        await loop.connect_read_pipe(lambda: protocol, sys.stdin)
        last_was_newline = False
        last_was_tilde = False
        while self._running:
            try:
                data = await asyncio.wait_for(reader.read(4096), timeout=0.1)
                if not data:
                    break
                # Check for detach sequences byte by byte
                for byte in data:
                    char = chr(byte)
                    # Ctrl+C — disconnect immediately
                    if byte == 0x03:
                        self._running = False
                        return
                    # Enter → ~ → . sequence (like SSH)
                    if last_was_tilde and char == ".":
                        self._running = False
                        return
                    if last_was_newline and char == "~":
                        last_was_tilde = True
                        last_was_newline = False
                        continue
                    # If we buffered a tilde but next char
                    # wasn't '.', send the tilde through
                    if last_was_tilde:
                        await self.client.send_input(self.agent_id, "~")
                        last_was_tilde = False
                    last_was_newline = char in ("\r", "\n")
                    last_was_tilde = False

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
