"""Conservative, version-specific harness permission facts.

CLI options are candidate mechanisms, not proof of complete isolation. Only a
verified, version-scoped fact may become ``enforceable``. No request input can
set or override these facts.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from platform import system

from .session_permissions import LEVELS

HARNESSES = ("claude", "codex", "pi", "opencode")

CANDIDATES: dict[str, dict[str, str]] = {
    "codex": {
        "filesystem.read-only": "read-only command sandbox or :read-only permission profile; agent launch unverified",
        "filesystem.workspace-write": "workspace-scoped permission profile with temp roots denied; agent launch unverified",
        "network.off": "command sandbox network disabled; web, MCP and connector surfaces unverified",
        "network.on": "workspace-write sandbox with explicit network allowance",
    },
    "claude": {
        "filesystem.read-only": "--restricted --strict-mcp-config --tools Read,Glob,Grep --permission-mode dontAsk",
        "filesystem.workspace-write": "--restricted --strict-mcp-config --tools Read,Glob,Grep,Edit,Write --allowedTools Read,Glob,Grep,Edit,Write --permission-mode dontAsk",
        "network.off": "restrict tools; deny Bash, WebFetch, WebSearch and MCP; full egress unverified",
        "network.on": "explicitly allow network tools",
    },
    "pi": {},
    "opencode": {},
}

# These are observations of narrower surfaces, not complete agent enforcement
# claims. An exact harness version and platform match is required to attach one.
# The planner keeps status=unknown until every path in its permission definition
# has been verified and S3 can launch that exact recipe.
PROBE_OBSERVATIONS: dict[tuple[str, str, str], dict[str, object]] = {
    ("codex", "codex-cli 0.154.0", "Darwin"): {
        "id": "macos-codex-0.154.0-2026-10-04",
        "observations": {
            "filesystem.read-only": "Command sandbox denied inside, outside and symlink writes.",
            "filesystem.workspace-write": "Command sandbox allowed inside write; denied outside and symlink writes.",
            "network.off": "Command sandbox denied loopback connection; agent web/MCP paths untested.",
        },
    },
    ("claude", "2.1.289 (Claude Code)", "Darwin"): {
        "id": "macos-claude-2.1.289-2026-10-04",
        "observations": {
            "filesystem.read-only": "Restricted read-only tool set exposed no write tool; files unchanged.",
            "filesystem.workspace-write": "Restricted Write changed inside file; denied outside and symlink writes.",
            "network.off": "Network-capable built-ins absent in probe; full egress untested.",
        },
    },
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
    probe = (
        PROBE_OBSERVATIONS.get((name, version, system()), {})
        if version is not None
        else {}
    )
    observations = probe.get("observations", {})
    assert isinstance(observations, dict)
    dimensions = {
        dimension: {
            level: {
                "status": "unknown",
                "mechanism": CANDIDATES[name].get(f"{dimension}.{level}"),
                "evidence": observations.get(f"{dimension}.{level}")
                or (
                    "Candidate mechanism; complete boundary not yet verified"
                    if version_known and f"{dimension}.{level}" in CANDIDATES[name]
                    else "harness unavailable, version unknown, or no verified mechanism"
                ),
                "probe_id": probe["id"]
                if f"{dimension}.{level}" in observations
                else None,
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
