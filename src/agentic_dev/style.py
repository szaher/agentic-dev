"""Terminal presentation for human-readable CLI output.

Styling is purely additive. While disabled, every helper returns its input
unchanged, so the plain text that agents, pipes, CI, and tests receive is
byte-for-byte the unstyled view. ``--json`` documents never pass through here.

Color is enabled only for an interactive terminal, unless overridden:

1. ``--color always|never|auto`` (global CLI flag)
2. ``AGENTIC_COLOR=always|never|auto``
3. ``NO_COLOR`` (any value) disables; ``FORCE_COLOR``/``CLICOLOR_FORCE`` enables
4. ``TERM=dumb``, CI, or a coding-agent environment disables
5. otherwise: the stream is a TTY

Animations (spinners) follow the same rules for stderr and never run when
color is off, so automated callers never see carriage returns or escapes.
"""

from __future__ import annotations

import contextlib
import itertools
import os
import re
import sys
import threading
from collections.abc import Iterator
from typing import TextIO

MODES = ("auto", "always", "never")

# Environment markers set by CI systems and coding-agent harnesses. Their
# output is read by programs, so it stays plain even if a PTY is attached.
AUTOMATION_ENV = (
    "CI",
    "CLAUDECODE",
    "CODEX_SANDBOX",
    "CODEX_SANDBOX_NETWORK_DISABLED",
    "GEMINI_CLI",
    "AGENTIC_AUTOMATION",
)

_ANSI = re.compile(r"\x1b\[[0-9;]*m")

# Brand palette (docs/BRAND.md) with 256-color fallbacks.
_BRAND = {
    "orange": ((233, 74, 24), 202),
    "bright": ((255, 122, 26), 208),
    "amber": ((255, 178, 26), 214),
}

_mode = "never"
_enabled = False
_truecolor = False


def _wants_color(stream: TextIO, mode: str, env: dict[str, str]) -> bool:
    if mode == "auto":
        mode = env.get("AGENTIC_COLOR", "auto").strip().lower()
        if mode not in MODES:
            mode = "auto"
    if mode != "auto":
        return mode == "always"
    if "NO_COLOR" in env:
        return False
    if env.get("FORCE_COLOR", "") not in {"", "0"} or env.get("CLICOLOR_FORCE", "") not in {"", "0"}:
        return True
    if env.get("TERM") == "dumb" or any(env.get(name) for name in AUTOMATION_ENV):
        return False
    isatty = getattr(stream, "isatty", None)
    return bool(isatty and isatty())


def configure(mode: str = "auto", *, stream: TextIO | None = None, env: dict[str, str] | None = None) -> bool:
    """Decide once, at startup, whether stdout output is styled."""

    global _mode, _enabled, _truecolor
    env = dict(os.environ) if env is None else env
    _mode = mode
    _enabled = _wants_color(stream or sys.stdout, mode, env)
    _truecolor = env.get("COLORTERM", "").lower() in {"truecolor", "24bit"}
    return _enabled


def enabled() -> bool:
    return _enabled


@contextlib.contextmanager
def target(stream: TextIO) -> Iterator[None]:
    """Style for ``stream`` (e.g. stderr) instead of stdout for a block."""

    global _enabled
    previous = _enabled
    _enabled = _wants_color(stream, _mode, dict(os.environ))
    try:
        yield
    finally:
        _enabled = previous


def strip(text: str) -> str:
    return _ANSI.sub("", text)


def _sgr(text: str, *codes: str) -> str:
    if not _enabled or not text:
        return text
    return f"\x1b[{';'.join(codes)}m{text}\x1b[0m"


def _brand(name: str) -> str:
    rgb, fallback = _BRAND[name]
    return "38;2;{};{};{}".format(*rgb) if _truecolor else f"38;5;{fallback}"


# Semantic roles. Renderers describe meaning; this module decides appearance.

def title(text: str) -> str:
    return _sgr(text, "1", _brand("orange"))


