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

import jsonschema

from agentic_dev.cli import build_parser
from agentic_dev.readiness import load_spec


ROOT = Path(__file__).resolve().parents[1]


def run(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    env["AGENTIC_DEV_CONFIG_DIR"] = env.get("AGENTIC_DEV_CONFIG_DIR") or tempfile.mkdtemp()
    return subprocess.run(
        [sys.executable, "-m", "agentic_dev.cli", *args],
        cwd=cwd, env=env, capture_output=True, text=True, check=False,
    )


def snapshot(root: Path) -> dict[str, tuple]:
    """Content, mode, and mtime of every file and directory, including .git."""

    state: dict[str, tuple] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        for name in dirnames + filenames:
            path = Path(dirpath) / name
            info = path.lstat()
            digest = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() and not path.is_symlink() else None
            state[str(path.relative_to(root))] = (info.st_mode, info.st_size, info.st_mtime_ns, digest)
    return state


class ReadyCliTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(tempfile.mkdtemp(prefix="ready-cli-"))
        subprocess.run(["git", "init", "-q", str(cls.root)], check=True)
        for key, value in (("maintenance.auto", "false"), ("gc.auto", "0")):
            subprocess.run(["git", "-C", str(cls.root), "config", key, value], check=True)
        files = {
            "README.md": "# Demo\n\n## Setup\n\nRun `make test`.\n",
            "Makefile": "test:\n\tpytest\n\nlint:\n\truff check .\n",
            "pyproject.toml": '[project]\nname = "demo"\n\n[tool.ruff]\n\n[tool.mypy]\nstrict = true\n',
            "AGENTS.md": "# Agents\n\n## Commands\n\n- `make test`\n\n## Do NOT\n\n- Never edit `src/demo/vendor.py`.\n",
            ".gitignore": ".env\n",
            "src/demo/__init__.py": "",
            "tests/test_demo.py": "def test_ok():\n    assert True\n",
        }
        for name, text in files.items():
            path = cls.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        subprocess.run(["git", "-C", str(cls.root), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(cls.root), "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                        "commit", "-qm", "init"], check=True)
        # An untracked local file must also stay untouched.
        (cls.root / ".env").write_text("TOKEN=local\n")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.root, ignore_errors=True)

    def schema(self, name: str) -> dict:
        return json.loads((ROOT / "src" / "agentic_dev" / "schemas" / name).read_text())

    def test_parser_accepts_ready_commands(self):
        parser = build_parser()
        args = parser.parse_args(["ready", "assess", ".", "--target", "structured", "--json"])
        self.assertEqual((args.ready_command, args.target, args.json), ("assess", "structured", True))
        args = parser.parse_args(["ready", "explain", "context.agent_instructions", "--path", "repo"])
        self.assertEqual((args.subject, args.path), ("context.agent_instructions", "repo"))
        args = parser.parse_args(["ready", "plan", "--spec", "bundle.json"])
        self.assertEqual((args.path, args.spec), (".", "bundle.json"))

    def test_assess_json_contract(self):
        completed = run("ready", "assess", str(self.root), "--json")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        document = json.loads(completed.stdout)
        jsonschema.validate(document, self.schema("readiness-assessment-v1.schema.json"))
        self.assertEqual(document["maturity"]["current"], "foundational")
        self.assertNotIn(str(self.root), completed.stdout)

    def test_assess_text(self):
        completed = run("ready", "assess", str(self.root), "--target", "structured")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("Maturity: Foundational (level 1 of 4)", completed.stdout)
        self.assertIn("Target:   Structured — not met", completed.stdout)
        self.assertIn("✓ feedback.tests.available", completed.stdout)
        self.assertIn(f"Spec: agent-ready {load_spec().version}", completed.stdout)

    def test_explain_repository_and_rule(self):
        overview = run("ready", "explain", ".", cwd=self.root)
        self.assertEqual(overview.returncode, 0, overview.stderr)
        self.assertIn("Why ", overview.stdout)
        self.assertIn("Level 2 — Structured", overview.stdout)

        rule = run("ready", "explain", "feedback.tests.available", "--path", str(self.root))
        self.assertEqual(rule.returncode, 0, rule.stderr)
        for expected in ("Runnable test suite", "Required from: foundational", "Status in", "PASS",
                         "Observed evidence:", "command.test: make test (Makefile)", "Why it matters:",
                         "Remediation: assisted"):
            self.assertIn(expected, rule.stdout)

        data = json.loads(run("ready", "explain", "context.architecture", "--path", str(self.root), "--json").stdout)
        jsonschema.validate(data, self.schema("readiness-explanation-v1.schema.json"))
        self.assertEqual(data["result"]["status"], "fail")
        self.assertIn("documentation.architecture", data["result"]["missing_evidence"])

    def test_plan_text_and_json(self):
        text = run("ready", "plan", str(self.root), "--target", "optimized")
        self.assertEqual(text.returncode, 0, text.stderr)
        self.assertIn("read-only; nothing was modified", text.stdout)
        self.assertIn("Current: Foundational", text.stdout)
        self.assertIn("Target:  Optimized", text.stdout)
        self.assertIn("Classification: human-required", text.stdout)
        self.assertIn("Required decision:", text.stdout)
        self.assertIn("Next: agentic ready diff <path>", text.stdout)
        self.assertNotIn("not performed in this version", text.stdout)
        data = json.loads(run("ready", "plan", str(self.root), "--json").stdout)
        jsonschema.validate(data, self.schema("readiness-plan-v1.schema.json"))
        self.assertEqual(data["maturity"]["target"], "structured")

    def test_errors_exit_2_with_a_message(self):
        unknown = run("ready", "explain", "context.nope", "--path", str(self.root))
        self.assertEqual(unknown.returncode, 2)
        self.assertIn("unknown rule 'context.nope'", unknown.stderr)
        target = run("ready", "plan", str(self.root), "--target", "legendary")
        self.assertEqual(target.returncode, 2)
        self.assertIn("unknown target level", target.stderr)
        spec = run("ready", "assess", str(self.root), "--spec", str(self.root / "missing.json"))
        self.assertEqual(spec.returncode, 2)

    def test_ready_commands_never_modify_the_repository(self):
        before = snapshot(self.root)
        commands = [
            ("ready", "assess", "."),
            ("ready", "assess", ".", "--json", "--target", "autonomous"),
            ("ready", "explain", "."),
            ("ready", "explain", ".", "--json"),
            ("ready", "explain", "constraints.architecture_boundaries"),
            ("ready", "explain", "context.agent_instructions", "--json"),
            ("ready", "plan", "."),
            ("ready", "plan", ".", "--target", "optimized", "--json"),
            ("ready", "diff", "."),
            ("ready", "diff", ".", "--target", "autonomous", "--json"),
            ("ready", "apply", ".", "--dry-run"),
            ("ready", "apply", ".", "--dry-run", "--target", "optimized", "--json"),
            ("ready", "apply", ".", "--dry-run", "--ci-check"),
            ("ready", "assess", ".", "--scope", "ci", "--json"),
            ("ready", "verify", ".", "--target", "foundational"),
            ("ready", "verify", ".", "--target", "foundational", "--json", "--scope", "local"),
            ("ready", "make", ".", "--target", "structured", "--dry-run"),
            ("ready", "make", ".", "--target", "optimized", "--dry-run", "--ci-check", "--json"),
        ]
        for command in commands:
            completed = run(*command, cwd=self.root)
            allowed = {0, 1, 4} if command[1] in {"verify", "make"} else {0}
            self.assertIn(completed.returncode, allowed, f"{command}: {completed.stderr}")
        self.assertEqual(snapshot(self.root), before)


if __name__ == "__main__":
    unittest.main()
