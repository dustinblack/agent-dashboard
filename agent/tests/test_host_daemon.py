"""Unit tests for the Host Daemon.

Tests pure helper functions and methods that do not require
a live Socket.IO connection or PTY. Grouped into sections:
A. _split_utf8
B. _extract_otel_value / _process_otel_attributes
C. _update_telemetry_from_attrs
D. _resolve_agent_id
E. get_git_info
F. _detect_mcp_servers
"""

import json
import subprocess
from unittest.mock import patch, mock_open

import pytest

from agent.host_daemon import HostDaemon, _split_utf8


@pytest.fixture
def daemon():
    """HostDaemon with dummy connection params for unit tests."""
    d = HostDaemon("http://dummy:8000", "dummy-token")
    return d


# ── A. _split_utf8 ──────────────────────────────────────────


class TestSplitUtf8:
    """Tests for the module-level _split_utf8 function."""

    def test_empty_bytes(self):
        """Empty input returns two empty byte strings."""
        assert _split_utf8(b"") == (b"", b"")

    def test_ascii_only(self):
        """Pure ASCII is always complete."""
        assert _split_utf8(b"hello") == (b"hello", b"")

    def test_complete_two_byte(self):
        """A complete 2-byte UTF-8 character (e.g. U+00E9)."""
        data = "é".encode("utf-8")  # b'\xc3\xa9'
        assert _split_utf8(data) == (data, b"")

    def test_complete_three_byte(self):
        """A complete 3-byte character (e.g. U+2603 snowman)."""
        data = "\u2603".encode("utf-8")
        assert _split_utf8(data) == (data, b"")

    def test_complete_four_byte(self):
        """A complete 4-byte character (e.g. U+1F600 emoji)."""
        data = "\U0001f600".encode("utf-8")
        assert _split_utf8(data) == (data, b"")

    def test_incomplete_two_byte(self):
        """Lead byte for 2-byte char without continuation."""
        data = b"abc\xc3"
        complete, remainder = _split_utf8(data)
        assert complete == b"abc"
        assert remainder == b"\xc3"

    def test_incomplete_three_byte(self):
        """Lead byte for 3-byte char with only 1 continuation."""
        data = b"ok\xe2\x98"
        complete, remainder = _split_utf8(data)
        assert complete == b"ok"
        assert remainder == b"\xe2\x98"

    def test_incomplete_four_byte(self):
        """Lead byte for 4-byte char with only 2 continuations."""
        data = b"hi\xf0\x9f\x98"
        complete, remainder = _split_utf8(data)
        assert complete == b"hi"
        assert remainder == b"\xf0\x9f\x98"

    def test_continuation_only(self):
        """Orphan continuation bytes with no lead byte.

        Should pass through as-is (edge case in corrupt data).
        """
        data = b"\x80\x80"
        complete, remainder = _split_utf8(data)
        assert complete == data
        assert remainder == b""


# ── B. _extract_otel_value / _process_otel_attributes ────────


class TestOtelHelpers:
    """Tests for OTLP attribute extraction helpers."""

    def test_extract_string_value(self, daemon):
        """Extracts stringValue from OTLP attribute."""
        assert daemon._extract_otel_value({"stringValue": "hello"}) == "hello"

    def test_extract_int_value(self, daemon):
        """Extracts intValue from OTLP attribute."""
        assert daemon._extract_otel_value({"intValue": 42}) == 42

    def test_extract_double_value(self, daemon):
        """Extracts doubleValue from OTLP attribute."""
        assert daemon._extract_otel_value({"doubleValue": 3.14}) == 3.14

    def test_extract_bool_value(self, daemon):
        """Extracts boolValue from OTLP attribute."""
        assert daemon._extract_otel_value({"boolValue": True}) is True

    def test_extract_unknown_value(self, daemon):
        """Returns None for unrecognised value types."""
        assert daemon._extract_otel_value({"arrayValue": [1, 2]}) is None

    def test_process_empty_list(self, daemon):
        """Empty attributes list produces empty dict."""
        assert daemon._process_otel_attributes([]) == {}

    def test_process_mixed_types(self, daemon):
        """Mixed attribute types are all extracted correctly."""
        attrs = [
            {"key": "model", "value": {"stringValue": "gpt-4"}},
            {"key": "tokens", "value": {"intValue": 500}},
            {"key": "temp", "value": {"doubleValue": 0.7}},
        ]
        result = daemon._process_otel_attributes(attrs)
        assert result == {
            "model": "gpt-4",
            "tokens": 500,
            "temp": 0.7,
        }

    def test_process_missing_key(self, daemon):
        """Attributes with missing 'key' field use empty string."""
        attrs = [{"value": {"stringValue": "orphan"}}]
        result = daemon._process_otel_attributes(attrs)
        assert result.get("") == "orphan"


