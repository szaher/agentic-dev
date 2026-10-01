from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class RepoContext:
    root: Path
    facts: set[str] = field(default_factory=set)
    evidence: dict[str, list[str]] = field(default_factory=dict)

    def add(self, fact: str, reason: str) -> None:
        self.facts.add(fact)
        self.evidence.setdefault(fact, [])
        if reason not in self.evidence[fact]:
            self.evidence[fact].append(reason)


def repo_root(path: str | Path) -> Path:
    p = Path(path).expanduser().resolve()
    try:
        out = subprocess.run(
            ["git", "-C", str(p), "rev-parse", "--show-toplevel"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        return Path(out)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return p


def _text(path: Path, limit: int = 2_000_000) -> str:
    try:
        return path.read_text(errors="ignore")[:limit]
    except OSError:
        return ""


def _glob(root: Path, pattern: str, limit: int = 1) -> list[Path]:
    ignored = {".git", ".venv", "node_modules", "vendor", "target", "dist", "build"}
    found: list[Path] = []
    try:
        for p in root.glob(pattern):
            if any(part in ignored for part in p.parts):
                continue
            found.append(p)
            if len(found) >= limit:
                break
    except OSError:
        pass
    return found


def detect_repo(path: str | Path = ".") -> RepoContext:
    root = repo_root(path)
    c = RepoContext(root=root)

    pyproject = root / "pyproject.toml"
    requirements = root / "requirements.txt"
    if pyproject.exists() or requirements.exists() or _glob(root, "**/*.py"):
        c.add("language:python", "Python project/source detected")
        py = _text(pyproject) + "\n" + _text(requirements)
        for dep, fact in [
            ("fastapi", "framework:fastapi"),
            ("django", "framework:django"),
            ("flask", "framework:flask"),
            ("pytest", "testing:pytest"),
            ("sqlalchemy", "database:sqlalchemy"),
            ("alembic", "database:migrations"),
            ("psycopg", "database:postgresql"),
            ("asyncpg", "database:postgresql"),
        ]:
            if dep in py.lower():
                c.add(fact, f"{dep} declared in Python project metadata")

    gomod = root / "go.mod"
    if gomod.exists() or _glob(root, "**/*.go"):
        c.add("language:go", "go.mod or Go source detected")
        go = _text(gomod)
        if "sigs.k8s.io/controller-runtime" in go or "k8s.io/apimachinery" in go:
            c.add("technology:kubernetes", "Kubernetes Go dependencies detected")
        if "sigs.k8s.io/controller-runtime" in go:
            c.add("repo-type:kubernetes-operator", "controller-runtime dependency detected")

    cargo = root / "Cargo.toml"
    if cargo.exists() or _glob(root, "**/*.rs"):
        c.add("language:rust", "Cargo.toml or Rust source detected")

    package = root / "package.json"
    if package.exists():
        c.add("language:typescript", "package.json detected")
        try:
            data = json.loads(_text(package))
        except json.JSONDecodeError:
            data = {}
        deps = {}
        deps.update(data.get("dependencies") or {})
        deps.update(data.get("devDependencies") or {})
        scripts = data.get("scripts") or {}
        for dep, fact in [
            ("@angular/core", "framework:angular"),
            ("svelte", "framework:svelte"),
            ("vue", "framework:vue"),
            ("react", "framework:react"),
            ("next", "framework:nextjs"),
            ("express", "framework:express"),
            ("fastify", "framework:fastify"),
            ("vitest", "testing:javascript"),
            ("jest", "testing:javascript"),
        ]:
            if dep in deps:
                c.add(fact, f"{dep} dependency detected")
        if "test" in scripts:
            c.add("testing:javascript", "package.json test script detected")

    if any((root / name).exists() for name in ["pom.xml", "build.gradle", "build.gradle.kts", "gradlew", "mvnw"]):
        c.add("language:jvm", "JVM build metadata detected")

    if (root / "CMakeLists.txt").exists() or _glob(root, "**/*.cpp") or _glob(root, "**/*.cc"):
        c.add("language:cpp", "C/C++ build/source detected")

    if (root / "Gemfile").exists() or _glob(root, "**/*.rb"):
        c.add("language:ruby", "Ruby project/source detected")

    if (root / "composer.json").exists() or _glob(root, "**/*.php"):
        c.add("language:php", "PHP project/source detected")

    if (root / "Package.swift").exists() or _glob(root, "**/*.swift"):
        c.add("language:swift", "Swift project/source detected")

    if _glob(root, "**/*.tf", 3):
        c.add("technology:terraform", "Terraform files detected")

    if _glob(root, "**/*.sh", 3):
        c.add("language:shell", "Shell scripts detected")

    if any((root / p).exists() for p in ["Dockerfile", "compose.yml", "docker-compose.yml"]):
        c.add("technology:containers", "Container build/compose files detected")

    if (root / "Chart.yaml").exists() or (root / "charts").is_dir():
        c.add("technology:helm", "Helm chart detected")
        c.add("technology:kubernetes", "Helm implies Kubernetes deployment")

    if any((root / p).exists() for p in ["kustomization.yaml", "kustomization.yml"]):
        c.add("technology:kustomize", "Kustomize configuration detected")
        c.add("technology:kubernetes", "Kustomize implies Kubernetes deployment")

    k8s_dirs = [root / "config" / "crd", root / "deploy", root / "manifests"]
    if any(p.exists() for p in k8s_dirs):
        c.add("technology:kubernetes", "Kubernetes manifest/config directory detected")
    if (root / "config" / "crd").exists() and (root / "config" / "rbac").exists():
        c.add("repo-type:kubernetes-operator", "config/crd and config/rbac detected")

    workflows = root / ".github" / "workflows"
    if workflows.is_dir() and list(workflows.glob("*.y*ml")):
        c.add("ci:github-actions", ".github/workflows detected")

    if (root / "tests").is_dir() or (root / "test").is_dir():
        c.add("workflow:testing", "tests/test directory detected")

    migration_dirs = [root / "migrations", root / "alembic", root / "db" / "migrations"]
    if any(p.exists() for p in migration_dirs):
        c.add("database:migrations", "migration directory detected")

    # API shape signals.
    api_names = ["openapi.yaml", "openapi.yml", "openapi.json", "swagger.yaml", "swagger.yml"]
    if any((root / name).exists() for name in api_names):
        c.add("repo-type:api", "OpenAPI/Swagger document detected")
    if {"framework:fastapi", "framework:express", "framework:fastify"} & c.facts:
        c.add("repo-type:api", "HTTP API framework detected")

    # Public library/package signals.
    if pyproject.exists() and re.search(r"\[project\]", _text(pyproject)):
        c.add("repo-type:package", "Python package metadata detected")
    if cargo.exists():
        c.add("repo-type:package", "Cargo package metadata detected")

    return c
