from __future__ import annotations

import json
import shlex
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from .capabilities import run_capability, status as capability_status
from .detect import repo_root
from .inspection import inspect_repository
from .execution import run as run_execution
from .metrics import record as record_metric


SOURCE_EXTENSIONS = {
    ".py": "python",
    ".go": "go",
    ".rs": "rust",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".java": "jvm",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".rb": "ruby",
    ".php": "php",
    ".swift": "swift",
    ".c": "cpp",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".h": "cpp",
    ".hpp": "cpp",
}

CONFIG_NAMES = {
    "pyproject.toml", "package.json", "Cargo.toml", "go.mod",
    "go.sum", "requirements.txt", "Dockerfile", "compose.yml",
    "docker-compose.yml", "Chart.yaml", "kustomization.yaml",
}

IAC_EXTENSIONS = {".tf", ".tfvars", ".yaml", ".yml"}


def _run(argv: list[str], *, cwd: Path, check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, cwd=cwd, capture_output=True, text=True, check=check)


def changed_files(path: str | Path = ".", base: str | None = None) -> list[str]:
    root = repo_root(path)
    files: set[str] = set()
    if base:
        diff = _run(["git", "diff", "--name-only", f"{base}...HEAD"], cwd=root)
        files.update(line.strip() for line in diff.stdout.splitlines() if line.strip())
    working = _run(["git", "diff", "--name-only", "HEAD"], cwd=root)
    files.update(line.strip() for line in working.stdout.splitlines() if line.strip())
    untracked = _run(["git", "ls-files", "--others", "--exclude-standard"], cwd=root)
    files.update(line.strip() for line in untracked.stdout.splitlines() if line.strip())
    return sorted(files)


def _codegraph_affected(root: Path, files: list[str]) -> dict[str, Any]:
    if not files or not shutil.which("codegraph") or not (root / ".codegraph").exists():
        return {"available": False, "tests": [], "raw": None}
    result = _run(["codegraph", "affected", *files, "--json"], cwd=root)
    if result.returncode != 0:
        return {
            "available": True,
            "tests": [],
            "raw": None,
            "error": (result.stderr or result.stdout).strip(),
        }
    raw = result.stdout.strip()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        tests = [line.strip() for line in raw.splitlines() if line.strip()]
        return {"available": True, "tests": tests, "raw": raw}
    tests: list[str] = []
    if isinstance(payload, list):
        tests = [str(x) for x in payload if isinstance(x, (str, int))]
    elif isinstance(payload, dict):
        for key in ("tests", "affected", "files", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, str):
                        tests.append(item)
                    elif isinstance(item, dict):
                        candidate = item.get("path") or item.get("file")
                        if candidate:
                            tests.append(str(candidate))
    return {"available": True, "tests": sorted(set(tests)), "raw": payload}


def _change_stats(root: Path, base: str | None) -> dict[str, int]:
    argv = ["git", "diff", "--numstat"]
    if base:
        argv.append(f"{base}...HEAD")
    else:
        argv.append("HEAD")
    result = _run(argv, cwd=root)
    insertions = 0
    deletions = 0
    for line in result.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        try:
            insertions += int(parts[0])
            deletions += int(parts[1])
        except ValueError:
            continue
    return {"insertions": insertions, "deletions": deletions}


def _changed_languages(files: list[str]) -> list[str]:
    return sorted({
        SOURCE_EXTENSIONS[Path(file).suffix.lower()]
        for file in files
        if Path(file).suffix.lower() in SOURCE_EXTENSIONS
    })