# ── C. _update_telemetry_from_attrs ──────────────────────────


class TestUpdateTelemetry:
    """Tests for _update_telemetry_from_attrs."""

    def _base_tel(self):
        """Returns a minimal telemetry dict for testing."""
        return {
            "model": "detecting...",
            "tokens": 0,
            "context_tokens": 0,
            "current_activity": "",
        }

    def test_model_detection_from_model_key(self, daemon):
        """Detects model from the 'model' attribute key."""
        tel = self._base_tel()
        changed = daemon._update_telemetry_from_attrs(tel, {"model": "claude-sonnet-4"})
        assert changed is True
        assert tel["model"] == "claude-sonnet-4"

    def test_model_detection_gen_ai_key(self, daemon):
        """Detects model from gen_ai.request.model attribute."""
        tel = self._base_tel()
        changed = daemon._update_telemetry_from_attrs(
            tel, {"gen_ai.request.model": "gemini-2.5-pro"}
        )
        assert changed is True
        assert tel["model"] == "gemini-2.5-pro"

    def test_token_accumulation(self, daemon):
        """Input + output tokens accumulate into total."""
        tel = self._base_tel()
        attrs = {"input_tokens": 100, "output_tokens": 50}
        changed = daemon._update_telemetry_from_attrs(tel, attrs)
        assert changed is True
        assert tel["tokens"] == 150

    def test_token_with_cache(self, daemon):
        """Cache tokens are included in the total."""
        tel = self._base_tel()
        attrs = {
            "input_tokens": 100,
            "output_tokens": 50,
            "cache_read_tokens": 200,
        }
        changed = daemon._update_telemetry_from_attrs(tel, attrs)
        assert changed is True
        assert tel["tokens"] == 350

    def test_tokens_no_decrease(self, daemon):
        """Total tokens should never decrease."""
        tel = self._base_tel()
        tel["tokens"] = 500
        attrs = {"input_tokens": 10, "output_tokens": 5}
        daemon._update_telemetry_from_attrs(tel, attrs)
        # 15 < 500, so tokens should stay at 500
        assert tel["tokens"] == 500

    def test_context_tokens_can_decrease(self, daemon):
        """context_tokens always reflects the latest value."""
        tel = self._base_tel()
        tel["context_tokens"] = 1000
        attrs = {"input_tokens": 500, "output_tokens": 100}
        daemon._update_telemetry_from_attrs(tel, attrs)
        assert tel["context_tokens"] == 500

    def test_activity_from_function_name(self, daemon):
        """Extracts current_activity from function_name attr."""
        tel = self._base_tel()
        attrs = {"function_name": "read_file"}
        changed = daemon._update_telemetry_from_attrs(tel, attrs)
        assert changed is True
        assert tel["current_activity"] == "read_file"

    def test_activity_from_event_name_fallback(self, daemon):
        """Falls back to event.name when no function_name."""
        tel = self._base_tel()
        attrs = {"event.name": "tool_call"}
        changed = daemon._update_telemetry_from_attrs(tel, attrs)
        assert changed is True
        assert tel["current_activity"] == "tool_call"

    def test_event_name_excluded(self, daemon):
        """gen_ai_operation_details event is excluded."""
        tel = self._base_tel()
        attrs = {"event.name": "gen_ai_operation_details"}
        changed = daemon._update_telemetry_from_attrs(tel, attrs)
        assert changed is False

    def test_no_change_returns_false(self, daemon):
        """Returns False when no telemetry values change."""
        tel = self._base_tel()
        changed = daemon._update_telemetry_from_attrs(tel, {})
        assert changed is False


