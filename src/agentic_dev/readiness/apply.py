"""``ready diff`` / ``ready apply``: execute permitted changes from the remediation contract.

Only changes owned by ``safe-automatic`` rule remediations or by maintenance
actions are ever written. ``human-decision`` and ``unsupported`` remediations
are reported, never applied.

A run is all-or-nothing. Every change is planned in memory first, and any
conflict or refusal means nothing is written. Otherwise every target is
snapshotted, written atomically, and restored if anything fails. Running again
with the same inputs is a no-op.
"""

from __future__ import annotations

import difflib
import hashlib
import os
import stat
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..detect import repo_root
from . import managed
from .assess import assess
from .remediation import check_document, propose
from .spec import Spec, load_spec

DRY_RUN = "dry-run"
APPLIED = "applied"


class ApplyError(RuntimeError):
    """A write failed; the run was rolled back."""


@dataclass
class FilePlan:
    path: str
    before: str | None
    after: str | None
    outcomes: list[dict[str, Any]] = field(default_factory=list)


def _read(root: Path, rel: str) -> tuple[str | None, str | None]:
    """Current text of a target, or a refusal reason when it must not be touched."""

    target = root / rel
    # Every existing path component must be a real directory inside the repository.
    current = root
    for part in Path(rel).parts[:-1]:
        current = current / part
        if current.is_symlink():
            return None, f"{rel}: a parent directory is a symlink"
        if current.exists() and not current.is_dir():
            return None, f"{rel}: a parent path is not a directory"
    if target.is_symlink():
        return None, f"{rel}: target is a symlink"
    if target.exists() and not target.is_file():
        return None, f"{rel}: target is not a regular file"
    try:
        resolved = target.resolve()
        resolved.relative_to(root.resolve())
    except (OSError, ValueError):
        return None, f"{rel}: target resolves outside the repository"
    if not target.exists():
        return None, None
    data = target.read_bytes()
    try:
        return data.decode("utf-8"), None
    except UnicodeDecodeError:
        return None, f"{rel}: target is not UTF-8 text"


def _sha(text: str | None) -> str | None:
    return hashlib.sha256(text.encode("utf-8")).hexdigest() if text is not None else None


def _diff(rel: str, before: str | None, after: str | None) -> str:
    return "".join(difflib.unified_diff(
        (before or "").splitlines(keepends=True),
        (after or "").splitlines(keepends=True),
        fromfile="/dev/null" if before is None else f"a/{rel}",
        tofile=f"b/{rel}",
    ))


def plan_changes(root: Path, document: dict[str, Any]) -> list[FilePlan]:
    """Plan every change of a remediation document against the files on disk (read-only)."""

    plans: dict[str, FilePlan] = {}
    for change in document["changes"]:
        rel = change["path"]
        if rel not in plans:
            text, refusal = _read(root, rel)
            plans[rel] = FilePlan(rel, text, text)
            if refusal:
                plans[rel].after = None
                plans[rel].outcomes.append({"change_id": change["id"], "outcome": managed.REFUSED, "reason": refusal})
                continue
            expected = change["target"]
            if (text is not None) != expected["exists"] or _sha(text) != expected["sha256"]:
                plans[rel].outcomes.append({
                    "change_id": change["id"], "outcome": managed.CONFLICT,
                    "reason": f"{rel} changed since the preview; preview again",
                })
                continue
        file_plan = plans[rel]
        if any(o["outcome"] in {managed.REFUSED, managed.CONFLICT} for o in file_plan.outcomes):
            file_plan.outcomes.append({"change_id": change["id"], "outcome": managed.CONFLICT,
                                       "reason": f"another change to {rel} cannot be applied"})
            continue
        planned = managed.plan(file_plan.after, change)
        file_plan.outcomes.append({"change_id": change["id"], "outcome": planned.outcome, "reason": planned.reason})
        if planned.text is not None:
            file_plan.after = planned.text
    return [plans[key] for key in sorted(plans)]


