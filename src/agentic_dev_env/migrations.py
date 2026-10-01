from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Callable


CURRENT_STATE_SCHEMA = 1


def _config_dir() -> Path:
    return Path(os.environ.get(
        "AGENTIC_DEV_ENV_CONFIG_DIR",
        Path.home() / ".config" / "agentic-dev-env",
    ))


def _state_file() -> Path:
    return _config_dir() / "state.json"


Migration = Callable[[Path], None]
MIGRATIONS: dict[int, Migration] = {}


def state() -> dict:
    path = _state_file()
    if not path.exists():
        return {"schema_version": 0}
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {"schema_version": 0}


def migrate() -> dict:
    current = state()
    from_version = int(current.get("schema_version", 0))
    applied: list[int] = []
    for target in range(from_version + 1, CURRENT_STATE_SCHEMA + 1):
        hook = MIGRATIONS.get(target)
        if hook:
            hook(_config_dir())
        applied.append(target)

    result = {
        "schema_version": CURRENT_STATE_SCHEMA,
        "previous_schema_version": from_version,
        "applied": applied,
    }
    path = _state_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result
