"""``ready make --target``: plan → safe remediation → reassess, until done.

Each round applies only permitted changes (``safe-automatic`` rule remediations
and requested maintenance actions) through ``ready apply`` semantics: managed
blocks, all-or-nothing, rollback. The loop ends when:

- the target is met (exit 0);
- a round makes no change: no safe progress remains, so make **stops and
  reports the human decisions** (with candidates) and unsupported items instead
  of guessing (exit 4);
- a round hits a conflict (exit 1, nothing written in that round);
- the round limit is reached (exit 4).

``dry_run`` previews the whole run, not just the first round. Later rounds
depend on earlier writes, so the loop runs for real in a throwaway copy of the
repository and only the resulting diffs are reported. The original repository
is never touched. No network, and no project code is executed.
"""

from __future__ import annotations

import difflib
import shutil
import tempfile
from pathlib import Path
from typing import Any

from ..detect import repo_root
from .apply import ApplyError, run as apply_run
from .assess import assess
from .evidence import EvidenceCollector, ScopeError
from .remediation import require_released_ci_check
from .spec import Spec, SpecError, load_spec

DOCUMENT_TYPE = "agentic.readiness-make"
EXIT_MET = 0
EXIT_CONFLICT = 1
EXIT_USAGE = 2
EXIT_ROLLED_BACK = 3
EXIT_STOPPED = 4
MAX_ROUNDS = 5


def _sandbox(root: Path, spec: Spec) -> Path:
    """Copy the repository (with .git, without ignored directories) for a dry run."""

    ignored = set(spec.document["path_matching"]["ignored_directories"]) - {".git"}
    target = Path(tempfile.mkdtemp(prefix="agentic-ready-make-")) / root.name
    shutil.copytree(root, target, symlinks=True,
                    ignore=lambda directory, names: [n for n in names if n in ignored])
    return target


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8") if path.is_file() and not path.is_symlink() else None
    except (OSError, UnicodeDecodeError):
        return None


def _remaining(document: dict[str, Any], target_rank: int, spec: Spec) -> dict[str, list[dict[str, Any]]]:
    in_scope = [r for r in document["remediations"]
                if r["status"] != "pass" and spec.rank(r["required_from"]) <= target_rank]
    return {
        "human_decision": [
            {"rule_id": r["rule_id"], "severity": r["severity"], "required_from": r["required_from"],
             "status": r["status"], "question": r["decision"]["question"],
             "candidates": r["decision"]["candidates"]}
            for r in in_scope if r["remediation_class"] == "human-decision"
        ],
        "unsupported": [
            {"rule_id": r["rule_id"], "severity": r["severity"], "required_from": r["required_from"],
             "reason": r["reason"]}
            for r in in_scope if r["remediation_class"] == "unsupported"
        ],
    }


def _loop(root: Path, spec: Spec, target: str | None, maintenance: tuple[str, ...],
          max_rounds: int) -> tuple[list[dict[str, Any]], str, dict[str, Any], str | None]:
    """Run rounds until done. Returns (rounds, stop reason, last remediation document, error)."""

    rounds: list[dict[str, Any]] = []
    last: dict[str, Any] = {}
    for number in range(1, max_rounds + 1):
        try:
            document = apply_run(root, spec=spec, target=target, dry_run=False,
                                 maintenance=maintenance if number == 1 else ())
        except ApplyError as exc:
            return rounds, "rolled-back", last, str(exc)
        last = document
        result = document["result"]
        state = assess(root, spec=spec, target=target)["maturity"]
        rounds.append({
            "round": number,
            "status": result["status"],
            "written": result["written"],
            "changes": [{"change_id": o["change_id"], "path": o["path"], "outcome": o["outcome"],
                         "reason": o["reason"]} for o in document["outcomes"]],
            "maturity_after": state["current"],
        })
        if result["status"] == "conflict":
            return rounds, "conflict", last, None
        if state["target_met"]:
            return rounds, "target-met", last, None
        if result["status"] == "no-op":
            # No safe progress is possible: stop instead of guessing.
            return rounds, "stopped", last, None
    return rounds, "round-limit", last, None


def make(
    path: str | Path = ".",
    *,
    target: str,
    spec: Spec | str | Path | None = None,
    dry_run: bool = False,
    maintenance: tuple[str, ...] | list[str] = (),
    max_rounds: int = MAX_ROUNDS,
) -> dict[str, Any]:
    """Drive the repository toward ``target`` using only permitted changes."""

    if not target:
        raise SpecError("ready make needs an explicit --target level")
    if max_rounds < 1:
        raise SpecError("--max-rounds must be at least 1")
    require_released_ci_check(maintenance)
    resolved = spec if isinstance(spec, Spec) else load_spec(spec)
    root = repo_root(path)
    before = assess(root, spec=resolved, target=target)
    header = {key: before[key] for key in ("schema_version", "assessor", "spec", "repository", "scope")}
    state = before["maturity"]

    rounds: list[dict[str, Any]] = []
    status = "target-met"
    work = root
    sandbox: Path | None = None
    last: dict[str, Any] = {}
    error: str | None = None
    try:
        if not state["target_met"]:
            if dry_run:
                sandbox = _sandbox(root, resolved)
                work = sandbox
            rounds, status, last, error = _loop(work, resolved, target, tuple(maintenance), max_rounds)
        after = assess(work, spec=resolved, target=target)
        written = sorted({path for r in rounds for path in r["written"]})
        diffs = []
        for rel in written:
            old, new = _read(root / rel), _read(work / rel)
            if dry_run:
                diffs.append("".join(difflib.unified_diff(
                    (old or "").splitlines(keepends=True), (new or "").splitlines(keepends=True),
                    fromfile="/dev/null" if old is None else f"a/{rel}", tofile=f"b/{rel}")))
        remaining = _remaining(last, after["maturity"]["target_rank"], resolved) if last else \
            {"human_decision": [], "unsupported": []}
        tracked: set[str] = set()
        ci = None
        try:
            repo = EvidenceCollector.for_repository(root, resolved, "ci").repo
            tracked = {rel for rel in written if repo.is_tracked(rel)}
            if not dry_run:
                ci = assess(root, spec=resolved, target=target, scope="ci")["maturity"]["current"]
        except ScopeError:
            pass  # not a Git repository: there is no CI-visible view
    finally:
        if sandbox is not None:
            shutil.rmtree(sandbox.parent, ignore_errors=True)

    if status == "stopped":
        status = "needs-decision" if remaining["human_decision"] else "no-safe-progress"
    exit_code = {
        "target-met": EXIT_MET,
        "conflict": EXIT_CONFLICT,
        "rolled-back": EXIT_ROLLED_BACK,
        "needs-decision": EXIT_STOPPED,
        "no-safe-progress": EXIT_STOPPED,
        "round-limit": EXIT_STOPPED,
    }[status]
    document = dict(header)
    document.update({
        "document_type": DOCUMENT_TYPE,
        "dry_run": dry_run,
        "target": state["target"],
        "status": status,
        "exit_code": exit_code,
        "error": error,
        "maturity": {
            "before": state["current"],
            "after": after["maturity"]["current"],
            "target": state["target"],
            "target_met": after["maturity"]["target_met"],
            "ci_visible": ci,
        },
        "rounds": rounds,
        "written": written,
        "uncommitted": sorted(set(written) - tracked),
        "diffs": diffs,
        "remaining": remaining,
    })
    return document