def section(text: str) -> str:
    return _sgr(text, "1")


def label(text: str) -> str:
    return _sgr(text, "2")


def muted(text: str) -> str:
    return _sgr(text, "2")


def accent(text: str) -> str:
    return _sgr(text, _brand("amber"))


def command(text: str) -> str:
    return _sgr(text, "36")


def ok(text: str) -> str:
    return _sgr(text, "32")


def fail(text: str) -> str:
    return _sgr(text, "1", "31")


def warn(text: str) -> str:
    return _sgr(text, "33")


def badge(text: str, tone: str) -> str:
    """A status word next to a title, e.g. ``READY`` or ``BLOCKED``."""

    color = {"ok": "32", "fail": "31", "warn": "33", "info": "36"}.get(tone, "37")
    return _sgr(text, "1", color)


def tone(text: str, name: str) -> str:
    return {"ok": ok, "fail": fail, "warn": warn, "info": command, "muted": muted}.get(name, str)(text)


_MARK_TONE = {"✓": "ok", "✗": "fail", "!": "warn", "?": "warn", "·": "muted", "–": "muted"}


def mark(symbol: str) -> str:
    """Color a status glyph such as ``✓`` or ``✗``."""

    return tone(symbol, _MARK_TONE.get(symbol, ""))


def err(prefix: str) -> str:
    """An error prefix (``agentic:``) styled for stderr, not stdout."""

    with target(sys.stderr):
        return fail(prefix)


def bullet() -> str:
    # Same glyph as plain output: styled text minus escapes equals plain text.
    return _sgr("-", _brand("bright"))


def heading(name: str, status: str = "", tone_name: str = "info") -> str:
    """``NAME  STATUS`` with the status rendered as a badge when styled."""

    if not status:
        return title(name)
    return f"{title(name)}  {badge(status, tone_name)}"


def paint(text: str, word: str, styler) -> str:
    """Style the first occurrence of ``word`` in already-wrapped ``text``."""

    if not _enabled or not word or word not in text:
        return text
    return text.replace(word, styler(word), 1)


# Status vocabulary shared by renderers.
STATUS_TONE = {
    "pass": "ok", "passed": "ok", "ready": "ok", "clean": "ok", "applied": "ok",
    "achieved": "ok", "met": "ok", "selected": "ok", "available": "ok", "configured": "ok",
    "fail": "fail", "failed": "fail", "blocked": "fail", "conflict": "fail", "refused": "fail",
    "error": "fail", "missing": "fail", "unavailable": "fail",
    "inspected": "ok", "undetermined": "warn",
    "unknown": "warn", "skip": "warn", "dirty": "warn", "planned": "warn", "no-checks": "warn",
    "not-applicable": "muted", "no-op": "muted",
}


def status(text: str, key: str | None = None) -> str:
    return tone(text, STATUS_TONE.get((key or text).strip().lower(), ""))


# Animation.

_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


@contextlib.contextmanager
def spinner(message: str, *, stream: TextIO | None = None) -> Iterator[None]:
    """Show an animated progress line on stderr while a slow step runs.

    No-op unless stderr is an interactive, color-enabled terminal, so piped
    and agent-driven runs never receive control characters.
    """

    stream = stream or sys.stderr
    with target(stream):
        # Forcing color (e.g. for a pager or log) never forces animation.
        isatty = getattr(stream, "isatty", None)
        active = _enabled and bool(isatty and isatty())
        frame_style = _brand("bright")
    if not active:
        yield
        return
    done = threading.Event()

    def run() -> None:
        for frame in itertools.cycle(_FRAMES):
            stream.write(f"\r\x1b[{frame_style}m{frame}\x1b[0m \x1b[2m{message}\x1b[0m\x1b[K")
            stream.flush()
            if done.wait(0.08):
                break
        stream.write("\r\x1b[K")
        stream.flush()

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    try:
        yield
    finally:
        done.set()
        thread.join()
