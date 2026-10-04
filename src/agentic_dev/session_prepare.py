"""Revalidate an approved session plan and prepare only its supplied worktree."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any

from . import __version__, contracts, skills
from .detect import repo_root
from .session import _digest, load_profile, plan_session, validate_request


class InvalidPlanError(ValueError):
    """The plan or supplied workspace cannot be trusted for preparation."""


class StalePlanError(ValueError):
    """The approved plan no longer describes the current inputs."""


class BlockedPlanError(ValueError):
    """A plan with blockers cannot be prepared."""


class DirtyWorkspaceError(ValueError):
    """The supplied worktree has unapproved tracked or untracked changes."""


class PlacementError(ValueError):
    """A selected skill cannot be placed without replacing other workspace state."""


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"},
    )
    if result.returncode:
        raise InvalidPlanError(
            f"workspace Git inspection failed: {result.stderr.strip()}"
        )
    return result.stdout.strip()


def _common_dir(root: Path) -> Path:
    value = Path(_git(root, "rev-parse", "--git-common-dir"))
    return (value if value.is_absolute() else root / value).resolve()


def _require_clean_workspace(workspace: Path) -> None:
    changes = _git(workspace, "status", "--porcelain=v1", "--untracked-files=all")
    if changes:
        raise DirtyWorkspaceError(
            "SESSION_WORKSPACE_DIRTY: supplied worktree has tracked or untracked changes"
        )


def _workspace(plan: dict, path: str | Path) -> Path:
    try:
        workspace = repo_root(path)
        source = repo_root(plan["repository"])
    except (KeyError, OSError, ValueError) as exc:
        raise InvalidPlanError(f"invalid plan repository or workspace: {exc}") from exc
    if Path(path).resolve() != workspace:
        raise InvalidPlanError("--path must name the root of the supplied worktree")
    if source == workspace:
        raise InvalidPlanError(
            "--path must be a separate worktree, not the planning checkout"
        )
    if _common_dir(source) != _common_dir(workspace):
        raise InvalidPlanError("workspace is not a worktree of the plan repository")
    return workspace


def _verify_plan(plan: Any) -> dict:
    if not isinstance(plan, dict):
        raise InvalidPlanError("session plan must be a JSON object")
    if (
        plan.get("schema_version") != "1"
        or plan.get("document_type") != "agentic.session-plan"
    ):
        raise InvalidPlanError("expected agentic.session-plan@1")
    try:
        request = validate_request(plan["request"])
        if request != plan["request"] or _digest(request) != plan["request_digest"]:
            raise InvalidPlanError("plan request does not match request_digest")
        semantic = {
            key: value
            for key, value in plan.items()
            if key not in {"repository", "plan_digest"}
        }
        if _digest(semantic) != plan["plan_digest"]:
            raise InvalidPlanError("plan content does not match plan_digest")
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, InvalidPlanError):
            raise
        raise InvalidPlanError(f"invalid session plan: {exc}") from exc
    return request


def _skill_targets(workspace: Path, plan: dict) -> list[tuple[str, str, Path, str]]:
    targets = []
    harnesses = sorted({item["harness"] for item in plan["invocations"]})
    for skill in plan["skills"]["selected"]:
        name = skill["name"]
        if Path(name).name != name or name in {".", ".."}:
            raise InvalidPlanError(f"unsafe skill name in plan: {name!r}")
        content = skills.skill_content(name)
        if hashlib.sha256(content.encode()).hexdigest() != skill["content_digest"]:
            raise StalePlanError(f"selected skill content changed: {name}")
        for harness in harnesses:
            if harness not in skills.SKILL_DIRS:
                raise InvalidPlanError(f"unsupported harness in plan: {harness}")
            target = workspace.joinpath(*skills.SKILL_DIRS[harness], name)
            targets.append((harness, name, target, content))
    return targets


def _preflight(
    workspace: Path, targets: list[tuple[str, str, Path, str]]
) -> list[tuple[str, str, Path, str]]:
    missing = []
    for harness, name, target, content in targets:
        current = workspace
        for part in target.relative_to(workspace).parts:
            current = current / part
            if current.is_symlink():
                raise PlacementError(
                    f"selected skill path contains a symlink: {current}"
                )
            if current.exists() and not current.is_dir():
                raise PlacementError(
                    f"selected skill path is not a directory: {current}"
                )
        if target.exists():
            files = {item.name for item in target.iterdir()}
            if (
                files != {".gitignore", "SKILL.md"}
                or (target / ".gitignore").read_text() != "*\n"
                or (target / "SKILL.md").read_text() != content
            ):
                raise PlacementError(
                    f"selected skill already has unmanaged content: {target}"
                )
        else:
            missing.append((harness, name, target, content))
    return missing


def _place(workspace: Path, targets: list[tuple[str, str, Path, str]]) -> list[str]:
    missing = _preflight(workspace, targets)
    created_files: list[Path] = []
    created_dirs: list[Path] = []
    try:
        for _harness, _name, target, content in missing:
            current = workspace
            for part in target.relative_to(workspace).parts:
                current = current / part
                if not current.exists():
                    current.mkdir()
                    created_dirs.append(current)
            for filename, text in ((".gitignore", "*\n"), ("SKILL.md", content)):
                path = target / filename
                with path.open("x", encoding="utf-8") as output:
                    output.write(text)
                created_files.append(path)
        paths = []
        for _harness, _name, target, _content in targets:
            relative = (target / "SKILL.md").relative_to(workspace).as_posix()
            if subprocess.run(
                ["git", "-C", str(workspace), "check-ignore", "-q", relative],
                check=False,
            ).returncode:
                raise PlacementError(f"selected skill is not Git-excluded: {relative}")
            paths.append(relative)
        return sorted(paths)
    except (OSError, PlacementError):
        for path in reversed(created_files):
            path.unlink(missing_ok=True)
        for path in reversed(created_dirs):
            try:
                path.rmdir()
            except OSError:
                pass
        raise


def _visibility(workspace: Path, plan: dict, prepared: list[str]) -> list[dict]:
    selected = set(prepared)
    findings = []
    user_paths = {
        "claude": ((".claude", "skills"), (".claude", "settings.json")),
        "codex": ((".codex", "skills"), (".codex", "config.toml")),
        "pi": ((".pi", "agent", "skills"), (".pi", "agent", "settings.json")),
        "opencode": (
            (".config", "opencode", "skills"),
            (".config", "opencode", "opencode.json"),
        ),
    }
    project_configs = {
        "claude": (".claude", "settings.json"),
        "codex": (".codex", "config.toml"),
        "pi": (".pi", "settings.json"),
        "opencode": ("opencode.json",),
    }
    for harness in sorted({item["harness"] for item in plan["invocations"]}):
        base = workspace.joinpath(*skills.SKILL_DIRS[harness])
        other = (
            sorted(
                (path / "SKILL.md").relative_to(workspace).as_posix()
                for path in base.iterdir()
                if path.is_dir()
                and (path / "SKILL.md").is_file()
                and (path / "SKILL.md").relative_to(workspace).as_posix()
                not in selected
            )
            if base.is_dir()
            else []
        )
        external = [{"kind": "workspace-skill", "path": path} for path in other]
        config = workspace.joinpath(*project_configs[harness])
        if config.is_file():
            external.append(
                {
                    "kind": "workspace-config",
                    "path": config.relative_to(workspace).as_posix(),
                }
            )
        for parts in user_paths[harness]:
            candidate = Path.home().joinpath(*parts)
            if candidate.exists():
                external.append(
                    {"kind": "user-path-present", "path": "~/" + "/".join(parts)}
                )
        findings.append(
            {
                "harness": harness,
                "prepared_skills": sorted(
                    path
                    for path in prepared
                    if path.startswith(base.relative_to(workspace).as_posix() + "/")
                ),
                "detected_external": external,
                "undetermined": [
                    "presence does not prove loading; plugin and MCP visibility were not exhaustively inspected"
                ],
            }
        )
    return findings


def prepare_session(
    plan: dict, path: str | Path, *, harness_facts: dict[str, dict] | None = None
) -> dict:
    """Prepare an existing worktree after a fresh, matching plan; never launch agents.

    ``harness_facts`` is an internal test seam. The CLI always uses installed
    harness observations and therefore still refuses real unknown enforcement.
    """

    request = _verify_plan(plan)
    workspace = _workspace(plan, path)
    _require_clean_workspace(workspace)
    refreshed = plan_session(workspace, request, harness_facts=harness_facts)
    if any(
        refreshed[key] != plan[key]
        for key in ("request_digest", "inputs_digest", "plan_digest")
    ):
        raise StalePlanError(
            "SESSION_PLAN_STALE: approved plan inputs changed; replan and approve again"
        )
    if refreshed["status"] != "ready":
        raise BlockedPlanError("session plan is blocked; no preparation performed")
    targets = _skill_targets(workspace, refreshed)
    planned_paths = sorted(
        (target / "SKILL.md").relative_to(workspace).as_posix()
        for _harness, _name, target, _content in targets
    )
    record = {
        "schema_version": "1",
        "document_type": "agentic.session-record",
        "status": "prepared",
        "repository": plan["repository"],
        "workspace": str(workspace),
        "commit": _git(workspace, "rev-parse", "HEAD"),
        "plan_digest": plan["plan_digest"],
        "request_digest": plan["request_digest"],
        "inputs_digest": plan["inputs_digest"],
        "profile_digest": _digest(load_profile(workspace)),
        "agentic_version": __version__,
        "contracts": contracts.document(),
        "skills": refreshed["skills"]["selected"],
        "capabilities": refreshed["capabilities"],
        "trust": refreshed["trust"],
        "readiness": refreshed["readiness"],
        "tools": refreshed["tools"],
        "invocations": refreshed["invocations"],
        "visibility": _visibility(workspace, refreshed, planned_paths),
        "prepared": {"skill_paths": planned_paths, "git_excluded": True},
    }
    prepared = _place(workspace, targets)
    record["prepared"]["skill_paths"] = prepared
    return record


def load_plan(path: str | Path) -> dict:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InvalidPlanError(f"invalid plan file: {exc}") from exc
