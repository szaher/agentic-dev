"""Evaluate Agent Ready rules against repository evidence.

Expressions use three-valued logic: True (observed), False (not observed), and
None (the assessor cannot establish the evidence). None never turns into a
failure. It produces ``unknown``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .. import __version__
from ..detect import repo_root
from . import maturity
from .evidence import EvidenceCollector, Observation
from .spec import Spec, load_spec

SCHEMA_VERSION = "1"
ASSESSMENT = "agentic.readiness-assessment"
EXPLANATION = "agentic.readiness-explanation"
PLAN = "agentic.readiness-plan"


def evaluate(expression: Any, observe) -> bool | None:
    if isinstance(expression, str):
        return observe(expression).satisfied
    (operator, operands), = expression.items()
    values = [evaluate(operand, observe) for operand in operands]
    if operator == "all":
        if False in values:
            return False
        return None if None in values else True
    found = True in values
    if operator == "any":
        if found:
            return True
        return None if None in values else False
    if operator == "none":
        if found:
            return False
        return None if None in values else True
    raise ValueError(f"unknown expression operator: {operator}")


def references(expression: Any, negated: bool = False) -> list[tuple[str, bool]]:
    """Evidence ids with polarity: True when nested under an odd number of ``none``."""

    if expression is None:
        return []
    if isinstance(expression, str):
        return [(expression, negated)]
    (operator, operands), = expression.items()
    inner = not negated if operator == "none" else negated
    found: list[tuple[str, bool]] = []
    for operand in operands:
        for item in references(operand, inner):
            if item not in found:
                found.append(item)
    return found


def _guard(operands: list[Any]) -> tuple[str, list[Any]] | None:
    """Recognize the implication idiom ``any: [{none: [A]}, B, ...]`` ("if A then any(B, ...)")."""

    guards = [o for o in operands if isinstance(o, dict) and list(o) == ["none"] and len(o["none"]) == 1
              and isinstance(o["none"][0], str)]
    if len(guards) == 1 and len(operands) > 1:
        rest = [o for o in operands if o is not guards[0]]
        return guards[0]["none"][0], rest
    return None


def describe(expression: Any) -> str:
    if isinstance(expression, str):
        return expression
    (operator, operands), = expression.items()
    if operator == "any" and (guard := _guard(operands)):
        condition, rest = guard
        return f"{condition} requires {describe({'any': rest})}"
    return f"{operator}({', '.join(describe(operand) for operand in operands)})"


def unmet(expression: Any, observe) -> tuple[str, list[str]]:
    """Describe only the failing branch of a False expression, plus prohibited evidence found."""

    if isinstance(expression, str):
        return expression, []
    (operator, operands), = expression.items()
    if operator == "all":
        failing = [unmet(o, observe) for o in operands if evaluate(o, observe) is False]
        prohibited = [ref for _, refs in failing for ref in refs]
        parts = [text for text, _ in failing]
        return (parts[0] if len(parts) == 1 else f"all({', '.join(parts)})"), prohibited
    if operator == "none":
        found = [o for o in operands if evaluate(o, observe) is True]
        refs = [ref for o in found for ref, _ in references(o)]
        return f"no {', '.join(describe(o) for o in found)}", refs
    return describe(expression), []


@dataclass
class Assessor:
    spec: Spec
    collector: EvidenceCollector

    def rule_result(self, rule: dict[str, Any]) -> dict[str, Any]:
        observe = self.collector.observe
        result: dict[str, Any] = {
            "id": rule["id"],
            "title": rule["title"],
            "pillar": rule["pillar"],
            "dimension": rule.get("dimension"),
            "severity": rule["severity"],
            "required_from": rule["required_from"],
            "required_for": self.required_for(rule),
            "depends_on": sorted(rule.get("depends_on", [])),
            "remediation": dict(sorted(rule["remediation"].items())),
            "applicability": None,
        }

        applies = rule.get("applies_when")
        if applies is not None:
            outcome = evaluate(applies, observe)
            result["applicability"] = {
                "expression": describe(applies),
                "result": {True: "applicable", False: "not-applicable", None: "unknown"}[outcome],
                "observed": sorted(ref for ref, _ in references(applies) if observe(ref).satisfied),
            }
            if outcome is False:
                return self._finish(result, "not-applicable", [], [], [],
                                    f"Not applicable: requires {describe(applies)}.")
            if outcome is None:
                unsupported = sorted(ref for ref, _ in references(applies) if observe(ref).satisfied is None)
                return self._finish(result, "unknown", [], [], unsupported,
                                    "Applicability cannot be established: evidence not supported by this "
                                    f"assessor ({', '.join(unsupported)}).")

        expression = rule["evidence"]
        refs = references(expression)
        outcome = evaluate(expression, observe)
        observed_items: list[dict[str, Any]] = []
        for ref, _ in refs:
            observed_items.extend(observe(ref).items)
        missing = sorted(ref for ref, negated in refs if not negated and observe(ref).satisfied is False)
        unsupported = sorted(ref for ref, _ in refs if observe(ref).satisfied is None)
        notes = [observe(ref).note for ref, _ in refs if observe(ref).note and observe(ref).satisfied is not None]

        if outcome is True:
            positive = sorted(ref for ref, negated in refs if not negated and observe(ref).satisfied)
            if positive:
                reason = f"Satisfied by {', '.join(positive)}."
            else:
                absent = sorted(ref for ref, negated in refs if negated)
                reason = f"Satisfied: no {', '.join(absent)} observed."
            return self._finish(result, "pass", observed_items, [], [], reason)

        if outcome is None:
            return self._finish(result, "unknown", observed_items, missing, unsupported,
                                "Evidence not supported by this assessor: "
                                f"{', '.join(unsupported)}.")

        expected, prohibited = unmet(expression, observe)
        prohibited = sorted(set(prohibited))
        if prohibited:
            reason = f"Prohibited evidence observed: {', '.join(prohibited)}."
        else:
            reason = f"Expected evidence was not found: {expected}."
        if notes:
            reason += " " + " ".join(f"{note[0].upper()}{note[1:]}." for note in sorted(set(notes)))
        if rule["evaluation"]["on_missing"] == "unknown" and not prohibited:
            reason = f"{rule['evaluation']['unknown_reason'].strip()} {reason}"
            return self._finish(result, "unknown", observed_items, missing, [], reason)
        return self._finish(result, "fail", observed_items, missing, [], reason)

    def required_for(self, rule: dict[str, Any]) -> list[str]:
        if rule["severity"] != "required":
            return []
        start = self.spec.rank(rule["required_from"])
        return [level.id for level in self.spec.levels if level.rank >= start]

    @staticmethod
    def _finish(result: dict[str, Any], status: str, items: list[dict[str, Any]],
                missing: list[str], unsupported: list[str], reason: str) -> dict[str, Any]:
        ordered = sorted(items, key=lambda i: (i["type"], i["source"], i.get("line", 0), i["value"]))
        result.update({
            "status": status,
            "reason": reason,
            "evidence": ordered,
            "missing_evidence": missing,
            "unsupported_evidence": unsupported,
        })
        return result


def _counts(results: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"passed": 0, "failed": 0, "unknown": 0, "not_applicable": 0}
    key = {"pass": "passed", "fail": "failed", "unknown": "unknown", "not-applicable": "not_applicable"}
    for result in results:
        counts[key[result["status"]]] += 1
    return counts


def _context(path: str | Path, spec: Spec | str | Path | None) -> tuple[Spec, EvidenceCollector]:
    resolved = spec if isinstance(spec, Spec) else load_spec(spec)
    root = repo_root(path)
    if not root.is_dir():
        raise FileNotFoundError(f"repository path does not exist: {Path(path).name or path}")
    return resolved, EvidenceCollector.for_repository(root, resolved)


def _header(document_type: str, spec: Spec, collector: EvidenceCollector) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "document_type": document_type,
        "assessor": {"name": "agentic-dev", "version": __version__},
        "spec": spec.identity(),
        "repository": {"name": collector.repo.root.name, "revision": collector.repo.revision},
    }


def assess(
    path: str | Path = ".",
    *,
    spec: Spec | str | Path | None = None,
    target: str | None = None,
) -> dict[str, Any]:
    """Assess a repository against the Agent Ready spec. Never modifies the repository."""

    resolved, collector = _context(path, spec)
    assessor = Assessor(resolved, collector)
    results = [assessor.rule_result(resolved.rules[rule_id]) for rule_id in sorted(resolved.rules)]
    statuses = {result["id"]: result["status"] for result in results}
    document = _header(ASSESSMENT, resolved, collector)
    document.update({
        "maturity": maturity.compute(resolved, statuses, target),
        "summary": _counts(results),
        "pillars": {
            pillar: _counts([r for r in results if r["pillar"] == pillar]) for pillar in resolved.pillars
        },
        "dimensions": {
            dimension: _counts([r for r in results if r["dimension"] == dimension])
            for dimension in resolved.dimensions
        },
        "requirements": results,
    })
    return document


def _conclusion(state: dict[str, Any]) -> str:
    current = state["current"]
    blocked = next((level for level in state["levels"] if not level["achieved"]), None)
    if blocked is None:
        return f"Maturity is {current}: every required rule at every level passes or is not applicable."
    if blocked["blocking"]:
        names = ", ".join(blocked["blocking"])
        return (f"Maturity is {current}: {blocked['id']} is blocked by "
                f"{len(blocked['blocking'])} required rule(s) that do not pass ({names}).")
    return f"Maturity is {current}: {blocked['id']} is blocked by a lower level."


def explain_repository(
    path: str | Path = ".",
    *,
    spec: Spec | str | Path | None = None,
    target: str | None = None,
) -> dict[str, Any]:
    """Why the repository has its maturity level, level by level."""

    assessment = assess(path, spec=spec, target=target)
    by_id = {result["id"]: result for result in assessment["requirements"]}
    levels = []
    for level in assessment["maturity"]["levels"]:
        requirements = [
            {"id": rid, "status": by_id[rid]["status"], "reason": by_id[rid]["reason"]}
            for rid in sorted(by_id)
            if by_id[rid]["severity"] == "required" and by_id[rid]["required_from"] == level["id"]
        ]
        levels.append({**level, "requirements": requirements})
    document = {key: assessment[key] for key in ("schema_version", "assessor", "spec", "repository")}
    document.update({
        "document_type": EXPLANATION,
        "subject": "repository",
        "conclusion": _conclusion(assessment["maturity"]),
        "maturity": {k: v for k, v in assessment["maturity"].items() if k != "levels"},
        "levels": levels,
        "summary": assessment["summary"],
    })
    return document


def explain_rule(
    rule_id: str,
    path: str | Path = ".",
    *,
    spec: Spec | str | Path | None = None,
) -> dict[str, Any]:
    """A rule's definition, its evidence semantics, and its status in the repository."""

    resolved = spec if isinstance(spec, Spec) else load_spec(spec)
    if rule_id not in resolved.rules:
        close = sorted(r for r in resolved.rules if r.split(".")[0] == rule_id.split(".")[0])
        hint = f" Rules in this pillar: {', '.join(close)}." if close else ""
        raise KeyError(f"unknown rule {rule_id!r} in {resolved.name} {resolved.version}.{hint}")
    rule = resolved.rules[rule_id]
    assessment = assess(path, spec=resolved)
    result = next(r for r in assessment["requirements"] if r["id"] == rule_id)
    refs = [ref for ref, _ in references(rule.get("applies_when"))] + [ref for ref, _ in references(rule["evidence"])]
    definition = {key: rule[key] for key in sorted(rule)}
    document = {key: assessment[key] for key in ("schema_version", "assessor", "spec", "repository")}
    document.update({
        "document_type": EXPLANATION,
        "subject": "rule",
        "rule": definition,
        "required_for": result["required_for"],
        "evidence_definitions": [
            {key: resolved.evidence[ref][key] for key in ("id", "title", "description", "detection")}
            for ref in sorted(set(refs))
        ],
        "result": {key: result[key] for key in (
            "status", "reason", "evidence", "missing_evidence", "unsupported_evidence", "applicability",
        )},
        "dependencies": [
            {"id": dep, "status": next(r["status"] for r in assessment["requirements"] if r["id"] == dep)}
            for dep in sorted(rule.get("depends_on", []))
        ],
        "maturity": {k: v for k, v in assessment["maturity"].items() if k != "levels"},
    })
    return document


