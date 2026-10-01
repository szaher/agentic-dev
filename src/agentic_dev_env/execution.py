from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .detect import repo_root
from .trust import check as trust_check


BACKENDS = ("host", "container", "devcontainer", "dagger")


def _config_dir() -> Path:
    return Path(os.environ.get(
        "AGENTIC_DEV_ENV_CONFIG_DIR",
        Path.home() / ".config" / "agentic-dev-env",
    ))


def _user_file() -> Path:
    return _config_dir() / "execution.json"


def _repo_file(root: Path) -> Path:
    return root / ".agentic" / "execution.json"


def _read(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text()) if path.exists() else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def _exclude_local(root: Path) -> None:
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
    if "/.agentic/" not in lines:
        with path.open("a") as handle:
            if lines:
                handle.write("\n")
            handle.write("/.agentic/\n")


def available_backends() -> dict[str, dict[str, Any]]:
    container = shutil.which("docker") or shutil.which("podman")
    return {
        "host": {"available": True, "binary": None},
        "container": {
            "available": bool(container),
            "binary": container,
            "engine": Path(container).name if container else None,
        },
        "devcontainer": {
            "available": bool(shutil.which("devcontainer")),
            "binary": shutil.which("devcontainer"),
        },
        "dagger": {
            "available": bool(shutil.which("dagger")),
            "binary": shutil.which("dagger"),
        },
    }


def _merged_config(root: Path) -> dict[str, Any]:
    user = _read(_user_file())
    repo = _read(_repo_file(root))
    merged = {
        "backend": user.get("backend", "host"),
        "image": user.get("image"),
        "network": user.get("network", "none"),
    }
    for key in ("backend", "image", "network"):
        if key in repo:
            merged[key] = repo[key]
    return merged


def configure(
    *,
    backend: str,
    path: str | Path = ".",
    image: str | None = None,
    network: str = "none",
    repo_scope: bool = False,
) -> dict[str, Any]:
    if backend not in BACKENDS:
        raise ValueError(f"unknown backend: {backend}")
    if network not in {"none", "default"}:
        raise ValueError("network must be 'none' or 'default'")
    if backend in {"container", "dagger"} and not image:
        raise ValueError(f"{backend} backend requires --image")

    root = repo_root(path)
    target = _repo_file(root) if repo_scope else _user_file()
    data = _read(target)
    data.update({
        "backend": backend,
        "image": image,
        "network": network,
    })
    _write(target, data)
    if repo_scope:
        _exclude_local(root)
    return {
        "schema_version": "1",
        "document_type": "agentic.execution-config",
        "scope": "repository" if repo_scope else "user",
        "repository": str(root),
        **data,
    }


def status(path: str | Path = ".") -> dict[str, Any]:
    root = repo_root(path)
    config = _merged_config(root)
    return {
        "schema_version": "1",
        "document_type": "agentic.execution-status",
        "repository": str(root),
        "selected": config,
        "backends": available_backends(),
    }


def _permissions(backend: str, network: str) -> tuple[str, ...]:
    required: list[str] = []
    if backend in {"container", "devcontainer", "dagger"}:
        required.append("container.run")
    if network == "default" or backend in {"devcontainer", "dagger"}:
        required.append("network.general")
    return tuple(sorted(set(required)))


def _resolve(
    root: Path,
    *,
    backend: str | None,
    image: str | None,
    network: str | None,
) -> tuple[str, str | None, str]:
    config = _merged_config(root)
    selected = backend or str(config.get("backend") or "host")
    selected_image = image if image is not None else config.get("image")
    selected_network = network or str(config.get("network") or "none")
    if selected not in BACKENDS:
        raise ValueError(f"unknown backend: {selected}")
    if selected_network not in {"none", "default"}:
        raise ValueError("network must be 'none' or 'default'")
    if selected in {"container", "dagger"} and not selected_image:
        raise ValueError(f"{selected} backend requires an image")
    return selected, selected_image, selected_network


def _result(
    *,
    backend: str,
    command: str,
    root: Path,
    argv: list[str],
    completed: subprocess.CompletedProcess[str],
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": "1",
        "document_type": "agentic.execution-result",
        "backend": backend,
        "repository": str(root),
        "command": command,
        "argv": argv,
        "success": completed.returncode == 0,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "metadata": metadata or {},
    }


def run(
    command: str,
    path: str | Path = ".",
    *,
    backend: str | None = None,
    image: str | None = None,
    network: str | None = None,
    profile: str | None = None,
) -> dict[str, Any]:
    root = repo_root(path)
    selected, selected_image, selected_network = _resolve(
        root, backend=backend, image=image, network=network,
    )
    allowed, missing, trust = trust_check(
        _permissions(selected, selected_network),
        profile_name=profile,
        root=root,
    )
    if not allowed:
        raise PermissionError(
            f"trust profile '{trust.name}' missing permissions: {', '.join(missing)}"
        )

    if selected == "host":
        completed = subprocess.run(
            command,
            cwd=root,
            shell=True,
            capture_output=True,
            text=True,
            check=False,
        )
        return _result(
            backend=selected, command=command, root=root,
            argv=["sh", "-lc", command], completed=completed,
            metadata={"trust_profile": trust.name, "network": "host"},
        )

    if selected == "container":
        engine = shutil.which("docker") or shutil.which("podman")
        if not engine:
            raise RuntimeError("container backend requires Docker or Podman")
        argv = [
            engine, "run", "--rm",
            "-v", f"{root}:/workspace",
            "-w", "/workspace",
        ]
        if selected_network == "none":
            argv += ["--network", "none"]
        argv += [str(selected_image), "sh", "-lc", command]
        completed = subprocess.run(argv, capture_output=True, text=True, check=False)
        return _result(
            backend=selected, command=command, root=root,
            argv=argv, completed=completed,
            metadata={
                "engine": Path(engine).name,
                "image": selected_image,
                "network": selected_network,
                "trust_profile": trust.name,
            },
        )

    if selected == "devcontainer":
        binary = shutil.which("devcontainer")
        if not binary:
            raise RuntimeError("devcontainer backend requires the Dev Container CLI")
        if not (root / ".devcontainer").exists() and not (root / ".devcontainer.json").exists():
            raise RuntimeError("no devcontainer configuration detected")
        up = [binary, "up", "--workspace-folder", str(root)]
        up_result = subprocess.run(up, capture_output=True, text=True, check=False)
        if up_result.returncode != 0:
            return _result(
                backend=selected, command=command, root=root,
                argv=up, completed=up_result,
                metadata={"phase": "up", "trust_profile": trust.name},
            )
        argv = [
            binary, "exec", "--workspace-folder", str(root),
            "sh", "-lc", command,
        ]
        completed = subprocess.run(argv, capture_output=True, text=True, check=False)
        return _result(
            backend=selected, command=command, root=root,
            argv=argv, completed=completed,
            metadata={
                "phase": "exec",
                "network": "devcontainer-configured",
                "trust_profile": trust.name,
            },
        )

    if selected == "dagger":
        binary = shutil.which("dagger")
        if not binary:
            raise RuntimeError("dagger backend requires the Dagger CLI")
        argv = [
            binary,
            "--workspace", str(root),
            "workspace", "exec",
            "--no-apply",
            f"--from={selected_image}",
            "--", "sh", "-lc", command,
        ]
        completed = subprocess.run(argv, capture_output=True, text=True, check=False)
        return _result(
            backend=selected, command=command, root=root,
            argv=argv, completed=completed,
            metadata={
                "image": selected_image,
                "apply": False,
                "network": "dagger-managed",
                "trust_profile": trust.name,
            },
        )

    raise AssertionError(selected)
