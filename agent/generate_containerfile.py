#!/usr/bin/env python3
"""Generates Containerfile from template + agent profiles.

Reads all agent profiles from agent/profiles/, collects
provisioning metadata (npm/pip/system packages, config
files, verification commands), and renders the Jinja2
template into agent/Containerfile.

Usage:
    python3 generate_containerfile.py

The generated Containerfile is written to the same
directory as this script. Static infrastructure
(base packages, gh CLI, gcloud, dev tools) is defined
directly in Containerfile.template — edit it there.
"""

import os
import sys

# Allow running from both the repo root and the agent/
# directory by adding the parent to sys.path.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from jinja2 import Environment, FileSystemLoader  # noqa: E402

from agent.profiles import load_profiles  # noqa: E402


def collect_provisioning(profiles):
    """Collects provisioning metadata from all profiles.

    Aggregates npm/pip/system packages, config files,
    and verify commands across all profiles that define
    a provisioning section.

    Args:
        profiles: Dict of name -> AgentProfile.

    Returns:
        Dict with npm_packages, pip_packages,
        system_packages, config_files, and
        verify_commands lists.
    """
    npm_packages = []
    pip_packages = []
    system_packages = []
    config_files = []
    verify_commands = []

    for profile in profiles.values():
        prov = profile.provisioning
        if not prov:
            continue
        npm_packages.extend(prov.install.npm)
        pip_packages.extend(prov.install.pip)
        system_packages.extend(prov.install.system)
        config_files.extend(prov.config_files)
        if prov.verify:
            verify_commands.append(prov.verify)

    return {
        "npm_packages": npm_packages,
        "pip_packages": pip_packages,
        "system_packages": system_packages,
        "config_files": config_files,
        "verify_commands": verify_commands,
    }


def generate():
    """Renders the Containerfile template with profile
    provisioning data and writes the output.
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    template_path = os.path.join(script_dir, "Containerfile.template")
    output_path = os.path.join(script_dir, "Containerfile")

    if not os.path.exists(template_path):
        print(f"Template not found: {template_path}")
        sys.exit(1)

    profiles = load_profiles(os.path.join(script_dir, "profiles"))
    context = collect_provisioning(profiles)

    env = Environment(  # nosec B701 — Dockerfile, not HTML
        loader=FileSystemLoader(script_dir),
        autoescape=False,
        keep_trailing_newline=True,
        lstrip_blocks=True,
        trim_blocks=True,
    )
    template = env.get_template("Containerfile.template")
    rendered = template.render(**context)

    # Add header comment after the Jinja2 comment block
    header = (
        "# Generated from Containerfile.template"
        " — do not edit directly.\n"
        "# Regenerate: python3 generate_containerfile.py\n"
    )
    rendered = header + rendered

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(rendered)

    print(f"Generated {output_path}")
    print(f"  npm: {context['npm_packages']}")
    print(f"  pip: {context['pip_packages']}")
    print(f"  system: {context['system_packages']}")
    print(f"  verify: {context['verify_commands']}")


if __name__ == "__main__":
    generate()
