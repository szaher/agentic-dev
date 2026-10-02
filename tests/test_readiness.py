from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest
from importlib import resources
from pathlib import Path
from unittest.mock import patch

import jsonschema

from agentic_dev.readiness import assess, explain_repository, explain_rule, load_spec, plan
from agentic_dev.readiness.assess import describe, evaluate
from agentic_dev.readiness.evidence import EvidenceCollector, Observation, compile_glob
from agentic_dev.readiness.maturity import compute
from agentic_dev.readiness.spec import BuiltinSpecSource, PathSpecSource, SpecError


ROOT = Path(__file__).resolve().parents[1]
SPEC = load_spec()


def write(root: Path, files: dict[str, str]) -> None:
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)


def git_repo(files: dict[str, str], *, commit: bool = True) -> Path:
    root = Path(tempfile.mkdtemp(prefix="ready-"))
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    for key, value in (("maintenance.auto", "false"), ("gc.auto", "0")):
        subprocess.run(["git", "-C", str(root), "config", key, value], check=True)
    write(root, files)
    if commit:
        subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
        subprocess.run([
            "git", "-C", str(root), "-c", "user.name=Agentic Test",
            "-c", "user.email=agentic@example.invalid", "commit", "-qm", "init", "--allow-empty",
        ], check=True)
    return root


def status(document: dict, rule_id: str) -> str:
    return next(r["status"] for r in document["requirements"] if r["id"] == rule_id)


def result(document: dict, rule_id: str) -> dict:
    return next(r for r in document["requirements"] if r["id"] == rule_id)


PYTHON_FOUNDATIONAL = {
    "README.md": "# Demo\n\n## Installation\n\n`uv sync`\n",
    "pyproject.toml": '[project]\nname = "demo"\nversion = "0.1.0"\n\n'
                      '[dependency-groups]\ndev = ["pytest", "ruff"]\n\n[tool.ruff]\nline-length = 100\n',
    "src/demo/__init__.py": "VALUE = 1\n",
    "tests/test_demo.py": "def test_value():\n    assert True\n",
}


class SpecLoadingTests(unittest.TestCase):
    def test_builtin_spec_is_pinned_and_verified(self):
        pin = BuiltinSpecSource().pin()
        data = resources.files("agentic_dev.readiness").joinpath("specs", pin["file"]).read_bytes()
        self.assertEqual(hashlib.sha256(data).hexdigest(), pin["sha256"])
        self.assertEqual(SPEC.version, pin["spec_version"])
        self.assertEqual(SPEC.identity()["source"], "builtin")
        self.assertRegex(pin["source"]["commit"], r"^[0-9a-f]{40}$")

    def test_corrupt_builtin_spec_is_rejected(self):
        pin = {**BuiltinSpecSource().pin(), "sha256": "0" * 64}
        with patch.object(BuiltinSpecSource, "pin", return_value=pin):
            with self.assertRaisesRegex(SpecError, "corrupt"):
                BuiltinSpecSource().load()

    def test_explicit_path_spec_file_and_directory(self):
        pin = BuiltinSpecSource().pin()
        bundle = resources.files("agentic_dev.readiness").joinpath("specs", pin["file"]).read_bytes()
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / pin["file"]).write_bytes(bundle)
            from_dir = PathSpecSource(Path(tmp)).load()
            from_file = load_spec(Path(tmp) / pin["file"])
        self.assertEqual(from_dir.sha256, pin["sha256"])
        self.assertEqual(from_file.identity()["source"], "path")

    def test_unsupported_documents_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            future = dict(SPEC.document, schema_version="2")
            path = Path(tmp) / "agent-ready-spec-2.0.0.json"
            path.write_text(json.dumps(future))
            with self.assertRaisesRegex(SpecError, "unsupported schema_version"):
                load_spec(path)
            yaml_source = Path(tmp) / "spec.yaml"
            yaml_source.write_text("schema_version: '1'\n")
            with self.assertRaisesRegex(SpecError, "not a JSON"):
                load_spec(yaml_source)


