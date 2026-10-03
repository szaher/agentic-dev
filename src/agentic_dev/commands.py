"""Canonical command discovery: the one place Agentic Dev learns how to build,
test, lint, format, typecheck, and install a repository.

``repo inspect``, readiness assessment, and verification all consume
:func:`discover`. Discovery only reads root-level repository metadata; it never
executes anything. Results are deterministic: kinds appear in ``KINDS`` order
and commands within a kind in rule order below, without duplicates.

Discovery reads through a :class:`FileView` so callers decide what is visible.
:class:`WorkingTree` sees the checkout; readiness passes a view that can be
limited to tracked files (its ``ci`` scope).
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Protocol

KINDS = ("install", "build", "test", "lint", "format", "typecheck")
MAKEFILES = ("Makefile", "makefile", "GNUmakefile")
MAX_FILE_BYTES = 1_000_000


@dataclass(frozen=True)
class Command:
    kind: str
    command: str
    source: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


class FileView(Protocol):
    def is_file(self, rel: str) -> bool: ...
    def text(self, rel: str) -> str: ...
    def root_files(self) -> list[str]: ...


class WorkingTree:
    """Root-level files of a checkout, matched with exact case, never escaping the root."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        try:
            self._names = frozenset(os.listdir(self.root))
        except OSError:
            self._names = frozenset()

    def _path(self, rel: str) -> Path | None:
        if "/" in rel or rel in {"", ".", ".."} or rel not in self._names:
            return None
        path = self.root / rel
        try:
            path.resolve().relative_to(self.root.resolve())
        except (OSError, ValueError):
            return None
        return path

    def is_file(self, rel: str) -> bool:
        path = self._path(rel)
        return bool(path and path.is_file())

    def text(self, rel: str) -> str:
        path = self._path(rel)
        try:
            if path and path.is_file() and path.stat().st_size <= MAX_FILE_BYTES:
                return path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            pass
        return ""

    def root_files(self) -> list[str]:
        return sorted(name for name in self._names if self.is_file(name))


def _make_target(text: str, names: Iterable[str]) -> str | None:
    for name in names:
        if re.search(rf"^{re.escape(name)}[ \t]*:(?!=)", text, re.MULTILINE):
            return name
    return None


def _just_recipe(text: str, names: Iterable[str]) -> str | None:
    for name in names:
        if re.search(rf"^@?{re.escape(name)}\b[^:=\n]*:(?!=)", text, re.MULTILINE):
            return name
    return None


# (kind, candidate target/script names); the first name present wins.
_TASK_TARGETS = (
    ("build", ("build",)),
    ("test", ("test", "check")),
    ("lint", ("lint",)),
    ("format", ("fmt", "format")),
    ("typecheck", ("typecheck", "type-check")),
)
_SCRIPT_NAMES = (
    ("build", ("build",)),
    ("test", ("test",)),
    ("lint", ("lint",)),
    ("format", ("format", "fmt")),
    ("typecheck", ("typecheck", "type-check")),
)


def discover(view: FileView) -> list[Command]:
    """Every discoverable command, deterministic and without duplicates."""

    found: list[Command] = []

    def add(kind: str, command: str, source: str) -> None:
        item = Command(kind, command, source)
        if not any(c.kind == kind and c.command == command for c in found):
            found.append(item)

    exists = view.is_file

    # Task runners: the project's own entry points come first.
    makefile = next((m for m in MAKEFILES if exists(m)), None)
    if makefile:
        text = view.text(makefile)
        for kind, names in _TASK_TARGETS:
            if target := _make_target(text, names):
                add(kind, f"make {target}", makefile)
    if exists("justfile"):
        text = view.text("justfile")
        for kind, names in _TASK_TARGETS:
            if recipe := _just_recipe(text, names):
                add(kind, f"just {recipe}", "justfile")

    # Go
    if exists("go.mod"):
        add("install", "go mod download", "go.mod")
        add("test", "go test ./...", "go.mod")
        add("format", "gofmt -w <changed-go-files>", "go.mod")
        add("build", "go build ./...", "go.mod")

    # Rust
    if exists("Cargo.toml"):
        add("install", "cargo fetch", "Cargo.toml")
        add("test", "cargo test", "Cargo.toml")
        add("lint", "cargo clippy --all-targets --all-features", "Cargo.toml")
        add("format", "cargo fmt --all", "Cargo.toml")
        add("build", "cargo build", "Cargo.toml")

    # Python
    pyproject = view.text("pyproject.toml").lower() if exists("pyproject.toml") else ""
    if exists("pyproject.toml"):
        if exists("poetry.lock"):
            add("install", "poetry install", "poetry.lock")
        elif exists("pdm.lock"):
            add("install", "pdm install", "pdm.lock")
        else:
            add("install", "uv sync", "pyproject.toml")
        if re.search(r"^\s*\[build-system\]", pyproject, re.MULTILINE):
            add("build", "python -m build", "pyproject.toml")
        if "ruff" in pyproject:
            add("lint", "uv run ruff check .", "pyproject.toml")
            add("format", "uv run ruff format .", "pyproject.toml")
        for tool in ("flake8", "pylint"):
            if tool in pyproject:
                add("lint", tool, "pyproject.toml")
        if "black" in pyproject:
            add("format", "black .", "pyproject.toml")
        if "mypy" in pyproject:
            add("typecheck", "uv run mypy .", "pyproject.toml")
        if "pyright" in pyproject or "basedpyright" in pyproject:
            add("typecheck", "uv run pyright", "pyproject.toml")
    elif exists("requirements.txt"):
        add("install", "uv venv && uv pip install -r requirements.txt", "requirements.txt")

    # One pytest command: pyproject wins, otherwise the first file that declares it.
    if "pytest" in pyproject:
        add("test", "uv run pytest", "pyproject.toml")
    else:
        declared = [name for name in ("setup.cfg", "tox.ini") if exists(name) and "pytest" in view.text(name).lower()]
        declared += [name for name in view.root_files()
                     if re.fullmatch(r"requirements.*\.txt", name) and "pytest" in view.text(name).lower()]
        declared += [name for name in ("pytest.ini", "conftest.py") if exists(name)]
        if declared:
            add("test", "pytest", declared[0])
    if exists("tox.ini"):
        add("test", "tox", "tox.ini")
    if exists("noxfile.py"):
        add("test", "nox", "noxfile.py")

    # JavaScript / TypeScript
    if exists("package.json"):
        try:
            data = json.loads(view.text("package.json") or "{}")
        except json.JSONDecodeError:
            data = {}
        scripts = data.get("scripts") if isinstance(data, dict) else None
        scripts = scripts if isinstance(scripts, dict) else {}
        if exists("pnpm-lock.yaml"):
            install, run = "pnpm install --frozen-lockfile", "pnpm {}"
        elif exists("yarn.lock"):
            install, run = "yarn install --immutable", "yarn {}"
        elif exists("bun.lock") or exists("bun.lockb"):
            install, run = "bun install --frozen-lockfile", "bun run {}"
        else:
            install, run = "npm ci", "npm run {}"
        add("install", install, "package.json")
        for kind, names in _SCRIPT_NAMES:
            name = next((n for n in names if n in scripts), None)
            if name:
                add(kind, run.format(name), "package.json")

    # JVM
    if exists("gradlew"):
        add("install", "./gradlew dependencies", "gradlew")
        add("test", "./gradlew test", "gradlew")
        add("build", "./gradlew build", "gradlew")
    else:
        for name in ("build.gradle", "build.gradle.kts"):
            if exists(name):
                add("test", "gradle test", name)
                add("build", "gradle build", name)
                break
    if exists("mvnw"):
        add("install", "./mvnw dependency:go-offline", "mvnw")
        add("test", "./mvnw test", "mvnw")
        add("build", "./mvnw package", "mvnw")
    elif exists("pom.xml"):
        add("test", "mvn test", "pom.xml")
        add("build", "mvn package", "pom.xml")

    # C/C++, Swift, Ruby, PHP
    if exists("CMakeLists.txt"):
        add("build", "cmake --build build", "CMakeLists.txt")
        if re.search(r"\b(enable_testing|add_test)\s*\(", view.text("CMakeLists.txt"), re.IGNORECASE):
            add("test", "ctest", "CMakeLists.txt")
    if exists("Package.swift"):
        add("build", "swift build", "Package.swift")
        add("test", "swift test", "Package.swift")
    if exists("Gemfile"):
        add("install", "bundle install", "Gemfile")
    if exists("Rakefile"):
        add("test", "rake test", "Rakefile")
    if exists(".rspec"):
        add("test", "rspec", ".rspec")
    if exists("composer.json"):
        add("install", "composer install", "composer.json")
        if re.search(r'"test"\s*:', view.text("composer.json")):
            add("test", "composer test", "composer.json")

    order = {kind: index for index, kind in enumerate(KINDS)}
    return sorted(found, key=lambda c: order[c.kind])  # stable: rule order within a kind


def by_kind(commands: Iterable[Command]) -> dict[str, list[str]]:
    """The ``repo inspect`` ``commands`` map: every kind present, commands in order."""

    grouped: dict[str, list[str]] = {kind: [] for kind in KINDS}
    for command in commands:
        grouped[command.kind].append(command.command)
    return grouped


def discover_in(root: str | Path) -> list[Command]:
    return discover(WorkingTree(root))


def as_documents(commands: Iterable[Command]) -> list[dict[str, Any]]:
    return [command.to_dict() for command in commands]