# ── D. _resolve_agent_id ─────────────────────────────────────


class TestResolveAgentId:
    """Tests for _resolve_agent_id."""

    def test_direct_match_service_name(self, daemon):
        """Direct match via service.name in resource attrs."""
        daemon.agents["agent-123"] = {"tool": "claude"}
        result = daemon._resolve_agent_id({"service.name": "agent-123"})
        assert result == "agent-123"

    def test_gemini_fallback_single_candidate(self, daemon):
        """Gemini tool hint matches single gemini agent."""
        daemon.agents["g-1"] = {
            "tool": "gemini",
            "last_output_time": 1.0,
        }
        result = daemon._resolve_agent_id({"service.name": "gemini-cli"})
        assert result == "g-1"

    def test_gemini_fallback_multiple_candidates(self, daemon):
        """Multiple gemini agents: picks most recent."""
        daemon.agents["g-old"] = {
            "tool": "gemini",
            "last_output_time": 1.0,
        }
        daemon.agents["g-new"] = {
            "tool": "gemini",
            "last_output_time": 99.0,
        }
        result = daemon._resolve_agent_id({"service.name": "gemini-cli"})
        assert result == "g-new"

    def test_claude_fallback(self, daemon):
        """Claude tool hint from resource attribute values."""
        daemon.agents["c-1"] = {
            "tool": "claude",
            "last_output_time": 1.0,
        }
        result = daemon._resolve_agent_id(
            {"service.name": "unknown", "sdk": "claude-sdk"}
        )
        assert result == "c-1"

    def test_single_agent_last_resort(self, daemon):
        """Falls back to the only agent if no other match."""
        daemon.agents["lonely"] = {"tool": "bash"}
        result = daemon._resolve_agent_id({"service.name": "something-random"})
        assert result == "lonely"

    def test_no_match_returns_none(self, daemon):
        """Returns None when no agents are running."""
        result = daemon._resolve_agent_id({"service.name": "nobody"})
        assert result is None

    def test_no_match_multiple_agents(self, daemon):
        """Returns None when multiple agents exist but no hint."""
        daemon.agents["a"] = {"tool": "bash"}
        daemon.agents["b"] = {"tool": "bash"}
        result = daemon._resolve_agent_id({"service.name": "unknown"})
        assert result is None


# ── E. get_git_info ──────────────────────────────────────────


class TestGetGitInfo:
    """Tests for get_git_info (mocked subprocess calls)."""

    def test_with_remote_origin(self, daemon):
        """Extracts branch and project from remote origin."""
        with patch("os.path.exists", return_value=True):
            with patch("subprocess.check_output") as mock_co:
                mock_co.side_effect = [
                    b"main\n",
                    b"git@github.com:user/my-repo.git\n",
                ]
                branch, project, _url = daemon.get_git_info("/tmp/repo")  # nosec B108
        assert branch == "main"
        assert project == "my-repo"

    def test_without_remote_toplevel_fallback(self, daemon):
        """Falls back to git toplevel basename when no remote."""
        with patch("os.path.exists", return_value=True):
            with patch("subprocess.check_output") as mock_co:
                mock_co.side_effect = [
                    b"feature-branch\n",
                    subprocess.CalledProcessError(1, "git"),
                    b"/home/user/my-project\n",
                ]
                branch, project, _url = daemon.get_git_info("/tmp/repo")  # nosec B108
        assert branch == "feature-branch"
        assert project == "my-project"

    def test_nonexistent_path(self, daemon):
        """Returns None, None for paths that don't exist."""
        branch, project, _url = daemon.get_git_info("/nonexistent/path/xyz")
        assert branch is None
        assert project is None

    def test_no_git_at_all(self, daemon):
        """Returns None, None when git commands all fail."""
        with patch("subprocess.check_output") as mock_co:
            mock_co.side_effect = subprocess.CalledProcessError(128, "git")
            with patch("os.path.exists", return_value=True):
                branch, project, _url = daemon.get_git_info("/tmp/nogit")  # nosec B108
        assert branch is None
        assert project is None

    def test_empty_path(self, daemon):
        """Returns None, None for empty string path."""
        branch, project, _url = daemon.get_git_info("")
        assert branch is None
        assert project is None


