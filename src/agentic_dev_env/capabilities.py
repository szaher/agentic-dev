from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .detect import RepoContext, detect_repo


@dataclass(frozen=True)
class Capability:
    name: str
    provider: str
    description: str
    risk: str
    targets: tuple[str, ...]


@dataclass(frozen=True)
class CapabilityRecommendation:
    name: str
    provider: str
    description: str
    reasons: tuple[str, ...]
    score: int


CAPABILITIES = (
    Capability(
        "browser-automation",
        "playwright",
        "Structured browser navigation and UI automation through Playwright MCP.",
        "Browser content and actions become accessible to the configured agent.",
        ("claude", "codex"),
    ),
    Capability(
        "browser-debug",
        "chrome-devtools",
        "Browser debugging, console/network inspection, tracing, and frontend performance analysis.",
        "The configured agent can inspect and control a Chrome session.",
        ("claude", "codex"),
    ),
    Capability(
        "browser-agent",
        "browser-use",
        "Advanced autonomous browser workflows through the Browser Use CLI and skill.",
        "May interact with authenticated browser state; configure browser/profile access deliberately.",
        ("all",),
    ),
)


def _config_dir() -> Path:
    return Path(os.environ.get("AGENTIC_DEV_ENV_CONFIG_DIR", Path.home() / ".config" / "agentic-dev-env"))


def _state_file() -> Path:
    return _config_dir() / "capabilities.json"


def _load_state() -> dict:
    path = _state_file()
    if not path.exists():
        return {"enabled": {}}
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {"enabled": {}}


def _save_state(data: dict) -> None:
    path = _state_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def list_capabilities() -> tuple[Capability, ...]:
    return CAPABILITIES


def get_capability(name: str) -> Capability:
    for capability in CAPABILITIES:
        if capability.name == name:
            return capability
    raise KeyError(name)


def suggest(context: RepoContext, task: str = "") -> list[CapabilityRecommendation]:
    task_l = task.lower()
    result: list[CapabilityRecommendation] = []

    web_signals = {
        "repo-type:web-app",
        "framework:react",
        "framework:nextjs",
        "framework:vue",
        "framework:svelte",
        "framework:angular",
        "testing:browser",
    }
    automation_reasons = []
    if context.facts & web_signals:
        automation_reasons.append("web application or browser-test signals detected")
    for word in ("browser", "ui", "e2e", "end-to-end", "website", "form", "playwright"):
        if word in task_l:
            automation_reasons.append(f"task mentions '{word}'")
    if automation_reasons:
        result.append(CapabilityRecommendation(
            "browser-automation", "playwright",
            get_capability("browser-automation").description,
            tuple(dict.fromkeys(automation_reasons)),
            6 + len(automation_reasons),
        ))

    debug_reasons = []
    for word in ("performance", "network", "console", "trace", "frontend latency", "page load"):
        if word in task_l:
            debug_reasons.append(f"task mentions '{word}'")
    if debug_reasons:
        result.append(CapabilityRecommendation(
            "browser-debug", "chrome-devtools",
            get_capability("browser-debug").description,
            tuple(debug_reasons),
            7 + len(debug_reasons),
        ))

    agent_reasons = []
    for word in ("research the web", "portal", "browse sites", "multi-step browser", "scrape", "web research"):
        if word in task_l:
            agent_reasons.append(f"task mentions '{word}'")
    if agent_reasons:
        result.append(CapabilityRecommendation(
            "browser-agent", "browser-use",
            get_capability("browser-agent").description,
            tuple(agent_reasons),
            7 + len(agent_reasons),
        ))

    return sorted(result, key=lambda item: (-item.score, item.name))


def suggest_for_repo(path: str | Path = ".", task: str = ""):
    context = detect_repo(path)
    return context, suggest(context, task)


def _run(argv: list[str]) -> int:
    print("$ " + " ".join(argv))
    return subprocess.run(argv, check=False).returncode


def _mcp_args(provider: str, mode: str) -> tuple[str, list[str]]:
    if provider == "playwright":
        args = ["npx", "@playwright/mcp@latest"]
        if mode == "isolated":
            args.append("--isolated")
        elif mode == "existing-browser":
            args.append("--extension")
        elif mode != "persistent":
            raise ValueError("Playwright mode must be isolated, persistent, or existing-browser")
        return "playwright", args

    if provider == "chrome-devtools":
        args = ["npx", "-y", "chrome-devtools-mcp@latest"]
        if mode == "isolated":
            args.append("--isolated")
        elif mode == "headless":
            args += ["--slim", "--headless"]
        elif mode != "persistent":
            raise ValueError("Chrome DevTools mode must be isolated, persistent, or headless")
        return "chrome-devtools", args

    raise ValueError(f"Provider is not MCP-based: {provider}")


def _targets(target: str) -> list[str]:
    if target == "both":
        return ["claude", "codex"]
    if target in {"claude", "codex"}:
        return [target]
    raise ValueError("MCP browser target must be claude, codex, or both")


def enable(name: str, *, target: str = "both", mode: str = "isolated") -> int:
    cap = get_capability(name)

    if cap.provider == "browser-use":
        if not shutil.which("uv"):
            print("! Browser Use installation requires uv.")
            return 2
        rc = _run(["uv", "tool", "install", "--python", "3.12", "--upgrade", "browser-use"])
        if rc == 0:
            browser_use = shutil.which("browser-use")
            if browser_use:
                rc = _run([browser_use, "skill", "install"])
        if rc != 0:
            return rc
    else:
        server, command = _mcp_args(cap.provider, mode)
        for agent in _targets(target):
            binary = shutil.which(agent)
            if not binary:
                print(f"· {agent} not installed; skipping.")
                continue
            # Make reruns idempotent where the client supports remove.
            subprocess.run([binary, "mcp", "remove", server], capture_output=True, text=True, check=False)
            rc = _run([binary, "mcp", "add", server, *command])
            if rc != 0:
                return rc

    state = _load_state()
    state.setdefault("enabled", {})[name] = {
        "provider": cap.provider,
        "target": target,
        "mode": mode,
    }
    _save_state(state)
    print(f"✓ enabled {name} via {cap.provider}")
    return 0


def disable(name: str) -> int:
    cap = get_capability(name)
    state = _load_state()
    entry = state.get("enabled", {}).get(name, {})
    target = entry.get("target", "both")

    if cap.provider in {"playwright", "chrome-devtools"}:
        server = "playwright" if cap.provider == "playwright" else "chrome-devtools"
        for agent in _targets(target if target in {"claude", "codex", "both"} else "both"):
            binary = shutil.which(agent)
            if binary:
                subprocess.run([binary, "mcp", "remove", server], check=False)
    elif cap.provider == "browser-use":
        print("· Browser Use remains installed as a CLI; capability state is being disabled only.")

    state.setdefault("enabled", {}).pop(name, None)
    _save_state(state)
    print(f"✓ disabled {name}")
    return 0


def status() -> dict:
    state = _load_state()
    enabled = state.get("enabled", {})
    return {
        capability.name: {
            "provider": capability.provider,
            "enabled": capability.name in enabled,
            "configuration": enabled.get(capability.name),
            "risk": capability.risk,
        }
        for capability in CAPABILITIES
    }
