from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from . import __version__
from .detect import repo_root
from .trust import check as trust_check


SCHEMA_VERSION = "1"


def _config_dir() -> Path:
    return Path(os.environ.get(
        "AGENTIC_DEV_ENV_CONFIG_DIR",
        Path.home() / ".config" / "agentic-dev-env",
    ))


def _providers_dir() -> Path:
    return _config_dir() / "providers"


def _version_tuple(value: str) -> tuple[int, ...]:
    parts = []
    for token in value.split("."):
        digits = "".join(ch for ch in token if ch.isdigit())
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts or [0])


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_manifest(data: dict[str, Any], *, base_dir: Path | None = None) -> list[str]:
    errors: list[str] = []
    for field in ("schema_version", "name", "version", "description"):
        if not isinstance(data.get(field), str) or not data.get(field):
            errors.append(f"missing/invalid field: {field}")
    if isinstance(data.get("name"), str) and not re.fullmatch(r"[A-Za-z0-9._-]+", data["name"]):
        errors.append("provider name may contain only letters, digits, dot, underscore, and dash")
    if data.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"unsupported schema_version: {data.get('schema_version')}")

    compatibility = data.get("compatibility") or {}
    minimum = compatibility.get("agentic_min")
    maximum = compatibility.get("agentic_max")
    current = _version_tuple(__version__)
    if minimum and current < _version_tuple(str(minimum)):
        errors.append(f"requires agentic-dev-env >= {minimum}")
    if maximum and current > _version_tuple(str(maximum)):
        errors.append(f"requires agentic-dev-env <= {maximum}")
    platforms = compatibility.get("platforms") or []
    if platforms and platform.system().lower() not in {str(x).lower() for x in platforms}:
        errors.append(f"platform {platform.system()} not supported by provider")

    names: set[str] = set()
    for skill in data.get("skills") or []:
        name = skill.get("name")
        path = skill.get("path")
        if not name or not path:
            errors.append("provider skill requires name and path")
            continue
        if not re.fullmatch(r"[A-Za-z0-9._-]+", str(name)):
            errors.append(f"invalid provider skill name: {name}")
            continue
        if name in names:
            errors.append(f"duplicate provider item: {name}")
        names.add(name)
        if base_dir:
            target = (base_dir / str(path)).resolve()
            try:
                target.relative_to(base_dir.resolve())
            except ValueError:
                errors.append(f"skill path escapes provider root: {path}")
                continue
            if target.name != "SKILL.md":
                errors.append(f"provider skill path must point to SKILL.md: {path}")
            if not target.is_file():
                errors.append(f"skill file not found: {path}")
            expected = skill.get("sha256")
            if expected and target.is_file() and _sha256(target) != expected:
                errors.append(f"skill sha256 mismatch: {name}")

    for capability in data.get("capabilities") or []:
        name = capability.get("name")
        command = capability.get("command")
        if not name or not isinstance(command, list) or not command:
            errors.append("provider capability requires name and non-empty command array")
            continue
        if not re.fullmatch(r"[A-Za-z0-9._-]+", str(name)):
            errors.append(f"invalid provider capability name: {name}")
            continue
        if name in names:
            errors.append(f"duplicate provider item: {name}")
        names.add(name)
        if not all(isinstance(x, str) and x for x in command):
            errors.append(f"provider capability command must be string argv: {name}")

    metadata = data.get("metadata") or {}
    signature = metadata.get("signature")
    if signature is not None:
        if not isinstance(signature, dict) or signature.get("type") != "minisign":
            errors.append("metadata.signature currently supports only type=minisign")
        elif not signature.get("public_key") or not signature.get("file"):
            errors.append("minisign signature requires public_key and file")
        elif base_dir:
            sig_path = (base_dir / str(signature["file"])).resolve()
            try:
                sig_path.relative_to(base_dir.resolve())
            except ValueError:
                errors.append("signature file escapes provider root")
            else:
                if not sig_path.is_file():
                    errors.append(f"signature file not found: {signature['file']}")
    digest = metadata.get("manifest_sha256")
    if digest is not None and (not isinstance(digest, str) or len(digest) != 64):
        errors.append("metadata.manifest_sha256 must be a 64-character SHA-256 hex digest")
    return errors


def load_manifest(path: str | Path) -> tuple[dict[str, Any], Path]:
    manifest = Path(path).expanduser().resolve()
    data = json.loads(manifest.read_text())
    errors = validate_manifest(data, base_dir=manifest.parent)
    if errors:
        raise ValueError("; ".join(errors))
    return data, manifest


