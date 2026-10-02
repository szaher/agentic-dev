"""Realistic readiness scenarios (see tests/readiness_fixtures.py)."""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import jsonschema

sys.path.insert(0, str(Path(__file__).resolve().parent))
from readiness_fixtures import SCENARIOS, materialize  # noqa: E402

from agentic_dev.readiness import assess, explain_repository, explain_rule, load_spec, plan  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
SPEC = load_spec()
SCHEMAS = {
    name: json.loads((ROOT / "schemas" / f"{name}-v1.schema.json").read_text())
    for name in ("readiness-assessment", "readiness-explanation", "readiness-plan")
}


class FixtureCase(unittest.TestCase):
    """Materializes each scenario once and assesses it once."""

    workspace: Path
    documents: dict[str, dict]

    @classmethod
    def setUpClass(cls):
        cls.workspace = Path(tempfile.mkdtemp(prefix="ready-fixtures-"))
        cls.documents = {}
        for name in SCENARIOS:
            cls.documents[name] = assess(materialize(name, cls.workspace / name))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.workspace, ignore_errors=True)

    def path(self, name: str) -> Path:
        return self.workspace / name

    def status(self, name: str, rule_id: str) -> str:
        return self.rule(name, rule_id)["status"]

    def rule(self, name: str, rule_id: str) -> dict:
        return next(r for r in self.documents[name]["requirements"] if r["id"] == rule_id)

    def maturity(self, name: str) -> dict:
        return self.documents[name]["maturity"]


class ScenarioMaturityTests(FixtureCase):
    EXPECTED = {
        "empty": ("unaware", ["context.readme", "context.readme.setup"]),
        "missing-tests": ("unaware", ["feedback.tests.available"]),
        "foundational-python": ("foundational", [
            "constraints.documented", "constraints.secrets.ignored", "context.agent_instructions",
            "context.agent_instructions.commands", "context.architecture", "conventions.documented",
            "conventions.enforced", "feedback.typecheck",
        ]),
        "no-agent-instructions": ("foundational", [
            "constraints.documented", "context.agent_instructions", "context.agent_instructions.commands",
        ]),
        "ambiguous-policy": ("structured", ["constraints.architecture_boundaries"]),
        "structured-go": ("structured", ["constraints.architecture_boundaries", "context.task_workflows"]),
        "optimized-node": ("optimized", [
            "context.contribution_workflow", "feedback.agent_effectiveness", "feedback.ci.security",
        ]),
        "autonomous-node": ("autonomous", []),
    }

    def test_every_scenario_has_an_expectation(self):
        self.assertEqual(sorted(self.EXPECTED), sorted(SCENARIOS))

    def test_maturity_and_next_level_blockers(self):
        for name, (level, blockers) in self.EXPECTED.items():
            with self.subTest(scenario=name):
                state = self.maturity(name)
                self.assertEqual(state["current"], level)
                self.assertEqual(state["target_blockers"], blockers)

    def test_documents_satisfy_the_contract(self):
        for name, document in self.documents.items():
            with self.subTest(scenario=name):
                jsonschema.validate(document, SCHEMAS["readiness-assessment"])
                self.assertEqual(document["spec"]["version"], SPEC.version)
                self.assertEqual(document["repository"]["name"], name)
                self.assertNotIn(str(self.workspace), json.dumps(document))

    def test_maturity_never_follows_counts(self):
        # optimized-node fails more rules overall than structured-go passes, yet
        # it is a higher level: only required rules per level matter.
        go, node = self.documents["structured-go"], self.documents["optimized-node"]
        self.assertGreater(node["maturity"]["current_rank"], go["maturity"]["current_rank"])
        failing = {name: doc["summary"]["failed"] for name, doc in self.documents.items()}
        self.assertGreater(failing["optimized-node"], 0)
        self.assertEqual(self.maturity("autonomous-node")["current"], "autonomous")
        self.assertGreater(failing["autonomous-node"], 0)


