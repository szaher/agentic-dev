"""Compact, actionable text views for CLI documents.

These functions only render supplied facts. Machine-readable documents and exit
codes remain owned by their commands.
"""

from __future__ import annotations

from collections.abc import Sequence
from textwrap import fill
from typing import Any

WIDTH = 88


def _line(label: str, value: object, *, indent: int = 2) -> str:
    prefix = " " * indent + label + ": "
    return fill(
        str(value),
        width=WIDTH,
        initial_indent=prefix,
        subsequent_indent=" " * len(prefix),
        break_long_words=False,
        break_on_hyphens=False,
    )


def _item(value: str, *, indent: int = 2) -> str:
    prefix = " " * indent + "- "
    return fill(
        value,
        width=WIDTH,
        initial_indent=prefix,
        subsequent_indent=" " * len(prefix),
        break_long_words=False,
        break_on_hyphens=False,
    )


def _numbered(number: int, value: str) -> str:
    prefix = f"  {number}. "
    return fill(
        value,
        width=WIDTH,
        initial_indent=prefix,
        subsequent_indent=" " * len(prefix),
        break_long_words=False,
        break_on_hyphens=False,
    )


def _names(values: list[str]) -> str:
    return ", ".join(values) if values else "none"


def _blocker_action(code: str, repository: str) -> str:
    return {
        "readiness": f"Review missing requirements: agentic ready plan {repository}",
        "skill-disallowed": "Adjust the approved skill allowlist or required skills, then replan.",
        "skill-missing": "Review available skills: agentic skills list",
        "capability-disabled": "Review capability state: agentic capabilities status",
        "capability-trust": "Review the selected trust profile: agentic trust show",
        "trust-ceiling": "Choose a trust profile within the approved ceiling, then replan.",
        "harness-unavailable": "Install the selected harness or choose an available one, then replan.",
        "permission-conflict": "Adjust the request bounds or repository permission ceiling, then replan.",
        "permission-unenforceable": (
            "The installed harness cannot yet prove this limit. Preparation stays "
            "blocked until a verified launch recipe is available."
        ),
    }.get(code, "Review the plan details and resolve this blocker, then replan.")


def _blocker_title(code: str) -> str:
    return {
        "readiness": "Readiness below minimum",
        "skill-disallowed": "Required skill disallowed",
        "skill-missing": "Required skill unavailable",
        "capability-disabled": "Required capability disabled",
        "capability-trust": "Capability exceeds trust profile",
        "trust-ceiling": "Trust profile exceeds ceiling",
        "harness-unavailable": "Harness unavailable",
        "permission-conflict": "Permission bounds conflict",
        "permission-unenforceable": "Permission enforcement unverified",
    }.get(code, code.replace("-", " ").capitalize())


def session_plan(document: dict[str, Any]) -> str:
    blocked = document["status"] == "blocked"
    lines = [
        f"SESSION PLAN  {'BLOCKED' if blocked else 'READY'}",
        _line("Task", document["task"]),
        _line("Repository", document["repository"]),
        _line("Plan digest", document["plan_digest"]),
        "  Planning made no changes.",
    ]
    if blocked:
        lines += ["", f"Needs attention ({len(document['blockers'])})"]
        for number, blocker in enumerate(document["blockers"], 1):
            where = f" · {blocker['invocation']}" if blocker.get("invocation") else ""
            lines.append(
                _numbered(
                    number,
                    f"{_blocker_title(blocker['code'])}{where} ({blocker['code']})",
                )
            )
            lines.append(_line("Detail", blocker["detail"], indent=5))
        actions = list(
            dict.fromkeys(
                _blocker_action(item["code"], document["repository"])
                for item in document["blockers"]
            )
        )
        lines += ["", "Next"] + [_item(action) for action in actions]
    else:
        lines += [
            "",
            "Next",
            _item(
                "Review and approve this plan digest. Save the --json plan for "
                "agentic session prepare in a linked worktree."
            ),
        ]

    readiness = document["readiness"]
    lines += [
        "",
        "Environment",
        _line("Readiness", f"{readiness['current']} (minimum {readiness['minimum']})"),
        _line(
            "Skills selected",
            _names([item["name"] for item in document["skills"]["selected"]]),
        ),
        _line("Capabilities", _names(document["capabilities"])),
        _line("Trust", document["trust"]["profile"]),
        _line("Verification", _names(document["verification_kinds"])),
    ]
    for tool in document["tools"]:
        state = "available" if tool["available"] else "unavailable"
        configured = "configured" if tool["configured"] else "not configured"
        lines.append(
            _line(
                tool["name"],
                f"{state}, {configured}; version {tool['version'] or 'unknown'}",
            )
        )
    lines += ["", "Harness permissions"]
    for invocation in document["invocations"]:
        lines.append(
            _item(
                f"{invocation['id']} · {invocation['role']} · {invocation['harness']} "
                f"({invocation['version'] or 'version unknown'})"
            )
        )
        for name, detail in invocation["permissions"].items():
            lines.append(
                _line(
                    name,
                    f"{detail['effective']['level']} — {detail['enforceable']}",
                    indent=6,
                )
            )
    return "\n".join(lines) + "\n"


