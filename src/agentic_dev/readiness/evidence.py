"""Read-only, repository-scoped evidence collection for Agent Ready assessment.

Evidence semantics come from the spec's evidence vocabulary. Declarative
detections (path / heading / content) are interpreted generically. ``derived``
detections are implemented here, reusing Agentic Dev's existing inspection
intelligence where it matches the spec definition.

Nothing in this module writes to the repository, executes project commands, or
reads workstation state. Reported paths are repository-relative.
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path
from typing import Any, Callable, Iterable

from ..inspection import discover_commands
from .spec import SUPPORTED_DETECTIONS, Spec

MAX_ITEMS = 10
MAX_FILE_BYTES = 1_000_000
MAX_VALUE_CHARS = 160
REDACTED_CATEGORIES = frozenset({"mcp", "security"})
ATX_HEADING = re.compile(r"^ {0,3}(#{1,6})(?:[ \t]+(.*?))?(?:[ \t]+#+)?[ \t]*$")
FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
GIT_ENV = {**os.environ, "GIT_OPTIONAL_LOCKS": "0", "GIT_TERMINAL_PROMPT": "0"}


@dataclass(frozen=True)
class Observation:
    """The outcome for one evidence id. ``satisfied`` is None when unsupported."""

    id: str
    satisfied: bool | None
    items: tuple[dict[str, Any], ...] = ()
    total: int = 0
    note: str | None = None


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[bytes] | None:
    try:
        return subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True, check=False, env=GIT_ENV, timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return None


class Repository:
    """A read-only view over a repository checkout."""

    def __init__(self, root: Path, ignored: Iterable[str], literal_prefixes: Iterable[str]):
        self.root = root
        self.ignored = frozenset(ignored)
        # Hidden directories are only entered when a glob names them literally.
        self._hidden_allowed = frozenset(literal_prefixes)
        self._listdir_cache: dict[str, frozenset[str]] = {}
        self._text_cache: dict[str, list[str] | None] = {}

    @cached_property
    def is_git(self) -> bool:
        result = _git(self.root, "rev-parse", "--is-inside-work-tree")
        return bool(result and result.returncode == 0 and result.stdout.strip() == b"true")

    @cached_property
    def revision(self) -> str | None:
        if not self.is_git:
            return None
        result = _git(self.root, "rev-parse", "--verify", "--quiet", "HEAD")
        if result and result.returncode == 0:
            return result.stdout.decode().strip() or None
        return None

    @cached_property
    def tracked_files(self) -> tuple[str, ...] | None:
        if not self.is_git:
            return None
        result = _git(self.root, "ls-files", "-z", "--cached")
        if not result or result.returncode != 0:
            return None
        names = [item.decode("utf-8", "surrogateescape") for item in result.stdout.split(b"\0") if item]
        return tuple(sorted(set(names)))

    def _hidden_ok(self, rel: str) -> bool:
        return any(prefix == rel or prefix.startswith(rel + "/") or rel.startswith(prefix + "/")
                   for prefix in self._hidden_allowed)

    @cached_property
    def entries(self) -> tuple[tuple[str, bool], ...]:
        """(relative path, is_dir) for the worktree, sorted. Never follows directory symlinks."""

        found: list[tuple[str, bool]] = []
        stack = [""]
        while stack:
            rel_dir = stack.pop()
            try:
                with os.scandir(self.root / rel_dir if rel_dir else self.root) as it:
                    children = sorted(it, key=lambda e: e.name)
            except OSError:
                continue
            for entry in children:
                rel = f"{rel_dir}/{entry.name}" if rel_dir else entry.name
                try:
                    is_dir = entry.is_dir(follow_symlinks=False)
                except OSError:
                    continue
                if is_dir:
                    if entry.name in self.ignored:
                        continue
                    if entry.name.startswith(".") and not self._hidden_ok(rel):
                        continue
                    found.append((rel, True))
                    stack.append(rel)
                else:
                    found.append((rel, False))
        return tuple(sorted(found))

    def _list(self, rel_dir: str) -> frozenset[str]:
        if rel_dir not in self._listdir_cache:
            try:
                names = frozenset(os.listdir(self.root / rel_dir if rel_dir else self.root))
            except OSError:
                names = frozenset()
            self._listdir_cache[rel_dir] = names
        return self._listdir_cache[rel_dir]

    def exists_exact(self, rel: str) -> str | None:
        """Return "file"/"dir" if ``rel`` exists with exactly this case, else None."""

        parts = [part for part in rel.split("/") if part]
        if not parts or any(part in {".", ".."} for part in parts):
            return None
        current = ""
        for part in parts:
            if part not in self._list(current):
                return None
            current = f"{current}/{part}" if current else part
        path = self.root / current
        if path.is_symlink() and not self._inside(path):
            return None
        return "dir" if path.is_dir() else "file"

    def _inside(self, path: Path) -> bool:
        try:
            path.resolve().relative_to(self.root.resolve())
            return True
        except (OSError, ValueError):
            return False

    def lines(self, rel: str) -> list[str] | None:
        if rel not in self._text_cache:
            path = self.root / rel
            text: list[str] | None = None
            try:
                if path.is_file() and self._inside(path) and path.stat().st_size <= MAX_FILE_BYTES:
                    text = path.read_text(encoding="utf-8", errors="ignore").splitlines()
            except OSError:
                text = None
            self._text_cache[rel] = text
        return self._text_cache[rel]

    def text(self, rel: str) -> str:
        lines = self.lines(rel)
        return "\n".join(lines) if lines else ""


def _segment_regex(segment: str) -> str:
    parts = [re.escape(part) for part in segment.split("*")]
    body = "[^/]*".join(parts)
    return ("(?!\\.)" + body) if segment.startswith("*") else body


def compile_glob(glob: str, ignored: Iterable[str]) -> re.Pattern[str]:
    """Translate a spec glob into a regex implementing ``path_matching`` semantics."""

    ignored_alt = "|".join(re.escape(name) for name in sorted(ignored))
    traversable = f"(?!\\.)(?!(?:{ignored_alt})(?:/|$))[^/]+" if ignored_alt else "(?!\\.)[^/]+"
    segments = glob.split("/")
    out: list[str] = []
    for index, segment in enumerate(segments):
        last = index == len(segments) - 1
        if segment == "**":
            out.append(f"(?:{traversable}(?:/{traversable})*)?" if last else f"(?:{traversable}/)*")
        else:
            out.append(_segment_regex(segment) + ("" if last else "/"))
    return re.compile("^" + "".join(out) + "$")


def literal_prefix(glob: str) -> str:
    parts: list[str] = []
    for segment in glob.split("/")[:-1]:
        if "*" in segment:
            break
        parts.append(segment)
    return "/".join(parts)


def _clip(value: str) -> str:
    value = value.strip()
    return value if len(value) <= MAX_VALUE_CHARS else value[: MAX_VALUE_CHARS - 1] + "…"


def _item(evidence_id: str, value: str, source: str, line: int | None = None) -> dict[str, Any]:
    item: dict[str, Any] = {"type": evidence_id, "value": _clip(value), "source": source}
    if line is not None:
        item["line"] = line
    return item


def _observation(evidence_id: str, items: list[dict[str, Any]], note: str | None = None) -> Observation:
    ordered = sorted(items, key=lambda i: (i["source"], i.get("line", 0), i["value"]))
    return Observation(evidence_id, bool(ordered), tuple(ordered[:MAX_ITEMS]), len(ordered), note)


# ---------------------------------------------------------------- commands ---

_MAKEFILES = ("Makefile", "makefile", "GNUmakefile")
_COMMAND_KINDS = ("build", "format", "lint", "test", "typecheck")


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


def _command_source(repo: Repository, command: str) -> str:
    prefixes = [
        ("make ", next((m for m in _MAKEFILES if repo.exists_exact(m)), "Makefile")),
        ("go ", "go.mod"), ("gofmt", "go.mod"), ("cargo ", "Cargo.toml"),
        ("uv run ", "pyproject.toml"), ("npm ", "package.json"), ("pnpm ", "package.json"),
        ("yarn ", "package.json"), ("bun ", "package.json"), ("./gradlew", "gradlew"),
        ("./mvnw", "mvnw"),
    ]
    for prefix, source in prefixes:
        if command.startswith(prefix):
            return source
    return "repository metadata"


def discover(repo: Repository) -> dict[str, list[tuple[str, str]]]:
    """(command, source) per kind, following the spec's ``command.*`` definitions.

    Starts from Agentic Dev's ``discover_commands`` (the same intelligence behind
    ``repo inspect``) and adds the spec-defined sources it does not cover.
    """

    found: dict[str, list[tuple[str, str]]] = {kind: [] for kind in _COMMAND_KINDS}
    base = discover_commands(repo.root)
    for kind in _COMMAND_KINDS:
        for command in base.get(kind, []):
            found[kind].append((command, _command_source(repo, command)))

    def add(kind: str, command: str, source: str) -> None:
        if (command, source) not in found[kind]:
            found[kind].append((command, source))

    def exists(name: str) -> bool:
        return repo.exists_exact(name) == "file"

    makefile = next((m for m in _MAKEFILES if exists(m)), None)
    if makefile:
        text = repo.text(makefile)
        if target := _make_target(text, ("test", "check")):
            add("test", f"make {target}", makefile)
        if target := _make_target(text, ("type-check",)):
            add("typecheck", f"make {target}", makefile)
    if exists("justfile"):
        text = repo.text("justfile")
        for kind, names in (("test", ("test", "check")), ("build", ("build",)), ("lint", ("lint",)),
                            ("format", ("fmt", "format")), ("typecheck", ("typecheck", "type-check"))):
            if recipe := _just_recipe(text, names):
                add(kind, f"just {recipe}", "justfile")

    if exists("package.json"):
        text = repo.text("package.json")
        for kind, script in (("format", "fmt"), ("typecheck", "type-check")):
            if re.search(rf'"{re.escape(script)}"\s*:', text):
                add(kind, f"npm run {script}", "package.json")
    if exists("composer.json") and re.search(r'"test"\s*:', repo.text("composer.json")):
        add("test", "composer test", "composer.json")

    pyproject = repo.text("pyproject.toml").lower() if exists("pyproject.toml") else ""
    for name in ("setup.cfg", "tox.ini"):
        if exists(name) and "pytest" in repo.text(name).lower():
            add("test", "pytest", name)
    for entry, is_dir in repo.entries:
        if not is_dir and "/" not in entry and re.fullmatch(r"requirements.*\.txt", entry):
            if "pytest" in repo.text(entry).lower():
                add("test", "pytest", entry)
    for name in ("pytest.ini", "conftest.py"):
        if exists(name):
            add("test", "pytest", name)
    if exists("tox.ini"):
        add("test", "tox", "tox.ini")
    if exists("noxfile.py"):
        add("test", "nox", "noxfile.py")
    if pyproject:
        if re.search(r"^\s*\[build-system\]", pyproject, re.MULTILINE):
            add("build", "python -m build", "pyproject.toml")
        for tool in ("flake8", "pylint"):
            if tool in pyproject:
                add("lint", tool, "pyproject.toml")
        if "black" in pyproject:
            add("format", "black .", "pyproject.toml")

    for name in ("build.gradle", "build.gradle.kts"):
        if exists(name) and not exists("gradlew"):
            add("test", "gradle test", name)
            add("build", "gradle build", name)
    if exists("pom.xml") and not exists("mvnw"):
        add("test", "mvn test", "pom.xml")
        add("build", "mvn package", "pom.xml")
    if exists("CMakeLists.txt"):
        add("build", "cmake --build build", "CMakeLists.txt")
        if re.search(r"\b(enable_testing|add_test)\s*\(", repo.text("CMakeLists.txt"), re.IGNORECASE):
            add("test", "ctest", "CMakeLists.txt")
    if exists("Package.swift"):
        add("build", "swift build", "Package.swift")
        add("test", "swift test", "Package.swift")
    if exists("Rakefile"):
        add("test", "rake test", "Rakefile")
    if exists(".rspec"):
        add("test", "rspec", ".rspec")
    return found


# --------------------------------------------------------------- collector ---

AGENT_FILE_EVIDENCE = (
    "file.agents_md", "file.claude_md", "file.copilot_instructions",
    "file.cursor_rules", "file.gemini_md",
)
ROOT_INSTRUCTION_FILES = ("AGENTS.md", "CLAUDE.md", "GEMINI.md")
CONCISE_MAX_LINES = 100
_CODE_SPAN = re.compile(r"`([^`\n]+)`")
_LINK_TARGET = re.compile(r"\]\(([^)\s]+)")
_URL = re.compile(r"^[a-z][a-z0-9+.-]*:", re.IGNORECASE)
_EXTENSION = re.compile(r"\.[A-Za-z0-9]{1,8}$")


@dataclass
class EvidenceCollector:
    repo: Repository
    spec: Spec
    _cache: dict[str, Observation] = field(default_factory=dict)
    _globs: dict[str, re.Pattern[str]] = field(default_factory=dict)
    _commands: dict[str, list[tuple[str, str]]] | None = None

    def commands(self) -> dict[str, list[tuple[str, str]]]:
        if self._commands is None:
            self._commands = discover(self.repo)
        return self._commands

    @classmethod
    def for_repository(cls, root: Path, spec: Spec) -> "EvidenceCollector":
        matching = spec.document["path_matching"]
        prefixes = sorted({
            literal_prefix(glob)
            for item in spec.evidence.values()
            for glob in [*item["detection"].get("paths", []), *item["detection"].get("exclude", [])]
            if literal_prefix(glob)
        })
        repo = Repository(root, matching["ignored_directories"], prefixes)
        return cls(repo=repo, spec=spec)

    def observe(self, evidence_id: str) -> Observation:
        if evidence_id not in self._cache:
            self._cache[evidence_id] = self._observe(evidence_id)
        return self._cache[evidence_id]

    def _observe(self, evidence_id: str) -> Observation:
        definition = self.spec.evidence.get(evidence_id)
        if definition is None:
            return Observation(evidence_id, None, note="evidence type is not defined by the spec")
        detection = definition["detection"]
        kind = detection.get("kind")
        if kind not in SUPPORTED_DETECTIONS:
            return Observation(evidence_id, None, note=f"detection kind {kind!r} is not supported by this assessor")
        if kind == "path":
            return self._path(evidence_id, detection)
        if kind in {"heading", "content"}:
            return self._text_match(evidence_id, definition, detection)
        handler = DERIVED.get(evidence_id)
        if handler is None:
            return Observation(evidence_id, None, note="derived evidence is not supported by this assessor")
        return handler(self, evidence_id)

    # -- declarative detections ------------------------------------------

    def _glob(self, glob: str) -> re.Pattern[str]:
        if glob not in self._globs:
            self._globs[glob] = compile_glob(glob, self.repo.ignored)
        return self._globs[glob]

    def match_paths(self, detection: dict[str, Any]) -> list[str]:
        wanted = detection.get("type", "file")
        scope = detection.get("scope", "worktree")
        includes = detection.get("paths", [])
        excludes = [self._glob(glob) for glob in detection.get("exclude", [])]

        tracked = self.repo.tracked_files if scope == "tracked" else None
        if tracked is not None:
            candidates: Iterable[tuple[str, bool]] = ((path, False) for path in tracked)
        else:
            candidates = self.repo.entries
        literal = [glob for glob in includes if "*" not in glob]
        patterns = [self._glob(glob) for glob in includes if "*" in glob]

        matches: set[str] = set()
        for path, is_dir in candidates:
            if wanted == "file" and is_dir or wanted == "directory" and not is_dir:
                continue
            if any(p.match(path) for p in patterns) and not any(x.match(path) for x in excludes):
                matches.add(path)
        for glob in literal:
            if tracked is not None:
                found = "file" if glob in tracked else None
            else:
                found = self.repo.exists_exact(glob)
            if found and (wanted == "any" or (wanted == "file") == (found == "file")):
                if not any(x.match(glob) for x in excludes):
                    matches.add(glob)
        return sorted(matches)

    def _path(self, evidence_id: str, detection: dict[str, Any]) -> Observation:
        return _observation(evidence_id, [_item(evidence_id, path, path) for path in self.match_paths(detection)])

    def _files_for(self, detection: dict[str, Any]) -> list[str]:
        if "in" in detection:
            files: set[str] = set()
            for ref in detection["in"]:
                ref_detection = self.spec.evidence.get(ref, {}).get("detection", {})
                if ref_detection.get("kind") == "path":
                    files.update(self.match_paths(ref_detection))
            return sorted(files)
        return self.match_paths({"kind": "path", "paths": detection.get("paths", [])})

    def _text_match(self, evidence_id: str, definition: dict[str, Any], detection: dict[str, Any]) -> Observation:
        patterns = [re.compile(p, re.IGNORECASE) for p in detection["patterns"]]
        redact = definition.get("category") in REDACTED_CATEGORIES
        headings_only = detection["kind"] == "heading"
        items: list[dict[str, Any]] = []
        for rel in self._files_for(detection):
            lines = self.repo.lines(rel) or []
            fence: str | None = None
            for number, line in enumerate(lines, start=1):
                candidate = line
                if headings_only:
                    marker = FENCE.match(line)
                    if marker:
                        token = marker.group(1)[0]
                        fence = None if fence == token else (fence or token)
                        continue
                    if fence:
                        continue
                    heading = ATX_HEADING.match(line)
                    if not heading:
                        continue
                    candidate = (heading.group(2) or "").strip()
                if any(p.search(candidate) for p in patterns):
                    items.append(_item(evidence_id, "<redacted>" if redact else candidate, rel, number))
        return _observation(evidence_id, items)


# ----------------------------------------------------------------- derived ---

def _derived_command(kind: str) -> Callable[[EvidenceCollector, str], Observation]:
    def handler(collector: EvidenceCollector, evidence_id: str) -> Observation:
        items = [_item(evidence_id, command, source) for command, source in collector.commands()[kind]]
        return _observation(evidence_id, items)
    return handler


def _project_language(collector: EvidenceCollector, evidence_id: str) -> Observation:
    items: list[dict[str, Any]] = []
    unsupported = False
    for other in sorted(collector.spec.evidence):
        if not other.startswith("project.language."):
            continue
        observation = collector.observe(other)
        if observation.satisfied is None:
            unsupported = True
        elif observation.satisfied:
            items.append(_item(evidence_id, other.removeprefix("project.language."), observation.items[0]["source"]))
    if not items and unsupported:
        return Observation(evidence_id, None, note="a language evidence type is not supported")
    return _observation(evidence_id, items)


def _concise(collector: EvidenceCollector, evidence_id: str) -> Observation:
    present = [name for name in ROOT_INSTRUCTION_FILES if collector.repo.exists_exact(name) == "file"]
    items: list[dict[str, Any]] = []
    ok = bool(present)
    for name in present:
        count = sum(1 for line in collector.repo.lines(name) or [] if line.strip())
        items.append(_item(evidence_id, f"{count} non-blank lines", name))
        ok = ok and count <= CONCISE_MAX_LINES
    if ok:
        return _observation(evidence_id, items)
    # Report what was measured even though the evidence is not satisfied.
    return Observation(evidence_id, False, tuple(items), len(items),
                       note=f"root instruction files must have at most {CONCISE_MAX_LINES} non-blank lines")


def _reference(raw: str) -> str | None:
    value = raw.strip().strip("<>")
    if not value or _URL.match(value) or value.startswith(("/", "~")) or " " in value:
        return None
    value = value.split("#", 1)[0]
    value = value.removeprefix("./").rstrip("/")
    if not value or ".." in value.split("/"):
        return None
    if "/" not in value and not _EXTENSION.search(value):
        return None
    return value


def _file_pointers(collector: EvidenceCollector, evidence_id: str) -> Observation:
    files: set[str] = set()
    for ref in AGENT_FILE_EVIDENCE:
        detection = collector.spec.evidence.get(ref, {}).get("detection", {})
        if detection.get("kind") == "path":
            files.update(collector.match_paths(detection))
    references: dict[str, tuple[str, int]] = {}
    for rel in sorted(files):
        for number, line in enumerate(collector.repo.lines(rel) or [], start=1):
            for raw in [*_CODE_SPAN.findall(line), *_LINK_TARGET.findall(line)]:
                target = _reference(raw)
                if target and target not in references and collector.repo.exists_exact(target):
                    references[target] = (rel, number)
    items = [_item(evidence_id, target, src, line) for target, (src, line) in references.items()]
    if len(items) >= 2:
        return _observation(evidence_id, items)
    return Observation(evidence_id, False, tuple(sorted(items, key=lambda i: i["value"])), len(items),
                       note="at least two existing repository paths must be referenced")


DERIVED: dict[str, Callable[[EvidenceCollector, str], Observation]] = {
    "agent.instructions.concise": _concise,
    "agent.instructions.file_pointers": _file_pointers,
    "project.language": _project_language,
    **{f"command.{kind}": _derived_command(kind) for kind in _COMMAND_KINDS},
}
