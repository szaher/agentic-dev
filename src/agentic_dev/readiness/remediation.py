"""Remediation contract: what may be changed, and how changes must behave.

This module is read-only. It turns an assessment into a remediation document
(``agentic.readiness-remediation`` v1) with three structurally separate parts:

- ``remediations``: one per open Agent Ready rule, classified as
  ``safe-automatic``, ``human-decision``, or ``unsupported``. The spec's
  remediation classification is a **ceiling**: Agentic Dev may downgrade it,
  never upgrade it.
- ``maintenance_actions``: operational scaffolding for Agentic Dev's own
  readiness lifecycle (for example a readiness CI check). They are not
  readiness rules, never reference rules, and must be *evidence-neutral*:
  they may not create evidence that any rule depends on. This makes it
  impossible to use maintenance as a back door around the ceiling.
- ``changes``: declarative, idempotent, reversible managed-block edits. Each
  change belongs to exactly one owner (a set of rule remediations, or one
  maintenance action).

The spec controls *what* may be remediated. Agentic Dev controls *how safely*
it performs permitted remediation. Maintenance actions only maintain Agentic
Dev/readiness infrastructure. Applying changes belongs to ``ready apply``
(v0.15 slice 2, #54). Nothing here writes.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Callable

from ..detect import repo_root
from . import maturity
from .assess import assess, references
from .evidence import ATX_HEADING, FENCE, EvidenceCollector, compile_glob
from .spec import Spec, load_spec

DOCUMENT_TYPE = "agentic.readiness-remediation"
CONTRACT = "readiness-remediation-v1"
SAFE = "safe-automatic"
HUMAN = "human-decision"
UNSUPPORTED = "unsupported"
CLASSES = (SAFE, HUMAN, UNSUPPORTED)

# Spec classification -> remediation classes Agentic Dev may assign (the ceiling).
ALLOWED = {
    "automatable": frozenset({SAFE, HUMAN, UNSUPPORTED}),
    "assisted": frozenset({HUMAN, UNSUPPORTED}),
    "human-required": frozenset({HUMAN}),
}

CHANGE_KINDS = ("managed-block",)
BLOCK_ID = re.compile(r"^readiness\.[a-z0-9][a-z0-9.-]*$")
MAINTENANCE_ID = re.compile(r"^readiness\.[a-z0-9][a-z0-9.-]*$")
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
COMMAND_LABELS = (("build", "Build"), ("test", "Test"), ("lint", "Lint"),
                  ("format", "Format"), ("typecheck", "Typecheck"))

# Closed allowlist of files maintenance actions may own. Adding a path is a
# contract change. None of them is a root-level file, so no ``derived``
# evidence (which reads root manifests) can observe them.
MAINTENANCE_TARGETS = frozenset({".github/workflows/agentic-readiness.yml"})

# Content a maintenance action must never contain, whatever its purpose.
FORBIDDEN_MAINTENANCE_CONTENT: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("credential reference", re.compile(r"\bsecrets\.|\$\{\{\s*secrets", re.IGNORECASE)),
    ("permission grant", re.compile(r"^\s*[\w-]+\s*:\s*write\b|write-all", re.IGNORECASE | re.MULTILINE)),
    ("cloud or cluster credentials", re.compile(
        r"aws-actions/configure-aws-credentials|google-github-actions/auth|azure/login|kubeconfig",
        re.IGNORECASE)),
    ("tool installation", re.compile(
        r"\b(curl|wget|sudo|apt(-get)?|brew|choco|npx|npm\s+(i|install)|pnpm\s+add|yarn\s+add|"
        r"cargo\s+install|go\s+install|gem\s+install|uv\s+tool\s+install|pipx\s+install|"
        r"pip3?\s+install)\b", re.IGNORECASE)),
)
# The single installation a maintenance action may perform: Agentic Dev itself,
# pinned to an exact version, so the readiness check runs the assessor it was
# generated for.
ALLOWED_INSTALL = re.compile(r"^\s*(-\s*run:\s*)?(python3?\s+-m\s+)?pip3?\s+install\s+agentic-dev==\d+\.\d+\.\d+\S*\s*$",
                             re.IGNORECASE)


class ContractError(ValueError):
    """A remediation change, maintenance action, or document violates the contract."""


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


def check_change(change: dict[str, Any]) -> None:
    """Structural safety rules every change must satisfy, whoever owns it."""

    if change["kind"] not in CHANGE_KINDS:
        raise ContractError(f"unknown change kind {change['kind']!r}")
    check_path(change["path"])
    fmt = block_format(change["path"])
    if fmt is None or fmt != change["format"]:
        raise ContractError(f"{change['path']}: managed blocks are not supported for this file type")
    if not BLOCK_ID.match(change["block_id"]):
        raise ContractError(f"invalid block id {change['block_id']!r}")
    if change["id"] != f"{change['block_id']}@{change['path']}":
        raise ContractError(f"{change['id']}: change id must be <block-id>@<path>")
    for text in (change["content"], change.get("prelude") or ""):
        if MARKER in text:
            raise ContractError(f"{change['id']}: content must not contain managed-block markers")
    if change["content_sha256"] != digest(normalize(change["content"])):
        raise ContractError(f"{change['id']}: content_sha256 does not match content")
    if not change["provenance"]:
        raise ContractError(f"{change['id']}: changes must record provenance")


# ------------------------------------------------------- evidence neutrality ---

def rule_evidence(spec: Spec) -> frozenset[str]:
    """Every evidence id that can influence a rule's status or applicability."""

    refs: set[str] = set()
    for rule in spec.rules.values():
        for expression in (rule["evidence"], rule.get("applies_when")):
            refs.update(ref for ref, _ in references(expression))
    if "project.language" in refs:
        refs.update(e for e in spec.evidence if e.startswith("project.language."))
    return frozenset(refs)


