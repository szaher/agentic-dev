from __future__ import annotations

import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .integrations import status as integration_status
from .providers import provider_document


def _version(binary: str) -> str | None:
    path = shutil.which(binary)
    if not path:
        return None
    for args in (["--version"], ["version"]):
        result = subprocess.run([path, *args], capture_output=True, text=True, check=False)
        text = (result.stdout or result.stderr).strip()
        if result.returncode == 0 and text:
            return text.splitlines()[0][:300]
    return "available"


def _wsl() -> bool:
    if platform.system() != "Linux":
        return False
    try:
        text = Path("/proc/version").read_text().lower()
        return "microsoft" in text or "wsl" in text
    except OSError:
        return False


def document() -> dict[str, Any]:
    integrations = [
        {
            "name": item.name,
            "available": item.available,
            "configured": item.configured,
            "detail": item.detail,
        }
        for item in integration_status()
    ]
    tools = {}
    for name in (
        "claude", "codex", "pi", "serena", "codegraph",
        "docker", "podman", "devcontainer", "dagger",
        "kubectl", "oc", "aws", "az", "gcloud",
    ):
        tools[name] = {
            "available": bool(shutil.which(name)),
            "version": _version(name),
        }
    return {
        "schema_version": "1",
        "document_type": "agentic.compatibility",
        "agentic_version": __version__,
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": sys.version.split()[0],
            "wsl": _wsl(),
        },
        "tools": tools,
        "integrations": integrations,
        "providers": provider_document()["providers"],
    }
