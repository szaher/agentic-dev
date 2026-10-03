"""ready diff / ready apply (v0.15 slice 2): managed blocks, idempotency, conflicts, rollback."""

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

sys.path.insert(0, str(Path(__file__).resolve().parent))
from readiness_fixtures import materialize  # noqa: E402

from agentic_dev.readiness import apply as apply_module  # noqa: E402
from agentic_dev.readiness import assess  # noqa: E402
from agentic_dev.readiness import managed  # noqa: E402
from agentic_dev.readiness.apply import ApplyError, plan_changes, run  # noqa: E402
from agentic_dev.readiness.remediation import (  # noqa: E402
    MAINTENANCE_GENERATORS, Context, digest, make_change, normalize, propose, render_block,
)


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "src" / "agentic_dev" / "schemas" / "readiness-remediation-v1.schema.json").read_text())


def change(content: str = "## Commands\n- x\n", prelude: str | None = None, path: str = "AGENTS.md",
           block_id: str = "readiness.commands", fmt: str = "markdown") -> dict:
    body = normalize(content)
    return {"id": f"{block_id}@{path}", "kind": "managed-block", "path": path, "format": fmt,
            "block_id": block_id, "content": body, "content_sha256": digest(body), "prelude": prelude}


def snapshot(root: Path) -> dict[str, tuple]:
    state: dict[str, tuple] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        for name in dirnames + filenames:
            path = Path(dirpath) / name
            info = path.lstat()
            data = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() and not path.is_symlink() else None
            state[str(path.relative_to(root))] = (info.st_mode, info.st_size, info.st_mtime_ns, data)
    return state


class ManagedBlockTextTests(unittest.TestCase):
    def test_create_with_prelude(self):
        planned = managed.plan(None, change(prelude="# Agent instructions\n"))
        self.assertEqual(planned.outcome, managed.CREATE)
        self.assertEqual(planned.text, "# Agent instructions\n\n" + render_block("markdown", "readiness.commands", "## Commands\n- x\n"))

    def test_append_preserves_existing_bytes(self):
        block = render_block("markdown", "readiness.commands", "## Commands\n- x\n")
        for original, expected_prefix in [
            ("# Team\n", "# Team\n\n"),
            ("# Team", "# Team\n\n"),                 # missing final newline is added
            ("  \n\n", "  \n\n\n"),                   # whitespace-only content is kept exactly
        ]:
            with self.subTest(original=original):
                planned = managed.plan(original, change())
                self.assertEqual(planned.outcome, managed.APPEND)
                self.assertEqual(planned.text, expected_prefix + block)
        self.assertEqual(managed.plan("", change()).text, block)

    def test_replace_only_touches_the_block(self):
        old = render_block("markdown", "readiness.commands", "## Commands\n- old\n")
        current = "# Team\n\nintro\n\n" + old + "\n## Rules\n\n- keep me\n"
        planned = managed.plan(current, change("## Commands\n- new\n"))
        self.assertEqual(planned.outcome, managed.REPLACE)
        self.assertEqual(planned.text, "# Team\n\nintro\n\n" + render_block("markdown", "readiness.commands", "## Commands\n- new\n")
                         + "\n## Rules\n\n- keep me\n")

    def test_idempotent(self):
        for current in (None, "# Team\n", "x"):
            first = managed.plan(current, change())
            second = managed.plan(first.text, change())
            self.assertEqual(second.outcome, managed.UNCHANGED)
            self.assertEqual(second.text, first.text)

    def test_hand_edited_block_is_a_conflict(self):
        current = managed.plan("# Team\n", change("## Commands\n- old\n")).text.replace("- old", "- edited by hand")
        planned = managed.plan(current, change("## Commands\n- new\n"))
        self.assertEqual(planned.outcome, managed.CONFLICT)
        self.assertIn("edited by hand", planned.reason)

    def test_malformed_markers_and_crlf(self):
        block = render_block("markdown", "readiness.commands", "## Commands\n- x\n")
        self.assertEqual(managed.plan(block + block, change("## C\n")).outcome, managed.CONFLICT)
        self.assertEqual(managed.plan(block.split("\n", 1)[0] + "\n", change()).outcome, managed.CONFLICT)
        self.assertEqual(managed.plan("# Team\r\n", change()).outcome, managed.REFUSED)

    def test_removal_is_the_inverse(self):
        for original in ("# Team\n", "# Team"):
            appended = managed.plan(original, change()).text
            restored = managed.remove(appended, change())
            self.assertEqual(restored, original if original.endswith("\n") else original + "\n")
        created = managed.plan(None, change(prelude="# Agent instructions\n")).text
        self.assertIsNone(managed.remove(created, change(prelude="# Agent instructions\n")))

    def test_hash_format_for_gitignore(self):
        planned = managed.plan("node_modules/\n", change(".env\n", path=".gitignore", block_id="readiness.secrets-ignored", fmt="hash"))
        self.assertTrue(planned.text.startswith("node_modules/\n\n# agentic-dev:begin readiness.secrets-ignored sha256="))


