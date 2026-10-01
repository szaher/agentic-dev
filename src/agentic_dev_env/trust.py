from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class TrustProfile:
    name: str
    description: str
    permissions: frozenset[str]


BUILTIN_PROFILES: dict[str, TrustProfile] = {
    "safe": TrustProfile(
        "safe",
        "Local development with low-risk read/isolated capabilities.",
        frozenset({
            "repo.read",
            "network.docs",
            "browser.isolated",
            "security.scan",
            "secret.scan",
        }),
    ),
    "development": TrustProfile(
        "development",
        "Normal development access, including local writes and authenticated dev tooling.",
        frozenset({
            "repo.read", "repo.write",
            "network.docs", "network.general",
            "browser.isolated", "browser.persistent", "browser.authenticated",
            "security.scan", "secret.scan",
            "container.run",
            "database.local", "database.read", "database.write",
            "cluster.read",
            "observability.read",
            "remote.read",
        }),
    ),
    "production-read": TrustProfile(
        "production-read",
        "Read-only production investigation profile.",
        frozenset({
            "repo.read",
            "network.docs", "network.general",
            "browser.isolated",
            "security.scan", "secret.scan",
            "database.read",
            "cluster.read",
            "cloud.read",
            "observability.read",
            "remote.read",
        }),
    ),
}


def _config_dir() -> Path:
    return Path(os.environ.get(
        "AGENTIC_DEV_ENV_CONFIG_DIR",
        Path.home() / ".config" / "agentic-dev-env",
    ))


def _user_file() -> Path:
    return _config_dir() / "trust.json"


def _repo_file(root: Path) -> Path:
    return root / ".agentic" / "trust.json"


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text()) if path.exists() else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def _custom_profiles() -> dict[str, TrustProfile]:
    data = _load_json(_user_file())
    profiles: dict[str, TrustProfile] = {}
    for name, item in (data.get("profiles") or {}).items():
        profiles[name] = TrustProfile(
            name,
            item.get("description") or "Custom trust profile.",
            frozenset(item.get("permissions") or []),
        )
    return profiles


def profiles() -> dict[str, TrustProfile]:
    result = dict(BUILTIN_PROFILES)
    result.update(_custom_profiles())
    return result


def get_profile(name: str) -> TrustProfile:
    try:
        return profiles()[name]
    except KeyError as exc:
        raise KeyError(f"unknown trust profile: {name}") from exc


def current_profile_name(root: str | Path | None = None) -> str:
    if root is not None:
        repo = _load_json(_repo_file(Path(root).resolve()))
        if repo.get("profile"):
            return str(repo["profile"])
    user = _load_json(_user_file())
    return str(user.get("current_profile") or "safe")


def current_profile(root: str | Path | None = None) -> TrustProfile:
    return get_profile(current_profile_name(root))


def _exclude_local(root: Path, entry: str) -> None:
    try:
        raw = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--git-path", "info/exclude"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return
    path = Path(raw)
    if not path.is_absolute():
        path = root / path
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = path.read_text().splitlines() if path.exists() else []
    if entry not in lines:
        with path.open("a") as handle:
            if lines:
                handle.write("\n")
            handle.write(entry + "\n")


def set_current(name: str, root: str | Path | None = None) -> None:
    get_profile(name)
    if root is None:
        data = _load_json(_user_file())
        data["current_profile"] = name
        _save_json(_user_file(), data)
        return
    repo_root = Path(root).resolve()
    path = _repo_file(repo_root)
    data = _load_json(path)
    data["profile"] = name
    _save_json(path, data)
    _exclude_local(repo_root, "/.agentic/")


def define_profile(name: str, permissions: Iterable[str], description: str = "") -> None:
    if name in BUILTIN_PROFILES:
        raise ValueError(f"cannot overwrite built-in profile: {name}")
    perms = sorted(set(permissions))
    if not perms:
        raise ValueError("custom profile requires at least one permission")
    data = _load_json(_user_file())
    data.setdefault("profiles", {})[name] = {
        "description": description or "Custom trust profile.",
        "permissions": perms,
    }
    _save_json(_user_file(), data)


def check(required: Iterable[str], *, profile_name: str | None = None, root: str | Path | None = None) -> tuple[bool, list[str], TrustProfile]:
    profile = get_profile(profile_name) if profile_name else current_profile(root)
    required_set = set(required)
    missing = sorted(required_set - set(profile.permissions))
    return (not missing, missing, profile)


def document(root: str | Path | None = None) -> dict:
    selected = current_profile_name(root)
    return {
        "schema_version": "1",
        "document_type": "agentic.trust",
        "current_profile": selected,
        "profiles": {
            name: {
                "description": profile.description,
                "permissions": sorted(profile.permissions),
                "selected": name == selected,
                "builtin": name in BUILTIN_PROFILES,
            }
            for name, profile in sorted(profiles().items())
        },
    }
