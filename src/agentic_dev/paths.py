from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


NEW_CONFIG_ENV = "AGENTIC_DEV_CONFIG_DIR"
LEGACY_CONFIG_ENV = "AGENTIC_DEV_ENV_CONFIG_DIR"


def default_config_dir() -> Path:
    return Path.home() / ".config" / "agentic-dev"


def legacy_default_config_dir() -> Path:
    return Path.home() / ".config" / "agentic-dev-env"


def config_dir() -> Path:
    current = os.environ.get(NEW_CONFIG_ENV)
    if current:
        return Path(current).expanduser()
    legacy = os.environ.get(LEGACY_CONFIG_ENV)
    if legacy:
        return Path(legacy).expanduser()
    return default_config_dir()


def _copy_missing(source: Path, destination: Path, copied: list[str], skipped: list[str]) -> None:
    if source.is_dir():
        destination.mkdir(parents=True, exist_ok=True)
        for child in source.iterdir():
            _copy_missing(child, destination / child.name, copied, skipped)
        return
    if destination.exists():
        skipped.append(str(destination))
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    copied.append(str(destination))


def migrate_legacy_config() -> dict[str, Any]:
    """Copy legacy user state into the new config root without deleting or overwriting.

    Explicit config environment variables are treated as authoritative and are never migrated.
    The old embedded Python copy and policy template are intentionally skipped because the
    current package/install supplies those files.
    """

    if os.environ.get(NEW_CONFIG_ENV):
        return {"performed": False, "reason": f"{NEW_CONFIG_ENV} is explicitly set"}
    if os.environ.get(LEGACY_CONFIG_ENV):
        return {
            "performed": False,
            "reason": f"{LEGACY_CONFIG_ENV} is explicitly set and remains supported",
        }

    source = legacy_default_config_dir()
    destination = default_config_dir()
    marker = destination / ".migration-from-agentic-dev-env-v1.json"

    if marker.exists():
        try:
            previous = json.loads(marker.read_text())
        except (OSError, json.JSONDecodeError):
            previous = {}
        return {"performed": False, "reason": "migration already recorded", **previous}

    if not source.exists():
        return {"performed": False, "reason": "no legacy config found"}

    destination.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    skipped: list[str] = []

    for child in source.iterdir():
        if child.name in {"python", "templates"}:
            skipped.append(str(child))
            continue
        _copy_missing(child, destination / child.name, copied, skipped)

    result = {
        "performed": True,
        "source": str(source),
        "destination": str(destination),
        "copied": copied,
        "skipped": skipped,
        "legacy_source_preserved": True,
        "worktrees_moved": False,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    marker.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def prepare_runtime_state() -> dict[str, Any]:
    """Apply environment-variable compatibility and one-time default-state migration."""

    if NEW_CONFIG_ENV not in os.environ and LEGACY_CONFIG_ENV in os.environ:
        os.environ[NEW_CONFIG_ENV] = os.environ[LEGACY_CONFIG_ENV]
        return {
            "performed": False,
            "reason": f"using legacy {LEGACY_CONFIG_ENV} as {NEW_CONFIG_ENV}",
        }
    return migrate_legacy_config()