def _rendered_lines(change: dict[str, Any]) -> list[str]:
    """Every line a change can introduce: prelude (when creating) and the full block."""

    text = (change.get("prelude") or "") + render_block(change["format"], change["block_id"], change["content"])
    return text.splitlines()


def _matches(spec: Spec, globs: list[str], excludes: list[str], path: str) -> bool:
    ignored = spec.document["path_matching"]["ignored_directories"]
    hit = any(glob == path or ("*" in glob and compile_glob(glob, ignored).match(path)) for glob in globs)
    return hit and not any(glob == path or compile_glob(glob, ignored).match(path) for glob in excludes)


def evidence_created(spec: Spec, change: dict[str, Any]) -> set[str]:
    """Evidence ids a change could make observable, judged from the spec's detections.

    ``derived`` evidence cannot be judged here. Maintenance targets therefore
    come from a closed allowlist that excludes root-level files, which are the
    only inputs derived definitions read.
    """

    path = change["path"]
    lines = _rendered_lines(change)
    created: set[str] = set()
    for evidence_id, definition in spec.evidence.items():
        detection = definition["detection"]
        kind = detection["kind"]
        if kind == "path":
            if _matches(spec, detection["paths"], detection.get("exclude", []), path):
                created.add(evidence_id)
            continue
        if kind not in {"heading", "content"}:
            continue
        if "in" in detection:
            sources = [spec.evidence[ref]["detection"] for ref in detection["in"]]
            in_scope = any(_matches(spec, d["paths"], d.get("exclude", []), path) for d in sources)
        else:
            in_scope = _matches(spec, detection["paths"], [], path)
        if not in_scope:
            continue
        patterns = [re.compile(p, re.IGNORECASE) for p in detection["patterns"]]
        fence: str | None = None
        for line in lines:
            candidate = line
            if kind == "heading":
                marker = FENCE.match(line)
                if marker:
                    token = marker.group(1)[0]
                    fence = None if fence == token else (fence or token)
                    continue
                heading = ATX_HEADING.match(line) if not fence else None
                if not heading:
                    continue
                candidate = (heading.group(2) or "").strip()
            if any(p.search(candidate) for p in patterns):
                created.add(evidence_id)
                break
    return created


