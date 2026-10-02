from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass


MARKETPLACE_REPO = "szaher/agentic-dev"
CLAUDE_PLUGIN_ID = "agentic-dev@agentic-dev"
PI_SOURCE = "git:github.com/szaher/agentic-dev"


@dataclass(frozen=True)
class IntegrationStatus:
    name: str
    available: bool
    configured: bool
    detail: str


def _capture(argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, capture_output=True, text=True, check=False)


def _visible_output(result: subprocess.CompletedProcess[str]) -> str:
    return (result.stdout or result.stderr or "").strip()


def status() -> list[IntegrationStatus]:
    result: list[IntegrationStatus] = []

    claude = shutil.which("claude")
    if claude:
        probe = _capture([claude, "plugin", "list"])
        text = _visible_output(probe)
        configured = CLAUDE_PLUGIN_ID in text
        detail = "plugin installed" if configured else "plugin not installed"
    else:
        configured = False
        detail = "Claude Code not installed"
    result.append(IntegrationStatus("claude", bool(claude), configured, detail))

    codex = shutil.which("codex")
    if codex:
        probe = _capture([codex, "plugin", "marketplace", "list"])
        text = _visible_output(probe)
        configured = "agentic-dev" in text
        detail = "marketplace registered" if configured else "marketplace not registered"
    else:
        configured = False
        detail = "Codex not installed"
    result.append(IntegrationStatus("codex", bool(codex), configured, detail))

    pi = shutil.which("pi")
    if pi:
        probe = _capture([pi, "list"])
        text = _visible_output(probe)
        configured = "agentic-dev" in text or MARKETPLACE_REPO in text
        detail = "package installed" if configured else "package not installed"
    else:
        configured = False
        detail = "Pi not installed"
    result.append(IntegrationStatus("pi", bool(pi), configured, detail))

    return result


def _run(argv: list[str]) -> int:
    print("$ " + " ".join(argv))
    result = subprocess.run(argv, check=False)
    return result.returncode


def install_claude() -> int:
    claude = shutil.which("claude")
    if not claude:
        print("! Claude Code is not installed.")
        return 2

    current = _capture([claude, "plugin", "list"])
    if CLAUDE_PLUGIN_ID in _visible_output(current):
        print(f"✓ Claude plugin already installed: {CLAUDE_PLUGIN_ID}")
        return 0

    # Adding an existing marketplace may return non-zero on some versions.
    # Continue to the install command so reruns remain useful.
    _run([claude, "plugin", "marketplace", "add", MARKETPLACE_REPO])
    rc = _run([claude, "plugin", "install", CLAUDE_PLUGIN_ID])
    if rc == 0:
        print("✓ Claude Code integration installed. Start a new session or reload plugins.")
    return rc


def install_codex() -> int:
    codex = shutil.which("codex")
    if not codex:
        print("! Codex is not installed.")
        return 2

    current = _capture([codex, "plugin", "marketplace", "list"])
    if "agentic-dev" not in _visible_output(current):
        rc = _run([codex, "plugin", "marketplace", "add", MARKETPLACE_REPO])
        if rc != 0:
            return rc
    else:
        print("✓ Codex marketplace already registered: agentic-dev")

    # Current Codex authoring flow registers local/Git marketplaces from the CLI,
    # then installs the selected plugin from /plugins or the desktop Plugins Directory.
    print("→ Open Codex, run /plugins, choose the agentic-dev marketplace, and install Agentic Dev.")
    return 0


def install_pi() -> int:
    pi = shutil.which("pi")
    if not pi:
        print("! Pi is not installed.")
        return 2

    current = _capture([pi, "list"])
    text = _visible_output(current)
    if "agentic-dev" in text or MARKETPLACE_REPO in text:
        print("✓ Pi package already installed: agentic-dev")
        return 0

    rc = _run([pi, "install", PI_SOURCE])
    if rc == 0:
        print("✓ Pi package installed. Restart Pi or reload its configuration.")
    return rc


def install(target: str) -> int:
    installers = {
        "claude": install_claude,
        "codex": install_codex,
        "pi": install_pi,
    }
    binaries = {"claude": "claude", "codex": "codex", "pi": "pi"}
    targets = ["claude", "codex", "pi"] if target == "all" else [target]
    codes: list[int] = []
    for name in targets:
        if target == "all" and not shutil.which(binaries[name]):
            print(f"· {name} not installed; skipping.")
            continue
        codes.append(installers[name]())
    return max(codes, default=0)
