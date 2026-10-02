#!/usr/bin/env python3
"""Vendor a pinned Agent Ready spec bundle into Agentic Dev.

The spec is owned by https://github.com/szaher/agent-ready. Agentic Dev ships a
copy of its generated canonical bundle (spec/dist/agent-ready-spec-*.json)
together with a pin recording the version, sha256, and source commit.

    # vendor from a clean agent-ready checkout at the commit to pin
    python3 scripts/sync-agent-ready-spec.py --from ../agent-ready

    # verify the vendored bundle matches its pin (used by CI/tests)
    python3 scripts/sync-agent-ready-spec.py --check
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

REPOSITORY = "https://github.com/szaher/agent-ready"
TARGET = Path(__file__).resolve().parents[1] / "src" / "agentic_dev" / "readiness" / "specs"
PIN = TARGET / "PIN.json"


def git(checkout: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(checkout), *args], check=True, capture_output=True, text=True,
    ).stdout.strip()


def check() -> int:
    pin = json.loads(PIN.read_text())
    bundle = TARGET / pin["file"]
    problems = []
    if not bundle.is_file():
        problems.append(f"missing vendored bundle {pin['file']}")
    else:
        digest = hashlib.sha256(bundle.read_bytes()).hexdigest()
        if digest != pin["sha256"]:
            problems.append(f"{pin['file']} sha256 {digest} does not match pin {pin['sha256']}")
        document = json.loads(bundle.read_text())
        if document.get("spec_version") != pin["spec_version"]:
            problems.append("bundle spec_version does not match pin")
    extra = sorted(p.name for p in TARGET.glob("agent-ready-spec-*.json") if p.name != pin["file"])
    if extra:
        problems.append(f"unpinned bundles present: {', '.join(extra)}")
    for problem in problems:
        print(f"error: {problem}", file=sys.stderr)
    if not problems:
        print(f"ok: {pin['name']} {pin['spec_version']} sha256={pin['sha256']} commit={pin['source']['commit']}")
    return 1 if problems else 0


def sync(checkout: Path, commit: str | None) -> int:
    dist = checkout / "spec" / "dist"
    bundles = sorted(dist.glob("agent-ready-spec-*.json"))
    if len(bundles) != 1:
        print(f"error: expected exactly one bundle in {dist}, found {len(bundles)}", file=sys.stderr)
        return 1
    bundle = bundles[0]
    relative = bundle.relative_to(checkout).as_posix()
    if commit is None:
        if git(checkout, "status", "--porcelain", "--", "spec"):
            print("error: agent-ready spec/ has uncommitted changes; commit them or pass --commit", file=sys.stderr)
            return 1
        commit = git(checkout, "rev-parse", "HEAD")
    data = bundle.read_bytes()
    document = json.loads(data)
    if document.get("document_type") != "agent-ready.spec":
        print(f"error: {bundle.name} is not an Agent Ready spec bundle", file=sys.stderr)
        return 1
    for old in TARGET.glob("agent-ready-spec-*.json"):
        if old.name != bundle.name:
            old.unlink()
    (TARGET / bundle.name).write_bytes(data)
    pin = {
        "file": bundle.name,
        "name": document["name"],
        "sha256": hashlib.sha256(data).hexdigest(),
        "source": {"commit": commit, "path": relative, "repository": REPOSITORY},
        "spec_version": document["spec_version"],
    }
    PIN.write_text(json.dumps(pin, indent=2, sort_keys=True) + "\n")
    print(f"vendored {bundle.name} ({pin['spec_version']}) sha256={pin['sha256']} commit={commit}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--from", dest="checkout", type=Path, help="path to an agent-ready checkout")
    mode.add_argument("--check", action="store_true", help="verify the vendored bundle against its pin")
    parser.add_argument("--commit", help="source commit to record (default: the checkout's HEAD)")
    args = parser.parse_args()
    if args.check:
        return check()
    return sync(args.checkout.resolve(), args.commit)


if __name__ == "__main__":
    raise SystemExit(main())