def check_maintenance(action: dict[str, Any], changes: dict[str, dict[str, Any]], spec: Spec) -> None:
    """Guarantee a maintenance action cannot stand in for rule remediation."""

    if action["class"] != SAFE or action["kind"] != "maintenance-action":
        raise ContractError(f"{action['id']}: maintenance actions are safe-automatic maintenance-action entries")
    if action["source"] != {"type": "agentic-dev", "contract": CONTRACT}:
        raise ContractError(f"{action['id']}: maintenance actions must be attributed to the agentic-dev contract")
    if not MAINTENANCE_ID.match(action["id"]):
        raise ContractError(f"invalid maintenance action id {action['id']!r}")
    if not action["change_ids"]:
        raise ContractError(f"{action['id']}: maintenance actions must own at least one change")
    gated = rule_evidence(spec)
    for change_id in action["change_ids"]:
        change = changes.get(change_id)
        if change is None:
            raise ContractError(f"{action['id']}: unknown change {change_id}")
        if change["path"] not in MAINTENANCE_TARGETS:
            raise ContractError(f"{action['id']}: {change['path']} is not an allowlisted maintenance target")
        content = (change.get("prelude") or "") + change["content"]
        for label, pattern in FORBIDDEN_MAINTENANCE_CONTENT:
            for line in content.splitlines():
                if pattern.search(line) and not (label == "tool installation" and ALLOWED_INSTALL.match(line)):
                    raise ContractError(f"{action['id']}: maintenance content must not contain a {label}: {line.strip()!r}")
        leaked = sorted(evidence_created(spec, change) & gated)
        if leaked:
            raise ContractError(
                f"{action['id']}: maintenance would create readiness evidence ({', '.join(leaked)}); "
                "maintenance actions must not satisfy or change any Agent Ready rule"
            )


def check_document(document: dict[str, Any], spec: Spec) -> None:
    """Enforce the ceiling, ownership, and maintenance invariants across a document."""

    changes: dict[str, dict[str, Any]] = {}
    for change in document["changes"]:
        if change["id"] in changes:
            raise ContractError(f"duplicate change {change['id']}")
        check_change(change)
        changes[change["id"]] = change

    claimed: dict[str, str] = {}
    for remediation in document["remediations"]:
        rule_id = remediation["rule_id"]
        if rule_id not in spec.rules:
            raise ContractError(f"{rule_id}: not a rule in {spec.name} {spec.version}")
        ceiling = spec.rules[rule_id]["remediation"]["classification"]
        if remediation["spec_classification"] != ceiling:
            raise ContractError(f"{rule_id}: spec_classification must be the spec's ({ceiling!r})")
        if remediation["remediation_class"] not in ALLOWED[ceiling]:
            raise ContractError(f"{rule_id}: spec classification {ceiling!r} "
                                f"cannot become {remediation['remediation_class']!r}")
        if remediation["remediation_class"] == SAFE:
            if not remediation["change_ids"]:
                raise ContractError(f"{rule_id}: safe-automatic remediations must reference changes")
        elif remediation["change_ids"]:
            raise ContractError(f"{rule_id}: only safe-automatic remediations may reference changes")
        if remediation["status"] == "pass" and remediation["remediation_class"] != SAFE:
            raise ContractError(f"{rule_id}: passing rules only appear to refresh their own managed blocks")
        if remediation["remediation_class"] == HUMAN and not remediation["decision"]:
            raise ContractError(f"{rule_id}: human-decision remediations must state the decision")
        for change_id in remediation["change_ids"]:
            change = changes.get(change_id)
            if change is None:
                raise ContractError(f"{rule_id}: unknown change {change_id}")
            owner = change["owner"]
            if owner["type"] != "remediation" or rule_id not in owner["rules"]:
                raise ContractError(f"{rule_id}: change {change_id} is not owned by this remediation")
            claimed[change_id] = "remediation"

    for action in document["maintenance_actions"]:
        for change_id in action["change_ids"]:
            change = changes.get(change_id)
            if change is None:
                raise ContractError(f"{action['id']}: unknown change {change_id}")
            if change["owner"] != {"type": "maintenance-action", "id": action["id"]}:
                raise ContractError(f"{action['id']}: change {change_id} is not owned by this maintenance action")
            if change_id in claimed:
                raise ContractError(f"{change_id}: a change cannot belong to both a remediation and maintenance")
            claimed[change_id] = "maintenance"
        check_maintenance(action, changes, spec)

    for change_id, change in changes.items():
        if change_id not in claimed:
            raise ContractError(f"{change_id}: change is not referenced by its owner")
        if change["owner"]["type"] == "remediation":
            for rule_id in change["owner"]["rules"]:
                remediation = next((r for r in document["remediations"] if r["rule_id"] == rule_id), None)
                if remediation is None or change_id not in remediation["change_ids"]:
                    raise ContractError(f"{change_id}: owner rule {rule_id} does not reference it")

    remediation_paths = {c["path"] for c in changes.values() if c["owner"]["type"] == "remediation"}
    for change in changes.values():
        if change["owner"]["type"] == "maintenance-action" and change["path"] in remediation_paths:
            raise ContractError(f"{change['path']}: maintenance and remediation changes cannot share a file")


# --------------------------------------------------------------- generators ---

