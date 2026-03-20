import pytest
from unittest.mock import patch, MagicMock
import os
import sys

# Add the agent directory to the path so we can import the wrapper
sys.path.append(os.path.dirname(os.path.abspath(__file__)))


# We must mock os.getenv to avoid the sys.exit(1) on import if MACHINE_TOKEN is missing
@patch.dict(
    os.environ, {"MACHINE_TOKEN": "test-token", "DASHBOARD_URL": "http://test-url"}
)
def test_wrapper_imports_successfully():
    """
    Test that the wrapper can be imported without syntax errors or immediate crashes
    when the environment is properly configured.
    """
    try:
        import gemini_telemetry_wrapper

        assert gemini_telemetry_wrapper.sio is not None
    except Exception as e:
        pytest.fail(f"Importing the wrapper failed: {e}")


@patch.dict(os.environ, {"MACHINE_TOKEN": "test-token"})
@patch("gemini_telemetry_wrapper.sio.connect", new_callable=MagicMock)
@patch(
    "gemini_telemetry_wrapper.pty.fork", return_value=(1, 5)
)  # Simulate being the parent process
@patch("gemini_telemetry_wrapper.asyncio.get_running_loop")
@patch("gemini_telemetry_wrapper.sys.exit")
@pytest.mark.asyncio
async def test_wrapper_configuration(mock_exit, mock_loop, mock_fork, mock_connect):
    """
    A basic mock test to ensure the script tries to connect
    with the right parameters. Since the pty logic is highly
    dependent on an interactive shell, we mock the core event
    loop.
    """
    import gemini_telemetry_wrapper

    # We mock out the while loop part to prevent blocking
    mock_loop.return_value.run_in_executor = MagicMock(
        side_effect=Exception("Break loop for testing")
    )

    try:
        await gemini_telemetry_wrapper.main()
    except Exception as e:
        # We expect our dummy exception to break out of the infinite select loop
        assert str(e) == "Break loop for testing"

    mock_connect.assert_called_once()
    args, kwargs = mock_connect.call_args
    # Due to import-time evaluation in the script, this
    # might use the default if imported before the patch
    assert args[0] == "http://localhost:8000"
