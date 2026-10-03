"""Managed instruction blocks owned by other tools: ``agentic instructions block``.

Shared agent instruction files (``AGENTS.md``, ``CLAUDE.md``, ...) are edited by
people, by readiness remediation, and by tools such as AgentFlow. Agentic Dev
owns the mutation mechanics so no tool rewrites these files wholesale: a tool
owns *content* inside one managed block, and this module places, updates, or
removes that block with the same marker, hash, and conflict protocol as
readiness remediation (docs/REMEDIATION.md):

- only allowlisted instruction files, never arbitrary paths;
- a block id is ``<owner>.<id>``; ``readiness`` and every ``agentic*`` owner stay Agentic Dev's;
- a hand-edited block is a conflict and is never overwritten or removed;
- content outside the block is preserved byte for byte;
- writes are atomic, re-verified before writing, and rolled back on failure;
- repeating a request is a no-op.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .detect import repo_root
from .readiness import managed
from .readiness.apply import ApplyError, FilePlan, _diff, _read, write_transaction
from .readiness.remediation import MARKER, digest, normalize

SCHEMA_VERSION = "1"
DOCUMENT_TYPE = "agentic.instruction-block"
LIST_DOCUMENT_TYPE = "agentic.instruction-blocks"
FORMAT = "markdown"

# Shared instruction files a tool may place a block in. Adding one is a contract change.
INSTRUCTION_FILES = ("AGENTS.md", "CLAUDE.md", ".claude/CLAUDE.md", "GEMINI.md", ".github/copilot-instructions.md")
# Agentic Dev's own namespaces: ``readiness`` and every owner starting with ``agentic``.
RESERVED_OWNER = re.compile(r"^(readiness$|agentic)")
OWNER = re.compile(r"^[a-z][a-z0-9-]{1,31}$")
BLOCK_NAME = re.compile(r"^[a-z][a-z0-9-]{0,31}$")
MAX_CONTENT_BYTES = 64 * 1024

EXIT_OK = 0
EXIT_CONFLICT = 1
EXIT_USAGE = 2
EXIT_ROLLED_BACK = 3
OK_STATUSES = frozenset({"created", "appended", "replaced", "unchanged", "removed", "absent"})
_OUTCOME_STATUS = {managed.CREATE: "created", managed.APPEND: "appended", managed.REPLACE: "replaced",
                   managed.UNCHANGED: "unchanged", managed.CONFLICT: "conflict", managed.REFUSED: "refused"}
_ANY_BEGIN = re.compile(r"^<!-- agentic-dev:begin ([a-z][a-z0-9-]*\.[a-z0-9][a-z0-9.-]*) sha256=([0-9a-f]{64}) -->$")


class UsageError(ValueError):
    """The request itself is invalid (exit 2); nothing was read or written."""


def _validate(file: str, owner: str, block: str) -> str:
    if file not in INSTRUCTION_FILES:
        raise UsageError(f"{file!r} is not a supported instruction file; choose one of: {', '.join(INSTRUCTION_FILES)}")
    if not OWNER.match(owner):
        raise UsageError(f"invalid owner {owner!r}: use 2-32 lowercase letters, digits, or dashes")
    if RESERVED_OWNER.match(owner):
        raise UsageError(f"owner {owner!r} is reserved for Agentic Dev (readiness and agentic*)")
    if not BLOCK_NAME.match(block):
        raise UsageError(f"invalid block id {block!r}: use 1-32 lowercase letters, digits, or dashes")
    return f"{owner}.{block}"


def _check_content(content: str) -> str:
    if len(content.encode("utf-8")) > MAX_CONTENT_BYTES:
        raise UsageError(f"block content exceeds {MAX_CONTENT_BYTES} bytes")
    if "\r" in content:
        raise UsageError("block content must use LF line endings")
    if MARKER in content:
        raise UsageError("block content must not contain managed-block markers")
    if not content.strip():
        raise UsageError("block content is empty; use `instructions block remove` to delete a block")
    return normalize(content)


def _change(block_id: str, content: str) -> dict[str, Any]:
    return {"format": FORMAT, "block_id": block_id, "content": content,
            "content_sha256": digest(normalize(content)), "prelude": None}


def _document(root: Path, action: str, file: str, owner: str, block: str, *, dry_run: bool, status: str,
              written: bool, reason: str | None = None, content_sha256: str | None = None,
              diff: str = "") -> dict[str, Any]:
    exit_code = EXIT_OK if status in OK_STATUSES else EXIT_ROLLED_BACK if status == "rolled-back" else EXIT_CONFLICT
    return {
        "schema_version": SCHEMA_VERSION,
        "document_type": DOCUMENT_TYPE,
        "repository": {"name": root.name},
        "action": action,
        "dry_run": dry_run,
        "file": file,
        "owner": owner,
        "id": block,
        "block_id": f"{owner}.{block}",
        "status": status,
        "written": written,
        "reason": reason,
        "content_sha256": content_sha256,
        "diff": diff,
        "exit_code": exit_code,
    }


def put(path: str | Path, *, file: str, owner: str, block: str, content: str,
        dry_run: bool = False) -> dict[str, Any]:
    """Create, append, or update the ``<owner>.<block>`` managed block in ``file``."""

    block_id = _validate(file, owner, block)
    body = _check_content(content)
    root = repo_root(path)
    change = _change(block_id, body)
    common = {"dry_run": dry_run, "content_sha256": change["content_sha256"]}
    current, refusal = _read(root, file)
    if refusal:
        return _document(root, "put", file, owner, block, status="refused", written=False, reason=refusal, **common)
    planned = managed.plan(current, change)
    status = _OUTCOME_STATUS[planned.outcome]
    if planned.outcome not in managed.WRITES:
        return _document(root, "put", file, owner, block, status=status, written=False, reason=planned.reason, **common)
    diff = _diff(file, current, planned.text)
    if dry_run:
        return _document(root, "put", file, owner, block, status=status, written=False, diff=diff, **common)
    try:
        write_transaction(root, [FilePlan(file, current, planned.text)])
    except ApplyError as exc:
        return _document(root, "put", file, owner, block, status="rolled-back", written=False, reason=str(exc), **common)
    return _document(root, "put", file, owner, block, status=status, written=True, diff=diff, **common)


def remove(path: str | Path, *, file: str, owner: str, block: str, dry_run: bool = False) -> dict[str, Any]:
    """Remove the ``<owner>.<block>`` block; delete the file only if nothing else remains."""

    block_id = _validate(file, owner, block)
    root = repo_root(path)
    current, refusal = _read(root, file)
    if refusal:
        return _document(root, "remove", file, owner, block, dry_run=dry_run, status="refused", written=False,
                         reason=refusal)
    if current is None:
        return _document(root, "remove", file, owner, block, dry_run=dry_run, status="absent", written=False)
    if "\r\n" in current:
        return _document(root, "remove", file, owner, block, dry_run=dry_run, status="refused", written=False,
                         reason="file uses CRLF line endings (unsupported in contract v1)")
    lines = current.split("\n")
    if current.endswith("\n"):
        lines = lines[:-1]
    found = managed.locate(lines, FORMAT, block_id)
    if found is None:
        return _document(root, "remove", file, owner, block, dry_run=dry_run, status="absent", written=False)
    if isinstance(found, str):
        return _document(root, "remove", file, owner, block, dry_run=dry_run, status="conflict", written=False,
                         reason=found)
    if digest(found.body) != found.marker_sha256:
        return _document(root, "remove", file, owner, block, dry_run=dry_run, status="conflict", written=False,
                         reason=f"managed block {block_id} was edited by hand; refusing to remove it")
    after = managed.remove(current, {"format": FORMAT, "block_id": block_id, "prelude": None})
    diff = _diff(file, current, after)
    if dry_run:
        return _document(root, "remove", file, owner, block, dry_run=True, status="removed", written=False, diff=diff)
    target = root / file
    try:
        if after is None:
            if target.read_text(encoding="utf-8") != current:
                raise ApplyError(f"{file} changed while applying")
            target.unlink()
        else:
            write_transaction(root, [FilePlan(file, current, after)])
    except (ApplyError, OSError) as exc:
        return _document(root, "remove", file, owner, block, dry_run=False, status="rolled-back", written=False,
                         reason=str(exc))
    return _document(root, "remove", file, owner, block, dry_run=False, status="removed", written=True, diff=diff)


def list_blocks(path: str | Path = ".") -> dict[str, Any]:
    """Every managed block in the supported instruction files, with its owner and integrity."""

    root = repo_root(path)
    blocks: list[dict[str, Any]] = []
    for file in INSTRUCTION_FILES:
        current, refusal = _read(root, file)
        if refusal or current is None:
            continue
        lines = current.split("\n")
        for line in lines:
            match = _ANY_BEGIN.match(line)
            if not match:
                continue
            block_id = match.group(1)
            found = managed.locate(lines[:-1] if current.endswith("\n") else lines, FORMAT, block_id)
            owner, _, name = block_id.partition(".")
            intact = not isinstance(found, str) and found is not None and digest(found.body) == found.marker_sha256
            blocks.append({"file": file, "block_id": block_id, "owner": owner, "id": name, "intact": intact})
    return {
        "schema_version": SCHEMA_VERSION,
        "document_type": LIST_DOCUMENT_TYPE,
        "repository": {"name": root.name},
        "files": list(INSTRUCTION_FILES),
        "blocks": blocks,
    }
