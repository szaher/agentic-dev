"""Remediation contract: classify what can safely be fixed, and describe it.

This module is read-only. It turns an assessment into a remediation document
(``agentic.readiness-remediation`` v1) made of:

- ``items``: one per open rule, classified as ``safe-automatic``,
  ``human-decision``, or ``unsupported``;
- ``actions``: declarative, idempotent, reversible changes. Only
  ``safe-automatic`` items reference them.

Invariants (see docs/REMEDIATION.md):

- The spec's remediation classification is an upper bound. ``automatable`` may
  become any class, ``assisted`` never becomes ``safe-automatic``, and
  ``human-required`` is always ``human-decision``.
- Action content is derived only from observed evidence or from content the
  spec itself defines, and every action records that provenance. Nothing
  invents architecture, security, business, or other project policy.
- Targets are repository-relative, committable files outside ``.git/``.

Applying actions belongs to ``ready apply`` (v0.15 slice 2). Nothing here writes.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Callable

from ..detect import repo_root
from . import maturity
from .assess import assess
from .evidence import EvidenceCollector
from .spec import Spec, load_spec

DOCUMENT_TYPE = "agentic.readiness-remediation"
SAFE = "safe-automatic"
HUMAN = "human-decision"
UNSUPPORTED = "unsupported"
CLASSES = (SAFE, HUMAN, UNSUPPORTED)

# Spec classification -> remediation classes Agentic Dev may assign.
ALLOWED = {
    "automatable": frozenset({SAFE, HUMAN, UNSUPPORTED}),
    "assisted": frozenset({HUMAN, UNSUPPORTED}),
    "human-required": frozenset({HUMAN}),
}

ACTION_KINDS = ("managed-block",)
BLOCK_ID = re.compile(r"^readiness\.[a-z0-9][a-z0-9.-]*$")
MARKER = "agentic-dev:"
FORMATS = {
    # Comment syntax for managed-block markers, chosen by file name or suffix.
    "markdown": ("<!-- ", " -->"),
    "hash": ("# ", ""),
}
_HASH_NAMES = {".gitignore", ".gitattributes", ".dockerignore", "CODEOWNERS"}
_HASH_SUFFIXES = {".yml", ".yaml", ".toml", ".cfg", ".ini", ".sh", ".py"}
_MARKDOWN_SUFFIXES = {".md", ".mdc", ".markdown"}
ROOT_INSTRUCTION_FILES = ("AGENTS.md", "CLAUDE.md", "GEMINI.md", ".github/copilot-instructions.md")
COMMAND_LABELS = (("build", "Build"), ("test", "Test"),
                  ("lint", "Lint"), ("format", "Format"), ("typecheck", "Typecheck"))


class ContractError(ValueError):
    """A remediation action or document violates the contract."""


def block_format(path: str) -> str | None:
    name = PurePosixPath(path).name
    suffix = PurePosixPath(path).suffix.lower()
    if suffix in _MARKDOWN_SUFFIXES:
        return "markdown"
    if name in _HASH_NAMES or suffix in _HASH_SUFFIXES:
        return "hash"
    return None


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalize(content: str) -> str:
    """Block content is stored without leading/trailing blank lines, with one final newline."""

    return content.strip("\n") + "\n"


def markers(fmt: str, block_id: str, content_sha256: str) -> tuple[str, str]:
    open_, close = FORMATS[fmt]
    return (f"{open_}{MARKER}begin {block_id} sha256={content_sha256}{close}",
            f"{open_}{MARKER}end {block_id}{close}")


def render_block(fmt: str, block_id: str, content: str) -> str:
    """The exact bytes of a managed block, markers included."""

    body = normalize(content)
    begin, end = markers(fmt, block_id, digest(body))
    return f"{begin}\n{body}{end}\n"


def check_path(path: str) -> None:
    pure = PurePosixPath(path)
    if not path or pure.is_absolute() or "\\" in path or ".." in pure.parts or path != pure.as_posix():
        raise ContractError(f"target must be a normalized repository-relative path: {path!r}")
    if pure.parts[0] == ".git":
        raise ContractError(f"target must not be inside .git: {path!r}")


def check_action(action: dict[str, Any]) -> None:
    """Enforce the structural safety rules every action must satisfy."""

    if action["kind"] not in ACTION_KINDS:
        raise ContractError(f"unknown action kind {action['kind']!r}")
    check_path(action["path"])
    fmt = block_format(action["path"])
    if fmt is None or fmt != action["format"]:
        raise ContractError(f"{action['path']}: managed blocks are not supported for this file type")
    if not BLOCK_ID.match(action["block_id"]):
        raise ContractError(f"invalid block id {action['block_id']!r}")
    for text in (action["content"], action.get("prelude") or ""):
        if MARKER in text:
            raise ContractError(f"{action['id']}: content must not contain managed-block markers")
    if action["content_sha256"] != digest(normalize(action["content"])):
        raise ContractError(f"{action['id']}: content_sha256 does not match content")
    if not action["provenance"]:
        raise ContractError(f"{action['id']}: actions must record provenance")


def check_document(document: dict[str, Any]) -> None:
    """Enforce the classification invariants across a remediation document."""

    actions = {action["id"]: action for action in document["actions"]}
    referenced: set[str] = set()
    for item in document["items"]:
        allowed = ALLOWED[item["spec_classification"]]
        if item["remediation_class"] not in allowed:
            raise ContractError(
                f"{item['rule_id']}: spec classification {item['spec_classification']!r} "
                f"cannot become {item['remediation_class']!r}"
            )
        if item["remediation_class"] == SAFE:
            if not item["action_ids"]:
                raise ContractError(f"{item['rule_id']}: safe-automatic items must reference actions")
        elif item["action_ids"]:
            raise ContractError(f"{item['rule_id']}: only safe-automatic items may reference actions")
        if item["remediation_class"] == HUMAN and not item["decision"]:
            raise ContractError(f"{item['rule_id']}: human-decision items must state the decision")
        for action_id in item["action_ids"]:
            if action_id not in actions:
                raise ContractError(f"{item['rule_id']}: unknown action {action_id}")
            referenced.add(action_id)
    for action in actions.values():
        check_action(action)
        if action["id"] not in referenced:
            raise ContractError(f"{action['id']}: action is not referenced by any item")


# --------------------------------------------------------------- generators ---

@dataclass
class Context:
    spec: Spec
    collector: EvidenceCollector
    requirements: dict[str, dict[str, Any]]

    def target_state(self, path: str) -> dict[str, Any]:
        repo = self.collector.repo
        exists = repo.exists_exact(path) == "file"
        tracked = repo.tracked_files
        state: dict[str, Any] = {
            "exists": exists,
            "sha256": digest_bytes(repo.root / path) if exists else None,
            "tracked": (path in tracked) if tracked is not None else None,
        }
        return state


def digest_bytes(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _action(ctx: Context, *, block_id: str, path: str, content: str, provenance: list[dict[str, Any]],
            prelude: str | None = None) -> dict[str, Any]:
    body = normalize(content)
    fmt = block_format(path)
    if fmt is None:
        raise ContractError(f"{path}: unsupported managed-block file type")
    action = {
        "id": f"{block_id}@{path}",
        "kind": "managed-block",
        "path": path,
        "format": fmt,
        "block_id": block_id,
        "content": body,
        "content_sha256": digest(body),
        "prelude": prelude,
        "target": ctx.target_state(path),
        "provenance": provenance,
    }
    check_action(action)
    return action


def _instruction_target(ctx: Context) -> tuple[str, str | None]:
    """Existing root instruction file to extend, or AGENTS.md to create."""

    for name in ROOT_INSTRUCTION_FILES:
        if ctx.collector.repo.exists_exact(name) == "file":
            return name, None
    return "AGENTS.md", "# Agent instructions\n"


def _commands_action(ctx: Context) -> tuple[list[dict[str, Any]], str]:
    commands = ctx.collector.commands()
    lines: list[str] = []
    provenance: list[dict[str, Any]] = []
    for kind, label in COMMAND_LABELS:
        for command, source in commands.get(kind, []):
            lines.append(f"- {label}: `{command}` (from `{source}`)")
            provenance.append({"kind": "evidence", "type": f"command.{kind}", "value": command, "source": source})
    if not provenance:
        return [], "No build, test, lint, format, or typecheck commands were discovered, so there are no facts to document."
    path, prelude = _instruction_target(ctx)
    content = "\n".join([
        "## Commands",
        "",
        "Discovered from repository metadata by `agentic ready`. Edit the commands at their",
        "source; this block is regenerated.",
        "",
        *lines,
    ])
    return [_action(ctx, block_id="readiness.commands", path=path, content=content,
                    provenance=provenance, prelude=prelude)], ""


def _secrets_ignored_action(ctx: Context) -> tuple[list[dict[str, Any]], str]:
    content = "\n".join([
        "# Local environment files can hold secrets; keep them out of version control.",
        ".env",
        ".env.*",
        "!.env.example",
        "!.env.sample",
        "!.env.template",
    ])
    provenance = [{
        "kind": "spec",
        "type": "security.env_ignored",
        "value": "the root .gitignore ignores .env files",
        "source": f"{ctx.spec.name} {ctx.spec.version}",
    }]
    return [_action(ctx, block_id="readiness.secrets-ignored", path=".gitignore",
                    content=content, provenance=provenance)], ""


Generator = Callable[[Context], tuple[list[dict[str, Any]], str]]

# Only spec-``automatable`` rules may appear here (enforced by tests).
SAFE_GENERATORS: dict[str, Generator] = {
    "context.agent_instructions": _commands_action,
    "context.agent_instructions.commands": _commands_action,
    "constraints.secrets.ignored": _secrets_ignored_action,
}

# Spec-``automatable`` rules that have no safe action in this version, and why.
UNSUPPORTED_REASONS: dict[str, str] = {
    "feedback.dependencies.locked": (
        "Generating a lockfile runs the package manager, which can execute project code "
        "and reach the network. Run your package manager's lock command yourself."
    ),
    "context.issue_templates": (
        "Issue templates would be generic content not derived from repository evidence. "
        "Add templates that reflect how your team writes issues."
    ),
}


# ---------------------------------------------------------------- candidates ---

_MODULE_ROOTS = ("src", "internal", "pkg", "packages", "apps", "lib", "cmd", "services")


def _module_candidates(ctx: Context) -> list[dict[str, Any]]:
    """Top-level source directories, offered as boundary candidates only."""

    found: list[dict[str, Any]] = []
    for path, is_dir in ctx.collector.repo.entries:
        parts = path.split("/")
        if is_dir and len(parts) == 2 and parts[0] in _MODULE_ROOTS:
            found.append({"value": path, "source": path, "basis": "top-level source directory"})
    return found[:20]


def _tooling_candidates(ctx: Context) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for evidence_id in ("config.linter", "config.linter_declared", "config.formatter", "config.tsconfig"):
        for item in ctx.collector.observe(evidence_id).items:
            found.append({"value": item["value"], "source": item["source"],
                          "basis": f"{evidence_id}: conventions already enforced by tooling"})
    return found


def _command_candidates(ctx: Context) -> list[dict[str, Any]]:
    return [
        {"value": command, "source": source, "basis": f"discovered {kind} command"}
        for kind, _ in COMMAND_LABELS
        for command, source in ctx.collector.commands().get(kind, [])
    ]


CANDIDATES: dict[str, Callable[[Context], list[dict[str, Any]]]] = {
    "constraints.architecture_boundaries": _module_candidates,
    "context.architecture": _module_candidates,
    "conventions.documented": _tooling_candidates,
    "context.readme.setup": _command_candidates,
}


def _decision(ctx: Context, requirement: dict[str, Any]) -> dict[str, Any]:
    remediation = requirement["remediation"]
    question = remediation.get("decision") or remediation["summary"]
    provider = CANDIDATES.get(requirement["id"])
    return {
        "question": question.strip(),
        "guidance": remediation["summary"].strip(),
        "candidates": provider(ctx) if provider else [],
    }


def _classify(ctx: Context, requirement: dict[str, Any]) -> tuple[str, list[dict[str, Any]], str]:
    spec_class = requirement["remediation"]["classification"]
    rule_id = requirement["id"]
    if spec_class == "automatable":
        if rule_id in SAFE_GENERATORS:
            actions, why_not = SAFE_GENERATORS[rule_id](ctx)
            if actions:
                return SAFE, actions, "Generated from observed repository evidence as a managed block."
            return HUMAN, [], why_not
        return UNSUPPORTED, [], UNSUPPORTED_REASONS.get(
            rule_id, "No safe automatic remediation is implemented for this rule in this version.")
    if spec_class == "assisted":
        return HUMAN, [], "The spec marks this as assisted: a person must supply or confirm the content."
    return HUMAN, [], "The spec marks this as human-required: it is a project or team decision."


def propose(
    path: str = ".",
    *,
    spec: Spec | str | None = None,
    target: str | None = None,
) -> dict[str, Any]:
    """Build a read-only remediation document for rules blocking ``target``.

    Covers every open (``fail`` or ``unknown``) rule whose level is at or below
    the target, of any severity.
    """

    resolved = spec if isinstance(spec, Spec) else load_spec(spec)
    assessment = assess(path, spec=resolved, target=target)
    collector = EvidenceCollector.for_repository(repo_root(path), resolved)
    ctx = Context(resolved, collector, {r["id"]: r for r in assessment["requirements"]})
    state = assessment["maturity"]
    open_items = [
        r for r in assessment["requirements"]
        if r["status"] in maturity.BLOCKING and resolved.rank(r["required_from"]) <= state["target_rank"]
    ]

    actions: dict[str, dict[str, Any]] = {}
    items: list[dict[str, Any]] = []
    for requirement in open_items:
        remediation_class, generated, reason = _classify(ctx, requirement)
        for action in generated:
            existing = actions.setdefault(action["id"], {**action, "rules": []})
            existing["rules"].append(requirement["id"])
        items.append({
            "rule_id": requirement["id"],
            "title": requirement["title"],
            "severity": requirement["severity"],
            "required_from": requirement["required_from"],
            "status": requirement["status"],
            "spec_classification": requirement["remediation"]["classification"],
            "remediation_class": remediation_class,
            "reason": reason,
            "action_ids": sorted({action["id"] for action in generated}),
            "decision": _decision(ctx, requirement) if remediation_class == HUMAN else None,
            "depends_on": requirement["depends_on"],
        })

    severity_order = {"required": 0, "recommended": 1, "advisory": 2}
    items.sort(key=lambda i: (severity_order[i["severity"]], resolved.rank(i["required_from"]), i["rule_id"]))
    counts = {cls: sum(1 for i in items if i["remediation_class"] == cls) for cls in CLASSES}
    document = {key: assessment[key] for key in ("schema_version", "assessor", "spec", "repository")}
    document.update({
        "document_type": DOCUMENT_TYPE,
        "mode": "preview",
        "maturity": {"current": state["current"], "target": state["target"], "target_met": state["target_met"]},
        "actions": [actions[key] for key in sorted(actions)],
        "items": items,
        "summary": {
            "safe_automatic": counts[SAFE],
            "human_decision": counts[HUMAN],
            "unsupported": counts[UNSUPPORTED],
            "actions": len(actions),
        },
    })
    check_document(document)
    return document
