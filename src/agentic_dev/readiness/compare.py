"""``ready compare``: measure how readiness changed between two assessments.

Both sides are ``readiness-assessment`` v1 documents: a saved baseline
(``agentic ready assess --json > before.json``) and either a second saved
document or a fresh assessment of the repository. The comparison only reads
the two documents; it never assesses or modifies anything itself.

A rule moves along ``fail < unknown < pass``. Moving up is an improvement,
moving down a regression. A change to or from ``not-applicable`` is neutral:
the rule stopped or started applying, which says nothing about readiness.

Exit codes are part of the contract:

    0  no regression (improved, unchanged, or only neutral changes)
    1  regression: maturity dropped or at least one rule got worse
    2  usage error: a document is missing, unreadable, or not an assessment
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DOCUMENT_TYPE = "agentic.readiness-comparison"
ASSESSMENT_TYPE = "agentic.readiness-assessment"
EXIT_OK = 0
EXIT_REGRESSED = 1
EXIT_USAGE = 2

_ORDER = {"fail": 0, "unknown": 1, "pass": 2}
_COUNTS = ("passed", "failed", "unknown", "not_applicable")


class ComparisonError(ValueError):
    """A document cannot be compared (usage error)."""


def load_assessment(source: str | Path, *, text: str | None = None) -> dict[str, Any]:
    """Read one ``readiness-assessment`` v1 document from a file (or given text)."""

    try:
        raw = Path(source).read_text(encoding="utf-8") if text is None else text
        document = json.loads(raw)
    except (OSError, ValueError) as exc:
        raise ComparisonError(f"cannot read assessment {source}: {exc}") from exc
    if not isinstance(document, dict) or document.get("document_type") != ASSESSMENT_TYPE:
        raise ComparisonError(f"{source} is not a readiness assessment (agentic ready assess --json)")
    if document.get("schema_version") != "1":
        raise ComparisonError(f"{source}: unsupported assessment schema_version {document.get('schema_version')!r}")
    return document


def _direction(before: str, after: str) -> str:
    if before in _ORDER and after in _ORDER:
        return "improved" if _ORDER[after] > _ORDER[before] else "regressed"
    return "changed"


def _side(document: dict[str, Any]) -> dict[str, Any]:
    state = document["maturity"]
    return {
        "repository": document["repository"],
        "spec": document["spec"],
        "assessor": document["assessor"],
        "scope": document["scope"],
        "maturity": state["current"],
        "maturity_rank": state["current_rank"],
    }


def compare(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """The ``readiness-comparison`` v1 document for two assessments."""

    old_rules = {rule["id"]: rule for rule in before["requirements"]}
    new_rules = {rule["id"]: rule for rule in after["requirements"]}
    changes = []
    for rule_id in sorted(old_rules.keys() & new_rules.keys()):
        old, new = old_rules[rule_id], new_rules[rule_id]
        if old["status"] == new["status"]:
            continue
        changes.append({
            "id": rule_id,
            "title": new["title"],
            "pillar": new["pillar"],
            "severity": new["severity"],
            "required_from": new["required_from"],
            "before": old["status"],
            "after": new["status"],
            "direction": _direction(old["status"], new["status"]),
            "reason": new["reason"],
        })
    counts = {key: sum(c["direction"] == key for c in changes) for key in ("improved", "regressed", "changed")}

    old_levels = {level["id"]: level for level in before["maturity"]["levels"]}
    levels = [
        {
            "id": level["id"],
            "rank": level["rank"],
            "title": level["title"],
            "before": old_levels[level["id"]]["achieved"] if level["id"] in old_levels else None,
            "after": level["achieved"],
        }
        for level in after["maturity"]["levels"]
    ]

    rank_delta = after["maturity"]["current_rank"] - before["maturity"]["current_rank"]
    regressed = rank_delta < 0 or counts["regressed"] > 0
    improved = rank_delta > 0 or counts["improved"] > 0
    outcome = ("mixed" if regressed and improved else "regressed" if regressed
               else "improved" if improved else "unchanged")
    return {
        "schema_version": "1",
        "document_type": DOCUMENT_TYPE,
        "before": _side(before),
        "after": _side(after),
        "spec_changed": before["spec"]["sha256"] != after["spec"]["sha256"],
        "scope_changed": before["scope"] != after["scope"],
        "outcome": outcome,
        "exit_code": EXIT_REGRESSED if regressed else EXIT_OK,
        "maturity": {
            "before": before["maturity"]["current"],
            "after": after["maturity"]["current"],
            "delta": rank_delta,
        },
        "summary": {
            key: {"before": before["summary"][key], "after": after["summary"][key],
                  "delta": after["summary"][key] - before["summary"][key]}
            for key in _COUNTS
        },
        "levels": levels,
        "counts": counts,
        "changes": changes,
        "added": sorted(new_rules.keys() - old_rules.keys()),
        "removed": sorted(old_rules.keys() - new_rules.keys()),
    }
