"""Agent Ready specification loading.

The spec is owned by https://github.com/szaher/agent-ready. Agentic Dev ships a
pinned copy of its canonical JSON bundle (``specs/``) so that assessment never
needs the network. Sources are resolved through ``SpecSource`` implementations
so a later signed/remote resolver can be added without touching the engine.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any, Protocol

SUPPORTED_SCHEMA_VERSION = "1"
SUPPORTED_DOCUMENT_TYPE = "agent-ready.spec"
SUPPORTED_DETECTIONS = frozenset({"path", "heading", "content", "derived"})
STATUSES = ("pass", "fail", "unknown", "not-applicable")


class SpecError(ValueError):
    """The specification cannot be loaded or is not supported."""


@dataclass(frozen=True)
class Level:
    id: str
    rank: int
    title: str
    summary: str


@dataclass(frozen=True)
class Spec:
    document: dict[str, Any]
    sha256: str
    source: str
    levels: tuple[Level, ...] = field(init=False)
    rules: dict[str, dict[str, Any]] = field(init=False)
    evidence: dict[str, dict[str, Any]] = field(init=False)

    def __post_init__(self) -> None:
        levels = tuple(
            Level(item["id"], item["rank"], item["title"], item["summary"])
            for item in self.document["maturity"]["levels"]
        )
        object.__setattr__(self, "levels", levels)
        object.__setattr__(self, "rules", {rule["id"]: rule for rule in self.document["rules"]})
        object.__setattr__(self, "evidence", {item["id"]: item for item in self.document["evidence"]})

    @property
    def name(self) -> str:
        return self.document["name"]

    @property
    def version(self) -> str:
        return self.document["spec_version"]

    @property
    def pillars(self) -> list[str]:
        return [pillar["id"] for pillar in self.document["pillars"]]

    @property
    def dimensions(self) -> list[str]:
        return [dimension["id"] for dimension in self.document["dimensions"]]

    def level(self, level_id: str) -> Level:
        for level in self.levels:
            if level.id == level_id:
                return level
        raise SpecError(f"unknown maturity level: {level_id}")

    def rank(self, level_id: str) -> int:
        return self.level(level_id).rank

    def identity(self) -> dict[str, str]:
        return {
            "name": self.name,
            "version": self.version,
            "sha256": self.sha256,
            "source": self.source,
        }


class SpecSource(Protocol):
    """Resolves a spec document. Implementations must not require the network
    unless the user explicitly selected a remote source."""

    def load(self) -> Spec: ...


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _parse(data: bytes, origin: str) -> dict[str, Any]:
    try:
        document = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SpecError(f"{origin}: not a JSON Agent Ready spec bundle ({exc})") from exc
    if not isinstance(document, dict):
        raise SpecError(f"{origin}: spec bundle must be a JSON object")
    return document


def _expression_refs(expression: Any) -> list[str]:
    if isinstance(expression, str):
        return [expression]
    if isinstance(expression, dict):
        refs: list[str] = []
        for operands in expression.values():
            if isinstance(operands, list):
                for operand in operands:
                    refs.extend(_expression_refs(operand))
        return refs
    return []


def validate_document(document: dict[str, Any], origin: str = "spec") -> None:
    """Structural checks the assessment engine relies on.

    The authoritative validation (JSON Schema plus semantic checks) runs in the
    agent-ready repository. This guards against unsupported or corrupt input.
    """

    if document.get("schema_version") != SUPPORTED_SCHEMA_VERSION:
        raise SpecError(
            f"{origin}: unsupported schema_version {document.get('schema_version')!r}; "
            f"this assessor supports {SUPPORTED_SCHEMA_VERSION!r}"
        )
    if document.get("document_type") != SUPPORTED_DOCUMENT_TYPE:
        raise SpecError(f"{origin}: document_type must be {SUPPORTED_DOCUMENT_TYPE!r}")
    for key in ("name", "spec_version", "pillars", "dimensions", "maturity", "evidence", "rules", "statuses"):
        if key not in document:
            raise SpecError(f"{origin}: missing required key {key!r}")
    if [item.get("id") for item in document["statuses"]] != list(STATUSES):
        raise SpecError(f"{origin}: unsupported status vocabulary")

    levels = document["maturity"].get("levels") or []
    if [level.get("rank") for level in levels] != list(range(len(levels))) or len(levels) < 2:
        raise SpecError(f"{origin}: maturity levels must have contiguous ranks starting at 0")
    level_ids = {level["id"] for level in levels}

    evidence_ids: set[str] = set()
    for item in document["evidence"]:
        if item["id"] in evidence_ids:
            raise SpecError(f"{origin}: duplicate evidence id {item['id']}")
        evidence_ids.add(item["id"])
        for pattern in item.get("detection", {}).get("patterns", []):
            try:
                re.compile(pattern, re.IGNORECASE)
            except re.error as exc:
                raise SpecError(f"{origin}: evidence {item['id']} has invalid pattern {pattern!r}: {exc}") from exc

    rule_ids: set[str] = set()
    pillars = {pillar["id"] for pillar in document["pillars"]}
    for rule in document["rules"]:
        rule_id = rule.get("id")
        if rule_id in rule_ids:
            raise SpecError(f"{origin}: duplicate rule id {rule_id}")
        rule_ids.add(rule_id)
        if rule.get("pillar") not in pillars:
            raise SpecError(f"{origin}: rule {rule_id} has unknown pillar {rule.get('pillar')!r}")
        if rule.get("required_from") not in level_ids:
            raise SpecError(f"{origin}: rule {rule_id} has unknown level {rule.get('required_from')!r}")
        if rule.get("severity") not in {"required", "recommended", "advisory"}:
            raise SpecError(f"{origin}: rule {rule_id} has unknown severity {rule.get('severity')!r}")
        if rule.get("evaluation", {}).get("on_missing") not in {"fail", "unknown"}:
            raise SpecError(f"{origin}: rule {rule_id} has an unknown evaluation policy")
        for ref in _expression_refs(rule.get("evidence")) + _expression_refs(rule.get("applies_when")):
            if ref not in evidence_ids:
                raise SpecError(f"{origin}: rule {rule_id} references unknown evidence {ref}")
    for rule in document["rules"]:
        for dep in rule.get("depends_on", []):
            if dep not in rule_ids:
                raise SpecError(f"{origin}: rule {rule['id']} depends on unknown rule {dep}")


@dataclass(frozen=True)
class BuiltinSpecSource:
    """The spec bundle pinned and shipped inside the Agentic Dev distribution."""

    def pin(self) -> dict[str, Any]:
        text = resources.files(__package__).joinpath("specs", "PIN.json").read_text(encoding="utf-8")
        return json.loads(text)

    def load(self) -> Spec:
        pin = self.pin()
        data = resources.files(__package__).joinpath("specs", pin["file"]).read_bytes()
        digest = _digest(data)
        if digest != pin["sha256"]:
            raise SpecError(
                f"built-in spec {pin['file']} does not match its pinned sha256 "
                f"({digest} != {pin['sha256']}); the installation is corrupt"
            )
        document = _parse(data, f"built-in {pin['file']}")
        validate_document(document, f"built-in {pin['file']}")
        if document["spec_version"] != pin["spec_version"]:
            raise SpecError("built-in spec version does not match its pin")
        return Spec(document=document, sha256=digest, source="builtin")


@dataclass(frozen=True)
class PathSpecSource:
    """An explicit local bundle, for spec development and testing.

    Accepts a bundle file, or a directory containing exactly one
    ``agent-ready-spec-*.json`` (for example an agent-ready checkout's
    ``spec/dist``). YAML sources are not read: build them with
    ``pnpm spec:build`` in agent-ready first.
    """

    path: Path

    def _file(self) -> Path:
        path = self.path.expanduser()
        if path.is_dir():
            candidates = sorted(path.glob("agent-ready-spec-*.json"))
            if len(candidates) != 1:
                raise SpecError(
                    f"{path.name or path}: expected exactly one agent-ready-spec-*.json bundle, "
                    f"found {len(candidates)}"
                )
            return candidates[0]
        if not path.is_file():
            raise SpecError(f"spec bundle not found: {path.name or path}")
        return path

    def load(self) -> Spec:
        file = self._file()
        data = file.read_bytes()
        document = _parse(data, file.name)
        validate_document(document, file.name)
        return Spec(document=document, sha256=_digest(data), source="path")


def resolve(spec: str | Path | None = None) -> SpecSource:
    """Choose a spec source. ``None`` selects the pinned built-in spec."""

    if spec is None or spec == "builtin":
        return BuiltinSpecSource()
    return PathSpecSource(Path(spec))


def load_spec(spec: str | Path | None = None) -> Spec:
    return resolve(spec).load()
