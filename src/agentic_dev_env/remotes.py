from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

from .trust import check as trust_check


def _config_dir() -> Path:
    return Path(os.environ.get(
        "AGENTIC_DEV_ENV_CONFIG_DIR",
        Path.home() / ".config" / "agentic-dev-env",
    ))


def _file() -> Path:
    return _config_dir() / "remotes.json"


def _load() -> dict[str, Any]:
    path = _file()
    try:
        return json.loads(path.read_text()) if path.exists() else {"remotes": {}}
    except (OSError, json.JSONDecodeError):
        return {"remotes": {}}


def _save(data: dict[str, Any]) -> None:
    path = _file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    path.chmod(0o600)


def add(name: str, host: str, *, user: str | None = None, port: int | None = None, path: str | None = None) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9._-]+", name):
        raise ValueError("remote name may contain only letters, digits, dot, underscore, and dash")
    if not host or any(ch.isspace() for ch in host):
        raise ValueError("invalid remote host")
    data = _load()
    data.setdefault("remotes", {})[name] = {
        "host": host,
        "user": user,
        "port": port,
        "path": path,
    }
    _save(data)
    return get(name)


def get(name: str) -> dict:
    item = (_load().get("remotes") or {}).get(name)
    if not item:
        raise KeyError(f"unknown remote: {name}")
    return {"name": name, **item}


def remove(name: str) -> None:
    data = _load()
    if name not in (data.get("remotes") or {}):
        raise KeyError(f"unknown remote: {name}")
    del data["remotes"][name]
    _save(data)


def document() -> dict:
    return {
        "schema_version": "1",
        "document_type": "agentic.remotes",
        "remotes": [
            {"name": name, **item}
            for name, item in sorted((_load().get("remotes") or {}).items())
        ],
    }


def _target(item: dict) -> str:
    return f"{item['user']}@{item['host']}" if item.get("user") else item["host"]


def _ssh_argv(item: dict, command: str, *, timeout: int = 8) -> list[str]:
    argv = [
        "ssh", "-o", "BatchMode=yes",
        "-o", f"ConnectTimeout={timeout}",
    ]
    if item.get("port"):
        argv += ["-p", str(item["port"])]
    argv += [_target(item), command]
    return argv


def inspect(name: str, *, profile: str | None = None) -> dict[str, Any]:
    item = get(name)
    allowed, missing, trust = trust_check(["remote.read"], profile_name=profile)
    if not allowed:
        raise PermissionError(
            f"trust profile '{trust.name}' missing permissions: {', '.join(missing)}"
        )
    path = item.get("path") or "."
    command = f"cd {sh_quote(path)} && printf 'AGENTIC_REMOTE_OK\\n' && uname -srm && pwd && git status --short --branch 2>/dev/null || true"
    argv = _ssh_argv(item, command)
    completed = subprocess.run(argv, capture_output=True, text=True, check=False)
    return {
        "schema_version": "1",
        "document_type": "agentic.remote-status",
        "remote": item,
        "trust_profile": trust.name,
        "success": completed.returncode == 0 and "AGENTIC_REMOTE_OK" in completed.stdout,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def execute(name: str, command: str, *, profile: str | None = None) -> dict[str, Any]:
    item = get(name)
    allowed, missing, trust = trust_check(["remote.exec"], profile_name=profile)
    if not allowed:
        raise PermissionError(
            f"trust profile '{trust.name}' missing permissions: {', '.join(missing)}"
        )
    path = item.get("path") or "."
    remote_command = f"cd {sh_quote(path)} && {command}"
    argv = _ssh_argv(item, remote_command, timeout=15)
    completed = subprocess.run(argv, capture_output=True, text=True, check=False)
    return {
        "schema_version": "1",
        "document_type": "agentic.remote-execution",
        "remote": item,
        "trust_profile": trust.name,
        "command": command,
        "success": completed.returncode == 0,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def sh_quote(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"
