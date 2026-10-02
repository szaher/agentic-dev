from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Iterable

from . import __version__


MANIFEST = "agentic-provider.json"


def _config_dir() -> Path:
    return Path(os.environ.get(
        "AGENTIC_DEV_CONFIG_DIR",
        Path.home() / ".config" / "agentic-dev",
    ))


def providers_dir() -> Path:
    return _config_dir() / "providers"


def _registry_file() -> Path:
    return _config_dir() / "providers.json"


def _load_registry() -> dict[str, Any]:
    path = _registry_file()
    if not path.exists():
        return {"providers": {}}
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {"providers": {}}


def _save_registry(data: dict[str, Any]) -> None:
    path = _registry_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def _version_tuple(value: str) -> tuple[int, ...]:
    nums = re.findall(r"\d+", value)
    return tuple(int(x) for x in nums[:3]) or (0,)


def _compatible(spec: str | None, current: str = __version__) -> bool:
    if not spec:
        return True
    cur = _version_tuple(current)
    for raw in spec.split(","):
        rule = raw.strip()
        if not rule:
            continue
        op = next((x for x in (">=", "<=", "==", ">", "<") if rule.startswith(x)), None)
        if not op:
            raise ValueError(f"unsupported compatibility rule: {rule}")
        wanted = _version_tuple(rule[len(op):].strip())
        if op == ">=" and not (cur >= wanted):
            return False
        if op == "<=" and not (cur <= wanted):
            return False
        if op == "==" and not (cur == wanted):
            return False
        if op == ">" and not (cur > wanted):
            return False
        if op == "<" and not (cur < wanted):
            return False
    return True


def platform_id() -> str:
    system = platform.system().lower()
    if system == "linux":
        try:
            if "microsoft" in Path("/proc/version").read_text(errors="ignore").lower():
                return "wsl"
        except OSError:
            pass
    return {"darwin": "macos", "windows": "windows"}.get(system, system)


def _tree_digest(root: Path) -> str:
    h = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file() and ".git" not in p.parts):
        rel = path.relative_to(root).as_posix().encode()
        h.update(len(rel).to_bytes(8, "big"))
        h.update(rel)
        data = path.read_bytes()
        h.update(len(data).to_bytes(8, "big"))
        h.update(data)
    return h.hexdigest()