class ScenarioEvidenceTests(FixtureCase):
    def test_evidence_discovery_reports_concrete_sources(self):
        cases = {
            ("foundational-python", "feedback.tests.available"): ("command.test", "uv run pytest", "pyproject.toml"),
            ("structured-go", "feedback.build.available"): ("command.build", "go build ./...", "go.mod"),
            ("optimized-node", "feedback.tests.available"): ("command.test", "pnpm test", "package.json"),
            ("optimized-node", "constraints.architecture_boundaries"):
                ("config.architecture_boundaries", ".dependency-cruiser.cjs", ".dependency-cruiser.cjs"),
            ("structured-go", "context.agent_instructions"): ("file.agents_md", "AGENTS.md", "AGENTS.md"),
        }
        for (name, rule_id), (kind, value, source) in cases.items():
            with self.subTest(scenario=name, rule=rule_id):
                result = self.rule(name, rule_id)
                self.assertEqual(result["status"], "pass")
                self.assertIn({"type": kind, "value": value, "source": source}, result["evidence"])

    def test_heading_evidence_points_at_lines(self):
        result = self.rule("structured-go", "constraints.documented")
        sources = {(item["type"], item["source"], item.get("line")) for item in result["evidence"]}
        self.assertIn(("agent.instructions.constraints", "AGENTS.md", 16), sources)

    def test_unknown_is_distinct_from_fail(self):
        ambiguous = self.rule("ambiguous-policy", "constraints.architecture_boundaries")
        self.assertEqual(ambiguous["status"], "unknown")
        self.assertEqual(ambiguous["evidence"], [])
        self.assertIn("cannot be inferred safely", ambiguous["reason"])
        missing = self.rule("missing-tests", "feedback.tests.available")
        self.assertEqual(missing["status"], "fail")
        self.assertEqual(missing["missing_evidence"], ["command.test"])
        self.assertEqual(self.status("optimized-node", "constraints.architecture_boundaries"), "pass")

    def test_not_applicable(self):
        self.assertEqual(self.status("foundational-python", "feedback.build.available"), "not-applicable")
        self.assertEqual(self.status("structured-go", "feedback.build.available"), "pass")
        self.assertEqual(self.status("optimized-node", "feedback.build.available"), "pass")
        for name in SCENARIOS:
            with self.subTest(scenario=name):
                self.assertEqual(self.status(name, "context.agent_instructions.hierarchical"), "not-applicable")
                self.assertEqual(self.status(name, "constraints.mcp.no_inline_secrets"), "not-applicable")
        self.assertEqual(self.status("empty", "feedback.tests.available"), "not-applicable")

    def test_target_maturity(self):
        document = assess(self.path("structured-go"), target="autonomous")
        state = document["maturity"]
        self.assertEqual((state["current"], state["target"], state["target_met"]),
                         ("structured", "autonomous", False))
        self.assertEqual(state["target_blockers"][:2],
                         ["constraints.architecture_boundaries", "context.task_workflows"])
        met = assess(self.path("optimized-node"), target="structured")["maturity"]
        self.assertTrue(met["target_met"])
        self.assertEqual(met["target_blockers"], [])

    def test_stable_ordering_and_repeatability(self):
        for name in ("optimized-node", "ambiguous-policy"):
            with self.subTest(scenario=name):
                again = assess(self.path(name))
                self.assertEqual(json.dumps(again, sort_keys=True), json.dumps(self.documents[name], sort_keys=True))
                ids = [r["id"] for r in again["requirements"]]
                self.assertEqual(ids, sorted(ids))
                for result in again["requirements"]:
                    keys = [(i["type"], i["source"], i.get("line", 0), i["value"]) for i in result["evidence"]]
                    self.assertEqual(keys, sorted(keys))


class ScenarioExplainPlanTests(FixtureCase):
    def test_rule_explanation(self):
        document = explain_rule("context.agent_instructions", self.path("no-agent-instructions"))
        jsonschema.validate(document, SCHEMAS["readiness-explanation"])
        self.assertEqual(document["rule"]["required_from"], "structured")
        self.assertEqual(document["required_for"], ["structured", "optimized", "autonomous"])
        self.assertEqual(document["result"]["status"], "fail")
        self.assertEqual(sorted(document["result"]["missing_evidence"]), [
            "file.agents_md", "file.claude_md", "file.copilot_instructions", "file.cursor_rules", "file.gemini_md",
        ])
        self.assertTrue(document["rule"]["rationale"])
        self.assertEqual(document["rule"]["remediation"]["classification"], "automatable")

    def test_repository_explanation(self):
        document = explain_repository(self.path("ambiguous-policy"))
        jsonschema.validate(document, SCHEMAS["readiness-explanation"])
        self.assertIn("optimized is blocked by 1 required rule(s)", document["conclusion"])
        self.assertIn("constraints.architecture_boundaries", document["conclusion"])

    def test_plans(self):
        plans = {
            "no-agent-instructions": plan(self.path("no-agent-instructions")),
            "ambiguous-policy": plan(self.path("ambiguous-policy")),
            "optimized-node": plan(self.path("optimized-node"), target="optimized"),
        }
        for name, document in plans.items():
            jsonschema.validate(document, SCHEMAS["readiness-plan"])
            self.assertTrue(document["read_only"])
        steps = [s["id"] for s in plans["no-agent-instructions"]["steps"]]
        self.assertEqual(steps, ["context.agent_instructions", "context.agent_instructions.commands",
                                 "constraints.documented"])
        ambiguous = plans["ambiguous-policy"]["steps"]
        self.assertEqual([(s["id"], s["status"], s["classification"]) for s in ambiguous],
                         [("constraints.architecture_boundaries", "unknown", "human-required")])
        self.assertTrue(ambiguous[0]["decision"])
        self.assertEqual(plans["optimized-node"]["steps"], [])
        self.assertTrue(plans["optimized-node"]["maturity"]["target_met"])


if __name__ == "__main__":
    unittest.main()