@dataclass
class Context:
    spec: Spec
    collector: EvidenceCollector

    def target_state(self, path: str) -> dict[str, Any]:
        repo = self.collector.repo
        exists = repo.exists_exact(path) == "file"
        tracked = repo.tracked_files
        return {
            "exists": exists,
            "sha256": hashlib.sha256((repo.root / path).read_bytes()).hexdigest() if exists else None,
            "tracked": (path in tracked) if tracked is not None else None,
        }


def make_change(ctx: Context, *, block_id: str, path: str, content: str, provenance: list[dict[str, Any]],
                owner: dict[str, Any], prelude: str | None = None) -> dict[str, Any]:
    body = normalize(content)
    fmt = block_format(path)
    if fmt is None:
        raise ContractError(f"{path}: unsupported managed-block file type")
    change = {
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
        "owner": owner,
    }
    check_change(change)
    return change


def _instruction_target(ctx: Context) -> tuple[str, str | None]:
    """Existing root instruction file to extend, or AGENTS.md to create."""

    for name in ROOT_INSTRUCTION_FILES:
        if ctx.collector.repo.exists_exact(name) == "file":
            return name, None
    return "AGENTS.md", "# Agent instructions\n"


def _commands_change(ctx: Context) -> tuple[list[dict[str, Any]], str]:
    commands = ctx.collector.commands()
    lines: list[str] = []
    provenance: list[dict[str, Any]] = []
    for kind, label in COMMAND_LABELS:
        for command, source in commands.get(kind, []):
            lines.append(f"- {label}: `{command}` (from `{source}`)")
            provenance.append({"kind": "evidence", "type": f"command.{kind}", "value": command, "source": source})
    if not provenance:
        return [], ("No build, test, lint, format, or typecheck commands were discovered, "
                    "so there are no facts to document.")
    path, prelude = _instruction_target(ctx)
    content = "\n".join([
        "## Commands",
        "",
        "Discovered from repository metadata by `agentic ready`. Edit the commands at their",
        "source; this block is regenerated.",
        "",
        *lines,
    ])
    return [make_change(ctx, block_id="readiness.commands", path=path, content=content,
                        provenance=provenance, prelude=prelude,
                        owner={"type": "remediation", "rules": []})], ""


def _secrets_ignored_change(ctx: Context) -> tuple[list[dict[str, Any]], str]:
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
    return [make_change(ctx, block_id="readiness.secrets-ignored", path=".gitignore", content=content,
                        provenance=provenance, owner={"type": "remediation", "rules": []})], ""


Generator = Callable[[Context], tuple[list[dict[str, Any]], str]]

# Only spec-``automatable`` rules may appear here (enforced by tests).
SAFE_GENERATORS: dict[str, Generator] = {
    "context.agent_instructions": _commands_change,
    "context.agent_instructions.commands": _commands_change,
    "constraints.secrets.ignored": _secrets_ignored_change,
}

# Spec-``automatable`` rules that have no safe change in this version, and why.
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

# Maintenance action id -> generator returning (title, reason, changes).
# Empty in slice 1: the readiness CI check is added with `ready verify` (#55).
MAINTENANCE_GENERATORS: dict[str, Callable[[Context], tuple[str, str, list[dict[str, Any]]]]] = {}


