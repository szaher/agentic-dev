"""Deterministic human-readable rendering for readiness documents.

Renderers take the JSON documents produced by ``assess``/``explain``/``plan``
and never consult anything else. The text view and the ``--json`` view always
describe the same result.
"""

from __future__ import annotations

from typing import Any

SYMBOL = {"pass": "✓", "fail": "✗", "unknown": "?", "not-applicable": "–"}
LABEL = {"pass": "PASS", "fail": "FAIL", "unknown": "UNKNOWN", "not-applicable": "NOT APPLICABLE"}
PILLAR_TITLES = {
    "context": "Context",
    "conventions": "Conventions",
    "constraints": "Constraints",
    "feedback": "Feedback Loops",
}


def _title(level_id: str) -> str:
    return level_id.replace("-", " ").title()


def _spec_line(document: dict[str, Any]) -> str:
    spec = document["spec"]
    return f"Spec: {spec['name']} {spec['version']} ({spec['source']}, sha256 {spec['sha256'][:12]})"


def _counts(counts: dict[str, int]) -> str:
    return (f"{counts['passed']} passed, {counts['failed']} failed, "
            f"{counts['unknown']} unknown, {counts['not_applicable']} not applicable")


def _level_counts(level: dict[str, Any]) -> str:
    parts = [f"{level['required']} required"]
    for key, label in (("passed", "pass"), ("failed", "fail"), ("unknown", "unknown"),
                       ("not_applicable", "n/a")):
        if level[key]:
            parts.append(f"{level[key]} {label}")
    return ", ".join(parts)


def _evidence(item: dict[str, Any]) -> str:
    where = item["source"] + (f":{item['line']}" if "line" in item else "")
    if item["value"] == item["source"]:
        return f"{item['type']}: {where}"
    return f"{item['type']}: {item['value']} ({where})"


def assessment(document: dict[str, Any], *, verbose: bool = False) -> str:
    state = document["maturity"]
    top = max(level["rank"] for level in state["levels"])
    lines = [
        f"Agent Ready assessment — {document['repository']['name']}",
        _spec_line(document),
        "",
        f"Maturity: {_title(state['current'])} (level {state['current_rank']} of {top})",
        f"Target:   {_title(state['target'])} — {'met' if state['target_met'] else 'not met'}",
        "",
        "Levels",
    ]
    for level in state["levels"]:
        mark = "✓" if level["achieved"] else "✗"
        detail = f"  {_level_counts(level)}" if level["rank"] else ""
        lines.append(f"  {mark} {level['rank']} {level['title']:<13}{detail}".rstrip())
        if level["blocking"]:
            lines.append(f"      blocking: {', '.join(level['blocking'])}")
    lines += ["", "Requirements"]
    width = max(len(r["id"]) for r in document["requirements"])
    for pillar, title in PILLAR_TITLES.items():
        rules = [r for r in document["requirements"] if r["pillar"] == pillar]
        if not rules:
            continue
        lines.append(f"  {title}")
        for rule in rules:
            if not verbose and rule["status"] == "not-applicable":
                continue
            lines.append(
                f"    {SYMBOL[rule['status']]} {rule['id']:<{width}}  {rule['severity']:<11}  "
                f"{rule['required_from']:<12}  {rule['reason']}"
            )
    hidden = document["summary"]["not_applicable"]
    lines += ["", f"Summary: {_counts(document['summary'])}"]
    if hidden and not verbose:
        lines.append(f"({hidden} not-applicable rule(s) hidden; use --verbose to show them)")
    lines += [
        "Maturity is requirement-based: a level is reached only when all of its required rules,",
        "and those of every lower level, pass or are not applicable.",
        "",
        "Next: agentic ready plan <path>   ·   agentic ready explain <rule-id>",
    ]
    return "\n".join(lines)


def repository_explanation(document: dict[str, Any]) -> str:
    lines = [
        f"Why {document['repository']['name']} is {_title(document['maturity']['current'])}",
        _spec_line(document),
        "",
        document["conclusion"],
    ]
    for level in document["levels"]:
        if level["rank"] == 0:
            continue
        if level["achieved"]:
            state = "achieved"
        elif level["blocking"]:
            state = f"blocked by {len(level['blocking'])} required rule(s)"
        else:
            state = "not reached (a lower level is blocked)"
        lines += ["", f"Level {level['rank']} — {level['title']}: {state}"]
        for requirement in level["requirements"]:
            lines.append(f"  {SYMBOL[requirement['status']]} {requirement['id']} — {requirement['reason']}")
    lines += ["", f"Summary: {_counts(document['summary'])}"]
    return "\n".join(lines)