def _verify_signature(data: dict[str, Any], manifest: Path) -> bool:
    signature = (data.get("metadata") or {}).get("signature")
    if not signature:
        return False
    minisign = shutil.which("minisign")
    if not minisign:
        raise ValueError("provider declares a Minisign signature but minisign is not installed")
    sig_path = (manifest.parent / signature["file"]).resolve()
    result = subprocess.run(
        [
            minisign, "-Vm", str(manifest),
            "-P", str(signature["public_key"]),
            "-x", str(sig_path),
        ],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        raise ValueError("provider Minisign verification failed: " + (result.stderr or result.stdout).strip())
    return True


def add_provider(path: str | Path) -> dict[str, Any]:
    data, manifest = load_manifest(path)
    signed = _verify_signature(data, manifest)
    dest = _providers_dir() / data["name"]
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)

    # Copy only declared artifacts plus a normalized manifest. No provider code
    # is imported into the agentic-dev-env process.
    normalized = dict(data)
    for skill in normalized.get("skills") or []:
        source = (manifest.parent / skill["path"]).resolve()
        relative_dir = Path("skills") / skill["name"]
        target_dir = dest / relative_dir
        shutil.copytree(source.parent, target_dir)
        target = target_dir / "SKILL.md"
        relative = relative_dir / "SKILL.md"
        skill["path"] = relative.as_posix()
        skill["sha256"] = _sha256(target)

    normalized.setdefault("metadata", {})["source_manifest"] = str(manifest)
    normalized["metadata"]["installed_manifest_sha256"] = _sha256(manifest)
    normalized["metadata"]["signature_verified"] = signed
    signature = normalized["metadata"].get("signature")
    if signed and signature:
        source_sig = (manifest.parent / signature["file"]).resolve()
        target_sig = dest / "provenance" / "source-manifest.minisig"
        target_sig.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_sig, target_sig)
        signature["file"] = "provenance/source-manifest.minisig"
    (dest / "provider.json").write_text(json.dumps(normalized, indent=2, sort_keys=True) + "\n")

    return provider_document(data["name"])


def remove_provider(name: str) -> None:
    dest = _providers_dir() / name
    if not dest.exists():
        raise KeyError(f"unknown provider: {name}")
    shutil.rmtree(dest)


def installed_manifests() -> list[tuple[dict[str, Any], Path]]:
    result = []
    root = _providers_dir()
    if not root.exists():
        return result
    for manifest in sorted(root.glob("*/provider.json")):
        try:
            data = json.loads(manifest.read_text())
            if not validate_manifest(data, base_dir=manifest.parent):
                result.append((data, manifest))
        except (OSError, json.JSONDecodeError):
            continue
    return result


def provider_document(name: str | None = None) -> dict[str, Any]:
    providers = []
    for data, manifest in installed_manifests():
        if name and data["name"] != name:
            continue
        providers.append({
            "name": data["name"],
            "version": data["version"],
            "description": data["description"],
            "compatibility": data.get("compatibility") or {},
            "skills": [
                {
                    "name": item["name"],
                    "description": item.get("description", ""),
                    "category": item.get("category", "external"),
                    "sha256": item.get("sha256"),
                }
                for item in data.get("skills") or []
            ],
            "capabilities": [
                {
                    "name": item["name"],
                    "description": item.get("description", ""),
                    "category": item.get("category", "external"),
                    "required_permissions": item.get("required_permissions") or [],
                }
                for item in data.get("capabilities") or []
            ],
            "manifest": str(manifest),
            "signed": bool((data.get("metadata") or {}).get("signature_verified")),
        })
    if name and not providers:
        raise KeyError(f"unknown provider: {name}")
    return {
        "schema_version": "1",
        "document_type": "agentic.providers",
        "providers": providers,
    }


def external_skills() -> list[dict[str, Any]]:
    result = []
    for data, manifest in installed_manifests():
        for item in data.get("skills") or []:
            result.append({
                **item,
                "provider_name": data["name"],
                "provider_version": data["version"],
                "absolute_path": str((manifest.parent / item["path"]).resolve()),
            })
    return result


def find_external_skill(name: str) -> dict[str, Any] | None:
    matches = [x for x in external_skills() if x["name"] == name]
    if len(matches) > 1:
        providers = ", ".join(sorted(x["provider_name"] for x in matches))
        raise ValueError(f"external skill name is ambiguous ({providers}): {name}")
    return matches[0] if matches else None


def external_capabilities() -> list[dict[str, Any]]:
    result = []
    for data, manifest in installed_manifests():
        for item in data.get("capabilities") or []:
            result.append({
                **item,
                "provider_name": data["name"],
                "provider_version": data["version"],
                "manifest": str(manifest),
            })
    return result


def run_provider_capability(
    provider: str,
    capability: str,
    args: list[str],
    *,
    path: str | Path = ".",
    profile: str | None = None,
) -> dict[str, Any]:
    selected: dict[str, Any] | None = None
    for data, _manifest in installed_manifests():
        if data["name"] != provider:
            continue
        for item in data.get("capabilities") or []:
            if item["name"] == capability:
                selected = item
                break
    if selected is None:
        raise KeyError(f"unknown provider capability: {provider}/{capability}")

    required = selected.get("required_permissions") or []
    allowed, missing, trust = trust_check(required, profile_name=profile, root=path)
    if not allowed:
        raise PermissionError(
            f"trust profile '{trust.name}' missing permissions: {', '.join(missing)}"
        )

    root = repo_root(path)
    argv = [
        part.replace("{repo}", str(root))
        for part in selected["command"]
    ]
    argv.extend(args)
    binary = shutil.which(argv[0])
    if not binary:
        raise RuntimeError(f"provider command is not installed: {argv[0]}")
    argv[0] = binary
    completed = subprocess.run(
        argv, cwd=root, capture_output=True, text=True, check=False,
    )
    return {
        "schema_version": "1",
        "document_type": "agentic.provider-capability-result",
        "provider": provider,
        "capability": capability,
        "trust_profile": trust.name,
        "argv": argv,
        "success": completed.returncode == 0,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }
