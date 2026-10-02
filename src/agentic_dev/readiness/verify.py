"""``ready verify``: check readiness as a maintained repository property (CI).

Verification defaults to the ``ci`` scope: only files tracked by Git count as
evidence, so local, untracked, or Git-excluded Agentic Dev state can never make
CI pass. When the repository is a Git checkout, the local view is reported as
well, together with every rule whose status differs and the untracked files
responsible. That difference is useful and is never hidden.

Exit codes are part of the contract:

    0  target met (and the spec pin, if any, matched)
    1  target not met: a readiness regression or an unmet goal
    2  usage or spec error (raised to the CLI)
    3  pinned spec mismatch: the installed assessor's spec differs from the pin
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..detect import repo_root
from .assess import assess
from .evidence import EvidenceCollector
from .spec import Spec, SpecError, load_spec

DOCUMENT_TYPE = "agentic.readiness-verification"
EXIT_MET = 0
EXIT_NOT_MET = 1
EXIT_USAGE = 2
EXIT_PIN_MISMATCH = 3


def _pin(spec: Spec, spec_version: str | None, spec_sha256: str | None) -> dict[str, Any]:
    problems = []
    if spec_version is not None and spec_version != spec.version:
        problems.append(f"pinned spec version {spec_version} but the assessor uses {spec.name} {spec.version}")
    if spec_sha256 is not None and spec_sha256.lower() != spec.sha256:
        problems.append(f"pinned spec sha256 {spec_sha256} but the assessor's spec is {spec.sha256}")
    return {
        "spec_version": spec_version,
        "spec_sha256": spec_sha256.lower() if spec_sha256 else None,
        "matched": not problems,
        "problems": problems,
    }


def _differences(ci: dict[str, Any], local: dict[str, Any], root: Path, tracked) -> list[dict[str, Any]]:
    ci_by_id = {r["id"]: r for r in ci["requirements"]}
    found = []
    for result in local["requirements"]:
        other = ci_by_id[result["id"]]
        if result["status"] == other["status"]:
            continue
        local_only = sorted({
            item["source"] for item in result["evidence"]
            # Sources are repository-relative paths (or descriptive labels such as
            # "repository metadata"). Report real files that Git does not track.
            if (root / item["source"]).exists() and not tracked(item["source"])
        })
        found.append({
            "rule_id": result["id"],
            "severity": result["severity"],
            "required_from": result["required_from"],
            "local_status": result["status"],
            "ci_status": other["status"],
            "local_only_evidence": local_only,
        })
    return found


def verify(
    path: str | Path = ".",
    *,
    target: str,
    spec: Spec | str | Path | None = None,
    scope: str = "ci",
    spec_version: str | None = None,
    spec_sha256: str | None = None,
) -> dict[str, Any]:
    """Verify that ``target`` maturity is met in ``scope``. Read-only."""

    if not target:
        raise SpecError("ready verify needs an explicit --target level")
    resolved = spec if isinstance(spec, Spec) else load_spec(spec)
    pin = _pin(resolved, spec_version, spec_sha256)
    assessment = assess(path, spec=resolved, target=target, scope=scope)
    state = assessment["maturity"]
    by_id = {r["id"]: r for r in assessment["requirements"]}
    blockers = [
        {
            "id": rule_id,
            "title": by_id[rule_id]["title"],
            "required_from": by_id[rule_id]["required_from"],
            "status": by_id[rule_id]["status"],
            "reason": by_id[rule_id]["reason"],
        }
        for rule_id in state["target_blockers"]
    ]

    local_view = None
    if scope == "ci":
        local = assess(path, spec=resolved, target=target, scope="local")
        root = repo_root(path)
        repo = EvidenceCollector.for_repository(root, resolved, "ci").repo
        local_view = {
            "maturity": local["maturity"]["current"],
            "target_met": local["maturity"]["target_met"],
            "differences": _differences(assessment, local, root, repo.is_tracked),
        }

    if not pin["matched"]:
        exit_code = EXIT_PIN_MISMATCH
    elif state["target_met"]:
        exit_code = EXIT_MET
    else:
        exit_code = EXIT_NOT_MET
    document = {key: assessment[key] for key in ("schema_version", "assessor", "spec", "repository", "scope")}
    document.update({
        "document_type": DOCUMENT_TYPE,
        "target": state["target"],
        "passed": exit_code == EXIT_MET,
        "exit_code": exit_code,
        "pin": pin,
        "maturity": {"current": state["current"], "target": state["target"], "target_met": state["target_met"]},
        "blockers": blockers,
        "local": local_view,
    })
    return document
