from __future__ import annotations

import hashlib
import json
import os
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Iterable

from .paths import config_dir


SENSITIVE_KEY = re.compile(
    r"(secret|token|password|passwd|authorization|cookie|header|api[_-]?key|private[_-]?key|credential)",
    re.IGNORECASE,
)


def _config_dir() -> Path:
    return config_dir()


def _metrics_dir() -> Path:
    return _config_dir() / "metrics"


def _settings_file() -> Path:
    return _metrics_dir() / "settings.json"


def _events_file() -> Path:
    return _metrics_dir() / "events.jsonl"


def _load_settings() -> dict[str, Any]:
    path = _settings_file()
    if not path.exists():
        return {"enabled": False}
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {"enabled": False}
    return {"enabled": bool(data.get("enabled", False))}


def _save_settings(data: dict[str, Any]) -> None:
    path = _settings_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def enabled() -> bool:
    return bool(_load_settings().get("enabled"))


def set_enabled(value: bool) -> dict[str, Any]:
    data = {"enabled": bool(value)}
    _save_settings(data)
    return status()


def _sanitize(value: Any, key: str | None = None) -> Any:
    if key and SENSITIVE_KEY.search(key):
        return "<redacted>"
    if isinstance(value, dict):
        return {str(k): _sanitize(v, str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize(v) for v in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _repo_identity(repository: str | Path | None) -> dict[str, str] | None:
    if repository is None:
        return None
    path = Path(repository).expanduser().resolve()
    digest = hashlib.sha256(str(path).encode()).hexdigest()[:16]
    return {"name": path.name, "id": digest}


def _session_id(repository: str | Path | None) -> str | None:
    explicit = os.environ.get("AGENTIC_SESSION_ID")
    if explicit:
        return explicit
    if repository is None:
        return None
    root = Path(repository).expanduser().resolve()
    path = root / ".agentic" / "session.json"
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return data.get("name") or data.get("session_id")


def record(
    event_type: str,
    data: dict[str, Any] | None = None,
    *,
    repository: str | Path | None = None,
    session_id: str | None = None,
) -> dict[str, Any] | None:
    """Append one event and return it, or return None when metrics are disabled (the default)."""

    if not enabled():
        return None
    now = datetime.now(timezone.utc)
    event = {
        "schema_version": "1",
        "document_type": "agentic.metric-event",
        "timestamp": now.isoformat(),
        "event_type": event_type,
        "repository": _repo_identity(repository),
        "session_id": session_id or _session_id(repository),
        "data": _sanitize(data or {}),
    }
    path = _events_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        handle.write(json.dumps(event, sort_keys=True) + "\n")
    return event


def _parse_since(since: str | None) -> datetime | None:
    if not since:
        return None
    match = re.fullmatch(r"(\d+)([hdw])", since.strip().lower())
    if not match:
        raise ValueError("since must look like 24h, 7d, or 4w")
    amount = int(match.group(1))
    unit = match.group(2)
    delta = {
        "h": timedelta(hours=amount),
        "d": timedelta(days=amount),
        "w": timedelta(weeks=amount),
    }[unit]
    return datetime.now(timezone.utc) - delta


def read_events(
    *,
    since: str | None = None,
    repository: str | Path | None = None,
) -> list[dict[str, Any]]:
    path = _events_file()
    if not path.exists():
        return []
    cutoff = _parse_since(since)
    repo = _repo_identity(repository)
    result: list[dict[str, Any]] = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if cutoff:
            try:
                stamp = datetime.fromisoformat(event["timestamp"])
            except (KeyError, ValueError):
                continue
            if stamp < cutoff:
                continue
        event_repo = event.get("repository") or {}
        if repo and event_repo.get("id") != repo["id"]:
            continue
        result.append(event)
    return result


def clear(*, yes: bool = False) -> None:
    if not yes:
        raise PermissionError("clearing metrics requires explicit --yes")
    path = _events_file()
    if path.exists():
        path.unlink()


def status() -> dict[str, Any]:
    path = _events_file()
    count = 0
    if path.exists():
        with path.open() as handle:
            count = sum(1 for line in handle if line.strip())
    return {
        "schema_version": "1",
        "document_type": "agentic.metrics-status",
        "enabled": enabled(),
        "storage": str(path),
        "event_count": count,
        "network_export": False,
    }


def summary(
    *,
    since: str | None = None,
    repository: str | Path | None = None,
) -> dict[str, Any]:
    events = read_events(since=since, repository=repository)
    by_type = Counter(event["event_type"] for event in events)

    executions = [e for e in events if e["event_type"] == "execution.completed"]
    execution_failures = sum(1 for e in executions if not e["data"].get("success", False))
    execution_durations = [
        float(e["data"]["duration_ms"])
        for e in executions if isinstance(e["data"].get("duration_ms"), (int, float))
    ]

    verifications = [e for e in events if e["event_type"] == "verification.completed"]
    verification_passes = sum(1 for e in verifications if e["data"].get("success") is True)
    verification_durations = [
        float(e["data"]["duration_ms"])
        for e in verifications if isinstance(e["data"].get("duration_ms"), (int, float))
    ]

    checks = [e for e in events if e["event_type"] == "verification.check"]
    passing_tests = [
        e for e in checks
        if e["data"].get("kind") in {"test", "affected-test"}
        and e["data"].get("success") is True
        and isinstance(e["data"].get("elapsed_from_verification_start_ms"), (int, float))
    ]
    first_passing_test = min(
        (float(e["data"]["elapsed_from_verification_start_ms"]) for e in passing_tests),
        default=None,
    )

    context_counts = Counter()
    useful_context = Counter()
    for event in events:
        if event["event_type"] == "context.used":
            source = str(event["data"].get("source") or "unknown")
            context_counts[source] += 1
            if event["data"].get("useful") is True:
                useful_context[source] += 1

    agentflow = defaultdict(Counter)
    for event in events:
        if event["event_type"] == "agentflow.stage":
            stage = str(event["data"].get("stage") or "unknown")
            outcome = str(event["data"].get("outcome") or "unknown")
            agentflow[stage][outcome] += 1

    skill_suggested_names = Counter()
    skill_activated_names = Counter()
    cap_suggested_names = Counter()
    cap_enabled_names = Counter()
    for event in events:
        if event["event_type"] == "skills.suggested":
            for name in event["data"].get("recommended_names") or event["data"].get("names") or []:
                skill_suggested_names[str(name)] += 1
        elif event["event_type"] == "skills.activated":
            for name in event["data"].get("names") or []:
                skill_activated_names[str(name)] += 1
        elif event["event_type"] == "capabilities.suggested":
            for name in event["data"].get("names") or []:
                cap_suggested_names[str(name)] += 1
        elif event["event_type"] == "capability.enabled":
            name = event["data"].get("name")
            if name:
                cap_enabled_names[str(name)] += 1

    skill_suggested = sum(skill_suggested_names.values())
    skill_activated = sum(skill_activated_names.values())
    skill_accepted = sum(
        min(count, skill_activated_names.get(name, 0))
        for name, count in skill_suggested_names.items()
    )
    cap_suggested = sum(cap_suggested_names.values())
    cap_enabled = sum(cap_enabled_names.values())
    cap_accepted = sum(
        min(count, cap_enabled_names.get(name, 0))
        for name, count in cap_suggested_names.items()
    )

    change_insertions = sum(int(e["data"].get("insertions", 0)) for e in events if e["event_type"] == "change.measured")
    change_deletions = sum(int(e["data"].get("deletions", 0)) for e in events if e["event_type"] == "change.measured")
    reverted_edits = sum(int(e["data"].get("count", 0)) for e in events if e["event_type"] == "change.reverted")

    sessions_started = by_type.get("session.started", 0)
    sessions_ended = by_type.get("session.ended", 0)
    retries = by_type.get("retry", 0)

    per_session: dict[str, Counter] = defaultdict(Counter)
    for event in events:
        session = event.get("session_id")
        if not session:
            continue
        if event["event_type"] == "execution.completed":
            per_session[str(session)]["tool_calls"] += 1
            per_session[str(session)]["agentic_executions"] += 1
            if not event["data"].get("success", False):
                per_session[str(session)]["failed_tool_calls"] += 1
        elif event["event_type"] == "tool.call":
            per_session[str(session)]["tool_calls"] += 1
            per_session[str(session)]["external_tool_calls"] += 1
            if event["data"].get("success") is False:
                per_session[str(session)]["failed_tool_calls"] += 1
        elif event["event_type"] == "retry":
            per_session[str(session)]["retries"] += 1
        elif event["event_type"] == "verification.completed":
            per_session[str(session)]["verifications"] += 1

    session_rows = {
        name: dict(sorted(counts.items()))
        for name, counts in sorted(per_session.items())
    }
    tool_calls = [row.get("tool_calls", 0) for row in session_rows.values()]
    average_tool_calls = sum(tool_calls) / len(tool_calls) if tool_calls else None

    return {
        "schema_version": "1",
        "document_type": "agentic.metrics-summary",
        "filters": {
            "since": since,
            "repository": _repo_identity(repository),
        },
        "events": {
            "total": len(events),
            "by_type": dict(sorted(by_type.items())),
        },
        "execution": {
            "count": len(executions),
            "failures": execution_failures,
            "failure_rate": execution_failures / len(executions) if executions else None,
            "average_duration_ms": (
                sum(execution_durations) / len(execution_durations)
                if execution_durations else None
            ),
        },
        "verification": {
            "count": len(verifications),
            "passes": verification_passes,
            "pass_rate": verification_passes / len(verifications) if verifications else None,
            "total_duration_ms": sum(verification_durations),
            "average_duration_ms": (
                sum(verification_durations) / len(verification_durations)
                if verification_durations else None
            ),
            "time_to_first_passing_focused_test_ms": first_passing_test,
        },
        "workflow": {
            "retries": retries,
            "sessions_started": sessions_started,
            "sessions_ended": sessions_ended,
            "average_tool_calls_per_session": average_tool_calls,
            "per_session": session_rows,
            "agentflow_stage_outcomes": {
                stage: dict(sorted(outcomes.items()))
                for stage, outcomes in sorted(agentflow.items())
            },
        },
        "recommendations": {
            "skills_suggested": skill_suggested,
            "skills_activated": skill_activated,
            "skills_accepted_from_recommendations": skill_accepted,
            "skill_activation_ratio": (
                skill_accepted / skill_suggested if skill_suggested else None
            ),
            "capabilities_suggested": cap_suggested,
            "capabilities_enabled": cap_enabled,
            "capabilities_accepted_from_recommendations": cap_accepted,
            "capability_enable_ratio": (
                cap_accepted / cap_suggested if cap_suggested else None
            ),
        },
        "context": {
            "uses": dict(sorted(context_counts.items())),
            "useful": dict(sorted(useful_context.items())),
        },
        "changes": {
            "insertions": change_insertions,
            "deletions": change_deletions,
            "reverted_edits": reverted_edits,
        },
    }


def export(
    output: str | Path,
    *,
    format: str = "jsonl",
    since: str | None = None,
    repository: str | Path | None = None,
) -> dict[str, Any]:
    events = read_events(since=since, repository=repository)
    target = Path(output).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    if format == "jsonl":
        with target.open("w") as handle:
            for event in events:
                handle.write(json.dumps(event, sort_keys=True) + "\n")
    elif format == "json":
        target.write_text(json.dumps(events, indent=2, sort_keys=True) + "\n")
    else:
        raise ValueError("format must be json or jsonl")
    return {
        "schema_version": "1",
        "document_type": "agentic.metrics-export",
        "output": str(target),
        "format": format,
        "event_count": len(events),
        "network_export": False,
    }