# ── F. _detect_mcp_servers ───────────────────────────────────


class TestDetectMcpServers:
    """Tests for _detect_mcp_servers (mocked file reads)."""

    def test_claude_project_level(self, daemon):
        """Detects MCP servers from project .mcp.json."""
        mcp_data = json.dumps({"mcpServers": {"server-a": {}, "server-b": {}}})
        with patch("os.path.isfile", return_value=True):
            with patch("builtins.open", mock_open(read_data=mcp_data)):
                servers = daemon._detect_mcp_servers("/proj", "claude")
        assert "server-a" in servers
        assert "server-b" in servers

    def test_claude_user_level(self, daemon):
        """Detects MCP servers from ~/.claude.json."""
        user_data = json.dumps({"mcpServers": {"global-srv": {}}})

        def isfile_side_effect(path):
            # Only user-level exists
            return "/.claude.json" in path

        with patch("os.path.isfile", side_effect=isfile_side_effect):
            with patch("builtins.open", mock_open(read_data=user_data)):
                servers = daemon._detect_mcp_servers("/proj", "claude")
        assert "global-srv" in servers

    def test_claude_both_deduped(self, daemon):
        """Project and user MCP servers are merged, deduped."""
        proj_data = json.dumps({"mcpServers": {"shared": {}, "proj-only": {}}})
        user_data = json.dumps({"mcpServers": {"shared": {}, "user-only": {}}})

        call_count = {"n": 0}

        def open_side_effect(path, *args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return mock_open(read_data=proj_data)()
            return mock_open(read_data=user_data)()

        with patch("os.path.isfile", return_value=True):
            with patch("builtins.open", side_effect=open_side_effect):
                servers = daemon._detect_mcp_servers("/proj", "claude")
        assert servers.count("shared") == 1
        assert "proj-only" in servers
        assert "user-only" in servers

    def test_gemini_settings(self, daemon):
        """Detects MCP servers from Gemini settings.json."""
        settings_data = json.dumps({"mcpServers": {"gemini-mcp": {}}})
        with patch("os.path.isfile", return_value=True):
            with patch(
                "builtins.open",
                mock_open(read_data=settings_data),
            ):
                servers = daemon._detect_mcp_servers("/proj", "gemini")
        assert "gemini-mcp" in servers

    def test_unknown_tool(self, daemon):
        """Unknown tool type returns empty list."""
        servers = daemon._detect_mcp_servers("/proj", "bash")
        assert servers == []

    def test_missing_files(self, daemon):
        """Returns empty list when config files don't exist."""
        with patch("os.path.isfile", return_value=False):
            servers = daemon._detect_mcp_servers("/proj", "claude")
        assert servers == []


# ── G. Agent Profiles ───────────────────────────────────────


class TestAgentProfiles:
    """Tests for the agent profile loading system."""

    def test_load_bundled_profiles(self):
        """All three bundled profiles load successfully."""
        from agent.profiles import load_profiles

        profiles = load_profiles()
        assert "claude" in profiles
        assert "gemini" in profiles
        assert "bash" in profiles

    def test_claude_profile_fields(self):
        """Claude profile has expected configuration."""
        from agent.profiles import load_profiles

        profiles = load_profiles()
        claude = profiles["claude"]
        assert claude.binary == "claude"
        assert claude.display_name == "Claude"
        assert claude.commands.new == ["claude"]
        assert len(claude.commands.resume) > 0
        assert len(claude.env) > 0
        assert "ANTHROPIC_API_KEY" in claude.auth.env_vars
        assert claude.auth.require == "any"
        assert claude.mcp is not None
        assert claude.mcp.project_file == ".mcp.json"
        assert len(claude.telemetry.token_metrics) > 0
        assert claude.telemetry.cost_metric is not None
        assert len(claude.permission_patterns) > 0
        assert not claude.always_available

    def test_gemini_profile_fields(self):
        """Gemini profile has expected configuration."""
        from agent.profiles import load_profiles

        profiles = load_profiles()
        gemini = profiles["gemini"]
        assert gemini.binary == "gemini"
        assert "GEMINI_API_KEY" in gemini.auth.env_vars
        assert gemini.mcp is not None
        assert len(gemini.telemetry.token_metrics) > 0
        assert gemini.telemetry.runtime_metric is not None
        assert gemini.telemetry.runtime_metric.unit == "milliseconds"
        assert len(gemini.telemetry.excluded_metrics) > 0
        assert not gemini.always_available

    def test_bash_profile_fields(self):
        """Bash profile has sidecar config and always_available."""
        from agent.profiles import load_profiles

        profiles = load_profiles()
        bash = profiles["bash"]
        assert bash.binary == "bash"
        assert bash.always_available is True
        assert bash.sidecar is not None
        assert bash.sidecar.prompt_command is not None
        assert "agent_id" in bash.sidecar.file_pattern
        assert "current_activity" in bash.sidecar.fields

    def test_profile_permission_patterns_merged(self, daemon):
        """Permission patterns from profiles are merged
        into the instance permission_patterns list."""
        assert len(daemon.permission_patterns) > 0
        # Should include generic defaults
        patterns_str = [p.pattern for p in daemon.permission_patterns]
        assert any("Y/n" in p for p in patterns_str)
        # Should include Claude-specific
        assert any("proceed" in p.lower() for p in patterns_str)

    def test_otlp_lookup_tables_built(self, daemon):
        """OTLP metric lookup tables are populated from profiles."""
        assert "claude_code.token.usage" in daemon._token_metrics
        assert "gemini_cli.token.usage" in daemon._token_metrics
        assert "claude_code.cost.usage" in daemon._cost_metrics
        assert "claude_code.active_time.total" in daemon._runtime_metrics
        assert "gemini_cli.agent.duration" in daemon._runtime_metrics
        assert "gen_ai.client.token.usage" in daemon._excluded_metrics

    def test_supports_resume_property(self):
        """supports_resume is True when resume differs from
        new, False when they are the same."""
        from agent.profiles import load_profiles

        profiles = load_profiles()
        # Claude and Gemini have distinct resume commands
        assert profiles["claude"].supports_resume is True
        assert profiles["gemini"].supports_resume is True
        # Bash has resume == new == ["bash"]
        assert profiles["bash"].supports_resume is False

    def test_color_field_loaded(self):
        """Color field is loaded from profile YAML files."""
        from agent.profiles import load_profiles

        profiles = load_profiles()
        assert profiles["claude"].color == "purple"
        assert profiles["gemini"].color == "blue"
        assert profiles["bash"].color == "slate"

    def test_make_tool_info(self, daemon):
        """_make_tool_info builds correct metadata dict."""
        info = daemon._make_tool_info(daemon.profiles["claude"])
        assert info["name"] == "claude"
        assert info["display_name"] == "Claude"
        assert info["color"] == "purple"
        assert info["supports_resume"] is True
        assert info["has_model"] is True

        bash_info = daemon._make_tool_info(daemon.profiles["bash"])
        assert bash_info["name"] == "bash"
        assert bash_info["color"] == "slate"
        assert bash_info["supports_resume"] is False
        assert bash_info["has_model"] is False

    def test_unknown_profile_returns_empty(self):
        """Loading from empty directory returns no profiles."""
        import tempfile

        from agent.profiles import load_profiles

        with tempfile.TemporaryDirectory() as tmpdir:
            profiles = load_profiles(tmpdir)
        assert profiles == {}