class GlobSemanticsTests(unittest.TestCase):
    def match(self, glob: str, path: str) -> bool:
        return bool(compile_glob(glob, ["node_modules", ".git"]).match(path))

    def test_double_star_skips_hidden_and_ignored_directories(self):
        self.assertTrue(self.match("**/*.py", "main.py"))
        self.assertTrue(self.match("**/*.py", "src/pkg/main.py"))
        self.assertFalse(self.match("**/*.py", ".venv/lib/x.py"))
        self.assertFalse(self.match("**/*.py", "node_modules/x/y.py"))
        self.assertTrue(self.match("**/.env", ".env"))

    def test_star_does_not_match_leading_dot_but_literals_do(self):
        self.assertFalse(self.match("*/**/CLAUDE.md", ".claude/CLAUDE.md"))
        self.assertTrue(self.match("*/**/CLAUDE.md", "pkg/CLAUDE.md"))
        self.assertTrue(self.match(".github/workflows/*.yml", ".github/workflows/ci.yml"))
        self.assertFalse(self.match(".github/workflows/*.yml", ".github/workflows/.hidden.yml"))


class ExpressionTests(unittest.TestCase):
    def observe_with(self, values: dict[str, bool | None]):
        return lambda ref: Observation(ref, values[ref])

    def test_three_valued_logic(self):
        observe = self.observe_with({"a": True, "b": False, "u": None})
        self.assertIs(evaluate({"any": ["b", "a"]}, observe), True)
        self.assertIsNone(evaluate({"any": ["b", "u"]}, observe))
        self.assertIs(evaluate({"all": ["a", "b", "u"]}, observe), False)
        self.assertIsNone(evaluate({"all": ["a", "u"]}, observe))
        self.assertIs(evaluate({"none": ["b"]}, observe), True)
        self.assertIs(evaluate({"none": ["a", "u"]}, observe), False)
        self.assertIsNone(evaluate({"none": ["b", "u"]}, observe))

    def test_implication_is_described_readably(self):
        expression = {"any": [{"none": ["project.language.python"]}, "config.python_typecheck"]}
        self.assertEqual(describe(expression), "project.language.python requires any(config.python_typecheck)")


class MaturityTests(unittest.TestCase):
    def statuses(self, **overrides: str) -> dict[str, str]:
        base = {rule_id: "pass" for rule_id in SPEC.rules}
        base.update({key.replace("__", "."): value for key, value in overrides.items()})
        return base

    def test_all_pass_reaches_autonomous(self):
        state = compute(SPEC, self.statuses())
        self.assertEqual(state["current"], "autonomous")
        self.assertIsNone(state["next"])
        self.assertTrue(state["target_met"])

    def test_one_required_failure_blocks_its_level_and_all_higher(self):
        state = compute(SPEC, self.statuses(feedback__typecheck="fail"))
        self.assertEqual(state["current"], "foundational")
        achieved = {level["id"]: level["achieved"] for level in state["levels"]}
        self.assertEqual(achieved, {
            "unaware": True, "foundational": True, "structured": False,
            "optimized": False, "autonomous": False,
        })
        self.assertEqual(state["target_blockers"], ["feedback.typecheck"])

    def test_unknown_blocks_like_failure(self):
        state = compute(SPEC, self.statuses(constraints__architecture_boundaries="unknown"))
        self.assertEqual(state["current"], "structured")

    def test_not_applicable_and_non_required_rules_do_not_block(self):
        state = compute(SPEC, self.statuses(
            feedback__build__available="not-applicable",
            context__decisions="fail",
            context__codeowners="fail",
        ))
        self.assertEqual(state["current"], "autonomous")

    def test_lower_level_failure_caps_maturity_even_when_higher_rules_pass(self):
        state = compute(SPEC, self.statuses(context__readme="fail"))
        self.assertEqual(state["current"], "unaware")
        optimized = next(level for level in state["levels"] if level["id"] == "optimized")
        self.assertEqual(optimized["blocking"], [])
        self.assertFalse(optimized["achieved"])

    def test_explicit_target(self):
        state = compute(SPEC, self.statuses(feedback__typecheck="fail", context__task_workflows="fail"),
                        target="optimized")
        self.assertEqual(state["target"], "optimized")
        self.assertFalse(state["target_met"])
        self.assertEqual(state["target_blockers"], ["feedback.typecheck", "context.task_workflows"])
        with self.assertRaisesRegex(SpecError, "unknown target level"):
            compute(SPEC, self.statuses(), target="legendary")