def session_record(document: dict[str, Any]) -> str:
    paths = document["prepared"]["skill_paths"]
    lines = [
        "SESSION PREPARED",
        _line("Workspace", document["workspace"]),
        _line("Commit", document["commit"]),
        _line("Plan digest", document["plan_digest"]),
        "",
        f"Skills placed ({len(paths)})",
    ]
    lines += [_item(path) for path in paths] if paths else ["  none"]
    lines += ["", "Harness visibility"]
    for item in document["visibility"]:
        state = "undetermined" if item["undetermined"] else "inspected"
        lines.append(_item(f"{item['harness']}: {state}"))
        for external in item["detected_external"]:
            lines.append(_line(external["kind"], external["path"], indent=6))
    lines += [
        "",
        "Next",
        _item(
            "Review the session record and any undetermined external visibility before launch. "
            "Use --json for the full evidence."
        ),
    ]
    return "\n".join(lines) + "\n"


def session_error(kind: str, message: str) -> str:
    actions = {
        "stale": "Replan against current inputs and approve the new digest.",
        "blocked": "Resolve the plan blockers and approve a ready plan.",
        "dirty": "Commit or remove changes in the supplied worktree, then retry preparation.",
        "placement": "Resolve the conflicting skill path or filesystem error, then retry.",
        "invalid": "Provide an intact session-plan@1 and a linked worktree of its repository.",
    }
    return f"SESSION PREPARE  FAILED\n{_line('Reason', message)}\n\nNext\n{_item(actions[kind])}\n"


def session_plan_error(message: str) -> str:
    return (
        f"SESSION PLAN  FAILED\n{_line('Reason', message)}\n\nNext\n"
        f"{_item('Check the session-request@1 document and repository path, then replan.')}\n"
    )


def repository_inspection(document: dict[str, Any]) -> str:
    repo = document["repository"]
    recommended = [
        item["name"]
        for item in document["skills"]["recommended"]
        if item["recommended"]
    ]
    enabled = [
        name for name, item in document["capabilities"].items() if item["enabled"]
    ]
    lines = [
        f"REPOSITORY  {repo['name']}",
        _line("Root", repo["root"]),
        "",
        "Detected facts",
    ]
    lines += [_item(fact) for fact in repo["facts"]] if repo["facts"] else ["  none"]
    lines += ["", "Verification commands"]
    for kind, commands in document["commands"].items():
        lines.append(_line(kind, _names(commands)))
    lines += [
        "",
        "Environment suggestions",
        _line("Skills", _names(recommended)),
        _line("Enabled capabilities", _names(enabled)),
        "",
        "Next",
        _item(
            "Run agentic ready plan to see repository improvements, or agentic verify plan to see checks."
        ),
    ]
    return "\n".join(lines) + "\n"


