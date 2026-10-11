from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import jsonschema

from agentic_dev import readiness
from agentic_dev.contracts import EXIT_CODES, schema
from agentic_dev.readiness import compare as ready_compare
from agentic_dev.readiness import render

ROOT = Path(__file__).resolve().parents[1]


def run(*args: str, cwd: Path, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src"), "AGENTIC_DEV_CONFIG_DIR": tempfile.mkdtemp()}
    return subprocess.run([sys.executable, "-m", "agentic_dev.cli", *args], cwd=cwd, env=env,
                          input=stdin, capture_output=True, text=True, check=False)


def with_status(document: dict, **statuses: str) -> dict:
    changed = copy.deepcopy(document)
    for rule in changed["requirements"]:
        if rule["id"] in statuses:
            rule["status"] = statuses[rule["id"]]
    return changed


class CompareTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(tempfile.mkdtemp(prefix="ready-compare-"))
        subprocess.run(["git", "init", "-q", str(cls.root)], check=True)
        (cls.root / "README.md").write_text("# Demo\n\n## Setup\n\nRun `make test`.\n")
        (cls.root / "Makefile").write_text("test:\n\tpytest\n")
        (cls.root / "pyproject.toml").write_text('[project]\nname = "demo"\n')
        (cls.root / "tests").mkdir()
        (cls.root / "tests" / "test_demo.py").write_text("def test_ok():\n    assert True\n")
        cls.before = readiness.assess(cls.root)
        cls.before_file = cls.root / "before.json"
        cls.before_file.write_text(json.dumps(cls.before))
        (cls.root / "pyproject.toml").write_text('[project]\nname = "demo"\n\n[tool.ruff]\n\n[tool.mypy]\n')
        cls.after = readiness.assess(cls.root)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.root, ignore_errors=True)

    def test_real_improvement_is_measured_rule_by_rule(self):
        data = ready_compare.compare(self.before, self.after)
        jsonschema.validate(data, schema("readiness-comparison"))
        improved = {c["id"] for c in data["changes"] if c["direction"] == "improved"}
        self.assertIn("conventions.tooling", improved)
        self.assertIn("feedback.typecheck", improved)
        self.assertEqual(data["outcome"], "improved")
        self.assertEqual(data["exit_code"], 0)
        self.assertEqual(data["summary"]["passed"]["delta"],
                         self.after["summary"]["passed"] - self.before["summary"]["passed"])
        self.assertGreaterEqual(data["maturity"]["delta"], 1)
        self.assertIn("conventions.tooling", render.comparison(data))

    def test_identical_assessments_are_unchanged(self):
        data = ready_compare.compare(self.before, self.before)
        self.assertEqual((data["outcome"], data["exit_code"], data["changes"]), ("unchanged", 0, []))
        self.assertIn("No rule changed status.", render.comparison(data))

    def test_directions_and_outcomes(self):
        passing = [r["id"] for r in self.after["requirements"] if r["status"] == "pass"]
        failing = [r["id"] for r in self.after["requirements"] if r["status"] == "fail"]
        worse = with_status(self.after, **{passing[0]: "unknown"})
        data = ready_compare.compare(self.after, worse)
        self.assertEqual(data["changes"][0]["direction"], "regressed")
        self.assertEqual((data["outcome"], data["exit_code"]), ("regressed", 1))

        mixed = with_status(self.after, **{passing[0]: "fail", failing[0]: "pass"})
        self.assertEqual(ready_compare.compare(self.after, mixed)["outcome"], "mixed")

        neutral = with_status(self.after, **{failing[0]: "not-applicable"})
        data = ready_compare.compare(self.after, neutral)
        self.assertEqual(data["counts"], {"improved": 0, "regressed": 0, "changed": 1})
        self.assertEqual((data["outcome"], data["exit_code"]), ("unchanged", 0))

    def test_maturity_drop_is_a_regression(self):
        data = ready_compare.compare(self.after, self.before)
        self.assertLess(data["maturity"]["delta"], 0)
        self.assertEqual(data["exit_code"], 1)

    def test_added_removed_and_spec_change_are_reported(self):
        other = copy.deepcopy(self.after)
        other["spec"]["sha256"] = "0" * 64
        dropped = other["requirements"].pop()
        data = ready_compare.compare(self.after, other)
        self.assertTrue(data["spec_changed"])
        self.assertEqual(data["removed"], [dropped["id"]])
        self.assertIn("different specs", render.comparison(data))

    def test_cli_compares_a_baseline_with_the_repository_now(self):
        result = run("ready", "compare", str(self.before_file), "--path", str(self.root), "--json", cwd=self.root)
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        jsonschema.validate(data, schema("readiness-comparison"))
        self.assertEqual(data["outcome"], "improved")

        text = run("ready", "compare", "-", "--path", str(self.root), cwd=self.root,
                   stdin=self.before_file.read_text())
        self.assertEqual(text.returncode, 0, text.stderr)
        self.assertIn("Improved (", text.stdout)

    def test_cli_exit_codes_match_the_contract(self):
        after_file = self.root / "after.json"
        after_file.write_text(json.dumps(self.after))
        regressed = run("ready", "compare", str(after_file), str(self.before_file), cwd=self.root)
        self.assertEqual(regressed.returncode, 1)
        bad = self.root / "not-an-assessment.json"
        bad.write_text('{"document_type": "agentic.doctor"}')
        for args in ([str(bad)], [str(self.root / "missing.json")]):
            result = run("ready", "compare", *args, cwd=self.root)
            self.assertEqual(result.returncode, 2)
            self.assertIn("agentic ready:", result.stderr)
        self.assertEqual(set(EXIT_CODES["ready compare"]), {str(c) for c in (
            ready_compare.EXIT_OK, ready_compare.EXIT_REGRESSED, ready_compare.EXIT_USAGE)})


if __name__ == "__main__":
    unittest.main()
