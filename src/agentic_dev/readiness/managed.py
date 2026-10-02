"""Managed-block text operations (pure, no I/O).

Implements the normative apply table in docs/REMEDIATION.md for a single
change against a file's current text. Callers handle reading, writing,
preconditions, and transactions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .remediation import FORMATS, MARKER, digest, render_block

CREATE = "create"
APPEND = "append"
REPLACE = "replace"
UNCHANGED = "unchanged"
CONFLICT = "conflict"
REFUSED = "refused"
WRITES = frozenset({CREATE, APPEND, REPLACE})


@dataclass(frozen=True)
class Planned:
    outcome: str
    text: str | None
    reason: str | None = None


def _marker_patterns(fmt: str, block_id: str) -> tuple[re.Pattern[str], re.Pattern[str]]:
    open_, close = (re.escape(part) for part in FORMATS[fmt])
    bid = re.escape(block_id)
    begin = re.compile(rf"^{open_}{re.escape(MARKER)}begin {bid} sha256=([0-9a-f]{{64}}){close}$")
    end = re.compile(rf"^{open_}{re.escape(MARKER)}end {bid}{close}$")
    return begin, end


@dataclass(frozen=True)
class Located:
    start: int          # index of the begin marker line
    stop: int           # index of the end marker line
    marker_sha256: str
    body: str


def locate(lines: list[str], fmt: str, block_id: str) -> Located | None | str:
    """Find a block. Returns ``None`` if absent, or an error string if markers are malformed."""

    begin, end = _marker_patterns(fmt, block_id)
    begins = [i for i, line in enumerate(lines) if begin.match(line)]
    ends = [i for i, line in enumerate(lines) if end.match(line)]
    if not begins and not ends:
        return None
    if len(begins) != 1 or len(ends) != 1 or ends[0] < begins[0]:
        return f"duplicate or unbalanced markers for {block_id}"
    start, stop = begins[0], ends[0]
    body = "".join(line + "\n" for line in lines[start + 1:stop])
    return Located(start, stop, begin.match(lines[start]).group(1), body)


def plan(current: str | None, change: dict[str, Any]) -> Planned:
    """What applying ``change`` to a file whose text is ``current`` (None: absent) would do."""

    block = render_block(change["format"], change["block_id"], change["content"])
    if current is None:
        prelude = change.get("prelude")
        text = f"{prelude.rstrip(chr(10))}\n\n{block}" if prelude else block
        return Planned(CREATE, text)
    if "\r\n" in current:
        return Planned(REFUSED, None, "file uses CRLF line endings (unsupported in contract v1)")
    lines = current.split("\n")
    trailing_newline = current.endswith("\n")
    if trailing_newline:
        lines = lines[:-1]
    found = locate(lines, change["format"], change["block_id"])
    if isinstance(found, str):
        return Planned(CONFLICT, None, found)
    if found is None:
        if not current:
            return Planned(APPEND, block)
        # Bytes before the block are kept exactly; only a missing final newline
        # and one blank separator line are added.
        base = current if trailing_newline else current + "\n"
        return Planned(APPEND, base + "\n" + block)
    if digest(found.body) != found.marker_sha256:
        return Planned(CONFLICT, None, f"managed block {change['block_id']} was edited by hand; refusing to overwrite")
    if found.marker_sha256 == change["content_sha256"]:
        return Planned(UNCHANGED, current)
    before = "".join(line + "\n" for line in lines[:found.start])
    after = "".join(line + "\n" for line in lines[found.stop + 1:])
    if after and not trailing_newline:
        after = after[:-1]
    return Planned(REPLACE, before + block + after)


def remove(current: str, change: dict[str, Any]) -> str | None:
    """Remove a managed block per the contract. Returns ``None`` when the file should be deleted."""

    lines = current.split("\n")
    trailing_newline = current.endswith("\n")
    if trailing_newline:
        lines = lines[:-1]
    found = locate(lines, change["format"], change["block_id"])
    if found is None or isinstance(found, str):
        return current
    start = found.start
    if start > 0 and lines[start - 1] == "":
        start -= 1
    kept = lines[:start] + lines[found.stop + 1:]
    text = "".join(line + "\n" for line in kept)
    prelude = change.get("prelude") or ""
    if not text.strip() or (prelude and text.strip() == prelude.strip()):
        return None
    return text