def _manifest(path: Path) -> dict[str, Any]:
    file = path / MANIFEST
    if not file.exists():
        raise ValueError(f"provider source missing {MANIFEST}: {path}")
    try:
        data = json.loads(file.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid provider manifest: {exc}") from exc
    required = ("schema_version", "name", "version", "description")
    missing = [key for key in required if not data.get(key)]
    if missing:
        raise ValueError("provider manifest missing: " + ", ".join(missing))
    if data["schema_version"] != "1":
        raise ValueError(f"unsupported provider schema: {data['schema_version']}")
    compat = data.get("compatibility") or {}
    if not _compatible(compat.get("agentic")):
        raise ValueError(
            f"provider {data['name']} {data['version']} is incompatible with agentic {__version__}"
        )
    platforms = compat.get("platforms") or []
    if platforms and platform_id() not in platforms:
        raise ValueError(
            f"provider {data['name']} does not support platform {platform_id()}; supports {platforms}"
        )
    for entry in data.get("skills") or []:
        for key in ("name", "description", "category", "path"):
            if not entry.get(key):
                raise ValueError(f"provider skill missing {key}")
        if Path(entry["path"]).is_absolute() or ".." in Path(entry["path"]).parts:
            raise ValueError("provider skill path must stay inside provider source")
    for entry in data.get("capabilities") or []:
        for key in ("name", "category", "provider", "description", "risk"):
            if not entry.get(key):
                raise ValueError(f"provider capability missing {key}")
        command = entry.get("command")
        if command is not None and (not isinstance(command, list) or not command):
            raise ValueError("provider capability command must be a non-empty argv list")
    return data


def _run(argv: list[str], *, cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, cwd=cwd, capture_output=True, text=True, check=check)


def _copy_source(source: Path, destination: Path) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination, ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"))


def _prepare_source(source: str, ref: str | None) -> tuple[Path, dict[str, Any]]:
    candidate = Path(source).expanduser()
    if candidate.exists():
        root = candidate.resolve()
        return root, {
            "source_type": "local",
            "source": str(root),
            "ref": None,
            "commit_sha": None,
            "signed_commit": None,
        }

    if shutil.which("git") is None:
        raise RuntimeError("git is required for remote providers")
    temp = Path(tempfile.mkdtemp(prefix="agentic-provider-"))
    argv = ["git", "clone", "--filter=blob:none", "--depth", "1"]
    if ref:
        argv += ["--branch", ref]
    argv += [source, str(temp)]
    result = _run(argv, check=False)
    if result.returncode != 0:
        shutil.rmtree(temp, ignore_errors=True)
        raise RuntimeError(result.stderr.strip() or "git clone failed")
    commit = _run(["git", "-C", str(temp), "rev-parse", "HEAD"]).stdout.strip()
    signature = _run(
        ["git", "-C", str(temp), "log", "-1", "--format=%G?"],
        check=False,
    ).stdout.strip() or "N"
    return temp, {
        "source_type": "git",
        "source": source,
        "ref": ref,
        "commit_sha": commit,
        "signed_commit": signature in {"G", "U"},
        "signature_status": signature,
    }


def add_provider(
    source: str,
    *,
    ref: str | None = None,
    expected_sha256: str | None = None,
    require_signed_commit: bool = False,
) -> dict[str, Any]:
    prepared, source_meta = _prepare_source(source, ref)
    cleanup = source_meta["source_type"] == "git"
    try:
        manifest = _manifest(prepared)
        digest = _tree_digest(prepared)
        if expected_sha256 and digest.lower() != expected_sha256.lower():
            raise ValueError(f"provider digest mismatch: expected {expected_sha256}, got {digest}")
        if require_signed_commit:
            if source_meta["source_type"] != "git":
                raise ValueError("--require-signed-commit requires a Git provider")
            if not source_meta.get("signed_commit"):
                raise ValueError(
                    f"provider commit is not verified by git; signature status={source_meta.get('signature_status')}"
                )

        name = manifest["name"]
        destination = providers_dir() / name / "source"
        destination.parent.mkdir(parents=True, exist_ok=True)
        _copy_source(prepared, destination)

        record = {
            "name": name,
            "version": manifest["version"],
            "description": manifest["description"],
            "manifest_digest": hashlib.sha256((destination / MANIFEST).read_bytes()).hexdigest(),
            "content_digest": digest,
            "compatibility": manifest.get("compatibility") or {},
            **source_meta,
        }
        registry = _load_registry()
        registry.setdefault("providers", {})[name] = record
        _save_registry(registry)
        return record
    finally:
        if cleanup:
            shutil.rmtree(prepared, ignore_errors=True)


def remove_provider(name: str) -> None:
    registry = _load_registry()
    if name not in registry.get("providers", {}):
        raise KeyError(name)
    shutil.rmtree(providers_dir() / name, ignore_errors=True)
    registry["providers"].pop(name, None)
    _save_registry(registry)


def installed() -> list[dict[str, Any]]:
    registry = _load_registry()
    result = []
    for name, record in sorted((registry.get("providers") or {}).items()):
        root = providers_dir() / name / "source"
        item = dict(record)
        item["installed"] = root.exists()
        item["verified"] = root.exists() and _tree_digest(root) == record.get("content_digest")
        try:
            manifest = _manifest(root) if root.exists() else {}
            item["manifest_version"] = manifest.get("version")
            item["compatible"] = bool(manifest)
        except Exception as exc:
            item["compatible"] = False
            item["error"] = str(exc)
        result.append(item)
    return result


def verify_provider(name: str) -> dict[str, Any]:
    registry = _load_registry()
    record = (registry.get("providers") or {}).get(name)
    if not record:
        raise KeyError(name)
    root = providers_dir() / name / "source"
    if not root.exists():
        return {"name": name, "valid": False, "reason": "source directory missing"}
    manifest = _manifest(root)
    digest = _tree_digest(root)
    manifest_digest = hashlib.sha256((root / MANIFEST).read_bytes()).hexdigest()
    reasons: list[str] = []
    if digest != record.get("content_digest"):
        reasons.append("content digest changed")
    if manifest_digest != record.get("manifest_digest"):
        reasons.append("manifest digest changed")
    if manifest.get("version") != record.get("version"):
        reasons.append("manifest version differs from registry")
    return {
        "name": name,
        "valid": not reasons,
        "reasons": reasons,
        "version": manifest.get("version"),
        "content_digest": digest,
        "expected_content_digest": record.get("content_digest"),
    }


def _provider_root(name: str) -> Path:
    return providers_dir() / name / "source"


def manifests() -> list[tuple[dict[str, Any], Path]]:
    result = []
    for record in installed():
        if not record.get("installed") or not record.get("verified"):
            continue
        root = _provider_root(record["name"])
        try:
            result.append((_manifest(root), root))
        except ValueError:
            continue
    return result


def skill_entries() -> list[tuple[dict[str, Any], Path, str]]:
    result = []
    for manifest, root in manifests():
        for entry in manifest.get("skills") or []:
            result.append((entry, root, manifest["name"]))
    return result


def capability_entries() -> list[tuple[dict[str, Any], Path, str]]:
    result = []
    for manifest, root in manifests():
        for entry in manifest.get("capabilities") or []:
            result.append((entry, root, manifest["name"]))
    return result


def provider_capability_command(name: str) -> tuple[list[str], Path, str] | None:
    for entry, root, provider_name in capability_entries():
        if entry["name"] == name and entry.get("command"):
            return [str(x) for x in entry["command"]], root, provider_name
    return None


def pending_migrations(name: str) -> list[dict[str, Any]]:
    registry = _load_registry()
    record = (registry.get("providers") or {}).get(name)
    if not record:
        raise KeyError(name)
    manifest = _manifest(_provider_root(name))
    current = record.get("migration_version", "0")
    return [
        item for item in (manifest.get("migrations") or [])
        if _version_tuple(str(item.get("version", "0"))) > _version_tuple(str(current))
    ]


def migrate(name: str, *, yes: bool = False) -> list[dict[str, Any]]:
    if not yes:
        raise PermissionError("provider migration hooks require explicit --yes")
    pending = pending_migrations(name)
    root = _provider_root(name)
    completed = []
    for item in pending:
        command = item.get("command")
        if not isinstance(command, list) or not command:
            raise ValueError("provider migration command must be a non-empty argv list")
        before_digest = _tree_digest(root)
        state_dir = providers_dir() / name / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        env["AGENTIC_PROVIDER_ROOT"] = str(root)
        env["AGENTIC_PROVIDER_STATE_DIR"] = str(state_dir)
        result = subprocess.run(
            [str(x) for x in command],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
        source_changed = _tree_digest(root) != before_digest
        if source_changed and result.returncode == 0:
            result = subprocess.CompletedProcess(
                result.args, 70, result.stdout,
                result.stderr + "\nprovider migration modified immutable provider source",
            )
        completed.append({
            "version": str(item["version"]),
            "command": command,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        })
        if result.returncode != 0:
            break
        registry = _load_registry()
        registry["providers"][name]["migration_version"] = str(item["version"])
        _save_registry(registry)
    return completed


def update_provider(
    name: str,
    *,
    yes: bool = False,
    require_signed_commit: bool | None = None,
) -> dict[str, Any]:
    if not yes:
        raise PermissionError("provider updates require explicit --yes")
    registry = _load_registry()
    record = (registry.get("providers") or {}).get(name)
    if not record:
        raise KeyError(name)
    source = record["source"]
    ref = record.get("ref")
    signed = bool(require_signed_commit) if require_signed_commit is not None else bool(record.get("signed_commit"))
    previous = dict(record)
    updated = add_provider(
        source,
        ref=ref,
        require_signed_commit=signed,
    )
    updated["previous_version"] = previous.get("version")
    updated["changed"] = updated.get("content_digest") != previous.get("content_digest")
    return updated


def update_all(*, yes: bool = False) -> list[dict[str, Any]]:
    return [update_provider(item["name"], yes=yes) for item in installed()]


def doctor() -> dict[str, Any]:
    provider_status = []
    for record in installed():
        root = _provider_root(record["name"])
        manifest: dict[str, Any] = {}
        try:
            manifest = _manifest(root)
        except Exception as exc:
            provider_status.append({**record, "requirements_ok": False, "error": str(exc)})
            continue
        req = manifest.get("requires") or {}
        executables = {
            name: bool(shutil.which(name))
            for name in req.get("executables") or []
        }
        agents = {
            name: bool(shutil.which(name))
            for name in req.get("agents") or []
        }
        provider_status.append({
            **record,
            "requirements": {"executables": executables, "agents": agents},
            "requirements_ok": all(executables.values()) and all(agents.values()),
        })
    return {
        "schema_version": "1",
        "document_type": "agentic.providers",
        "platform": platform_id(),
        "agentic_version": __version__,
        "providers": provider_status,
    }


def source_metadata(name: str) -> dict[str, Any]:
    registry = _load_registry()
    record = (registry.get("providers") or {}).get(name)
    if not record:
        raise KeyError(name)
    return dict(record)
