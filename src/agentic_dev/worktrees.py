from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .detect import repo_root
from .metrics import record as record_metric


def _run(argv: list[str], *, cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, cwd=cwd, capture_output=True, text=True, check=check)


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-")
    if not slug:
        raise ValueError("worktree name must contain at least one usable character")
    return slug


def default_root(repo: Path) -> Path:
    base = os.environ.get("AGENTIC_WORKTREE_ROOT")
    if base:
        return Path(base).expanduser().resolve() / repo.name
    return Path.home() / ".local" / "share" / "agentic-dev-env" / "worktrees" / repo.name


def _exclude_local(root: Path, entry: str) -> None:
    try:
        raw = _run(["git", "-C", str(root), "rev-parse", "--git-path", "info/exclude"]).stdout.strip()
    except subprocess.CalledProcessError:
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


def _session_file(worktree: Path) -> Path:
    return worktree / ".agentic" / "session.json"


def _write_session(worktree: Path, data: dict[str, Any]) -> None:
    path = _session_file(worktree)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    _exclude_local(worktree, "/.agentic/")


def _read_session(worktree: Path) -> dict[str, Any] | None:
    path = _session_file(worktree)
    try:
        return json.loads(path.read_text()) if path.exists() else None
    except (OSError, json.JSONDecodeError):
        return None


def _porcelain(repo: Path) -> list[dict[str, Any]]:
    result = _run(["git", "-C", str(repo), "worktree", "list", "--porcelain"])
    entries: list[dict[str, Any]] = []
    current: dict[str, Any] = {}
    for raw in result.stdout.splitlines() + [""]:
        line = raw.strip()
        if not line:
            if current:
                path = Path(current["worktree"])
                current["session"] = _read_session(path)
                current["dirty"] = bool(_run(
                    ["git", "-C", str(path), "status", "--porcelain"],
                    check=False,
                ).stdout.strip())
                entries.append(current)
                current = {}
            continue
        key, _, value = line.partition(" ")
        if key == "worktree":
            current["worktree"] = value
        elif key == "HEAD":
            current["head"] = value
        elif key == "branch":
            current["branch"] = value.removeprefix("refs/heads/")
        elif key in {"bare", "detached", "locked", "prunable"}:
            current[key] = value or True
    return entries


def list_worktrees(path: str | Path = ".") -> dict[str, Any]:
    repo = repo_root(path)
    return {
        "schema_version": "1",
        "document_type": "agentic.worktrees",
        "repository": str(repo),
        "worktrees": _porcelain(repo),
    }


def create_worktree(
    name: str,
    path: str | Path = ".",
    *,
    branch: str | None = None,
    base: str = "HEAD",
    agent: str | None = None,
    task: str | None = None,
    worktree_root: str | Path | None = None,
) -> dict[str, Any]:
    repo = repo_root(path)
    slug = _slug(name)
    branch_name = branch or f"agentic/{slug}"
    root = Path(worktree_root).expanduser().resolve() if worktree_root else default_root(repo)
    target = root / slug

    existing = _porcelain(repo)
    if any(Path(item["worktree"]).resolve() == target.resolve() for item in existing):
        raise FileExistsError(f"worktree path already exists: {target}")
    if _run(["git", "-C", str(repo), "show-ref", "--verify", "--quiet", f"refs/heads/{branch_name}"], check=False).returncode == 0:
        raise FileExistsError(f"branch already exists: {branch_name}")

    root.mkdir(parents=True, exist_ok=True)
    _run(["git", "-C", str(repo), "worktree", "add", "-b", branch_name, str(target), base])

    session = {
        "schema_version": "1",
        "name": slug,
        "branch": branch_name,
        "base": base,
        "agent": agent,
        "task": task,
        "repository": str(repo),
        "worktree": str(target),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _write_session(target, session)
    record_metric(
        "session.started",
        {
            "agent": agent or "unspecified",
            "has_task": bool(task),
            "branch_prefix": branch_name.split("/", 1)[0] if "/" in branch_name else "",
        },
        repository=repo,
        session_id=slug,
    )

    return {
        "schema_version": "1",
        "document_type": "agentic.worktree",
        "repository": str(repo),
        "worktree": str(target),
        "branch": branch_name,
        "session": session,
    }


def _resolve_worktree(repo: Path, name_or_path: str) -> dict[str, Any]:
    candidate = Path(name_or_path).expanduser()
    entries = _porcelain(repo)
    for item in entries:
        path = Path(item["worktree"])
        session = item.get("session") or {}
        if (
            path.resolve() == candidate.resolve() if candidate.is_absolute() else False
        ) or path.name == name_or_path or session.get("name") == name_or_path:
            return item
    raise KeyError(f"unknown worktree: {name_or_path}")


def worktree_status(name_or_path: str, path: str | Path = ".") -> dict[str, Any]:
    repo = repo_root(path)
    item = _resolve_worktree(repo, name_or_path)
    return {
        "schema_version": "1",
        "document_type": "agentic.worktree-status",
        "repository": str(repo),
        **item,
    }


def clean_worktree(
    name_or_path: str,
    path: str | Path = ".",
    *,
    force: bool = False,
    delete_branch: bool = False,
) -> dict[str, Any]:
    repo = repo_root(path)
    item = _resolve_worktree(repo, name_or_path)
    worktree = Path(item["worktree"]).resolve()
    main = repo.resolve()
    if worktree == main:
        raise ValueError("refusing to remove the primary worktree")
    if item.get("dirty") and not force:
        raise RuntimeError("worktree has uncommitted changes; use --force to remove it")

    branch = item.get("branch")
    argv = ["git", "-C", str(repo), "worktree", "remove"]
    if force:
        argv.append("--force")
    argv.append(str(worktree))
    _run(argv)

    deleted_branch = False
    if delete_branch and branch:
        result = _run(["git", "-C", str(repo), "branch", "-D" if force else "-d", branch], check=False)
        deleted_branch = result.returncode == 0

    _run(["git", "-C", str(repo), "worktree", "prune"], check=False)
    session = item.get("session") or {}
    record_metric(
        "session.ended",
        {
            "agent": session.get("agent") or "unspecified",
            "dirty_before_clean": bool(item.get("dirty")),
            "forced": force,
            "deleted_branch": deleted_branch,
        },
        repository=repo,
        session_id=session.get("name"),
    )
    return {
        "schema_version": "1",
        "document_type": "agentic.worktree-clean",
        "repository": str(repo),
        "worktree": str(worktree),
        "branch": branch,
        "deleted_branch": deleted_branch,
    }