def _ordered(spec: Spec, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    pillar_order = {pillar: index for index, pillar in enumerate(spec.pillars)}
    key = {item["id"]: (spec.rank(item["required_from"]), pillar_order[item["pillar"]], item["id"])
           for item in items}
    remaining = sorted(items, key=lambda item: key[item["id"]])
    placed: list[dict[str, Any]] = []
    ids = {item["id"] for item in items}
    done: set[str] = set()
    while remaining:
        for index, item in enumerate(remaining):
            if all(dep in done or dep not in ids for dep in item["depends_on"]):
                placed.append(remaining.pop(index))
                done.add(item["id"])
                break
        else:  # pragma: no cover - the spec forbids cycles
            placed.extend(remaining)
            break
    return placed


def _step(result: dict[str, Any], order: int) -> dict[str, Any]:
    remediation = result["remediation"]
    return {
        "order": order,
        "id": result["id"],
        "title": result["title"],
        "pillar": result["pillar"],
        "dimension": result["dimension"],
        "required_from": result["required_from"],
        "severity": result["severity"],
        "status": result["status"],
        "classification": remediation["classification"],
        "action": remediation["summary"],
        "decision": remediation.get("decision"),
        "depends_on": result["depends_on"],
        "reason": result["reason"],
    }


def plan(
    path: str | Path = ".",
    *,
    spec: Spec | str | Path | None = None,
    target: str | None = None,
) -> dict[str, Any]:
    """A read-only remediation plan toward ``target`` (default: the next level)."""

    resolved = spec if isinstance(spec, Spec) else load_spec(spec)
    assessment = assess(path, spec=resolved, target=target)
    state = assessment["maturity"]
    goal_rank = state["target_rank"]
    open_items = [
        r for r in assessment["requirements"]
        if r["status"] in maturity.BLOCKING and resolved.rank(r["required_from"]) <= goal_rank
    ]

    def section(severity: str) -> list[dict[str, Any]]:
        items = _ordered(resolved, [r for r in open_items if r["severity"] == severity])
        return [_step(item, index) for index, item in enumerate(items, start=1)]

    required = section("required")
    classes = {"automatable": 0, "assisted": 0, "human-required": 0}
    for step in required:
        classes[step["classification"]] += 1
    document = {key: assessment[key] for key in ("schema_version", "assessor", "spec", "repository")}
    document.update({
        "document_type": PLAN,
        "read_only": True,
        "maturity": {
            "current": state["current"],
            "target": state["target"],
            "target_met": state["target_met"],
        },
        "steps": required,
        "recommended": section("recommended"),
        "optional": section("advisory"),
        "summary": {
            "required_steps": len(required),
            "automatable": classes["automatable"],
            "assisted": classes["assisted"],
            "human_required": classes["human-required"],
        },
    })
    return document