class ApplyCase(unittest.TestCase):
    def setUp(self):
        self.dirs: list[Path] = []

    def tearDown(self):
        for path in self.dirs:
            shutil.rmtree(path, ignore_errors=True)

    def repo(self, scenario: str = "foundational-python") -> Path:
        root = Path(tempfile.mkdtemp(prefix="ready-apply-"))
        self.dirs.append(root)
        return materialize(scenario, root)

    def statuses(self, root: Path) -> dict[str, str]:
        return {r["id"]: r["status"] for r in assess(root)["requirements"]}


class ApplyTests(ApplyCase):
    def test_dry_run_writes_nothing_and_shows_diffs(self):
        root = self.repo()
        before = snapshot(root)
        document = run(root, target="structured")
        jsonschema.validate(document, SCHEMA)
        self.assertEqual(document["mode"], "dry-run")
        self.assertEqual(document["result"], {"status": "planned", "written": [], "maturity_after": None})
        self.assertEqual(snapshot(root), before)
        agents = next(o for o in document["outcomes"] if o["path"] == "AGENTS.md")
        self.assertEqual(agents["outcome"], managed.CREATE)
        self.assertIn("+- Test: `uv run pytest` (from `pyproject.toml`)", agents["diff"])
        self.assertIs(agents["ci_visible"], False)

    def test_apply_fixes_safe_rules_and_is_idempotent(self):
        root = self.repo()
        document = run(root, target="structured", dry_run=False)
        jsonschema.validate(document, SCHEMA)
        self.assertEqual(document["result"]["status"], "applied")
        self.assertEqual(document["result"]["written"], [".gitignore", "AGENTS.md"])
        statuses = self.statuses(root)
        for rule_id in ("context.agent_instructions", "context.agent_instructions.commands", "constraints.secrets.ignored"):
            self.assertEqual(statuses[rule_id], "pass", rule_id)
        before = snapshot(root)
        again = run(root, target="structured", dry_run=False)
        self.assertEqual(again["result"]["status"], "no-op")
        self.assertEqual(snapshot(root), before)

    def test_human_decisions_are_never_applied(self):
        root = self.repo()
        before = self.statuses(root)
        document = run(root, target="structured", dry_run=False)
        after = self.statuses(root)
        changed = {rule for rule in before if before[rule] != after[rule]}
        self.assertTrue({"context.agent_instructions", "context.agent_instructions.commands",
                         "constraints.secrets.ignored"} <= changed)
        decided = {r["rule_id"] for r in document["remediations"] if r["remediation_class"] != "safe-automatic"}
        self.assertTrue({"conventions.documented", "constraints.documented"} <= decided)
        # No rule that needs a decision (or is unsupported) changes status. Side
        # effects of safe changes on out-of-scope rules (a short new AGENTS.md
        # also satisfies the recommended concise-instructions rule) are fine.
        self.assertEqual({rule: after[rule] for rule in decided}, {rule: before[rule] for rule in decided})
        self.assertEqual(sorted(path.name for path in root.iterdir() if path.name != ".git"),
                         sorted([".gitignore", "AGENTS.md", "README.md", "pyproject.toml", "src", "tests"]))

    def test_existing_files_are_extended_byte_for_byte(self):
        root = self.repo()
        (root / ".gitignore").write_text("node_modules/\n*.log")
        (root / "CLAUDE.md").write_text("# Team notes\n\nKeep this.\n")
        os.chmod(root / ".gitignore", 0o600)
        run(root, target="structured", dry_run=False)
        gitignore = (root / ".gitignore").read_text()
        self.assertTrue(gitignore.startswith("node_modules/\n*.log\n\n# agentic-dev:begin readiness.secrets-ignored"))
        self.assertEqual(os.stat(root / ".gitignore").st_mode & 0o777, 0o600)
        self.assertTrue((root / "CLAUDE.md").read_text().startswith("# Team notes\n\nKeep this.\n\n<!-- agentic-dev:begin"))
        self.assertFalse((root / "AGENTS.md").exists())

    def test_stale_blocks_are_refreshed(self):
        root = self.repo()
        run(root, target="structured", dry_run=False)
        (root / "Makefile").write_text("typecheck:\n\tmypy src\n")
        document = run(root, target="structured", dry_run=False)
        refresh = next(r for r in document["remediations"] if r["status"] == "pass")
        self.assertEqual(refresh["remediation_class"], "safe-automatic")
        self.assertEqual([o["outcome"] for o in document["outcomes"]], [managed.REPLACE])
        self.assertIn("- Typecheck: `make typecheck` (from `Makefile`)", (root / "AGENTS.md").read_text())

    def test_conflicts_write_nothing(self):
        root = self.repo()
        run(root, target="structured", dry_run=False)
        agents = root / "AGENTS.md"
        agents.write_text(agents.read_text().replace("- Test:", "- Tests (team edit):"))
        (root / ".gitignore").unlink()
        (root / "Makefile").write_text("typecheck:\n\tmypy src\n")
        before = snapshot(root)
        document = run(root, target="structured", dry_run=False)
        self.assertEqual(document["result"]["status"], "conflict")
        outcomes = {o["path"]: o["outcome"] for o in document["outcomes"]}
        self.assertEqual(outcomes, {"AGENTS.md": managed.CONFLICT, ".gitignore": managed.CREATE})
        self.assertEqual(snapshot(root), before)  # all-or-nothing: .gitignore was not created either

    def test_changed_since_preview_is_a_conflict(self):
        root = self.repo()
        document = propose(root, target="structured")
        (root / ".gitignore").write_text("dist/\n")
        plans = {p.path: p for p in plan_changes(root, document)}
        self.assertEqual(plans[".gitignore"].outcomes[0]["outcome"], managed.CONFLICT)
        self.assertIn("changed since the preview", plans[".gitignore"].outcomes[0]["reason"])

    def test_symlinked_targets_are_refused(self):
        root = self.repo()
        outside = Path(tempfile.mkdtemp())
        self.dirs.append(outside)
        (outside / "notes.md").write_text("# outside\n")
        (root / "AGENTS.md").symlink_to(outside / "notes.md")
        document = run(root, target="structured", dry_run=False)
        self.assertEqual(document["result"]["status"], "conflict")
        self.assertEqual((outside / "notes.md").read_text(), "# outside\n")
        self.assertFalse((root / ".gitignore").exists())

    def test_failed_write_rolls_back_everything(self):
        root = self.repo()
        (root / ".gitignore").write_text("dist/\n")
        before = snapshot(root)
        real = apply_module._write_atomic
        calls = {"n": 0}

        def flaky(path, text, mode):
            calls["n"] += 1
            if calls["n"] == 2:
                raise OSError("disk full")
            real(path, text, mode)

        with patch.object(apply_module, "_write_atomic", flaky), self.assertRaisesRegex(ApplyError, "rolled back"):
            run(root, target="structured", dry_run=False)
        self.assertEqual(calls["n"], 2)
        after = snapshot(root)
        self.assertEqual({k: v[3] for k, v in after.items()}, {k: v[3] for k, v in before.items()})
        self.assertEqual((root / ".gitignore").read_text(), "dist/\n")
        self.assertFalse((root / "AGENTS.md").exists())
        self.assertFalse(any(name.endswith((".agentic-tmp", ".agentic-restore")) for name in os.listdir(root)))

    def test_change_between_planning_and_writing_rolls_back(self):
        root = self.repo()
        (root / "README.md").write_text((root / "README.md").read_text())  # unrelated, untouched by apply
        document = propose(root, target="structured")
        plans = plan_changes(root, document)
        (root / "AGENTS.md").write_text("# raced\n")
        with self.assertRaisesRegex(ApplyError, "changed while applying"):
            apply_module.write_transaction(root, plans)
        self.assertEqual((root / "AGENTS.md").read_text(), "# raced\n")
        self.assertFalse((root / ".gitignore").exists())

    def test_maintenance_changes_are_written_but_never_change_readiness(self):
        root = self.repo("optimized-node")
        workflow = ".github/workflows/agentic-readiness.yml"
        content = ("name: Agent Ready\non: [pull_request]\njobs:\n  readiness:\n    runs-on: ubuntu-latest\n"
                   "    steps:\n      - uses: actions/checkout@v4\n      - run: pip install agentic-dev==0.15.0\n"
                   "      - run: agentic ready verify . --target optimized\n")

        def generate(ctx: Context):
            made = make_change(ctx, block_id="readiness.ci-check", path=workflow, content=content,
                               provenance=[{"kind": "spec", "type": "agentic-dev", "value": "readiness CI check",
                                            "source": "readiness-remediation-v1"}],
                               owner={"type": "maintenance-action", "id": "readiness.ci-check"})
            return "Readiness CI check", "Keep readiness from regressing.", [made]

        shutil.rmtree(root / ".github")
        before = self.statuses(root)
        with patch.dict(MAINTENANCE_GENERATORS, {"readiness.ci-check": generate}):
            document = run(root, target="optimized", dry_run=False, maintenance=["readiness.ci-check"])
        self.assertEqual(document["result"]["written"], [workflow])
        self.assertTrue((root / workflow).is_file())
        self.assertEqual(self.statuses(root), before)


