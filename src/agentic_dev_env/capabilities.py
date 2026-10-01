from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .detect import RepoContext, detect_repo
from .trust import check as trust_check
from .providers import capability_entries as provider_capability_entries, provider_capability_command


@dataclass(frozen=True)
class Capability:
    name: str
    category: str
    provider: str
    description: str
    risk: str
    targets: tuple[str, ...]
    required_permissions: tuple[str, ...] = ()


@dataclass(frozen=True)
class CapabilityRecommendation:
    name: str
    provider: str
    description: str
    reasons: tuple[str, ...]
    score: int


CAPABILITIES = (
    Capability(
        "browser-automation", "browser", "playwright",
        "Structured browser navigation and UI automation through Playwright MCP.",
        "Browser content and actions become accessible to the configured agent.",
        ("claude", "codex"), ("browser.isolated",),
    ),
    Capability(
        "browser-debug", "browser", "chrome-devtools",
        "Browser debugging, console/network inspection, tracing, and frontend performance analysis.",
        "The configured agent can inspect and control a Chrome session.",
        ("claude", "codex"), ("browser.isolated",),
    ),
    Capability(
        "browser-agent", "browser", "browser-use",
        "Advanced autonomous browser workflows through the Browser Use CLI and skill.",
        "May interact with authenticated browser state; configure browser/profile access deliberately.",
        ("all",), ("browser.isolated", "network.general"),
    ),
    Capability(
        "secret-scan", "security", "trivy",
        "Scan repository files for exposed secrets using Trivy.",
        "Reads repository files locally and may download/update Trivy rule/database metadata.",
        ("local",), ("repo.read", "secret.scan", "security.scan"),
    ),
    Capability(
        "dependency-vulnerability", "security", "trivy",
        "Scan dependency lockfiles and package metadata for known vulnerabilities.",
        "Reads dependency metadata locally and downloads vulnerability databases.",
        ("local",), ("repo.read", "security.scan"),
    ),
    Capability(
        "sast", "security", "semgrep",
        "Run source-level static analysis using Semgrep Community Edition.",
        "Reads source locally and downloads selected rule packs; no login is required for Community Edition.",
        ("local",), ("repo.read", "security.scan", "network.general"),
    ),
    Capability(
        "iac-misconfiguration", "security", "trivy",
        "Scan Terraform, Kubernetes, Docker and related configuration for misconfigurations.",
        "Reads infrastructure/configuration files locally and downloads Trivy checks.",
        ("local",), ("repo.read", "security.scan"),
    ),
    Capability(
        "container-image-scan", "security", "trivy",
        "Scan a container image for vulnerabilities, secrets and configuration findings.",
        "May pull image metadata/layers and vulnerability databases.",
        ("local",), ("security.scan", "network.general", "container.run"),
    ),
    Capability(
        "sbom", "security", "trivy",
        "Generate a CycloneDX software bill of materials from a repository filesystem.",
        "Reads package metadata and emits dependency inventory.",
        ("local",), ("repo.read", "security.scan"),
    ),
    Capability(
        "database-read", "database", "native-db",
        "Inspect schemas and execute explicitly read-only database queries using native CLIs.",
        "Uses existing local database credentials/configuration; query output may contain sensitive data.",
        ("local",), ("database.read",),
    ),
    Capability(
        "database-write", "database", "native-db",
        "Execute explicitly marked database write statements using native CLIs.",
        "Can mutate or destroy database state.",
        ("local",), ("database.write",),
    ),
    Capability(
        "database-local", "database", "container-db",
        "Run ephemeral local development databases in Docker/Podman.",
        "Creates local containers and stores generated development credentials in a mode-0600 local state file.",
        ("local",), ("database.local", "container.run"),
    ),
    Capability(
        "cluster-read", "cluster", "kubectl-oc",
        "Read Kubernetes/OpenShift resources, logs, events, and API information.",
        "Uses the selected kubeconfig context and may expose sensitive cluster data.",
        ("local",), ("cluster.read",),
    ),
    Capability(
        "cluster-write", "cluster", "kubectl-oc",
        "Perform explicitly selected Kubernetes/OpenShift mutation commands.",
        "Can change or delete cluster resources.",
        ("local",), ("cluster.write",),
    ),
    Capability(
        "cloud-read", "cloud", "cloud-cli",
        "Read cloud account/project identity and metadata through installed AWS/Azure/GCP CLIs.",
        "Uses existing cloud credentials and can expose account metadata.",
        ("local",), ("cloud.read",),
    ),
    Capability(
        "cloud-write", "cloud", "cloud-cli",
        "Run explicitly marked cloud mutation commands.",
        "Can create, modify, or delete cloud resources and incur cost.",
        ("local",), ("cloud.write",),
    ),
    Capability(
        "observability-read", "observability", "opentelemetry",
        "Inspect local OpenTelemetry configuration and observability tooling.",
        "May expose telemetry endpoints and service metadata.",
        ("local",), ("observability.read",),
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
    result = list(CAPABILITIES)
    names = {item.name for item in result}
    for item, _root, provider_name in provider_capability_entries():
        name = item["name"]
        if name in names:
            continue
        result.append(Capability(
            name=name,
            category=item["category"],
            provider=item.get("provider") or provider_name,
            description=item["description"],
            risk=item["risk"],
            targets=tuple(item.get("targets") or ["local"]),
            required_permissions=tuple(item.get("required_permissions") or []),
        ))
        names.add(name)
    return tuple(result)


def get_capability(name: str) -> Capability:
    for capability in list_capabilities():
        if capability.name == name:
            return capability
    raise KeyError(name)


def required_permissions(name: str, mode: str = "isolated") -> tuple[str, ...]:
    cap = get_capability(name)
    perms = list(cap.required_permissions)
    if name in {"browser-automation", "browser-debug"}:
        perms = [p for p in perms if not p.startswith("browser.")]
        if mode == "existing-browser":
            perms.append("browser.authenticated")
        elif mode == "persistent":
            perms.append("browser.persistent")
        else:
            perms.append("browser.isolated")
    return tuple(sorted(set(perms)))


def suggest(context: RepoContext, task: str = "") -> list[CapabilityRecommendation]:
    task_l = task.lower()
    result: list[CapabilityRecommendation] = []

    def add(name: str, reasons: list[str], base: int = 6) -> None:
        if not reasons:
            return
        cap = get_capability(name)
        result.append(CapabilityRecommendation(
            name, cap.provider, cap.description,
            tuple(dict.fromkeys(reasons)), base + len(reasons),
        ))

    web_signals = {
        "repo-type:web-app", "framework:react", "framework:nextjs",
        "framework:vue", "framework:svelte", "framework:angular",
        "testing:browser",
    }
    reasons = []
    if context.facts & web_signals:
        reasons.append("web application or browser-test signals detected")
    for word in ("browser", "ui", "e2e", "end-to-end", "website", "form", "playwright"):
        if word in task_l:
            reasons.append(f"task mentions '{word}'")
    add("browser-automation", reasons)

    reasons = [f"task mentions '{word}'" for word in (
        "performance", "network", "console", "trace", "frontend latency", "page load"
    ) if word in task_l]
    add("browser-debug", reasons, 7)

    reasons = [f"task mentions '{word}'" for word in (
        "research the web", "portal", "browse sites", "multi-step browser", "scrape", "web research"
    ) if word in task_l]
    add("browser-agent", reasons, 7)

    has_source = any(f.startswith("language:") for f in context.facts)
    has_packages = any(f.startswith("language:") for f in context.facts) or any(
        f.startswith("repo-type:package") for f in context.facts
    )
    has_iac = bool(context.facts & {
        "technology:terraform", "technology:kubernetes", "technology:helm",
        "technology:kustomize", "technology:containers",
    })

    reasons = []
    if has_source:
        reasons.append("source code detected")
    if any(word in task_l for word in ("security", "secret", "credential", "review", "pre-merge")):
        reasons.append("task requests security/secret-sensitive review")
    add("secret-scan", reasons, 5)

    reasons = []
    if has_packages:
        reasons.append("package/dependency metadata detected")
    if any(word in task_l for word in ("dependency", "vulnerability", "cve", "security", "supply chain")):
        reasons.append("task mentions dependency/security risk")
    add("dependency-vulnerability", reasons, 5)

    reasons = []
    if has_source:
        reasons.append("source code detected")
    if any(word in task_l for word in ("sast", "security", "injection", "xss", "sql injection")):
        reasons.append("task requests source security analysis")
    add("sast", reasons, 5)

    reasons = []
    if has_iac:
        reasons.append("infrastructure/container configuration detected")
    if any(word in task_l for word in ("terraform", "kubernetes", "docker", "misconfig", "hardening")):
        reasons.append("task mentions infrastructure configuration")
    add("iac-misconfiguration", reasons, 6)

    reasons = []
    if "technology:containers" in context.facts:
        reasons.append("container build/runtime files detected")
    if any(word in task_l for word in ("container image", "image scan", "docker image")):
        reasons.append("task mentions container image")
    add("container-image-scan", reasons, 5)

    reasons = []
    if has_packages:
        reasons.append("software package metadata detected")
    if any(word in task_l for word in ("sbom", "bill of materials", "supply chain")):
        reasons.append("task requests software inventory")
    add("sbom", reasons, 4)

    has_database = any(f.startswith("database:") for f in context.facts)
    reasons = []
    if has_database:
        reasons.append("database or migration signals detected")
    if any(word in task_l for word in ("database", "schema", "migration", "sql", "postgres", "mysql", "sqlite")):
        reasons.append("task mentions database work")
    add("database-read", reasons, 6)

    reasons = []
    if "technology:kubernetes" in context.facts:
        reasons.append("Kubernetes/OpenShift configuration detected")
    if any(word in task_l for word in ("cluster", "kubernetes", "openshift", "kubectl", "oc ", "pod logs")):
        reasons.append("task mentions cluster operations")
    add("cluster-read", reasons, 6)

    reasons = []
    if any(word in task_l for word in ("aws", "azure", "gcp", "cloud account", "cloud project")):
        reasons.append("task explicitly mentions a cloud provider")
    add("cloud-read", reasons, 6)

    reasons = []
    if any(word in task_l for word in ("logs", "metrics", "traces", "opentelemetry", "observability", "otel")):
        reasons.append("task mentions observability/telemetry")
    add("observability-read", reasons, 6)

    return sorted(result, key=lambda item: (-item.score, item.name))


def suggest_for_repo(path: str | Path = ".", task: str = ""):
    context = detect_repo(path)
    return context, suggest(context, task)


def _run(argv: list[str], *, cwd: Path | None = None) -> int:
    print("$ " + " ".join(argv))
    return subprocess.run(argv, cwd=cwd, check=False).returncode


def _capture(argv: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, cwd=cwd, capture_output=True, text=True, check=False)


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


def _ensure_security_provider(provider: str) -> int:
    if shutil.which(provider):
        return 0
    brew = shutil.which("brew")
    if brew:
        return _run([brew, "install", provider])
    if provider == "semgrep" and shutil.which("uv"):
        return _run(["uv", "tool", "install", "--upgrade", "semgrep"])
    print(f"! {provider} is required. Install it and retry.")
    return 2


def enable(
    name: str,
    *,
    target: str = "both",
    mode: str = "isolated",
    profile: str | None = None,
    path: str | Path | None = None,
) -> int:
    cap = get_capability(name)
    allowed, missing, selected = trust_check(
        required_permissions(name, mode),
        profile_name=profile,
        root=path,
    )
    if not allowed:
        print(f"! trust profile '{selected.name}' does not allow {name}.")
        print("  missing permissions: " + ", ".join(missing))
        return 3

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
    elif cap.category == "browser":
        server, command = _mcp_args(cap.provider, mode)
        for agent in _targets(target):
            binary = shutil.which(agent)
            if not binary:
                print(f"· {agent} not installed; skipping.")
                continue
            subprocess.run([binary, "mcp", "remove", server], capture_output=True, text=True, check=False)
            rc = _run([binary, "mcp", "add", server, *command])
            if rc != 0:
                return rc
    elif cap.category == "security":
        rc = _ensure_security_provider(cap.provider)
        if rc != 0:
            return rc

    state = _load_state()
    state.setdefault("enabled", {})[name] = {
        "category": cap.category,
        "provider": cap.provider,
        "target": target,
        "mode": mode,
        "trust_profile": selected.name,
    }
    _save_state(state)
    print(f"✓ enabled {name} via {cap.provider} under trust profile {selected.name}")
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
    elif cap.category == "security":
        print(f"· {cap.provider} remains installed; capability state is being disabled only.")

    state.setdefault("enabled", {}).pop(name, None)
    _save_state(state)
    print(f"✓ disabled {name}")
    return 0


def _security_command(name: str, root: Path, image: str | None = None) -> list[str]:
    if name == "secret-scan":
        return ["trivy", "fs", "--scanners", "secret", "--format", "json", str(root)]
    if name == "dependency-vulnerability":
        return ["trivy", "fs", "--scanners", "vuln", "--format", "json", str(root)]
    if name == "iac-misconfiguration":
        return ["trivy", "fs", "--scanners", "misconfig", "--format", "json", str(root)]
    if name == "sast":
        return ["semgrep", "--config=auto", "--json", str(root)]
    if name == "container-image-scan":
        if not image:
            raise ValueError("container-image-scan requires --image")
        return ["trivy", "image", "--format", "json", image]
    if name == "sbom":
        return ["trivy", "fs", "--format", "cyclonedx", str(root)]
    raise ValueError(f"{name} is not a runnable security capability")


def _finding_count(name: str, payload: Any) -> int | None:
    if name == "sast" and isinstance(payload, dict):
        return len(payload.get("results") or [])
    if name == "sbom" and isinstance(payload, dict):
        return len(payload.get("components") or [])
    if isinstance(payload, dict):
        total = 0
        seen = False
        for result in payload.get("Results") or []:
            for key in ("Vulnerabilities", "Misconfigurations", "Secrets"):
                values = result.get(key)
                if isinstance(values, list):
                    total += len(values)
                    seen = True
        return total if seen else 0
    return None


def run_capability(
    name: str,
    path: str | Path = ".",
    *,
    image: str | None = None,
    profile: str | None = None,
) -> dict[str, Any]:
    cap = get_capability(name)
    external = provider_capability_command(name)
    if external is not None:
        command, provider_root, provider_name = external
        allowed, missing, selected = trust_check(
            required_permissions(name),
            profile_name=profile,
            root=path,
        )
        if not allowed:
            raise PermissionError(
                f"trust profile '{selected.name}' missing permissions: {', '.join(missing)}"
            )
        state = _load_state().get("enabled", {})
        if name not in state:
            raise RuntimeError(f"{name} is not enabled; enable it before running provider commands")
        root = Path(path).resolve()
        argv = [part.replace("{repo}", str(root)) for part in command]
        result = _capture(argv, cwd=provider_root)
        payload: Any = None
        parse_error: str | None = None
        if result.stdout.strip():
            try:
                payload = json.loads(result.stdout)
            except json.JSONDecodeError as exc:
                parse_error = str(exc)
                payload = result.stdout
        return {
            "schema_version": "1",
            "document_type": "agentic.capability-result",
            "capability": name,
            "category": cap.category,
            "provider": provider_name,
            "trust_profile": selected.name,
            "command": argv,
            "returncode": result.returncode,
            "success": result.returncode == 0,
            "finding_count": None,
            "result": payload,
            "stderr": result.stderr.strip(),
            "parse_error": parse_error,
        }
    if cap.category != "security":
        raise ValueError("capability run is only implemented for security or command-backed provider capabilities")
    allowed, missing, selected = trust_check(
        required_permissions(name),
        profile_name=profile,
        root=path,
    )
    if not allowed:
        raise PermissionError(
            f"trust profile '{selected.name}' missing permissions: {', '.join(missing)}"
        )
    if not shutil.which(cap.provider):
        raise RuntimeError(f"{cap.provider} is not installed; enable {name} first")

    root = Path(path).resolve()
    command = _security_command(name, root, image=image)
    result = _capture(command, cwd=root)
    payload: Any = None
    parse_error: str | None = None
    try:
        payload = json.loads(result.stdout) if result.stdout.strip() else None
    except json.JSONDecodeError as exc:
        parse_error = str(exc)

    return {
        "schema_version": "1",
        "document_type": "agentic.capability-result",
        "capability": name,
        "category": cap.category,
        "provider": cap.provider,
        "trust_profile": selected.name,
        "command": command,
        "returncode": result.returncode,
        "success": result.returncode == 0,
        "finding_count": _finding_count(name, payload),
        "result": payload,
        "stderr": result.stderr.strip(),
        "parse_error": parse_error,
    }


def status() -> dict:
    state = _load_state()
    enabled = state.get("enabled", {})
    return {
        capability.name: {
            "category": capability.category,
            "provider": capability.provider,
            "enabled": capability.name in enabled,
            "configuration": enabled.get(capability.name),
            "risk": capability.risk,
            "required_permissions": list(capability.required_permissions),
        }
        for capability in list_capabilities()
    }