def _detection(definition: dict[str, Any]) -> str:
    detection = definition["detection"]
    kind = detection["kind"]
    if kind == "path":
        scope = " (tracked files)" if detection.get("scope") == "tracked" else ""
        return f"path{scope}: {', '.join(detection['paths'])}"
    if kind in {"heading", "content"}:
        where = ", ".join(detection.get("in") or detection.get("paths") or [])
        return f"{kind} in {where} matching: {', '.join(detection['patterns'])}"
    return f"derived: {detection['definition']}"


def rule_explanation(document: dict[str, Any]) -> str:
    rule = document["rule"]
    result = document["result"]
    gates = (f"gates {', '.join(document['required_for'])}" if document["required_for"]
             else "does not gate maturity")
    dimension = f"   Dimension: {rule['dimension']}" if rule.get("dimension") else ""
    lines = [
        f"{rule['id']} — {rule['title']}",
        f"Pillar: {rule['pillar']}{dimension}   Severity: {rule['severity']}   "
        f"Required from: {rule['required_from']} ({gates})",
        _spec_line(document),
        "",
        rule["description"].strip(),
        "",
        "Why it matters:",
        f"  {rule['rationale'].strip()}",
        "",
        f"Status in {document['repository']['name']}: {LABEL[result['status']]}",
        f"  {result['reason']}",
    ]
    if result.get("applicability"):
        applicability = result["applicability"]
        lines.append(f"  Applies when: {applicability['expression']} → {applicability['result']}")
    if result["evidence"]:
        lines += ["", "Observed evidence:"] + [f"  - {_evidence(item)}" for item in result["evidence"]]
    definitions = {item["id"]: item for item in document["evidence_definitions"]}
    if result["missing_evidence"]:
        lines += ["", "Missing evidence:"] + [
            f"  - {ref} — {definitions[ref]['title']}" if ref in definitions else f"  - {ref}"
            for ref in result["missing_evidence"]
        ]
    if result["unsupported_evidence"]:
        lines += ["", "Not supported by this assessor:"] + [f"  - {ref}" for ref in result["unsupported_evidence"]]
    lines += ["", "How evidence is detected:"] + [
        f"  - {item['id']}: {_detection(item)}" for item in document["evidence_definitions"]
    ]
    remediation = rule["remediation"]
    lines += ["", f"Remediation: {remediation['classification']}", f"  {remediation['summary'].strip()}"]
    if remediation.get("decision"):
        lines.append(f"  Decision required: {remediation['decision'].strip()}")
    if document["dependencies"]:
        lines += ["", "Depends on:"] + [
            f"  {SYMBOL[dep['status']]} {dep['id']}" for dep in document["dependencies"]
        ]
    lines += ["", "Sources (Agent Ready course):"] + [f"  - {source}" for source in rule["sources"]]
    return "\n".join(lines)


def _plan_steps(steps: list[dict[str, Any]], *, start: int = 1) -> list[str]:
    lines: list[str] = []
    for offset, step in enumerate(steps):
        status = " (unknown)" if step["status"] == "unknown" else ""
        lines += [
            f"{start + offset}. {step['id']} — {step['title']}{status}",
            f"   Level: {step['required_from']}   Classification: {step['classification']}",
            f"   Why: {step['reason']}",
        ]
        if step["classification"] == "human-required":
            lines.append(f"   Required decision: {step['decision']}")
            lines.append(f"   Then: {step['action']}")
        else:
            lines.append(f"   Suggested remediation: {step['action']}")
        if step["depends_on"]:
            lines.append(f"   After: {', '.join(step['depends_on'])}")
        lines.append("")
    return lines


def plan(document: dict[str, Any]) -> str:
    state = document["maturity"]
    lines = [
        f"Agent Ready plan — {document['repository']['name']} (read-only; nothing was modified)",
        _spec_line(document),
        "",
        f"Current: {_title(state['current'])}",
        f"Target:  {_title(state['target'])}",
        "",
    ]
    if state["target_met"] and not document["steps"]:
        lines.append("The target level is already met. No required steps.")
        lines.append("")
    else:
        lines += ["Missing requirements:", ""] + _plan_steps(document["steps"])
    if document["recommended"]:
        lines += ["Recommended (does not gate maturity):", ""] + _plan_steps(document["recommended"])
    if document["optional"]:
        lines += ["Optional (advisory):"] + [
            f"  - {step['id']} — {step['action']}" for step in document["optional"]
        ] + [""]
    summary = document["summary"]
    lines.append(
        f"Summary: {summary['required_steps']} required step(s) — {summary['automatable']} automatable, "
        f"{summary['assisted']} assisted, {summary['human_required']} human-required."
    )
    lines.append("Automated remediation is not performed in this version; this plan only describes it.")
    return "\n".join(lines).rstrip() + "\n"
