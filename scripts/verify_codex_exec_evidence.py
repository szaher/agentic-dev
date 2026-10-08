"""Verify integrity and internal consistency of a Codex exec probe bundle."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from probe_codex_exec_permissions import (
    EXPECTED_PLATFORM,
    EXPECTED_VERSION,
    PAYLOAD,
    PROBE_ID,
    digest_bytes,
    digest_file,
    evaluate,
    recipe as expected_recipe,
    tool_result,
)


def verify_bundle(directory: Path) -> None:
    summary = json.loads((directory / "summary.json").read_text())
    recorded_digest = summary.pop("probe_digest")
    canonical = json.dumps(summary, sort_keys=True, separators=(",", ":")).encode()
    if digest_bytes(canonical) != recorded_digest:
        raise ValueError("summary digest mismatch")
    if summary["probe_id"] != PROBE_ID:
        raise ValueError("unexpected probe identity")
    if summary["probe_script_digest"] != digest_file(
        Path(__file__).with_name("probe_codex_exec_permissions.py")
    ):
        raise ValueError("probe script differs from the recorded run")
    if not summary["identity_stable"]:
        raise ValueError("Codex executable changed during probe")
    identity = summary["identity"]
    if identity["version"] != EXPECTED_VERSION or (
        identity["platform"], identity["arch"]
    ) != EXPECTED_PLATFORM:
        raise ValueError("unsupported Codex version or platform")
    if summary["payload_digest"] != digest_bytes(PAYLOAD.encode()):
        raise ValueError("payload differs from the recorded run")
    if len(summary["cases"]) != 2:
        raise ValueError("expected implementer and reviewer cases")
    roles = set()
    for case in summary["cases"]:
        recipe = case["recipe"]
        role = recipe["role"]
        roles.add(role)
        mode = recipe["sandbox"]
        if (role, mode) not in {
            ("implementer", "workspace-write"), ("reviewer", "read-only")
        }:
            raise ValueError("unexpected recipe role or sandbox")
        arguments = recipe["argv"]
        workspace = Path(arguments[arguments.index("-C") + 1])
        if recipe != expected_recipe(arguments[0], mode, workspace, identity):
            raise ValueError(f"{role} recipe differs from the frozen launch")
        for name in ("events", "stderr"):
            file = directory / case[name]["path"]
            if digest_file(file) != case[name]["digest"]:
                raise ValueError(f"{role} {name} digest mismatch")
        events = [json.loads(line) for line in
                  (directory / case["events"]["path"]).read_text().splitlines()
                  if line.startswith("{")]
        nonce = case["command"].rsplit(" ", 1)[1]
        observed, command_seen, approval_seen = tool_result(events, nonce)
        if not any(
            event.get("type") == "item.completed"
            and event.get("item", {}).get("type") == "command_execution"
            and case["command"] in event["item"].get("command", "")
            for event in events
        ):
            raise ValueError(f"{role} expected command missing from raw events")
        if (observed != case["observed_tool_output"] or
                command_seen != case["command_seen"] or
                approval_seen != case["approval_event_seen"]):
            raise ValueError(f"{role} raw events disagree with summary")
        checks = evaluate(
            mode, observed, case["side_effects"], summary["host_network_controls"],
            command_seen, approval_seen, case["returncode"],
        )
        if checks != case["checks"] or not all(checks.values()) or not case["pass"]:
            raise ValueError(f"{role} checks do not pass")
    if roles != {"implementer", "reviewer"} or not summary["pass"]:
        raise ValueError("missing passing role")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    try:
        verify_bundle(args.directory)
    except (OSError, KeyError, TypeError, ValueError) as exc:
        print(f"Codex evidence invalid: {exc}", file=sys.stderr)
        return 1
    print(f"Codex evidence verified: {args.directory}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