def verification_plan(document: dict[str, Any]) -> str:
    lines = [
        f"VERIFICATION PLAN  {len(document['checks'])} check(s)",
        _line("Repository", document["repository"]),
        "",
        "Changed files",
    ]
    lines += (
        [_item(path) for path in document["changed_files"]]
        if document["changed_files"]
        else ["  none"]
    )
    lines += ["", "Checks"]
    for check in document["checks"]:
        label = (
            check.get("command")
            or check.get("test_file")
            or check.get("capability")
            or "unknown"
        )
        lines.append(_item(f"[{check['kind']}] {label}"))
        lines.append(_line("Why", check["reason"], indent=6))
    if not document["checks"]:
        lines.append("  none detected")
    if document["skipped_checks"]:
        lines += ["", f"Skipped ({len(document['skipped_checks'])})"]
        for check in document["skipped_checks"]:
            lines.append(
                _item(f"[{check['kind']}] {check['command']}: {check['reason']}")
            )
    lines += [
        "",
        "Next",
        _item(
            "Run agentic verify run to execute these checks."
            if document["checks"]
            else "Add a discoverable verification command, then run agentic verify plan again."
        ),
    ]
    return "\n".join(lines) + "\n"


def verification_run(document: dict[str, Any]) -> str:
    status = document["status"]
    lines = [f"VERIFICATION  {status.upper().replace('-', ' ')}", "", "Checks"]
    for result in document["results"]:
        state = (
            "PASS"
            if result.get("success") is True
            else ("SKIP" if result.get("success") is None else "FAIL")
        )
        label = (
            result.get("command")
            or result.get("test_file")
            or result.get("capability")
            or "unknown"
        )
        lines.append(_item(f"{state} [{result['kind']}] {label}"))
        if result.get("success") is False:
            reason = (
                result.get("error")
                or result.get("stderr")
                or result.get("stdout")
                or ""
            )
            tail = [part.strip() for part in str(reason).splitlines() if part.strip()][
                -3:
            ]
            if tail:
                lines.append(_line("Failure", " | ".join(tail)[-500:], indent=6))
            if result.get("returncode") is not None:
                lines.append(_line("Exit code", result["returncode"], indent=6))
    if not document["results"]:
        lines.append("  no checks executed")
    if document["missing_kinds"]:
        lines += ["", _line("Missing kinds", _names(document["missing_kinds"]))]
    if status != "passed":
        lines += [
            "",
            "Next",
            _item(
                "Add runnable checks for the missing kinds and retry."
                if document["missing_kinds"] or status == "no-checks"
                else "Inspect failing check output with --json, fix the failure, and retry."
            ),
        ]
    return "\n".join(lines) + "\n"


def skills_status(root: str, found: dict[str, list[str]]) -> str:
    lines = ["PROJECT SKILLS", _line("Repository", root), ""]
    for harness in ("claude", "codex", "pi", "opencode"):
        label = "OpenCode" if harness == "opencode" else harness.title()
        lines.append(_line(label, _names(found[harness])))
    lines += [
        "",
        "Next",
        _item(
            "Use agentic skills list to browse, or agentic skills add NAME to activate a skill."
        ),
    ]
    return "\n".join(lines) + "\n"


def capabilities_status(document: dict[str, dict[str, Any]]) -> str:
    enabled = [(name, item) for name, item in document.items() if item["enabled"]]
    disabled = [(name, item) for name, item in document.items() if not item["enabled"]]
    lines = [
        f"CAPABILITIES  {len(enabled)} enabled / {len(document)} available",
        "",
        "Enabled",
    ]
    for name, item in enabled:
        config = item["configuration"] or {}
        suffix = f" ({config.get('target')}, {config.get('mode')})" if config else ""
        lines.append(_item(f"{name} · {item['provider']}{suffix}"))
    if not enabled:
        lines.append("  none")
    lines += ["", "Available to enable"]
    lines += (
        [_item(f"{name} · {item['provider']}") for name, item in disabled]
        if disabled
        else ["  none"]
    )
    lines += [
        "",
        "Next",
        _item(
            "Use agentic capabilities list for requirements, then agentic capabilities enable NAME."
        ),
    ]
    return "\n".join(lines) + "\n"


