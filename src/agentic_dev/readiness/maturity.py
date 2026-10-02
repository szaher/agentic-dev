"""Requirement-based maturity calculation.

A repository is at level N (N >= 1) only when every rule with severity
``required`` whose ``required_from`` rank is <= N has status ``pass`` or
``not-applicable``. ``fail`` and ``unknown`` both block. Counts are reported
for diagnostics only. They never decide the level.
"""

from __future__ import annotations

from typing import Any, Mapping

from .spec import Spec, SpecError

BLOCKING = frozenset({"fail", "unknown"})


def blockers_by_level(spec: Spec, statuses: Mapping[str, str]) -> dict[str, list[str]]:
    """Required rules introduced at each level that currently block it."""

    blockers: dict[str, list[str]] = {level.id: [] for level in spec.levels}
    for rule_id in sorted(spec.rules):
        rule = spec.rules[rule_id]
        if rule["severity"] == "required" and statuses.get(rule_id) in BLOCKING:
            blockers[rule["required_from"]].append(rule_id)
    return blockers


def compute(spec: Spec, statuses: Mapping[str, str], target: str | None = None) -> dict[str, Any]:
    """Compute current maturity and progress toward an optional target level."""

    if target is not None:
        try:
            spec.level(target)
        except SpecError:
            levels = ", ".join(level.id for level in spec.levels)
            raise SpecError(f"unknown target level {target!r}; choose one of: {levels}") from None

    blockers = blockers_by_level(spec, statuses)
    levels: list[dict[str, Any]] = []
    achieved_so_far = True
    current = spec.levels[0]
    for level in spec.levels:
        introduced = sorted(
            rule_id for rule_id, rule in spec.rules.items()
            if rule["severity"] == "required" and rule["required_from"] == level.id
        )
        counts = {status: 0 for status in ("pass", "fail", "unknown", "not-applicable")}
        for rule_id in introduced:
            counts[statuses.get(rule_id, "unknown")] += 1
        own_blockers = blockers[level.id]
        achieved = achieved_so_far and not own_blockers
        if achieved:
            current = level
        levels.append({
            "id": level.id,
            "rank": level.rank,
            "title": level.title,
            "achieved": achieved,
            "required": len(introduced),
            "passed": counts["pass"],
            "failed": counts["fail"],
            "unknown": counts["unknown"],
            "not_applicable": counts["not-applicable"],
            "blocking": own_blockers,
        })
        achieved_so_far = achieved

    following = [level for level in spec.levels if level.rank == current.rank + 1]
    next_level = following[0] if following else None
    goal = spec.level(target) if target else (next_level or current)
    target_blockers = [
        rule_id
        for level in spec.levels
        if current.rank < level.rank <= goal.rank
        for rule_id in blockers[level.id]
    ]
    return {
        "current": current.id,
        "current_rank": current.rank,
        "next": next_level.id if next_level else None,
        "target": goal.id,
        "target_rank": goal.rank,
        "target_met": current.rank >= goal.rank,
        "target_blockers": target_blockers,
        "levels": levels,
    }
