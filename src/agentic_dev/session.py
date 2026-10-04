"""Read-only, deterministic session planning for the S1 contracts."""

from __future__ import annotations

import hashlib
import json
import subprocess
import tomllib
from dataclasses import asdict
from pathlib import Path
from typing import Any

from . import capabilities, contracts, providers, skills, trust
from .detect import detect_repo, repo_root
from .inspection import tool_status
from .readiness.spec import load_spec
from .readiness.verify import verify as verify_readiness
from .session_harnesses import HARNESSES, inspect_harness
from .session_permissions import (
    LEVELS,
    ROLES,
    compose,
    validate_bounds,
    validate_ceilings,
)
from .verification import FULL_KINDS

PROFILE_TYPE = "agentic.repository-profile"
REQUEST_TYPE = "agentic.session-request"
PLAN_TYPE = "agentic.session-plan"
PROFILE_KEYS = {
    "schema_version",
    "document_type",
    "preferred_harness",
    "readiness_minimum",
    "required_capabilities",
    "allowed_skills",
    "required_skills",
    "trust_ceiling",
    "permissions",
}
REQUEST_KEYS = {
    "schema_version",
    "document_type",
    "task",
    "invocations",
    "readiness_minimum",
    "required_capabilities",
    "allowed_skills",
    "required_skills",
    "trust_profile",
    "trust_ceiling",
    "verification_kinds",
}
INVOCATION_KEYS = {"id", "role", "harness", "permissions"}


def _digest(value: Any) -> str:
    raw = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    return hashlib.sha256(raw).hexdigest()


def _keys(data: Any, allowed: set[str], name: str) -> dict:
    if not isinstance(data, dict):
        raise TypeError(f"{name} must be an object")
    unknown = set(data) - allowed
    if unknown:
        raise ValueError(f"unknown {name} keys: {', '.join(sorted(unknown))}")
    return data


def _string(data: dict, key: str, name: str, *, required: bool = False) -> str | None:
    if key not in data and not required:
        return None
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name}.{key} must be a non-empty string")
    return value


def _names(data: dict, key: str, name: str) -> list[str] | None:
    if key not in data:
        return None
    value = data[key]
    if not isinstance(value, list) or any(
        not isinstance(x, str) or not x for x in value
    ):
        raise ValueError(f"{name}.{key} must be an array of non-empty strings")
    if len(value) != len(set(value)):
        raise ValueError(f"{name}.{key} contains duplicates")
    return sorted(value)


def _readiness_level(value: str | None) -> str:
    level = value or "unaware"
    load_spec().level(level)
    return level


def _header(data: dict, document_type: str, name: str) -> None:
    if data.get("schema_version") != "1" or data.get("document_type") != document_type:
        raise ValueError(
            f"{name} requires schema_version=1 and document_type={document_type}"
        )


def load_profile(root: str | Path) -> dict[str, Any]:
    path = repo_root(root) / ".agentic" / "profile.toml"
    if not path.exists():
        return {"schema_version": "1", "document_type": PROFILE_TYPE, "permissions": {}}
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ValueError(f"invalid repository profile: {exc}") from exc
    _keys(raw, PROFILE_KEYS, "profile")
    _header(raw, PROFILE_TYPE, "profile")
    result: dict[str, Any] = {"schema_version": "1", "document_type": PROFILE_TYPE}
    for key in ("preferred_harness", "readiness_minimum", "trust_ceiling"):
        value = _string(raw, key, "profile")
        if value is not None:
            result[key] = value
    if result.get("preferred_harness") not in (None, *HARNESSES):
        raise ValueError("unknown preferred harness")
    _readiness_level(result.get("readiness_minimum"))
    if result.get("trust_ceiling") is not None:
        trust.get_profile(result["trust_ceiling"])
    for key in ("required_capabilities", "allowed_skills", "required_skills"):
        names = _names(raw, key, "profile")
        if names is not None:
            result[key] = names
    result["permissions"] = validate_ceilings(raw.get("permissions", {}))
    return result