def skills_list(items: list[Any]) -> str:
    lines = [f"SKILLS  {len(items)} available"]
    categories = sorted({item.category for item in items})
    for category in categories:
        lines += ["", category.title()]
        for item in items:
            if item.category == category:
                lines.append(_item(f"{item.name}: {item.description}"))
    lines += [
        "",
        "Next",
        _item(
            "Use agentic skills explain NAME for details, then agentic skills add NAME to activate it."
        ),
    ]
    return "\n".join(lines) + "\n"


def capabilities_list(items: Sequence[Any], *, verbose: bool = False) -> str:
    lines = [f"CAPABILITIES  {len(items)} available"]
    for category in sorted({item.category for item in items}):
        group = [item for item in items if item.category == category]
        lines += ["", f"{category.title()} ({len(group)})"]
        for item in group:
            lines.append(_item(f"{item.name} — {item.description}"))
            if verbose:
                lines.append(_line("Provider", item.provider, indent=6))
                lines.append(_line("Targets", _names(list(item.targets)), indent=6))
                lines.append(
                    _line(
                        "Permissions", _names(list(item.required_permissions)), indent=6
                    )
                )
                lines.append(_line("Risk", item.risk, indent=6))
    lines += [
        "",
        "Next",
        _item(
            "Run agentic capabilities list --verbose to review access and risk, then "
            "agentic capabilities status before enabling a capability."
        ),
    ]
    return "\n".join(lines) + "\n"


def doctor(
    tools: dict[str, str | None],
    integrations: list[Any],
    capabilities: dict[str, dict[str, Any]],
) -> str:
    harness_names = {"claude", "codex", "pi", "opencode"}
    core = {name: path for name, path in tools.items() if name not in harness_names}
    found = [name for name, path in core.items() if path]
    missing = [name for name, path in core.items() if not path]
    harnesses = [
        name for name in ("claude", "codex", "pi", "opencode") if tools.get(name)
    ]
    absent_harnesses = [
        name for name in ("claude", "codex", "pi", "opencode") if not tools.get(name)
    ]
    configured = [item for item in integrations if item.configured]
    needs_setup = [
        item for item in integrations if item.available and not item.configured
    ]
    lines = [
        f"ENVIRONMENT  {len(found)}/{len(core)} workspace tools found",
        _line("Available", _names(found)),
        _line("Missing", _names(missing)),
        "",
        f"Harnesses  {len(harnesses)}/4 installed",
        _line("Installed", _names(harnesses)),
        _line("Not installed", _names(absent_harnesses)),
    ]
    lines += ["", f"Native integrations  {len(configured)} configured"]
    lines += (
        [_item(f"{item.name}: {item.detail}") for item in configured]
        if configured
        else ["  none"]
    )
    if needs_setup:
        lines += ["", "Available but not configured"]
        lines += [_item(f"{item.name}: {item.detail}") for item in needs_setup]
    enabled = [name for name, item in capabilities.items() if item["enabled"]]
    lines += ["", _line("Enabled capabilities", _names(enabled))]
    if missing or needs_setup:
        lines += ["", "Next"]
        if missing:
            lines.append(
                _item(
                    "Install the missing workspace tools you need, then rerun agentic doctor."
                )
            )
        if needs_setup:
            lines.append(_item("Run agentic integrations status for setup details."))
    else:
        lines += [
            "",
            "Next",
            _item("Run agentic repo inspect to review a repository's context."),
        ]
    return "\n".join(lines) + "\n"


