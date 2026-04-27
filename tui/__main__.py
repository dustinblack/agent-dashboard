"""Entry point for running the TUI as a module.

Usage:
    python -m tui              # Launch dashboard TUI
    python -m tui attach <id>  # Attach to agent session
"""

import sys

if len(sys.argv) > 1 and sys.argv[1] == "attach":
    # Shift args so terminal_client sees agent_id as first arg
    sys.argv = [sys.argv[0]] + sys.argv[2:]
    from tui.terminal_client import main as attach_main

    attach_main()
else:
    from tui.app import main as app_main

    app_main()