def load_request(path: str | Path) -> dict[str, Any]:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid session request: {exc}") from exc
    return validate_request(raw)


def validate_request(raw: Any) -> dict[str, Any]:
    data = _keys(raw, REQUEST_KEYS, "request")
    _header(data, REQUEST_TYPE, "request")
    result: dict[str, Any] = {
        "schema_version": "1",
        "document_type": REQUEST_TYPE,
        "task": _string(data, "task", "request", required=True),
    }
    for key in ("readiness_minimum", "trust_profile", "trust_ceiling"):
        value = _string(data, key, "request")
        if value is not None:
            result[key] = value
    _readiness_level(result.get("readiness_minimum"))
    for key in ("trust_profile", "trust_ceiling"):
        if key in result:
            trust.get_profile(result[key])
    for key in (
        "required_capabilities",
        "allowed_skills",
        "required_skills",
        "verification_kinds",
    ):
        names = _names(data, key, "request")
        if names is not None:
            result[key] = names
    if set(result.get("verification_kinds", [])) - set(FULL_KINDS):
        raise ValueError("unknown verification kinds")
    invocations = data.get("invocations")
    if not isinstance(invocations, list) or not invocations:
        raise ValueError("request.invocations must be a non-empty array")
    normalized = []
    for item in invocations:
        _keys(item, INVOCATION_KEYS, "invocation")
        name = _string(item, "id", "invocation", required=True)
        role = _string(item, "role", "invocation", required=True)
        if role not in ROLES:
            raise ValueError(f"unknown invocation role: {role}")
        harness = _string(item, "harness", "invocation")
        if harness is not None and harness not in HARNESSES:
            raise ValueError(f"unknown harness: {harness}")
        invocation = {
            "id": name,
            "role": role,
            "permissions": validate_bounds(role, item.get("permissions", {})),
        }
        if harness is not None:
            invocation["harness"] = harness
        normalized.append(invocation)
    if len({item["id"] for item in normalized}) != len(normalized):
        raise ValueError("duplicate invocation ids")
    if sum(item["role"] == "implementer" for item in normalized) != 1:
        raise ValueError("request requires exactly one implementer invocation")
    result["invocations"] = sorted(normalized, key=lambda item: item["id"])
    return result


def _commit(root: Path) -> str | None:
    completed = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.stdout.strip() if completed.returncode == 0 else None


def _skill_catalog() -> tuple[dict[str, skills.Skill], dict[str, dict[str, str]]]:
    catalog = {item.name: item for item in skills.load_registry()}
    digests: dict[str, dict[str, str]] = {}
    for name, item in sorted(catalog.items()):
        try:
            content = skills.skill_content(name)
            digests[name] = {
                "provider": item.provider,
                "content_digest": hashlib.sha256(content.encode()).hexdigest(),
            }
        except (OSError, KeyError):
            # A missing provider file is a missing skill, not an empty skill.
            continue
    return catalog, digests


def _provider_facts() -> list[dict]:
    facts = []
    for record in providers.installed():
        item = {"registration": record}
        try:
            item["source"] = providers.verify_provider(record["name"])
        except (OSError, ValueError) as exc:
            item["source"] = {"error": str(exc)}
        facts.append(item)
    return facts


def _environment_tools(root: Path) -> list[dict[str, Any]]:
    """Report environment navigation tools without local binary paths."""

    available = tool_status()
    return [
        {
            "name": "serena",
            "available": available["serena"]["available"],
            "configured": (root / ".serena" / "project.yml").is_file(),
        },
        {
            "name": "codegraph",
            "available": available["codegraph"]["available"],
            "configured": (root / ".codegraph").is_dir(),
        },
    ]


def _block(code: str, detail: str, **extra: str) -> dict[str, str]:
    return {"code": code, "detail": detail, **extra}