def _select_commands(inspection: dict[str, Any], files: list[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    commands = inspection["commands"]
    languages = _changed_languages(files)
    source_changed = bool(languages)
    config_changed = any(Path(file).name in CONFIG_NAMES for file in files)
    docs_only = bool(files) and all(Path(file).suffix.lower() in {".md", ".rst", ".txt"} for file in files)

    selected: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    def add(kind: str, command: str, reason: str) -> None:
        item = {"kind": kind, "command": command, "reason": reason}
        if item not in selected:
            selected.append(item)

    if docs_only:
        for kind, values in commands.items():
            for value in values:
                skipped.append({"kind": kind, "command": value, "reason": "documentation-only change"})
        return selected, skipped

    if source_changed or config_changed:
        for command in commands.get("lint", []):
            add("lint", command, "source/configuration changed")
        for command in commands.get("typecheck", []):
            add("typecheck", command, "typed source/configuration changed")
        for command in commands.get("test", []):
            add("test", command, "source/configuration changed")

    if config_changed or any(Path(f).name in {"Cargo.toml", "go.mod", "package.json", "pyproject.toml"} for f in files):
        for command in commands.get("build", []):
            add("build", command, "build/package metadata changed")

    if not selected and files:
        for kind in ("test", "lint", "typecheck", "build"):
            values = commands.get(kind, [])
            if values:
                add(kind, values[0], "fallback repository verification for changed files")

    selected_keys = {(x["kind"], x["command"]) for x in selected}
    for kind, values in commands.items():
        if kind == "install":
            continue
        for command in values:
            if (kind, command) not in selected_keys:
                skipped.append({
                    "kind": kind,
                    "command": command,
                    "reason": "not selected by change-aware rules",
                })

    return selected, skipped


def _security_checks(files: list[str]) -> list[dict[str, Any]]:
    state = capability_status()
    checks: list[dict[str, Any]] = []
    source_changed = any(Path(f).suffix.lower() in SOURCE_EXTENSIONS for f in files)
    iac_changed = any(Path(f).suffix.lower() in IAC_EXTENSIONS or Path(f).name in {"Dockerfile", "Chart.yaml"} for f in files)

    mapping = [
        ("secret-scan", bool(files), "changed files should be checked for exposed secrets"),
        ("dependency-vulnerability", bool(files), "dependency/security capability is enabled"),
        ("sast", source_changed, "source code changed"),
        ("iac-misconfiguration", iac_changed, "infrastructure/configuration changed"),
        ("sbom", any(Path(f).name in CONFIG_NAMES for f in files), "package/build metadata changed"),
    ]
    for name, relevant, reason in mapping:
        if relevant and state.get(name, {}).get("enabled"):
            checks.append({
                "kind": "security",
                "capability": name,
                "command": f"agentic capabilities run {name} . --json",
                "reason": reason,
            })
    return checks


def plan(
    path: str | Path = ".",
    *,
    base: str | None = None,
    symbols: list[str] | None = None,
) -> dict[str, Any]:
    root = repo_root(path)
    files = changed_files(root, base=base)
    inspection = inspect_repository(root)
    selected, skipped = _select_commands(inspection, files)
    codegraph = _codegraph_affected(root, files)

    for test_file in codegraph.get("tests", []):
        selected.append({
            "kind": "affected-test",
            "command": None,
            "test_file": test_file,
            "reason": "CodeGraph dependency analysis reports this test as affected",
        })

    symbol_impacts: list[dict[str, Any]] = []
    if symbols and shutil.which("codegraph") and (root / ".codegraph").exists():
        for symbol in symbols:
            result = _run(["codegraph", "impact", symbol, "--json"], cwd=root)
            payload: Any = result.stdout.strip()
            if result.returncode == 0:
                try:
                    payload = json.loads(result.stdout)
                except json.JSONDecodeError:
                    pass
            symbol_impacts.append({
                "symbol": symbol,
                "success": result.returncode == 0,
                "result": payload,
                "error": result.stderr.strip(),
            })

    security = _security_checks(files)
    selected.extend(security)

    return {
        "schema_version": "1",
        "document_type": "agentic.verification-plan",
        "repository": str(root),
        "base": base,
        "changed_files": files,
        "changed_languages": _changed_languages(files),
        "change_stats": _change_stats(root, base),
        "checks": selected,
        "skipped_checks": skipped,
        "impact": {
            "codegraph": codegraph,
            "symbols": symbol_impacts,
            "serena": {
                "available": bool(shutil.which("serena")),
                "automated_reference_expansion": False,
                "reason": "Serena reference navigation is exposed through agent/MCP workflows; the CLI planner does not invent a batch-reference API.",
            },
        },
    }


def execute(
    verification_plan: dict[str, Any],
    *,
    continue_on_failure: bool = False,
    backend: str | None = None,
    image: str | None = None,
    network: str | None = None,
    profile: str | None = None,
) -> dict[str, Any]:
    root = Path(verification_plan["repository"])
    results: list[dict[str, Any]] = []
    success = True
    verification_started = time.perf_counter()

    stats = verification_plan.get("change_stats") or {}
    record_metric(
        "change.measured",
        {
            "insertions": int(stats.get("insertions", 0)),
            "deletions": int(stats.get("deletions", 0)),
            "changed_files": len(verification_plan.get("changed_files") or []),
        },
        repository=root,
    )

    impact = verification_plan.get("impact") or {}
    codegraph = impact.get("codegraph") or {}
    if codegraph.get("available"):
        record_metric(
            "context.used",
            {
                "source": "codegraph",
                "useful": bool(codegraph.get("tests") or impact.get("symbols")),
            },
            repository=root,
        )

    for check in verification_plan["checks"]:
        check_started = time.perf_counter()
        if check["kind"] == "affected-test" and not check.get("command"):
            results.append({
                **check,
                "executed": False,
                "success": None,
                "reason_not_executed": "affected test path is evidence for selection; repository-specific runner arguments are not inferred",
            })
            continue

        if check["kind"] == "security":
            try:
                result = run_capability(check["capability"], root)
                passed = bool(result["success"])
                entry = {**check, "executed": True, "success": passed, "result": result}
            except Exception as exc:
                passed = False
                entry = {**check, "executed": True, "success": False, "error": str(exc)}
        else:
            command = check["command"]
            try:
                execution = run_execution(
                    command,
                    root,
                    backend=backend,
                    image=image,
                    network=network,
                    profile=profile,
                )
                passed = bool(execution["success"])
                entry = {
                    **check,
                    "executed": True,
                    "success": passed,
                    "execution": execution,
                    "returncode": execution["returncode"],
                    "stdout": execution["stdout"],
                    "stderr": execution["stderr"],
                }
            except Exception as exc:
                passed = False
                entry = {
                    **check,
                    "executed": True,
                    "success": False,
                    "error": str(exc),
                }

        entry["duration_ms"] = (time.perf_counter() - check_started) * 1000
        results.append(entry)
        record_metric(
            "verification.check",
            {
                "kind": check["kind"],
                "success": passed,
                "duration_ms": entry["duration_ms"],
                "elapsed_from_verification_start_ms": (
                    time.perf_counter() - verification_started
                ) * 1000,
            },
            repository=root,
        )
        if not passed:
            success = False
            if not continue_on_failure:
                break

    duration_ms = (time.perf_counter() - verification_started) * 1000
    record_metric(
        "verification.completed",
        {
            "success": success,
            "duration_ms": duration_ms,
            "checks_total": len(results),
            "checks_failed": sum(1 for item in results if item.get("success") is False),
            "changed_files": len(verification_plan.get("changed_files") or []),
            "codegraph_available": bool(codegraph.get("available")),
            "serena_available": bool((impact.get("serena") or {}).get("available")),
        },
        repository=root,
    )
    return {
        "schema_version": "1",
        "document_type": "agentic.verification-run",
        "repository": str(root),
        "success": success,
        "duration_ms": duration_ms,
        "plan": verification_plan,
        "execution": {
            "backend": backend,
            "image": image,
            "network": network,
            "profile": profile,
        },
        "results": results,
    }
