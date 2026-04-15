"""Version display widget for the TUI dashboard footer.

Shows the current version and upgrade notification if a
newer release is available.
"""

from rich.text import Text
from textual.reactive import reactive
from textual.widgets import Static


class VersionBar(Static):
    """Footer widget showing version and upgrade status.

    Args:
        version_info: Version data dict from /version endpoint.
    """

    version_info = reactive({}, always_update=True)

    def render(self) -> Text:
        """Renders the version display."""
        text = Text()
        current = self.version_info.get("current", "dev")
        is_dev = self.version_info.get("is_dev", True)
        latest = self.version_info.get("latest")
        update = self.version_info.get("update_available", False)

        text.append(f" {current}", style="dim")

        if update and latest:
            text.append(f" → {latest} available", style="bold green")
        elif is_dev and latest:
            text.append(f" · latest: {latest}", style="dim")

        return text