def _allowed(profile: dict, request: dict) -> set[str] | None:
    bounds = [
        set(item["allowed_skills"])
        for item in (profile, request)
        if "allowed_skills" in item
    ]
    return set.intersection(*bounds) if bounds else None


def _trust_resolution(
    root: Path, profile: dict, request: dict
) -> tuple[dict, list[dict[str, str]]]:
    selected = request.get("trust_profile") or trust.current_profile_name(root)
    active = trust.get_profile(selected)
    limits = [
        item["trust_ceiling"] for item in (profile, request) if "trust_ceiling" in item
    ]
    blockers = []
    for ceiling_name in limits:
        ceiling = trust.get_profile(ceiling_name)
        if not active.permissions <= ceiling.permissions:
            blockers.append(
                _block(
                    "trust-ceiling",
                    f"trust profile {selected} exceeds ceiling {ceiling_name}",
                )
            )
    return {
        "profile": selected,
        "permissions": sorted(active.permissions),
        "ceilings": sorted(limits),
    }, blockers


def plan_session(
    root: str | Path, request: dict, *, harness_facts: dict[str, dict] | None = None
) -> dict:
    """Resolve a validated request without changing repository or global state.

    ``harness_facts`` is an internal test seam. The CLI always probes the local
    harnesses and never takes caller-supplied enforcement claims.
    """

    root_path = repo_root(root)
    request = validate_request(request)
    profile = load_profile(root_path)
    spec = load_spec()
    readiness_levels = [
        spec.level(_readiness_level(item.get("readiness_minimum")))
        for item in (profile, request)
    ]
    minimum_readiness = max(readiness_levels, key=lambda item: item.rank).id
    readiness = verify_readiness(root_path, target=minimum_readiness, scope="local")
    blockers: list[dict[str, str]] = []
    if not readiness["passed"]:
        blockers.append(
            _block(
                "readiness",
                f"readiness {readiness['maturity']['current']} is below {minimum_readiness}",
            )
        )

    catalog, skill_digests = _skill_catalog()
    required_skills = set(profile.get("required_skills", [])) | set(
        request.get("required_skills", [])
    )
    allowed = _allowed(profile, request)
    context = detect_repo(root_path)
    recommended = {
        item.skill.name
        for item in skills.recommend(context, task=request["task"])
        if item.recommended
    }
    selected_names = required_skills | recommended
    if allowed is not None:
        selected_names &= allowed
    for name in sorted(required_skills):
        if allowed is not None and name not in allowed:
            blockers.append(
                _block(
                    "skill-disallowed",
                    f"required skill {name} is outside the allowed set",
                )
            )
        if name not in skill_digests:
            blockers.append(
                _block("skill-missing", f"required skill {name} is unavailable")
            )
    selected = [
        {"name": name, **skill_digests[name]}
        for name in sorted(selected_names & skill_digests.keys())
    ]
    not_exposed = sorted(set(catalog) - {item["name"] for item in selected})

    capability_state = capabilities.status()
    required_capabilities = set(profile.get("required_capabilities", [])) | set(
        request.get("required_capabilities", [])
    )
    recommended_caps = {
        item.name for item in capabilities.suggest(context, request["task"])
    }
    chosen_caps = required_capabilities | {
        name
        for name in recommended_caps
        if capability_state.get(name, {}).get("enabled")
    }
    for name in sorted(required_capabilities):
        if not capability_state.get(name, {}).get("enabled"):
            blockers.append(
                _block(
                    "capability-disabled", f"required capability {name} is not enabled"
                )
            )
    selected_capabilities = sorted(
        name for name in chosen_caps if capability_state.get(name, {}).get("enabled")
    )

    resolved_trust, trust_blockers = _trust_resolution(root_path, profile, request)
    blockers.extend(trust_blockers)
    for name in selected_capabilities:
        missing = set(capability_state[name]["required_permissions"]) - set(
            resolved_trust["permissions"]
        )
        if missing:
            blockers.append(
                _block(
                    "capability-trust",
                    f"capability {name} lacks trust permissions: {', '.join(sorted(missing))}",
                )
            )

    facts = (
        harness_facts
        if harness_facts is not None
        else {
            name: inspect_harness(name)
            for name in sorted(
                {
                    item.get("harness") or profile.get("preferred_harness") or "codex"
                    for item in request["invocations"]
                }
            )
        }
    )
    invocations = []
    for item in request["invocations"]:
        name = item["id"]
        harness = item.get("harness") or profile.get("preferred_harness") or "codex"
        fact = facts[harness]
        effective, conflicts = compose(
            name, item["role"], item["permissions"], profile["permissions"]
        )
        blockers.extend(block.document() for block in conflicts)
        if not fact["available"]:
            blockers.append(
                _block(
                    "harness-unavailable",
                    f"harness {harness} is unavailable",
                    invocation=name,
                )
            )
        permissions = {}
        for dimension in LEVELS:
            level = effective[dimension]["level"]
            detail = fact["permissions"][dimension][level]
            permissions[dimension] = {
                "requested": item["permissions"][dimension],
                "effective": effective[dimension],
                "enforceable": detail["status"],
                "enforcement": {
                    "mechanism": detail["mechanism"],
                    "evidence": detail["evidence"],
                    "probe_id": detail.get("probe_id"),
                },
            }
            if detail["status"] != "enforceable":
                blockers.append(
                    _block(
                        "permission-unenforceable",
                        f"{dimension}={level} on {harness} is {detail['status']}",
                        invocation=name,
                        dimension=dimension,
                    )
                )
        invocations.append(
            {
                "id": name,
                "role": item["role"],
                "harness": harness,
                "version": fact["version"],
                "permissions": permissions,
            }
        )

    environment_tools = _environment_tools(root_path)
    inputs = {
        "commit": _commit(root_path),
        "profile": profile,
        "skill_catalog": {
            name: {"metadata": asdict(item), "content": skill_digests.get(name)}
            for name, item in sorted(catalog.items())
        },
        "providers": _provider_facts(),
        "capabilities": capability_state,
        "trust": trust.document(root_path),
        "harnesses": facts,
        "contracts": contracts.document(),
        "readiness": {
            key: value for key, value in readiness.items() if key != "repository"
        },
        "environment_tools": environment_tools,
        "repository_facts": sorted(context.facts),
        "repository_evidence": context.evidence,
        "spec": spec.identity(),
    }
    plan = {
        "schema_version": "1",
        "document_type": PLAN_TYPE,
        "status": "blocked" if blockers else "ready",
        "repository": str(root_path),
        "request": request,
        "task": request["task"],
        "readiness": {
            "minimum": minimum_readiness,
            "current": readiness["maturity"]["current"],
            "met": readiness["passed"],
        },
        "skills": {"selected": selected, "not_exposed": not_exposed},
        "capabilities": selected_capabilities,
        "trust": resolved_trust,
        "tools": environment_tools,
        "invocations": invocations,
        "verification_kinds": request.get("verification_kinds", []),
        "isolation": {
            "workspace_required": True,
            "workspace_created": False,
            "writable_scope": "prepared-workspace",
        },
        "visibility": {"status": "undetermined"},
        "blockers": sorted(
            blockers,
            key=lambda item: (
                item["code"],
                item.get("invocation", ""),
                item.get("dimension", ""),
                item["detail"],
            ),
        ),
        "request_digest": _digest(request),
        "inputs_digest": _digest(inputs),
    }
    # The repository path locates this checkout but is not part of approval's
    # semantic identity; S2 may prepare the same plan in a separate worktree.
    plan["plan_digest"] = _digest(
        {key: value for key, value in plan.items() if key != "repository"}
    )
    return plan
