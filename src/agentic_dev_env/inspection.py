from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from . import __version__
from .capabilities import status as capability_status
from .detect import RepoContext, detect_repo
from .integrations import status as integration_status
from .execution import status as execution_status
from .infrastructure import status as infrastructure_status
from .compatibility import document as compatibility_document
from .providers import provider_document
from .remotes import document as remote_document
from .skills import installed_skills, recommend
from .trust import document as trust_document

SCHEMA_VERSION = "1"

CORE_TOOLS = (
    "git", "gh", "rg", "fd", "ast-grep", "serena", "codegraph",
    "repomix", "mise", "uv", "jq", "yq", "just",
)
AGENT_TOOLS = ("claude", "codex", "pi")


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


def _command(root: Path, name: str) -> str | None:
    for makefile in ("Makefile", "makefile", "GNUmakefile"):
        path = root / makefile
        if path.exists():
            text = path.read_text(errors="ignore")
            if any(line.startswith(f"{name}:") for line in text.splitlines()):
                return f"make {name}"
    return None


def discover_commands(root: Path) -> dict[str, list[str]]:
    commands: dict[str, list[str]] = {
        "install": [], "test": [], "lint": [], "format": [],
        "typecheck": [], "build": [],
    }

    aliases = {"format": ("fmt", "format")}
    for key in ("test", "lint", "typecheck", "build"):
        value = _command(root, key)
        if value:
            commands[key].append(value)
    for candidate in aliases["format"]:
        value = _command(root, candidate)
        if value:
            commands["format"].append(value)
            break

    if (root / "go.mod").exists():
        commands["install"].append("go mod download")
        commands["test"].append("go test ./...")
        commands["format"].append("gofmt -w <changed-go-files>")
        commands["build"].append("go build ./...")

    if (root / "Cargo.toml").exists():
        commands["install"].append("cargo fetch")
        commands["test"].append("cargo test")
        commands["lint"].append("cargo clippy --all-targets --all-features")
        commands["format"].append("cargo fmt --all")
        commands["build"].append("cargo build")

    pyproject = root / "pyproject.toml"
    if pyproject.exists():
        text = pyproject.read_text(errors="ignore").lower()
        if (root / "poetry.lock").exists():
            commands["install"].append("poetry install")
        elif (root / "pdm.lock").exists():
            commands["install"].append("pdm install")
        else:
            commands["install"].append("uv sync")
        if "pytest" in text or "[tool.pytest" in text:
            commands["test"].append("uv run pytest")
        if "ruff" in text:
            commands["lint"].append("uv run ruff check .")
            commands["format"].append("uv run ruff format .")
        if "mypy" in text:
            commands["typecheck"].append("uv run mypy .")
        if "pyright" in text or "basedpyright" in text:
            commands["typecheck"].append("uv run pyright")
    elif (root / "requirements.txt").exists():
        commands["install"].append("uv venv && uv pip install -r requirements.txt")

    package = root / "package.json"
    if package.exists():
        try:
            data = json.loads(package.read_text(errors="ignore"))
        except json.JSONDecodeError:
            data = {}
        if (root / "pnpm-lock.yaml").exists():
            pm, install = "pnpm", "pnpm install --frozen-lockfile"
        elif (root / "yarn.lock").exists():
            pm, install = "yarn", "yarn install --immutable"
        elif (root / "bun.lock").exists() or (root / "bun.lockb").exists():
            pm, install = "bun", "bun install --frozen-lockfile"
        else:
            pm, install = "npm", "npm ci"
        commands["install"].append(install)
        scripts = data.get("scripts") or {}
        for key in ("test", "lint", "format", "typecheck", "build"):
            if key in scripts:
                commands[key].append(f"npm run {key}" if pm == "npm" else f"{pm} {key}")

    if (root / "gradlew").exists():
        commands["install"].append("./gradlew dependencies")
        commands["test"].append("./gradlew test")
        commands["build"].append("./gradlew build")
    if (root / "mvnw").exists():
        commands["install"].append("./mvnw dependency:go-offline")
        commands["test"].append("./mvnw test")
        commands["build"].append("./mvnw package")
    if (root / "Gemfile").exists():
        commands["install"].append("bundle install")
    if (root / "composer.json").exists():
        commands["install"].append("composer install")

    return {key: list(dict.fromkeys(values)) for key, values in commands.items()}


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
        "compatibility": compatibility_document(),
        "providers": provider_document(),
        "remotes": remote_document(),
    }


def inspect_repository(path: str | Path = ".", task: str = "") -> dict[str, Any]:
    context = detect_repo(path)
    root = context.root
    skill_recs = recommend(context, task=task)
    installed = installed_skills(root)
    cap_state = capability_status()

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
        "commands": discover_commands(root),
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
        "providers": provider_document(),
        "remotes": remote_document(),
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
