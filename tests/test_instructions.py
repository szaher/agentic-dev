"""Managed instruction blocks owned by other tools (v0.16 slice 1): agentic instructions block."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import jsonschema

from agentic_dev import instructions
from agentic_dev.contracts import schema
from agentic_dev.instructions import UsageError, list_blocks, put, remove
from agentic_dev.readiness import apply as apply_module
from agentic_dev.readiness.apply import run as ready_apply

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = schema("instruction-block")
WORKFLOW = "## AgentFlow\n\nFollow the selected AgentFlow pattern. Run `agentflow status`.\n"


def snapshot(root: Path) -> dict[str, tuple]:
    state: dict[str, tuple] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d != ".git"]
        for name in filenames:
            path = Path(dirpath) / name
            state[str(path.relative_to(root))] = (path.stat().st_mtime_ns, hashlib.sha256(path.read_bytes()).hexdigest())
    return state


class BlockCase(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="blocks-"))
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def put(self, content: str = WORKFLOW, **kwargs) -> dict:
        document = put(self.root, file=kwargs.pop("file", "AGENTS.md"), owner=kwargs.pop("owner", "agentflow"),
                       block=kwargs.pop("block", "workflow"), content=content, **kwargs)
        jsonschema.validate(document, SCHEMA)
        return document

    def remove(self, **kwargs) -> dict:
        document = remove(self.root, file=kwargs.pop("file", "AGENTS.md"), owner="agentflow", block="workflow",
                          **kwargs)
        jsonschema.validate(document, SCHEMA)
        return document


class PutRemoveTests(BlockCase):
    def test_create_then_remove_round_trips(self):
        created = self.put()
        self.assertEqual((created["status"], created["written"], created["exit_code"]), ("created", True, 0))
        self.assertTrue((self.root / "AGENTS.md").read_text().startswith(
            "<!-- agentic-dev:begin agentflow.workflow sha256="))
        removed = self.remove()
        self.assertEqual((removed["status"], removed["written"]), ("removed", True))
        self.assertFalse((self.root / "AGENTS.md").exists())
        self.assertEqual(self.remove()["status"], "absent")

    def test_content_outside_the_block_is_preserved_byte_for_byte(self):
        original = "# Team notes\n\nKeep this exactly.   \n\n- no trailing newline"
        (self.root / "AGENTS.md").write_text(original)
        self.assertEqual(self.put()["status"], "appended")
        self.assertTrue((self.root / "AGENTS.md").read_text().startswith(original + "\n\n"))
        self.remove()
        self.assertEqual((self.root / "AGENTS.md").read_text(), original + "\n")

    def test_repeating_a_put_is_a_no_op(self):
        self.put()
        before = snapshot(self.root)
        again = self.put()
        self.assertEqual((again["status"], again["written"], again["diff"]), ("unchanged", False, ""))
        self.assertEqual(snapshot(self.root), before)

    def test_changed_content_replaces_only_the_block(self):
        (self.root / "AGENTS.md").write_text("# Notes\n")
        self.put()
        (self.root / "AGENTS.md").write_text((self.root / "AGENTS.md").read_text() + "\n## After\n\ntext\n")
        updated = self.put("## AgentFlow\n\nNew rules.\n")
        self.assertEqual(updated["status"], "replaced")
        text = (self.root / "AGENTS.md").read_text()
        self.assertIn("New rules.", text)
        self.assertTrue(text.startswith("# Notes\n") and text.endswith("## After\n\ntext\n"))

    def test_hand_edited_blocks_are_never_overwritten_or_removed(self):
        self.put()
        path = self.root / "AGENTS.md"
        path.write_text(path.read_text().replace("Run `agentflow status`.", "Run `agentflow status` often."))
        before = snapshot(self.root)
        for document in (self.put("## AgentFlow\n\nOther.\n"), self.remove()):
            self.assertEqual((document["status"], document["written"], document["exit_code"]), ("conflict", False, 1))
            self.assertIn("edited by hand", document["reason"])
        self.assertEqual(snapshot(self.root), before)

    def test_dry_run_writes_nothing(self):
        (self.root / "CLAUDE.md").write_text("# Claude\n")
        before = snapshot(self.root)
        preview = self.put(file="CLAUDE.md", dry_run=True)
        self.assertEqual((preview["status"], preview["written"]), ("appended", False))
        self.assertIn("+<!-- agentic-dev:begin agentflow.workflow", preview["diff"])
        self.assertEqual(snapshot(self.root), before)

    def test_refusals(self):
        (self.root / "real.md").write_text("# x\n")
        (self.root / "AGENTS.md").symlink_to(self.root / "real.md")
        self.assertEqual(self.put()["status"], "refused")
        (self.root / "CLAUDE.md").write_bytes(b"# x\r\nwindows\r\n")
        crlf = self.put(file="CLAUDE.md")
        self.assertEqual((crlf["status"], crlf["exit_code"]), ("refused", 1))

    def test_failed_write_rolls_back(self):
        (self.root / "AGENTS.md").write_text("# Notes\n")
        before = snapshot(self.root)

        def broken(path, text, mode):
            raise OSError("disk full")

        with patch.object(apply_module, "_write_atomic", broken):
            document = self.put()
        self.assertEqual((document["status"], document["exit_code"], document["written"]), ("rolled-back", 3, False))
        self.assertEqual({k: v[1] for k, v in snapshot(self.root).items()}, {k: v[1] for k, v in before.items()})


class UsageTests(BlockCase):
    def test_invalid_requests_are_rejected_before_reading(self):
        cases = {
            "unsupported file": dict(file="README.md"),
            "arbitrary path": dict(file="../AGENTS.md"),
            "reserved owner readiness": dict(owner="readiness"),
            "reserved owner agentic": dict(owner="agentic"),
            "reserved owner agentic-dev": dict(owner="agentic-dev"),
            "reserved owner agentic-tools": dict(owner="agentic-tools"),
            "bad owner": dict(owner="Agent Flow"),
            "bad id": dict(block="work.flow"),
        }
        for label, kwargs in cases.items():
            with self.subTest(label), self.assertRaises(UsageError):
                put(self.root, **{"file": "AGENTS.md", "owner": "agentflow", "block": "workflow",
                                  "content": WORKFLOW, **kwargs})
        for content in ("", "x\r\n", "<!-- agentic-dev:begin x -->\n", "x" * (instructions.MAX_CONTENT_BYTES + 1)):
            with self.subTest(content=content[:20]), self.assertRaises(UsageError):
                put(self.root, file="AGENTS.md", owner="agentflow", block="workflow", content=content)


class OwnerNamespaceTests(BlockCase):
    def test_reserved_and_allowed_owners_agree_across_code_and_schema(self):
        allowed = self.put(owner="agentflow")
        self.assertEqual(allowed["status"], "created")
        for owner in ("readiness", "agentic", "agentic-dev", "agentic-tools"):
            with self.subTest(owner=owner):
                with self.assertRaises(UsageError):
                    put(self.root, file="AGENTS.md", owner=owner, block="workflow", content=WORKFLOW)
                forged = {**allowed, "owner": owner, "block_id": f"{owner}.workflow"}
                with self.assertRaises(jsonschema.ValidationError):
                    jsonschema.validate(forged, SCHEMA)
        for owner in ("agentflow", "readiness-bot", "my-agentic"):
            with self.subTest(owner=owner):
                jsonschema.validate({**allowed, "owner": owner}, SCHEMA)


class ReadinessCoexistenceTests(BlockCase):
    def test_tool_blocks_and_readiness_blocks_coexist(self):
        files = {"README.md": "# Demo\n\n## Setup\n\nRun `make test`.\n", "Makefile": "test:\n\ttrue\n",
                 "app.py": "x = 1\n", "AGENTS.md": "# Agent instructions\n\n## Architecture\n\nSee app.py.\n"}
        for name, text in files.items():
            (self.root / name).write_text(text)
        ready_apply(self.root, target="structured", dry_run=False)
        self.put()
        listed = list_blocks(self.root)
        jsonschema.validate(listed, schema("instruction-block-list"))
        self.assertEqual({(b["owner"], b["intact"]) for b in listed["blocks"]}, {("readiness", True), ("agentflow", True)})
        again = ready_apply(self.root, target="structured", dry_run=False)
        self.assertEqual(again["result"]["status"], "no-op")


class CliTests(BlockCase):
    def cli(self, *args: str, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
        env = {**os.environ, "PYTHONPATH": str(ROOT / "src"), "AGENTIC_DEV_CONFIG_DIR": tempfile.mkdtemp()}
        return subprocess.run([sys.executable, "-m", "agentic_dev.cli", "instructions", "block", *args],
                              cwd=self.root, env=env, input=stdin, capture_output=True, text=True, check=False)

    def test_exit_codes(self):
        common = ("--file", "AGENTS.md", "--owner", "agentflow", "--id", "workflow")
        created = self.cli("put", *common, "--content-file", "-", "--json", stdin=WORKFLOW)
        self.assertEqual(created.returncode, 0, created.stderr)
        jsonschema.validate(json.loads(created.stdout), SCHEMA)
        content = self.root / "workflow.md"
        content.write_text(WORKFLOW)
        self.assertEqual(self.cli("put", *common, "--content-file", str(content)).returncode, 0)
        path = self.root / "AGENTS.md"
        path.write_text(path.read_text().replace("pattern", "PATTERN"))
        self.assertEqual(self.cli("remove", *common).returncode, 1)
        self.assertEqual(self.cli("put", "--file", "README.md", "--owner", "agentflow", "--id", "w",
                                  "--content-file", "-", stdin="x").returncode, 2)
        self.assertEqual(self.cli("put", *common[:2], "--owner", "readiness", "--id", "w",
                                  "--content-file", "-", stdin="x").returncode, 2)
        listed = self.cli("list", "--json")
        self.assertEqual(json.loads(listed.stdout)["blocks"][0]["intact"], False)


if __name__ == "__main__":
    unittest.main()
