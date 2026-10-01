from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any


def _config_dir() -> Path:
    return Path(os.environ.get(
        "AGENTIC_DEV_ENV_CONFIG_DIR",
        Path.home() / ".config" / "agentic-dev-env",
    ))


def _file() -> Path:
    return _config_dir() / "remotes.json"


def _load() -> dict[str, Any]:
    path = _file()
    if not path.exists():
        return {"remotes": {}}
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {"remotes": {}}


def _save(data: dict[str, Any]) -> None:
    path = _file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def add(
    name: str,
    host: str,
    *,
    user: str | None = None,
    port: int | None = None,
    identity_file: str | None = None,
    workdir: str | None = None,
) -> dict[str, Any]:
    if not name.strip() or not host.strip():
        raise ValueError("remote name and host are required")
    if port is not None and not (1 <= port <= 65535):
        raise ValueError("SSH port must be between 1 and 65535")
    identity: str | None = None
    if identity_file:
        path = Path(identity_file).expanduser()
        identity = str(path)
    data = _load()
    record = {
        "name": name,
        "host": host,
        "user": user,
        "port": port,
        "identity_file": identity,
        "workdir": workdir,
    }
    data.setdefault("remotes", {})[name] = record
    _save(data)
    return record


def remove(name: str) -> None:
    data = _load()
    if name not in data.get("remotes", {}):
        raise KeyError(name)
    data["remotes"].pop(name, None)
    _save(data)


def get(name: str) -> dict[str, Any]:
    data = _load()
    try:
        return dict(data["remotes"][name])
    except KeyError as exc:
        raise KeyError(name) from exc


def list_profiles() -> list[dict[str, Any]]:
    return [dict(item) for _, item in sorted((_load().get("remotes") or {}).items())]


def _ssh_args(profile: dict[str, Any]) -> list[str]:
    target = profile["host"]
    if profile.get("user"):
        target = f"{profile['user']}@{target}"
    args = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8"]
    if profile.get("port"):
        args += ["-p", str(profile["port"])]
    if profile.get("identity_file"):
        args += ["-i", profile["identity_file"]]
    args.append(target)
    return args


def test(name: str) -> dict[str, Any]:
    profile = get(name)
    if not shutil.which("ssh"):
        raise RuntimeError("ssh executable not found")
    args = _ssh_args(profile) + ["printf", "agentic-remote-ok"]
    result = subprocess.run(args, capture_output=True, text=True, check=False)
    return {
        "schema_version": "1",
        "document_type": "agentic.remote-test",
        "name": name,
        "host": profile["host"],
        "success": result.returncode == 0 and "agentic-remote-ok" in result.stdout,
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


def command(name: str, argv: list[str]) -> list[str]:
    if not argv:
        raise ValueError("remote command requires argv")
    profile = get(name)
    args = _ssh_args(profile)
    remote = []
    if profile.get("workdir"):
        remote += ["cd", profile["workdir"], "&&"]
    remote += argv
    return args + remote


def status() -> dict[str, Any]:
    return {
        "schema_version": "1",
        "document_type": "agentic.remotes",
        "ssh_available": bool(shutil.which("ssh")),
        "remotes": list_profiles(),
    }