class AssessmentTests(unittest.TestCase):
    def setUp(self):
        self.dirs: list[Path] = []

    def tearDown(self):
        for path in self.dirs:
            shutil.rmtree(path, ignore_errors=True)

    def repo(self, files: dict[str, str], **kwargs) -> Path:
        root = git_repo(files, **kwargs)
        self.dirs.append(root)
        return root

    def schema(self, name: str) -> dict:
        return json.loads((ROOT / "src" / "agentic_dev" / "schemas" / name).read_text())

    def test_empty_repository_is_unaware_with_code_rules_not_applicable(self):
        document = assess(self.repo({}))
        jsonschema.validate(document, self.schema("readiness-assessment-v1.schema.json"))
        self.assertEqual(document["maturity"]["current"], "unaware")
        self.assertEqual(status(document, "context.readme"), "fail")
        self.assertEqual(status(document, "feedback.tests.available"), "not-applicable")
        self.assertEqual(status(document, "constraints.secrets.untracked"), "pass")

    def test_python_repository_reaches_foundational_with_concrete_evidence(self):
        document = assess(self.repo(PYTHON_FOUNDATIONAL))
        self.assertEqual(document["maturity"]["current"], "foundational")
        tests = result(document, "feedback.tests.available")
        self.assertEqual(tests["status"], "pass")
        self.assertIn(
            {"type": "command.test", "value": "uv run pytest", "source": "pyproject.toml"},
            tests["evidence"],
        )
        self.assertEqual(tests["required_for"], ["foundational", "structured", "optimized", "autonomous"])
        self.assertEqual(status(document, "feedback.build.available"), "not-applicable")
        setup = result(document, "context.readme.setup")
        self.assertEqual(setup["evidence"][0]["line"], 3)

    def test_failure_identifies_missing_evidence(self):
        files = {k: v for k, v in PYTHON_FOUNDATIONAL.items() if k != "tests/test_demo.py"}
        files["pyproject.toml"] = '[project]\nname = "demo"\n\n[tool.ruff]\n'
        document = assess(self.repo(files))
        tests = result(document, "feedback.tests.available")
        self.assertEqual(tests["status"], "fail")
        self.assertEqual(tests["missing_evidence"], ["command.test"])
        self.assertIn("command.test", tests["reason"])
        self.assertEqual(document["maturity"]["current"], "unaware")

    def test_policy_rules_report_unknown_not_fail(self):
        document = assess(self.repo(PYTHON_FOUNDATIONAL))
        boundaries = result(document, "constraints.architecture_boundaries")
        self.assertEqual(boundaries["status"], "unknown")
        self.assertIn("cannot be inferred safely", boundaries["reason"])
        self.assertEqual(boundaries["remediation"]["classification"], "human-required")

    def test_policy_rule_passes_on_explicit_enforcement(self):
        files = dict(PYTHON_FOUNDATIONAL)
        files["pyproject.toml"] += "\n[tool.importlinter]\nroot_package = \"demo\"\n"
        document = assess(self.repo(files))
        boundaries = result(document, "constraints.architecture_boundaries")
        self.assertEqual(boundaries["status"], "pass")
        self.assertEqual(boundaries["evidence"][0]["source"], "pyproject.toml")

    def test_unsupported_evidence_is_unknown(self):
        from agentic_dev.readiness import evidence as module

        handlers = {k: v for k, v in module.DERIVED.items() if k != "command.test"}
        with patch.dict(module.DERIVED, handlers, clear=True):
            document = assess(self.repo(PYTHON_FOUNDATIONAL))
        tests = result(document, "feedback.tests.available")
        self.assertEqual(tests["status"], "unknown")
        self.assertIn("command.test", tests["unsupported_evidence"])

    def test_only_tracked_secret_files_count(self):
        root = self.repo({".gitignore": ".env\n", "README.md": "# x\n"})
        write(root, {".env": "TOKEN=abc\n"})
        self.assertEqual(status(assess(root), "constraints.secrets.untracked"), "pass")
        tracked = self.repo({".env": "TOKEN=abc\n", "tests/fixtures/key.pem": "test\n", ".env.example": "X=\n"})
        failing = result(assess(tracked), "constraints.secrets.untracked")
        self.assertEqual(failing["status"], "fail")
        self.assertEqual([item["source"] for item in failing["evidence"]], [".env"])
        self.assertIn("Prohibited evidence observed", failing["reason"])

    def test_mcp_secrets_are_redacted_and_not_applicable_without_config(self):
        self.assertEqual(status(assess(self.repo(PYTHON_FOUNDATIONAL)), "constraints.mcp.no_inline_secrets"),
                         "not-applicable")
        leaky = dict(PYTHON_FOUNDATIONAL)
        leaky[".mcp.json"] = '{"mcpServers": {"gh": {"env": {"GITHUB_TOKEN": "ghp_abcdefghijklmnopqrstuvwxyz0123"}}}}\n'
        failing = result(assess(self.repo(leaky)), "constraints.mcp.no_inline_secrets")
        self.assertEqual(failing["status"], "fail")
        self.assertNotIn("ghp_", json.dumps(failing))
        safe = dict(PYTHON_FOUNDATIONAL)
        safe[".mcp.json"] = '{"mcpServers": {"gh": {"env": {"GITHUB_TOKEN": "${GITHUB_TOKEN}"}}}}\n'
        self.assertEqual(status(assess(self.repo(safe)), "constraints.mcp.no_inline_secrets"), "pass")

    def test_headings_inside_code_fences_are_ignored(self):
        files = dict(PYTHON_FOUNDATIONAL)
        files["AGENTS.md"] = "# Agents\n\n```md\n## Build and test\n```\n"
        self.assertEqual(status(assess(self.repo(files)), "context.agent_instructions.commands"), "fail")
        files["AGENTS.md"] += "\n## Commands\n\n- `uv run pytest`\n"
        self.assertEqual(status(assess(self.repo(files)), "context.agent_instructions.commands"), "pass")

    def commands_status(self, agents: str, extra: dict[str, str] | None = None) -> dict:
        files = {**PYTHON_FOUNDATIONAL, **(extra or {}), "AGENTS.md": agents}
        return result(assess(self.repo(files)), "context.agent_instructions.commands")

    def test_a_commands_heading_alone_is_not_evidence(self):
        # Spec 1.0.1 erratum: AgentFlow's "Useful commands" section lists only workflow commands.
        agentflow = ("# Agentflow project instructions\n\n## Useful commands\n"
                     "- `agentflow patterns`\n- `agentflow status`\n- `agentflow verify`\n")
        self.assertEqual(self.commands_status(agentflow)["status"], "fail")
        self.assertEqual(self.commands_status("# A\n\n## Testing\n\nRun the tests with pytest.\n")["status"], "fail")

    def test_project_commands_in_code_are_evidence(self):
        for text in (
            "# A\n\n- Test: `uv run pytest`\n",
            "# A\n\n```bash\n$ CI=1 make check\n```\n",
            "# A\n\nUse `cd web && pnpm test`.\n",
            "# A\n\n`python3 -m pytest -q`\n",
            "# A\n\n~~~\ngo test ./...\n~~~\n",
        ):
            with self.subTest(text=text):
                observed = self.commands_status(text)
                self.assertEqual(observed["status"], "pass")
        evidence = self.commands_status("# A\n\n## Commands\n\n- `uv run pytest`\n")["evidence"]
        self.assertEqual(evidence, [{"line": 5, "source": "AGENTS.md", "type": "agent.instructions.commands",
                                     "value": "uv run pytest"}])

    def test_other_programs_and_missing_scripts_are_not_evidence(self):
        for text in (
            "# A\n\n`python -c 'print(1)'`\n",
            "# A\n\n`python -m http.server`\n",
            "# A\n\n`./scripts/missing.sh`\n",
            "# A\n\n`../outside/test.sh`\n",
            "# A\n\n`docker ps`\n",
            "# A\n\nRead `.agentflow/config.json` first.\n",
            "# A\n\nSee `./README.md`.\n",
            "# A\n\n`scripts/test.sh`\n",
        ):
            with self.subTest(text=text):
                existing = {".agentflow/config.json": "{}\n", "scripts/test.sh": "#!/bin/sh\n"}
                self.assertEqual(self.commands_status(text, existing)["status"], "fail")

    def test_existing_repository_scripts_are_evidence(self):
        observed = self.commands_status("# A\n\n`./scripts/test.sh --fast`\n", {"scripts/test.sh": "#!/bin/sh\n"})
        self.assertEqual(observed["status"], "pass")

    def test_untracked_scripts_do_not_count_in_ci_scope(self):
        files = {**PYTHON_FOUNDATIONAL, "AGENTS.md": "# A\n\n`./scripts/test.sh`\n"}
        root = self.repo(files)
        write(root, {"scripts/test.sh": "#!/bin/sh\n"})
        self.assertEqual(status(assess(root), "context.agent_instructions.commands"), "pass")
        self.assertEqual(status(assess(root, scope="ci"), "context.agent_instructions.commands"), "fail")

    def test_output_is_deterministic_and_has_no_absolute_paths(self):
        root = self.repo(PYTHON_FOUNDATIONAL)
        first = json.dumps(assess(root), sort_keys=True)
        second = json.dumps(assess(root), sort_keys=True)
        self.assertEqual(first, second)
        self.assertNotIn(str(root), first)
        self.assertNotIn(str(Path.home()), first)
        ids = [r["id"] for r in json.loads(first)["requirements"]]
        self.assertEqual(ids, sorted(ids))

    def test_same_content_in_different_checkouts_assesses_identically(self):
        first = assess(self.repo(PYTHON_FOUNDATIONAL))
        second = assess(self.repo(PYTHON_FOUNDATIONAL))
        for document in (first, second):
            document["repository"] = None
        self.assertEqual(first, second)

    def test_spec_version_is_reported(self):
        document = assess(self.repo({}))
        self.assertEqual(document["spec"], SPEC.identity())
        self.assertEqual(document["spec"]["name"], "agent-ready")

    def test_target_is_reported(self):
        document = assess(self.repo(PYTHON_FOUNDATIONAL), target="optimized")
        self.assertEqual(document["maturity"]["target"], "optimized")
        self.assertFalse(document["maturity"]["target_met"])
        self.assertIn("context.agent_instructions", document["maturity"]["target_blockers"])


