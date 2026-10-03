from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from . import __version__
from .capabilities import status as capability_status
from .commands import as_documents, by_kind, discover_in
from .detect import RepoContext, detect_repo
from .integrations import status as integration_status
from .execution import status as execution_status
from .infrastructure import status as infrastructure_status
from .skills import installed_skills, recommend
from .providers import doctor as provider_doctor
from .remote import status as remote_status
from .metrics import status as metrics_status
from .trust import document as trust_document

SCHEMA_VERSION = "1"

CORE_TOOLS = (
    "git", "gh", "rg", "fd", "ast-grep", "serena", "codegraph",
    "repomix", "mise", "uv", "jq", "yq", "just",
)
AGENT_TOOLS = ("claude", "codex", "pi", "opencode")


def _package_managers(root: Path) -> list[str]:
    checks = [
        ("uv", "uv.lock"),
        ("poetry", "poetry.lock"),
        ("pdm", "pdm.lock"),
        ("pnpm", "pnpm-lock.yaml"),
        ("yarn", "yarn.lock"),
        ("npm", "package-lock.json"),
        ("cargo", "Cargo.toml"),
        ("go-modules", "go.mod"),
        ("bundler", "Gemfile"),
        ("composer", "composer.json"),
        ("maven-wrapper", "mvnw"),
        ("gradle-wrapper", "gradlew"),
        ("maven", "pom.xml"),
    ]
    found = [name for name, filename in checks if (root / filename).exists()]
    if (root / "build.gradle").exists() or (root / "build.gradle.kts").exists():
        found.append("gradle-wrapper" if (root / "gradlew").exists() else "gradle")
    if (root / "bun.lock").exists() or (root / "bun.lockb").exists():
        found.append("bun")
    return sorted(set(found))


def _group_facts(context: RepoContext) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for fact in sorted(context.facts):
        kind, _, value = fact.partition(":")
        grouped.setdefault(kind, []).append(value)
    return {key: sorted(values) for key, values in sorted(grouped.items())}


def tool_status() -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for name in (*CORE_TOOLS, *AGENT_TOOLS):
        path = shutil.which(name)
        result[name] = {"available": bool(path), "path": path}
    return result


def doctor_document() -> dict[str, Any]:
    tools = tool_status()
    integrations = [
        {
            "name": item.name,
            "available": item.available,
            "configured": item.configured,
            "detail": item.detail,
        }
        for item in integration_status()
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "document_type": "agentic.doctor",
        "agentic_version": __version__,
        "tools": tools,
        "integrations": integrations,
        "capabilities": capability_status(),
        "trust": trust_document(),
        "execution": execution_status(),
        "infrastructure": infrastructure_status(),
        "providers": provider_doctor(),
        "remotes": remote_status(),
        "metrics": metrics_status(),
    }


def inspect_repository(path: str | Path = ".", task: str = "") -> dict[str, Any]:
    context = detect_repo(path)
    root = context.root
    skill_recs = recommend(context, task=task)
    installed = installed_skills(root)
    cap_state = capability_status()
    commands = discover_in(root)

    return {
        "schema_version": SCHEMA_VERSION,
        "document_type": "agentic.repo-inspection",
        "agentic_version": __version__,
        "repository": {
            "name": root.name,
            "root": str(root),
            "facts": sorted(context.facts),
            "facts_by_type": _group_facts(context),
            "evidence": {
                key: sorted(values)
                for key, values in sorted(context.evidence.items())
            },
            "package_managers": _package_managers(root),
        },
        "commands": by_kind(commands),
        "discovered_commands": as_documents(commands),
        "skills": {
            "installed": installed,
            "recommended": [
                {
                    "name": rec.skill.name,
                    "category": rec.skill.category,
                    "description": rec.skill.description,
                    "score": rec.score,
                    "recommended": rec.recommended,
                    "reasons": rec.reasons,
                }
                for rec in skill_recs
            ],
        },
        "capabilities": cap_state,
        "trust": trust_document(root),
        "execution": execution_status(root),
        "infrastructure": infrastructure_status(root),
        "providers": provider_doctor(),
        "remotes": remote_status(),
        "integrations": [
            {
                "name": item.name,
                "available": item.available,
                "configured": item.configured,
                "detail": item.detail,
            }
            for item in integration_status()
        ],
    }
