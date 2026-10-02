"""Canonical command discovery (v0.16 slice 1): one service, three consumers."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import jsonschema

from agentic_dev import inspection
from agentic_dev.commands import KINDS, Command, WorkingTree, by_kind, discover, discover_in
from agentic_dev.inspection import inspect_repository
from agentic_dev.readiness import assess
from agentic_dev.readiness import evidence as readiness_evidence
from agentic_dev.verification import execute, full_plan

ROOT = Path(__file__).resolve().parents[1]


def git_repo(files: dict[str, str]) -> Path:
    root = Path(tempfile.mkdtemp(prefix="commands-"))
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    for key, value in (("maintenance.auto", "false"), ("gc.auto", "0")):
        subprocess.run(["git", "-C", str(root), "config", key, value], check=True)
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                    "commit", "-qm", "init"], check=True)
    return root


class CommandCase(unittest.TestCase):
    def setUp(self):
        self.dirs: list[Path] = []

    def tearDown(self):
        for path in self.dirs:
            shutil.rmtree(path, ignore_errors=True)

    def repo(self, files: dict[str, str]) -> Path:
        root = git_repo(files)
        self.dirs.append(root)
        return root


class OneDiscovererTests(CommandCase):
    """R4: the consumers used to disagree. A repo whose only test entry point is `make check`."""

    FILES = {"README.md": "# Demo\n", "Makefile": "check:\n\tpython3 app.py\n", "app.py": "print(1)\n"}

    def test_repo_inspect_and_readiness_report_the_same_command(self):
        root = self.repo(self.FILES)
        expected = Command("test", "make check", "Makefile")
        self.assertEqual(discover_in(root), [expected])

        document = inspect_repository(root)
        jsonschema.validate(document, json.loads((ROOT / "src" / "agentic_dev" / "schemas" / "repo-inspection-v1.schema.json").read_text()))
        self.assertEqual(document["commands"]["test"], ["make check"])
        self.assertEqual(document["discovered_commands"], [expected.to_dict()])

        readiness = next(r for r in assess(root)["requirements"] if r["id"] == "feedback.tests.available")
        self.assertEqual(readiness["status"], "pass")
        self.assertEqual([(e["value"], e["source"]) for e in readiness["evidence"]], [("make check", "Makefile")])

    def test_full_verification_runs_the_same_command(self):
        root = self.repo({**self.FILES, "Makefile": "check:\n\ttouch ran-make-check\n"})
        document = execute(full_plan(root, kinds=["test"]))
        self.assertEqual(document["status"], "passed")
        self.assertEqual([(r["kind"], r["command"], r["source"]) for r in document["results"]],
                         [("test", "make check", "Makefile")])
        self.assertTrue((root / "ran-make-check").exists())

    def test_there_is_no_second_discoverer(self):
        self.assertFalse(hasattr(inspection, "discover_commands"))
        for name in ("_make_target", "_just_recipe", "_command_source", "_MAKEFILES"):
            self.assertFalse(hasattr(readiness_evidence, name), name)


class DiscoveryRuleTests(CommandCase):
    def commands(self, files: dict[str, str]) -> list[tuple[str, str, str]]:
        root = self.repo(files)
        return [(c.kind, c.command, c.source) for c in discover_in(root)]

    def test_order_is_deterministic_by_kind_then_rule(self):
        files = {
            "Makefile": "lint:\n\truff check\ntest:\n\tpytest\nbuild:\n\tpython -m build\n",
            "pyproject.toml": "[build-system]\nrequires=[]\n[tool.ruff]\n[dependency-groups]\ndev=['pytest','mypy']\n",
        }
        found = self.commands(files)
        self.assertEqual([k for k, _, _ in found], sorted((k for k, _, _ in found), key=KINDS.index))
        self.assertEqual(found, self.commands(files))
        self.assertEqual([c for k, c, _ in found if k == "test"], ["make test", "uv run pytest"])

    def test_one_pytest_command_per_repository(self):
        both = self.commands({"pyproject.toml": "[tool.pytest.ini_options]\n", "conftest.py": "", "pytest.ini": ""})
        self.assertEqual([c for k, c, _ in both if k == "test"], ["uv run pytest"])
        legacy = self.commands({"setup.cfg": "[tool:pytest]\n", "conftest.py": ""})
        self.assertEqual([(c, s) for k, c, s in legacy if k == "test"], [("pytest", "setup.cfg")])

    def test_package_manager_forms(self):
        scripts = json.dumps({"scripts": {"test": "x", "fmt": "x", "type-check": "x"}})
        self.assertIn(("test", "bun run test", "package.json"),
                      self.commands({"package.json": scripts, "bun.lockb": ""}))
        pnpm = self.commands({"package.json": scripts, "pnpm-lock.yaml": ""})
        self.assertIn(("format", "pnpm fmt", "package.json"), pnpm)
        self.assertIn(("typecheck", "pnpm type-check", "package.json"), pnpm)

    def test_make_assignments_are_not_targets(self):
        self.assertEqual(self.commands({"Makefile": "test := 1\ncheck:\n\ttrue\n"}),
                         [("test", "make check", "Makefile")])

    def test_only_root_files_and_exact_case(self):
        self.assertEqual(self.commands({"sub/Makefile": "test:\n\ttrue\n", "MAKEFILE": "test:\n\ttrue\n"}), [])

    def test_symlinks_outside_the_repository_are_ignored(self):
        outside = Path(tempfile.mkdtemp())
        self.dirs.append(outside)
        (outside / "Makefile").write_text("test:\n\ttrue\n")
        root = self.repo({"README.md": "x\n"})
        (root / "Makefile").symlink_to(outside / "Makefile")
        self.assertEqual(discover(WorkingTree(root)), [])

    def test_by_kind_lists_every_kind(self):
        self.assertEqual(by_kind([Command("test", "go test ./...", "go.mod")]),
                         {**{kind: [] for kind in KINDS}, "test": ["go test ./..."]})


if __name__ == "__main__":
    unittest.main()