def maintenance_action(action_id: str, *, title: str, reason: str, change_ids: list[str]) -> dict[str, Any]:
    return {
        "id": action_id,
        "class": SAFE,
        "kind": "maintenance-action",
        "title": title,
        "reason": reason,
        "source": {"type": "agentic-dev", "contract": CONTRACT},
        "change_ids": sorted(change_ids),
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
            changes, why_not = SAFE_GENERATORS[rule_id](ctx)
            if changes:
                return SAFE, changes, "Generated from observed repository evidence as a managed block."
            return HUMAN, [], why_not
        return UNSUPPORTED, [], UNSUPPORTED_REASONS.get(
            rule_id, "No safe automatic remediation is implemented for this rule in this version.")
    if spec_class == "assisted":
        return HUMAN, [], "The spec marks this as assisted: a person must supply or confirm the content."
    return HUMAN, [], "The spec marks this as human-required: it is a project or team decision."


def _stale(ctx: Context, change: dict[str, Any]) -> bool:
    """Whether the file already holds this managed block with different generated content."""

    from .managed import locate

    if not change["target"]["exists"]:
        return False
    lines = ctx.collector.repo.text(change["path"]).split("\n")
    found = locate(lines, change["format"], change["block_id"])
    if found is None:
        return False
    return isinstance(found, str) or found.marker_sha256 != change["content_sha256"]


def propose(
    path: str = ".",
    *,
    spec: Spec | str | None = None,
    target: str | None = None,
) -> dict[str, Any]:
    """Build a read-only remediation document for rules blocking ``target``.

    Covers every open (``fail`` or ``unknown``) rule whose level is at or below
    the target, of any severity, plus applicable maintenance actions.
    """

    resolved = spec if isinstance(spec, Spec) else load_spec(spec)
    assessment = assess(path, spec=resolved, target=target)
    ctx = Context(resolved, EvidenceCollector.for_repository(repo_root(path), resolved))
    state = assessment["maturity"]
    open_rules = [
        r for r in assessment["requirements"]
        if r["status"] in maturity.BLOCKING and resolved.rank(r["required_from"]) <= state["target_rank"]
    ]

    changes: dict[str, dict[str, Any]] = {}
    remediations: list[dict[str, Any]] = []
    for requirement in open_rules:
        remediation_class, generated, reason = _classify(ctx, requirement)
        for change in generated:
            owned = changes.setdefault(change["id"], change)
            owned["owner"]["rules"] = sorted({*owned["owner"]["rules"], requirement["id"]})
        remediations.append({
            "rule_id": requirement["id"],
            "title": requirement["title"],
            "severity": requirement["severity"],
            "required_from": requirement["required_from"],
            "status": requirement["status"],
            "spec_classification": requirement["remediation"]["classification"],
            "remediation_class": remediation_class,
            "reason": reason,
            "change_ids": sorted({change["id"] for change in generated}),
            "decision": _decision(ctx, requirement) if remediation_class == HUMAN else None,
            "depends_on": requirement["depends_on"],
        })

    # Passing rules whose own managed block has gone stale (for example a new
    # command was discovered) get a refresh. The rule already passes, so a
    # refresh cannot satisfy anything new. Hand-edited blocks are left alone
    # unless they are stale, in which case apply reports a conflict.
    for requirement in assessment["requirements"]:
        if (requirement["status"] != "pass" or requirement["id"] not in SAFE_GENERATORS
                or resolved.rank(requirement["required_from"]) > state["target_rank"]):
            continue
        generated, _ = SAFE_GENERATORS[requirement["id"]](ctx)
        stale = [change for change in generated if _stale(ctx, change)]
        if not stale:
            continue
        for change in stale:
            owned = changes.setdefault(change["id"], change)
            owned["owner"]["rules"] = sorted({*owned["owner"]["rules"], requirement["id"]})
        remediations.append({
            "rule_id": requirement["id"],
            "title": requirement["title"],
            "severity": requirement["severity"],
            "required_from": requirement["required_from"],
            "status": "pass",
            "spec_classification": requirement["remediation"]["classification"],
            "remediation_class": SAFE,
            "reason": "Refreshes the managed block Agentic Dev generated earlier; the rule already passes.",
            "change_ids": sorted({change["id"] for change in stale}),
            "decision": None,
            "depends_on": requirement["depends_on"],
        })

    maintenance: list[dict[str, Any]] = []
    for action_id, generator in sorted(MAINTENANCE_GENERATORS.items()):
        title, reason, generated = generator(ctx)
        if not generated:
            continue
        for change in generated:
            changes[change["id"]] = change
        maintenance.append(maintenance_action(action_id, title=title, reason=reason,
                                              change_ids=[c["id"] for c in generated]))

    severity_order = {"required": 0, "recommended": 1, "advisory": 2}
    remediations.sort(key=lambda r: (severity_order[r["severity"]], resolved.rank(r["required_from"]), r["rule_id"]))
    counts = {cls: sum(1 for r in remediations if r["remediation_class"] == cls) for cls in CLASSES}
    document = {key: assessment[key] for key in ("schema_version", "assessor", "spec", "repository")}
    document.update({
        "document_type": DOCUMENT_TYPE,
        "mode": "preview",
        "maturity": {"current": state["current"], "target": state["target"], "target_met": state["target_met"]},
        "remediations": remediations,
        "maintenance_actions": maintenance,
        "changes": [changes[key] for key in sorted(changes)],
        "summary": {
            "safe_automatic": counts[SAFE],
            "human_decision": counts[HUMAN],
            "unsupported": counts[UNSUPPORTED],
            "maintenance_actions": len(maintenance),
            "changes": len(changes),
        },
    })
    check_document(document, resolved)
    return document
