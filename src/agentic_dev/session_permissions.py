"""Independent, fail-closed permission bounds for session invocations.

Capability trust permissions are intentionally separate from these harness
sandbox requirements. This module is pure: it probes no tools and writes no
state, so the resolver can use it while remaining read-only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Role = Literal["implementer", "reviewer"]
Dimension = Literal["filesystem", "network"]
Enforceability = Literal["enforceable", "unenforceable", "unknown"]

LEVELS: dict[str, tuple[str, ...]] = {
    "filesystem": ("read-only", "workspace-write"),
    "network": ("off", "on"),
}
ROLES = ("implementer", "reviewer")

DEFAULT_BOUNDS: dict[str, dict[str, dict[str, str]]] = {
    "implementer": {
        "filesystem": {"minimum": "workspace-write", "maximum": "workspace-write"},
        "network": {"minimum": "off", "maximum": "off"},
    },
    "reviewer": {
        "filesystem": {"minimum": "read-only", "maximum": "read-only"},
        "network": {"minimum": "off", "maximum": "off"},
    },
}


@dataclass(frozen=True)
class PermissionBlocker:
    invocation: str
    dimension: str
    code: str
    detail: str

    def document(self) -> dict[str, str]:
        return {
            "invocation": self.invocation,
            "dimension": self.dimension,
            "code": self.code,
            "detail": self.detail,
        }


def _level(dimension: str, value: str) -> int:
    if dimension not in LEVELS:
        raise ValueError(f"unknown permission dimension: {dimension}")
    try:
        return LEVELS[dimension].index(value)
    except ValueError as exc:
        raise ValueError(f"unknown {dimension} permission level: {value}") from exc


def validate_bounds(role: str, bounds: dict) -> dict[str, dict[str, str]]:
    """Fill omitted dimensions from the role defaults, rejecting unknown data."""

    if role not in ROLES:
        raise ValueError(f"unknown invocation role: {role}")
    if not isinstance(bounds, dict):
        raise TypeError("permissions must be an object")
    unknown = set(bounds) - set(LEVELS)
    if unknown:
        raise ValueError(f"unknown permission dimensions: {', '.join(sorted(unknown))}")
    result: dict[str, dict[str, str]] = {}
    for dimension, defaults in DEFAULT_BOUNDS[role].items():
        supplied = bounds.get(dimension, {})
        if not isinstance(supplied, dict):
            raise TypeError(f"{dimension} permissions must be an object")
        unknown_keys = set(supplied) - {"minimum", "maximum"}
        if unknown_keys:
            raise ValueError(
                f"unknown {dimension} permission keys: {', '.join(sorted(unknown_keys))}"
            )
        minimum = supplied.get("minimum", defaults["minimum"])
        maximum = supplied.get("maximum", defaults["maximum"])
        _level(dimension, minimum)
        _level(dimension, maximum)
        if (
            role == "reviewer"
            and dimension == "filesystem"
            and (minimum != "read-only" or maximum != "read-only")
        ):
            raise ValueError("reviewers cannot request filesystem writes")
        result[dimension] = {"minimum": minimum, "maximum": maximum}
    return result


def validate_ceilings(ceilings: dict) -> dict[str, dict[str, str]]:
    if not isinstance(ceilings, dict):
        raise TypeError("profile permissions must be an object")
    unknown = set(ceilings) - set(ROLES)
    if unknown:
        raise ValueError(f"unknown permission roles: {', '.join(sorted(unknown))}")
    result: dict[str, dict[str, str]] = {}
    for role, dimensions in ceilings.items():
        if not isinstance(dimensions, dict):
            raise TypeError(f"profile permissions for {role} must be an object")
        unknown_dimensions = set(dimensions) - set(LEVELS)
        if unknown_dimensions:
            raise ValueError(
                f"unknown permission dimensions: {', '.join(sorted(unknown_dimensions))}"
            )
        result[role] = {}
        for dimension, value in dimensions.items():
            _level(dimension, value)
            if (
                role == "reviewer"
                and dimension == "filesystem"
                and value != "read-only"
            ):
                raise ValueError("reviewer filesystem ceiling must be read-only")
            result[role][dimension] = value
    return result


def compose(
    invocation: str,
    role: str,
    bounds: dict,
    profile_ceilings: dict,
) -> tuple[dict[str, dict[str, str]], list[PermissionBlocker]]:
    """Resolve each dimension to the least sufficient level under both ceilings."""

    requested = validate_bounds(role, bounds)
    ceilings = validate_ceilings(profile_ceilings)
    effective: dict[str, dict[str, str]] = {}
    blockers: list[PermissionBlocker] = []
    for dimension in LEVELS:
        minimum = requested[dimension]["minimum"]
        request_maximum = requested[dimension]["maximum"]
        profile_maximum = ceilings.get(role, {}).get(dimension, LEVELS[dimension][-1])
        limiting_source = (
            "profile"
            if _level(dimension, profile_maximum) < _level(dimension, request_maximum)
            else "request"
        )
        ceiling = min(
            (request_maximum, profile_maximum),
            key=lambda value: _level(dimension, value),
        )
        if _level(dimension, minimum) > _level(dimension, ceiling):
            blockers.append(
                PermissionBlocker(
                    invocation,
                    dimension,
                    "permission-conflict",
                    f"minimum {minimum} exceeds {limiting_source} ceiling {ceiling}",
                )
            )
        effective[dimension] = {
            "minimum": minimum,
            "maximum": request_maximum,
            "profile_ceiling": profile_maximum,
            "level": minimum
            if _level(dimension, minimum) <= _level(dimension, ceiling)
            else ceiling,
        }
    return effective, blockers


def enforcement(
    invocation: str,
    effective: dict[str, dict[str, str]],
    facts: dict[str, dict[str, str]],
) -> tuple[dict[str, dict[str, str]], list[PermissionBlocker]]:
    """Attach measured harness facts; absent or unverified facts block."""

    result: dict[str, dict[str, str]] = {}
    blockers: list[PermissionBlocker] = []
    for dimension in LEVELS:
        level = effective[dimension]["level"]
        fact = facts.get(dimension, {}).get(level, "unknown")
        if fact not in ("enforceable", "unenforceable", "unknown"):
            raise ValueError(f"unknown enforceability fact: {fact}")
        result[dimension] = {"level": level, "status": fact}
        if fact != "enforceable":
            blockers.append(
                PermissionBlocker(
                    invocation,
                    dimension,
                    "permission-unenforceable",
                    f"{dimension}={level} enforcement is {fact}",
                )
            )
    return result, blockers