def _write_atomic(path: Path, text: str, mode: int | None) -> None:
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".agentic-tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        os.chmod(temp, mode if mode is not None else 0o644)
        os.replace(temp, path)
    except BaseException:
        Path(temp).unlink(missing_ok=True)
        raise


def write_transaction(root: Path, plans: list[FilePlan]) -> None:
    """Write planned files all-or-nothing, restoring every snapshot on failure."""

    snapshots: list[tuple[Path, bytes | None, int | None]] = []
    created_dirs: list[Path] = []
    try:
        for file_plan in plans:
            if file_plan.after is None or file_plan.after == file_plan.before:
                continue
            path = root / file_plan.path
            current = path.read_bytes().decode("utf-8") if path.is_file() and not path.is_symlink() else None
            if current != file_plan.before or (path.exists() and current is None):
                raise ApplyError(f"{file_plan.path} changed while applying")
            missing = [p for p in [*reversed(path.parents)] if p != root and root in p.parents and not p.exists()]
            for directory in missing:
                directory.mkdir()
                created_dirs.append(directory)
            if path.exists():
                snapshots.append((path, path.read_bytes(), stat.S_IMODE(path.stat().st_mode)))
                _write_atomic(path, file_plan.after, stat.S_IMODE(path.stat().st_mode))
            else:
                snapshots.append((path, None, None))
                _write_atomic(path, file_plan.after, None)
    except BaseException as exc:
        for path, data, mode in reversed(snapshots):
            if data is None:
                path.unlink(missing_ok=True)
            else:
                fd, temp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".agentic-restore")
                with os.fdopen(fd, "wb") as handle:
                    handle.write(data)
                os.chmod(temp, mode if mode is not None else 0o644)
                os.replace(temp, path)
        for directory in reversed(created_dirs):
            try:
                directory.rmdir()
            except OSError:
                pass
        raise ApplyError(f"write failed and was rolled back: {exc}") from exc


def run(
    path: str | Path = ".",
    *,
    spec: Spec | str | Path | None = None,
    target: str | None = None,
    dry_run: bool = True,
    maintenance: tuple[str, ...] | list[str] = (),
) -> dict[str, Any]:
    """Preview (default) or apply the permitted changes toward ``target``."""

    resolved = spec if isinstance(spec, Spec) else load_spec(spec)
    root = repo_root(path)
    document = propose(root, spec=resolved, target=target, maintenance=maintenance)
    plans = plan_changes(root, document)
    owners = {change["id"]: change["owner"] for change in document["changes"]}
    tracked = {change["id"]: change["target"]["tracked"] for change in document["changes"]}
    outcomes: list[dict[str, Any]] = []
    for file_plan in plans:
        diff = _diff(file_plan.path, file_plan.before, file_plan.after) if file_plan.after is not None else ""
        for index, outcome in enumerate(file_plan.outcomes):
            outcomes.append({
                **outcome,
                "path": file_plan.path,
                "owner": owners[outcome["change_id"]],
                "ci_visible": tracked[outcome["change_id"]],
                # The file-level diff is attached to the file's first change only.
                "diff": diff if index == 0 else "",
            })
    outcomes.sort(key=lambda o: o["change_id"])

    blocked = [o for o in outcomes if o["outcome"] in {managed.CONFLICT, managed.REFUSED}]
    writes = [o for o in outcomes if o["outcome"] in managed.WRITES]
    if blocked:
        status = "conflict"
    elif not writes:
        status = "no-op"
    else:
        status = "planned" if dry_run else "applied"

    maturity_after = None
    if status == "applied":
        write_transaction(root, plans)
        maturity_after = assess(root, spec=resolved, target=target)["maturity"]["current"]

    document["mode"] = DRY_RUN if dry_run else APPLIED
    document["outcomes"] = outcomes
    document["result"] = {
        "status": status,
        "written": [p.path for p in plans if status == "applied" and p.after not in (None, p.before)],
        "maturity_after": maturity_after,
    }
    check_document(document, resolved)
    return document
