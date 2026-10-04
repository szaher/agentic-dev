"""Throwaway Codex sandbox side-effect probe; never touches project files."""

import json
import os
import socket
import subprocess
import tempfile
from pathlib import Path

PAYLOAD = r"""
import json
import socket
import sys
from pathlib import Path

workspace, outside, port = Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3])
observed = {}
for label, path in (
    ("inside", workspace / "inside.txt"),
    ("outside", outside / "outside.txt"),
    ("symlink", workspace / "link-outside" / "via-link.txt"),
):
    try:
        path.write_text("changed")
        observed[label] = "write-returned"
    except Exception as exc:
        observed[label] = type(exc).__name__ + ": " + str(exc)
try:
    with socket.create_connection(("127.0.0.1", port), timeout=2) as connection:
        connection.sendall(b"probe")
    observed["network"] = "connected"
except Exception as exc:
    observed["network"] = type(exc).__name__ + ": " + str(exc)
print(json.dumps(observed))
"""


def codex_version() -> str:
    completed = subprocess.run(
        ["codex", "--version"], capture_output=True, text=True, timeout=10, check=True
    )
    return completed.stdout.strip()


def run_case(root: Path, label: str, mode: str | None) -> dict:
    workspace = root / "workspace"
    outside = root / "outside"
    inside_file = workspace / "inside.txt"
    outside_file = outside / "outside.txt"
    inside_file.write_text("original")
    outside_file.write_text("original")
    link_file = outside / "via-link.txt"
    if link_file.exists():
        link_file.unlink()
    listener = socket.socket()
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]
    payload = [
        "/usr/bin/python3",
        "-B",
        str(workspace / "payload.py"),
        str(workspace),
        str(outside),
        str(port),
    ]
    cmd = (
        payload
        if mode is None
        else [
            "codex",
            "sandbox",
            "-P",
            mode,
            "-C",
            str(workspace),
            "-c",
            'approval_policy="never"',
            "--",
            *payload,
        ]
    )
    try:
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
            env={**os.environ, "CODEX_HOME": str(root / "codex-home")},
        )
        lines = completed.stdout.splitlines()
        observed = json.loads(lines[-1]) if lines else {}
        return {
            "case": label,
            "command": cmd,
            "returncode": completed.returncode,
            "observed": observed,
            "side_effects": {
                "inside_changed": inside_file.read_text() != "original",
                "outside_changed": outside_file.read_text() != "original",
                "symlink_escape_created": link_file.exists(),
            },
            "stderr_tail": completed.stderr[-800:],
        }
    finally:
        listener.close()


version_before = codex_version()
with tempfile.TemporaryDirectory(
    prefix="agentic-permission-probe-", dir="/private/tmp"
) as temporary:
    root = Path(temporary)
    workspace = root / "workspace"
    outside = root / "outside"
    workspace.mkdir()
    outside.mkdir()
    (workspace / "link-outside").symlink_to(outside, target_is_directory=True)
    (workspace / "payload.py").write_text(PAYLOAD)
    codex_home = root / "codex-home"
    codex_home.mkdir()
    (codex_home / "config.toml").write_text("""
[permissions.probe-workspace]
extends = ":workspace"

[permissions.probe-workspace.filesystem]
":tmpdir" = "deny"
":slash_tmp" = "deny"

[permissions.probe-workspace.network]
enabled = false
""")
    results = [
        run_case(root, "control", None),
        run_case(root, "read-only", ":read-only"),
        run_case(root, "workspace-write-network-off", "probe-workspace"),
    ]

version_after = codex_version()
for result in results:
    result["version_before"] = version_before
    result["version_after"] = version_after

Path("/private/tmp/agentic-permission-probe-results.json").write_text(
    json.dumps(results, indent=2) + "\n"
)
for result in results:
    print(
        json.dumps(
            {
                key: result[key]
                for key in (
                    "case",
                    "version_before",
                    "version_after",
                    "returncode",
                    "observed",
                    "side_effects",
                    "stderr_tail",
                )
            }
        )
    )
if version_before != version_after:
    raise SystemExit("Codex changed versions during the probe; discard these results")
control, read_only, workspace_write = results
if not (
    all(item["returncode"] == 0 for item in results)
    and all(control["side_effects"].values())
    and control["observed"]["network"] == "connected"
    and not any(read_only["side_effects"].values())
    and read_only["observed"]["network"] != "connected"
    and workspace_write["side_effects"]
    == {
        "inside_changed": True,
        "outside_changed": False,
        "symlink_escape_created": False,
    }
    and workspace_write["observed"]["network"] != "connected"
):
    raise SystemExit("Codex sandbox side effects did not match the expected boundary")