class ExplainAndPlanTests(unittest.TestCase):
    def setUp(self):
        self.root = git_repo(PYTHON_FOUNDATIONAL)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def schema(self, name: str) -> dict:
        return json.loads((ROOT / "src" / "agentic_dev" / "schemas" / name).read_text())

    def test_explain_repository(self):
        document = explain_repository(self.root)
        jsonschema.validate(document, self.schema("readiness-explanation-v1.schema.json"))
        self.assertEqual(document["subject"], "repository")
        self.assertIn("Maturity is foundational", document["conclusion"])
        structured = next(level for level in document["levels"] if level["id"] == "structured")
        self.assertFalse(structured["achieved"])
        self.assertTrue(any(req["status"] == "fail" for req in structured["requirements"]))

    def test_explain_rule(self):
        document = explain_rule("context.agent_instructions", self.root)
        jsonschema.validate(document, self.schema("readiness-explanation-v1.schema.json"))
        self.assertEqual(document["rule"]["required_from"], "structured")
        self.assertEqual(document["result"]["status"], "fail")
        self.assertIn("file.agents_md", document["result"]["missing_evidence"])
        self.assertEqual(document["rule"]["remediation"]["classification"], "automatable")
        self.assertIn("file.agents_md", [e["id"] for e in document["evidence_definitions"]])
        with self.assertRaisesRegex(KeyError, "unknown rule"):
            explain_rule("context.nope", self.root)

    def test_plan_is_ordered_and_classified(self):
        document = plan(self.root)
        jsonschema.validate(document, self.schema("readiness-plan-v1.schema.json"))
        self.assertTrue(document["read_only"])
        self.assertEqual(document["maturity"], {"current": "foundational", "target": "structured", "target_met": False})
        ids = [step["id"] for step in document["steps"]]
        self.assertLess(ids.index("context.agent_instructions"), ids.index("context.agent_instructions.commands"))
        self.assertTrue(all(step["required_from"] == "structured" for step in document["steps"]))
        classes = {step["id"]: step["classification"] for step in document["steps"]}
        self.assertEqual(classes["context.agent_instructions"], "automatable")
        self.assertEqual(classes["conventions.documented"], "human-required")
        self.assertEqual([s["order"] for s in document["steps"]], list(range(1, len(ids) + 1)))

    def test_plan_to_higher_target_includes_policy_unknowns(self):
        document = plan(self.root, target="optimized")
        steps = {step["id"]: step for step in document["steps"]}
        self.assertEqual(steps["constraints.architecture_boundaries"]["status"], "unknown")
        self.assertIsNotNone(steps["constraints.architecture_boundaries"]["decision"])
        levels = [SPEC.rank(step["required_from"]) for step in document["steps"]]
        self.assertEqual(levels, sorted(levels))


if __name__ == "__main__":
    unittest.main()
