"""Agent profile loader for the Host Daemon.

Loads agent tool profiles from YAML/JSON files in the
profiles/ directory. Each profile defines how to spawn,
detect, and monitor a specific agent tool (e.g. Claude
Code, Gemini CLI, Bash).

Profiles are loaded once at daemon startup and used
throughout the daemon's lifecycle to drive tool-specific
behavior without hardcoded if/elif branches.
"""

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import yaml


@dataclass
class CommandConfig:
    """Spawn command configuration for an agent tool."""

    new: List[str] = field(default_factory=list)
    resume: List[str] = field(default_factory=list)


@dataclass
class AuthConfig:
    """Authentication detection configuration."""

    env_vars: List[str] = field(default_factory=list)
    require: str = "any"


@dataclass
class McpConfig:
    """MCP server detection configuration."""

    project_file: Optional[str] = None
    user_files: List[str] = field(default_factory=list)


@dataclass
class RuntimeMetric:
    """Runtime duration metric configuration."""

    name: str = ""
    unit: str = "seconds"


@dataclass
class TelemetryConfig:
    """OTLP telemetry metric mapping configuration."""

    token_metrics: List[str] = field(default_factory=list)
    cost_metric: Optional[str] = None
    activity_metrics: List[str] = field(default_factory=list)
    runtime_metric: Optional[RuntimeMetric] = None
    excluded_metrics: List[str] = field(default_factory=list)


@dataclass
class SidecarConfig:
    """Sidecar telemetry configuration (e.g. bash
    PROMPT_COMMAND).
    """

    prompt_command: Optional[str] = None
    file_pattern: str = "{tmpdir}/.agent-telemetry-{agent_id}"
    fields: Dict[str, str] = field(default_factory=dict)


@dataclass
class AgentProfile:
    """Complete profile for an agent tool.

    Defines all tool-specific behavior: how to spawn it,
    what env vars it needs, where its MCP configs live,
    what OTLP metrics it emits, how to detect if it's
    installed, and what permission prompts it uses.
    """

    name: str = ""
    display_name: str = ""
    color: str = ""
    binary: str = ""
    always_available: bool = False
    commands: CommandConfig = field(default_factory=CommandConfig)
    env: Dict[str, str] = field(default_factory=dict)
    auth: AuthConfig = field(default_factory=AuthConfig)
    mcp: Optional[McpConfig] = None
    telemetry: TelemetryConfig = field(default_factory=TelemetryConfig)
    sidecar: Optional[SidecarConfig] = None
    permission_patterns: List[str] = field(default_factory=list)

    @property
    def supports_resume(self) -> bool:
        """Whether the tool supports resuming a previous
        session. True when the resume command is defined
        and differs from the new-session command.
        """
        return bool(self.commands.resume) and self.commands.resume != self.commands.new


def _parse_profile(data: dict) -> AgentProfile:
    """Parses a raw dict (from YAML/JSON) into an
    AgentProfile dataclass.

    Args:
        data: Raw profile dict from yaml.safe_load().

    Returns:
        Populated AgentProfile instance.
    """
    profile = AgentProfile(
        name=data.get("name", ""),
        display_name=data.get("display_name", ""),
        color=data.get("color", ""),
        binary=data.get("binary", ""),
        always_available=data.get("always_available", False),
        permission_patterns=data.get("permission_patterns", []),
        env=data.get("env", {}),
    )

    # Commands
    cmds = data.get("commands", {})
    profile.commands = CommandConfig(
        new=cmds.get("new", []),
        resume=cmds.get("resume", []),
    )

    # Auth
    auth = data.get("auth", {})
    profile.auth = AuthConfig(
        env_vars=auth.get("env_vars", []),
        require=auth.get("require", "any"),
    )

    # MCP
    mcp = data.get("mcp")
    if mcp:
        profile.mcp = McpConfig(
            project_file=mcp.get("project_file"),
            user_files=mcp.get("user_files", []),
        )

    # Telemetry
    tel = data.get("telemetry", {})
    runtime = tel.get("runtime_metric")
    profile.telemetry = TelemetryConfig(
        token_metrics=tel.get("token_metrics", []),
        cost_metric=tel.get("cost_metric"),
        activity_metrics=tel.get("activity_metrics", []),
        runtime_metric=(
            RuntimeMetric(
                name=runtime.get("name", ""),
                unit=runtime.get("unit", "seconds"),
            )
            if runtime
            else None
        ),
        excluded_metrics=tel.get("excluded_metrics", []),
    )

    # Sidecar
    sc = data.get("sidecar")
    if sc:
        profile.sidecar = SidecarConfig(
            prompt_command=sc.get("prompt_command"),
            file_pattern=sc.get(
                "file_pattern",
                "{tmpdir}/.agent-telemetry-{agent_id}",
            ),
            fields=sc.get("fields", {}),
        )

    return profile


def load_profiles(
    directory: str = None,
) -> Dict[str, AgentProfile]:
    """Loads all agent profiles from a directory.

    Reads all .yaml, .yml, and .json files from the
    specified directory and parses them into AgentProfile
    instances.

    Args:
        directory: Path to the profiles directory.
            Defaults to agent/profiles/ relative to this
            file.

    Returns:
        Dict mapping profile name to AgentProfile.
    """
    if directory is None:
        directory = os.path.join(os.path.dirname(__file__), "profiles")

    profiles = {}
    if not os.path.isdir(directory):
        print(f"Profiles directory not found: {directory}")
        return profiles

    for filename in sorted(os.listdir(directory)):
        if not filename.endswith((".yaml", ".yml", ".json")):
            continue
        filepath = os.path.join(directory, filename)
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            if not data or not isinstance(data, dict):
                print(f"Skipping empty profile: {filename}")
                continue
            profile = _parse_profile(data)
            if not profile.name:
                print(f"Profile missing 'name' field: " f"{filename}")
                continue
            profiles[profile.name] = profile
            print(f"Loaded agent profile: {profile.name} " f"({profile.display_name})")
        except Exception as e:
            print(f"Error loading profile {filename}: {e}")

    return profiles