def worktree_list(document: dict[str, Any]) -> str:
    entries = document["worktrees"]
    root = document["repository"]
    lines = [f"WORKTREES  {len(entries)}", _line("Repository", root)]
    for item in entries:
        role = "primary" if item["worktree"] == root else "linked"
        state = "dirty" if item.get("dirty") else "clean"
        lines += [
            "",
            f"{role.upper()}  {state}",
            _line("Path", item["worktree"]),
            _line("Branch", item.get("branch", "detached")),
        ]
        session = item.get("session") or {}
        if session.get("agent"):
            lines.append(_line("Agent", session["agent"]))
        if session.get("task"):
            lines.append(_line("Task", session["task"]))
    lines += [
        "",
        "Next",
        _item(
            "Use agentic worktree status NAME for details before cleanup or preparation."
        ),
    ]
    return "\n".join(lines) + "\n"


def worktree_status(document: dict[str, Any]) -> str:
    state = "DIRTY" if document.get("dirty") else "CLEAN"
    lines = [
        f"WORKTREE  {state}",
        _line("Path", document["worktree"]),
        _line("Branch", document.get("branch", "detached")),
        _line("Commit", document.get("head") or "unknown"),
    ]
    session = document.get("session") or {}
    if session.get("agent"):
        lines.append(_line("Agent", session["agent"]))
    if session.get("task"):
        lines.append(_line("Task", session["task"]))
    lines += [
        "",
        "Next",
        _item(
            "Inspect uncommitted changes in this worktree with git status before preparation or cleanup."
            if document.get("dirty")
            else "This worktree is clean. Review its branch and commit before preparation or cleanup."
        ),
    ]
    return "\n".join(lines) + "\n"


def trust_list(document: dict[str, Any]) -> str:
    lines = [f"TRUST PROFILES  selected: {document['current_profile']}"]
    for name, item in document["profiles"].items():
        mark = "SELECTED" if item["selected"] else "AVAILABLE"
        lines += [
            "",
            f"{name}  {mark}",
            _line("Purpose", item["description"]),
            _line("Permissions", _names(item["permissions"])),
        ]
    lines += [
        "",
        "Next",
        _item(
            "Use agentic trust show NAME for details, or agentic trust set NAME to select a profile."
        ),
    ]
    return "\n".join(lines) + "\n"


def trust_show(document: dict[str, Any]) -> str:
    if "profiles" in document:
        name = document["current_profile"]
        item = document["profiles"][name]
    else:
        name = document["name"]
        item = document
    lines = [
        f"TRUST PROFILE  {name}",
        _line("Purpose", item["description"]),
        _line("Permissions", _names(item["permissions"])),
    ]
    if "profiles" in document:
        others = [other for other in document["profiles"] if other != name]
        lines.append(_line("Other profiles", _names(others)))
    lines += [
        "",
        "Next",
        _item(
            "Use agentic trust list to compare profiles. Changing the selected profile requires agentic trust set NAME."
        ),
    ]
    return "\n".join(lines) + "\n"


def infrastructure_status(document: dict[str, Any]) -> str:
    available = [name for name, item in document["tools"].items() if item["available"]]
    absent = [name for name, item in document["tools"].items() if not item["available"]]
    cluster = document["cluster"]
    cloud = document["cloud"]
    observability = document["observability"]
    lines = [
        "INFRASTRUCTURE",
        _line("Repository", document["repository"]),
        "",
        "Tools",
        _line("Available", _names(available)),
        _line("Not installed", _names(absent)),
        "",
        "Cluster",
        _line("Context", cluster["context"] or "none selected"),
        _line("Namespace", cluster["namespace"] or "none selected"),
        "",
        "Cloud",
        _line("AWS profile", cloud["aws_profile"] or "none selected"),
        _line(
            "Azure CLI", "available" if cloud["azure_configured"] else "not installed"
        ),
        _line(
            "Google Cloud CLI",
            "available" if cloud["gcp_configured"] else "not installed",
        ),
        "",
        "Observability",
        _line(
            "Collector",
            "available" if observability["collector_available"] else "not installed",
        ),
        _line("Config files", _names(observability["config_files"])),
        "",
        "Next",
        _item(
            "Use --json for all detected paths and environment details. Choose an infra subcommand for a specific operation."
        ),
    ]
    return "\n".join(lines) + "\n"
