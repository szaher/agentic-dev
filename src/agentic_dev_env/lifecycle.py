from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from . import __version__


def _config_dir() -> Path:
    return Path(os.environ.get(
        "AGENTIC_DEV_ENV_CONFIG_DIR",
        Path.home() / ".config" / "agentic-dev-env",
    ))


def _install_file() -> Path:
    return _config_dir() / "install.json"


def install_metadata() -> dict[str, Any]:
    path = _install_file()
    try:
        return json.loads(path.read_text()) if path.exists() else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True, text=True, check=False,
    )


def update_status(*, fetch: bool = False) -> dict[str, Any]:
    meta = install_metadata()
    source = Path(meta.get("source_root", "")).expanduser() if meta.get("source_root") else None
    result: dict[str, Any] = {
        "schema_version": "1",
        "document_type": "agentic.update-status",
        "installed_version": __version__,
        "source_root": str(source) if source else None,
        "source_available": bool(source and source.exists()),
        "git_source": False,
        "head": None,
        "upstream": None,
        "update_available": None,
        "fetch_attempted": False,
        "fetch_success": None,
    }
    if not source or not source.exists():
        return result
    if _git(source, "rev-parse", "--is-inside-work-tree").returncode != 0:
        return result
    result["git_source"] = True
    if fetch:
        result["fetch_attempted"] = True
        fetched = _git(source, "fetch", "--quiet", "origin")
        result["fetch_success"] = fetched.returncode == 0
        if fetched.returncode != 0:
            result["fetch_error"] = fetched.stderr.strip()

    head = _git(source, "rev-parse", "HEAD")
    upstream = _git(source, "rev-parse", "@{upstream}")
    if upstream.returncode != 0:
        upstream = _git(source, "rev-parse", "origin/main")
    result["head"] = head.stdout.strip() if head.returncode == 0 else None
    result["upstream"] = upstream.stdout.strip() if upstream.returncode == 0 else None
    if result["head"] and result["upstream"]:
        result["update_available"] = result["head"] != result["upstream"]
        relation = _git(source, "merge-base", "--is-ancestor", result["head"], result["upstream"])
        result["fast_forward_possible"] = relation.returncode == 0
    return result


def apply_update() -> dict[str, Any]:
    status = update_status(fetch=True)
    if not status["source_available"] or not status["git_source"]:
        raise RuntimeError("installation source is unavailable or not a Git checkout; reinstall from a clone")
    source = Path(status["source_root"])
    dirty = _git(source, "status", "--porcelain")
    if dirty.stdout.strip():
        raise RuntimeError("installation source has uncommitted changes; refusing to update")
    if status.get("update_available"):
        if not status.get("fast_forward_possible"):
            raise RuntimeError("source cannot be fast-forwarded to upstream; update it manually")
        pull = _git(source, "pull", "--ff-only")
        if pull.returncode != 0:
            raise RuntimeError(pull.stderr.strip() or "git pull --ff-only failed")

    install = source / "install.sh"
    if not install.is_file():
        raise RuntimeError("install.sh not found in installation source")
    proc = subprocess.run([str(install)], cwd=source, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or "install.sh failed")
    return {
        "schema_version": "1",
        "document_type": "agentic.update-result",
        "success": True,
        "source_root": str(source),
        "before": status,
        "installer_stdout": proc.stdout,
    }
