"""Conservative, version-specific harness permission facts.

CLI options are candidate mechanisms, not proof of complete isolation. Only a
verified, version-scoped fact may become ``enforceable``. No request input can
set or override these facts.
"""

from __future__ import annotations

import re
import shutil
import subprocess

from .session_permissions import LEVELS

HARNESSES = ("claude", "codex", "pi", "opencode")

CANDIDATES: dict[str, dict[str, str]] = {
    "codex": {
        "filesystem.read-only": "codex exec --sandbox read-only --ask-for-approval never --cd WORKSPACE",
        "filesystem.workspace-write": "codex exec --sandbox workspace-write --ask-for-approval never --cd WORKSPACE",
        "network.off": "sandbox network restriction; disable web search and external tools",
        "network.on": "workspace-write sandbox with explicit network allowance",
    },
    "claude": {
        "filesystem.read-only": "restricted file tools and command-tool denial",
        "filesystem.workspace-write": "restricted workspace with write tools",
        "network.off": "deny WebFetch, network commands, plugins and MCP tools",
        "network.on": "explicitly allow network tools",
    },
    "pi": {},
    "opencode": {},
}


def inspect_harness(name: str) -> dict:
    if name not in HARNESSES:
        raise ValueError(f"unknown harness: {name}")
    executable = shutil.which(name)
    version = None
    if executable:
        try:
            completed = subprocess.run(
                [executable, "--version"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            output = (completed.stdout or completed.stderr).strip()
            version = (
                output.splitlines()[0] if completed.returncode == 0 and output else None
            )
        except (OSError, subprocess.TimeoutExpired):
            pass
    # A version string is needed before a fact can be asserted. Unparseable
    # or missing versions stay unknown, as do all unverified mechanisms.
    version_known = bool(version and re.search(r"\d+\.\d+", version))
    dimensions = {
        dimension: {
            level: {
                "status": "unknown",
                "mechanism": CANDIDATES[name].get(f"{dimension}.{level}"),
                "evidence": "CLI option identified; complete boundary not yet verified"
                if version_known
                else "harness unavailable or version unknown",
            }
            for level in levels
        }
        for dimension, levels in LEVELS.items()
    }
    return {
        "name": name,
        "available": executable is not None,
        "executable": executable,
        "version": version,
        "permissions": dimensions,
    }
