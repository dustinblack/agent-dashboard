"""Host group widget for the TUI dashboard.

Groups agents under a host name header with online/offline
status indicator.
"""

from rich.text import Text
from textual.widgets import Static


class HostHeader(Static):
    """Header for a host group showing name and status.

    Args:
        host: Host data dict from the backend API.
    """

    def __init__(self, host: dict, **kwargs):
        super().__init__(**kwargs)
        self.host = host

    def render(self) -> Text:
        """Renders the host header."""
        name = self.host.get("name", "Unknown Host")
        status = self.host.get("status", "offline")
        text = Text()
        if status == "online":
            text.append(" ● ", style="green")
        else:
            text.append(" ○ ", style="red")
        text.append(name, style="bold")
        return text