class ApplyCliTests(ApplyCase):
    def cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        env = {**os.environ, "PYTHONPATH": str(ROOT / "src"), "AGENTIC_DEV_CONFIG_DIR": tempfile.mkdtemp()}
        return subprocess.run([sys.executable, "-m", "agentic_dev.cli", *args],
                              env=env, capture_output=True, text=True, check=False)

    def test_diff_apply_and_conflict_exit_codes(self):
        root = self.repo()
        before = snapshot(root)
        diff = self.cli("ready", "diff", str(root), "--target", "structured")
        self.assertEqual(diff.returncode, 0, diff.stderr)
        self.assertIn("dry run: nothing was written", diff.stdout)
        self.assertIn("+++ b/AGENTS.md", diff.stdout)
        self.assertIn("Needs a human decision", diff.stdout)
        self.assertEqual(snapshot(root), before)

        applied = self.cli("ready", "apply", str(root), "--target", "structured", "--json")
        self.assertEqual(applied.returncode, 0, applied.stderr)
        document = json.loads(applied.stdout)
        jsonschema.validate(document, SCHEMA)
        self.assertEqual(document["result"]["status"], "applied")
        self.assertNotIn(str(root), applied.stdout)

        agents = root / "AGENTS.md"
        agents.write_text(agents.read_text().replace("- Test:", "- Tests:"))
        (root / "Makefile").write_text("typecheck:\n\tmypy src\n")
        conflict = self.cli("ready", "apply", str(root), "--target", "structured")
        self.assertEqual(conflict.returncode, 1)
        self.assertIn("conflict: nothing was written", conflict.stdout)

        bad = self.cli("ready", "apply", str(root), "--target", "legendary")
        self.assertEqual(bad.returncode, 2)


if __name__ == "__main__":
    unittest.main()
