"""Remediation contract (v0.15 slice 1): classification, actions, invariants."""

from __future__ import annotations

import copy
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
from readiness_fixtures import SCENARIOS, materialize  # noqa: E402

from agentic_dev.readiness import load_spec  # noqa: E402
from agentic_dev.readiness.remediation import (  # noqa: E402
    ALLOWED, HUMAN, MAINTENANCE_GENERATORS, SAFE, SAFE_GENERATORS, UNSUPPORTED, UNSUPPORTED_REASONS,
    Context, ContractError, block_format, check_change, check_document, digest, maintenance_action, make_change,
    propose, render_block,
)


ROOT = Path(__file__).resolve().parents[1]
SPEC = load_spec()
SCHEMA = json.loads((ROOT / "schemas" / "readiness-remediation-v1.schema.json").read_text())


def snapshot(root: Path) -> dict[str, tuple]:
    state: dict[str, tuple] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        for name in dirnames + filenames:
            path = Path(dirpath) / name
            info = path.lstat()
            data = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
            state[str(path.relative_to(root))] = (info.st_mode, info.st_size, info.st_mtime_ns, data)
    return state


class RemediationCase(unittest.TestCase):
    workspace: Path

    @classmethod
    def setUpClass(cls):
        cls.workspace = Path(tempfile.mkdtemp(prefix="ready-remediation-"))
        for name in SCENARIOS:
            materialize(name, cls.workspace / name)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.workspace, ignore_errors=True)

    def item(self, document: dict, rule_id: str) -> dict:
        return next(i for i in document["remediations"] if i["rule_id"] == rule_id)

    def action(self, document: dict, change_id: str) -> dict:
        return next(a for a in document["changes"] if a["id"] == change_id)


class CatalogTests(unittest.TestCase):
    def test_every_automatable_rule_is_explicitly_handled(self):
        automatable = {rid for rid, rule in SPEC.rules.items()
                       if rule["remediation"]["classification"] == "automatable"}
        self.assertEqual(automatable, set(SAFE_GENERATORS) | set(UNSUPPORTED_REASONS))
        self.assertFalse(set(SAFE_GENERATORS) & set(UNSUPPORTED_REASONS))

    def test_safe_generators_only_target_automatable_rules(self):
        for rule_id in SAFE_GENERATORS:
            self.assertEqual(SPEC.rules[rule_id]["remediation"]["classification"], "automatable", rule_id)

    def test_upper_bound_table(self):
        self.assertEqual(ALLOWED["human-required"], {HUMAN})
        self.assertNotIn(SAFE, ALLOWED["assisted"])
        self.assertEqual(ALLOWED["automatable"], {SAFE, HUMAN, UNSUPPORTED})


class ManagedBlockTests(unittest.TestCase):
    def test_marker_formats(self):
        self.assertEqual(block_format("AGENTS.md"), "markdown")
        self.assertEqual(block_format(".cursor/rules/x.mdc"), "markdown")
        self.assertEqual(block_format(".gitignore"), "hash")
        self.assertEqual(block_format(".github/workflows/ready.yml"), "hash")
        self.assertIsNone(block_format("package.json"))

    def test_render_block_is_exact_and_stable(self):
        block = render_block("markdown", "readiness.commands", "\n\n## Commands\n- x\n\n")
        body = "## Commands\n- x\n"
        self.assertEqual(block, (
            f"<!-- agentic-dev:begin readiness.commands sha256={digest(body)} -->\n"
            f"{body}<!-- agentic-dev:end readiness.commands -->\n"
        ))
        self.assertEqual(block, render_block("markdown", "readiness.commands", body))
        hashed = render_block("hash", "readiness.secrets-ignored", ".env")
        self.assertTrue(hashed.startswith("# agentic-dev:begin readiness.secrets-ignored sha256="))
        self.assertTrue(hashed.endswith("# agentic-dev:end readiness.secrets-ignored\n"))

    def valid_action(self, **overrides) -> dict:
        content = "x\n"
        action = {
            "id": "readiness.test@AGENTS.md", "kind": "managed-block", "path": "AGENTS.md",
            "format": "markdown", "block_id": "readiness.test", "content": content,
            "content_sha256": digest(content), "prelude": None,
            "target": {"exists": False, "sha256": None, "tracked": None},
            "provenance": [{"kind": "spec", "type": "t", "value": "v", "source": "s"}],
            "owner": {"type": "remediation", "rules": ["context.readme"]},
        }
        action.update(overrides)
        return action

    def test_check_change_rejects_unsafe_changes(self):
        check_change(self.valid_action())
        bad = {
            "escape": {"path": "../outside.md", "id": "readiness.test@../outside.md"},
            "id mismatch": {"id": "readiness.other@AGENTS.md"},
            "absolute": {"path": "/etc/passwd.md"},
            "git": {"path": ".git/info/exclude", "format": "hash", "id": "readiness.test@.git/info/exclude"},
            "unnormalized": {"path": "./AGENTS.md"},
            "kind": {"kind": "rewrite-file"},
            "format": {"format": "hash"},
            "file type": {"path": "package.json"},
            "block id": {"block_id": "commands"},
            "marker injection": {"content": "<!-- agentic-dev:end readiness.test -->\n"},
            "digest": {"content_sha256": "0" * 64},
            "provenance": {"provenance": []},
        }
        for label, overrides in bad.items():
            with self.subTest(label), self.assertRaises(ContractError):
                action = self.valid_action(**overrides)
                if label == "marker injection":
                    action["content_sha256"] = digest(action["content"])
                check_change(action)


class ProposalTests(RemediationCase):
    def test_all_documents_satisfy_schema_and_invariants(self):
        for name in SCENARIOS:
            for target in ("structured", "autonomous"):
                with self.subTest(scenario=name, target=target):
                    document = propose(self.workspace / name, target=target)
                    jsonschema.validate(document, SCHEMA)
                    check_document(document, SPEC)
                    self.assertEqual(document["mode"], "preview")
                    for item in document["remediations"]:
                        self.assertIn(item["remediation_class"], ALLOWED[item["spec_classification"]])

    def test_commands_and_gitignore_are_safe_automatic_with_provenance(self):
        document = propose(self.workspace / "foundational-python", target="structured")
        commands = self.action(document, "readiness.commands@AGENTS.md")
        self.assertEqual(commands["target"], {"exists": False, "sha256": None, "tracked": False})
        self.assertEqual(commands["prelude"], "# Agent instructions\n")
        self.assertIn("- Test: `uv run pytest` (from `pyproject.toml`)", commands["content"])
        self.assertIn({"kind": "evidence", "type": "command.test", "value": "uv run pytest",
                       "source": "pyproject.toml"}, commands["provenance"])
        self.assertEqual(commands["owner"], {"type": "remediation",
                                             "rules": ["context.agent_instructions", "context.agent_instructions.commands"]})
        for rule_id in commands["owner"]["rules"]:
            self.assertEqual(self.item(document, rule_id)["change_ids"], [commands["id"]])
        ignored = self.action(document, "readiness.secrets-ignored@.gitignore")
        self.assertEqual(ignored["provenance"][0]["kind"], "spec")
        self.assertIn(".env.*\n", ignored["content"])

    def test_existing_instruction_file_is_extended_not_replaced(self):
        root = self.workspace / "ambiguous-policy"
        document = propose(root, target="autonomous")
        self.assertFalse(any(a["path"] == "AGENTS.md" and not a["target"]["exists"] for a in document["changes"]))
        claude = Path(tempfile.mkdtemp())
        try:
            materialize("foundational-python", claude)
            (claude / "CLAUDE.md").write_text("# Team notes\n")
            action = self.action(propose(claude, target="structured"), "readiness.commands@CLAUDE.md")
            self.assertTrue(action["target"]["exists"])
            self.assertIsNone(action["prelude"])
            self.assertEqual(action["target"]["sha256"], digest("# Team notes\n"))
        finally:
            shutil.rmtree(claude, ignore_errors=True)

    def test_no_facts_means_no_instruction_file_is_invented(self):
        document = propose(self.workspace / "empty", target="structured")
        item = self.item(document, "context.agent_instructions")
        self.assertEqual(item["remediation_class"], HUMAN)
        self.assertIn("no facts to document", item["reason"])
        self.assertNotIn("readiness.commands@AGENTS.md", [c["id"] for c in document["changes"]])

    def test_policy_rules_are_human_decisions_with_candidates(self):
        document = propose(self.workspace / "ambiguous-policy", target="optimized")
        boundaries = self.item(document, "constraints.architecture_boundaries")
        self.assertEqual((boundaries["status"], boundaries["remediation_class"]), ("unknown", HUMAN))
        self.assertEqual(boundaries["change_ids"], [])
        self.assertIn("which dependencies are forbidden", boundaries["decision"]["question"])
        self.assertIn("src/demo", [c["value"] for c in boundaries["decision"]["candidates"]])

    def test_assisted_rules_never_become_automatic(self):
        document = propose(self.workspace / "missing-tests", target="autonomous")
        tests = self.item(document, "feedback.tests.available")
        self.assertEqual((tests["spec_classification"], tests["remediation_class"]), ("assisted", HUMAN))

    def test_unsupported_explains_why(self):
        document = propose(self.workspace / "foundational-python", target="structured")
        locked = self.item(document, "feedback.dependencies.locked")
        self.assertEqual(locked["remediation_class"], UNSUPPORTED)
        self.assertIn("package manager", locked["reason"])
        self.assertIsNone(locked["decision"])

    def test_target_scopes_items(self):
        structured = propose(self.workspace / "foundational-python", target="structured")
        self.assertTrue(all(SPEC.rank(i["required_from"]) <= SPEC.rank("structured") for i in structured["remediations"]))
        self.assertGreater(len(propose(self.workspace / "foundational-python", target="autonomous")["remediations"]),
                           len(structured["remediations"]))
        met = propose(self.workspace / "autonomous-node", target="autonomous")
        self.assertTrue(met["maturity"]["target_met"])
        self.assertFalse([i for i in met["remediations"] if i["severity"] == "required"])

    def test_proposal_is_read_only_and_deterministic(self):
        root = self.workspace / "foundational-python"
        before = snapshot(root)
        first = propose(root, target="autonomous")
        second = propose(root, target="autonomous")
        self.assertEqual(snapshot(root), before)
        self.assertEqual(json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True))
        self.assertNotIn(str(root), json.dumps(first))


class DocumentInvariantTests(RemediationCase):
    def document(self) -> dict:
        return propose(self.workspace / "foundational-python", target="structured")

    def test_tampered_documents_are_rejected(self):
        base = self.document()

        def tamper(fn):
            document = copy.deepcopy(base)
            fn(document)
            return document

        def upgrade(doc):
            item = next(i for i in doc["remediations"] if i["spec_classification"] == "assisted")
            item.update(remediation_class=SAFE, change_ids=[doc["changes"][0]["id"]], decision=None)

        def safe_without_actions(doc):
            next(i for i in doc["remediations"] if i["remediation_class"] == SAFE)["change_ids"] = []

        def decision_with_actions(doc):
            next(i for i in doc["remediations"] if i["remediation_class"] == HUMAN)["change_ids"] = [doc["changes"][0]["id"]]

        def missing_decision(doc):
            next(i for i in doc["remediations"] if i["remediation_class"] == HUMAN)["decision"] = None

        def orphan_action(doc):
            doc["changes"].append({**doc["changes"][0], "id": "readiness.orphan@AGENTS.md", "block_id": "readiness.orphan"})

        def no_provenance(doc):
            doc["changes"][0]["provenance"] = []

        for label, fn in {
            "assisted upgraded to safe": upgrade,
            "safe without actions": safe_without_actions,
            "non-safe with actions": decision_with_actions,
            "human decision without a decision": missing_decision,
            "unreferenced change": orphan_action,
            "change without provenance": no_provenance,
            "spec classification misreported": lambda doc: doc["remediations"][0].update(spec_classification="automatable", remediation_class=SAFE),
            "unknown rule": lambda doc: doc["remediations"][0].update(rule_id="context.invented"),
        }.items():
            with self.subTest(label), self.assertRaises(ContractError):
                check_document(tamper(fn), SPEC)

    def test_schema_rejects_upgrades_too(self):
        document = self.document()
        item = next(i for i in document["remediations"] if i["spec_classification"] == "human-required")
        item.update(remediation_class=SAFE, change_ids=[document["changes"][0]["id"]], decision=None)
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(document, SCHEMA)


READINESS_WORKFLOW = """name: Agent Ready
on: [pull_request]
jobs:
  readiness:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install agentic-dev==0.15.0
      - run: agentic ready verify . --target structured
"""
WORKFLOW = ".github/workflows/agentic-readiness.yml"


class MaintenanceActionTests(RemediationCase):
    """Maintenance actions maintain readiness infrastructure. They never stand in for rules."""

    def generator(self, content: str, path: str = WORKFLOW, action_id: str = "readiness.ci-check"):
        def generate(ctx: Context):
            change = make_change(
                ctx, block_id="readiness.ci-check", path=path, content=content,
                provenance=[{"kind": "spec", "type": "agentic-dev", "value": "readiness CI check",
                             "source": "readiness-remediation-v1"}],
                owner={"type": "maintenance-action", "id": action_id},
            )
            return "Readiness CI check", "Keep readiness from regressing.", [change]
        return generate

    def propose_with(self, content: str, scenario: str = "foundational-python", **kwargs) -> dict:
        with patch.dict(MAINTENANCE_GENERATORS, {"readiness.ci-check": self.generator(content, **kwargs)}):
            return propose(self.workspace / scenario, target="optimized")

    def test_benign_ci_check_is_a_separate_safe_maintenance_action(self):
        baseline = propose(self.workspace / "foundational-python", target="optimized")
        document = self.propose_with(READINESS_WORKFLOW)
        jsonschema.validate(document, SCHEMA)
        self.assertEqual(document["maintenance_actions"], [{
            "id": "readiness.ci-check", "class": SAFE, "kind": "maintenance-action",
            "title": "Readiness CI check", "reason": "Keep readiness from regressing.",
            "source": {"type": "agentic-dev", "contract": "readiness-remediation-v1"},
            "change_ids": [f"readiness.ci-check@{WORKFLOW}"],
        }])
        change = self.action(document, f"readiness.ci-check@{WORKFLOW}")
        self.assertEqual(change["owner"], {"type": "maintenance-action", "id": "readiness.ci-check"})
        # Maintenance does not alter any rule remediation.
        self.assertEqual(document["remediations"], baseline["remediations"])
        self.assertEqual(document["summary"]["maintenance_actions"], 1)

    def test_secret_scanning_stays_assisted_and_cannot_be_smuggled_in(self):
        baseline = propose(self.workspace / "foundational-python", target="optimized")
        scanning = self.item(baseline, "constraints.secrets.scanning")
        self.assertEqual((scanning["spec_classification"], scanning["remediation_class"]), ("assisted", HUMAN))
        with self.assertRaisesRegex(ContractError, "would create readiness evidence .*ci.runs_security"):
            self.propose_with(READINESS_WORKFLOW + "      - run: gitleaks detect --source .\n")

    def test_maintenance_cannot_create_any_rule_evidence(self):
        for label, extra in {
            "tests in CI": "      - run: npm test\n",
            "lint in CI": "      - run: make check\n",
            "security scanner": "      - uses: github/codeql-action/analyze@v3\n",
        }.items():
            with self.subTest(label), self.assertRaisesRegex(ContractError, "would create readiness evidence"):
                self.propose_with(READINESS_WORKFLOW + extra)

    def test_maintenance_cannot_grant_credentials_permissions_or_install_tools(self):
        for label, extra in {
            "credential": "        env:\n          TOKEN: ${{ secrets.DEPLOY_TOKEN }}\n",
            "permission": "    permissions:\n      contents: write\n",
            "cloud credentials": "      - uses: aws-actions/configure-aws-credentials@v4\n",
            "installer": "      - run: curl -sSL https://example.invalid/install.sh | sh\n",
            "arbitrary pip install": "      - run: pip install semgrep\n",
            "unpinned agentic-dev": "      - run: pip install agentic-dev\n",
        }.items():
            with self.subTest(label), self.assertRaisesRegex(ContractError, "must not contain"):
                self.propose_with(READINESS_WORKFLOW + extra)

    def test_maintenance_targets_are_allowlisted(self):
        with self.assertRaisesRegex(ContractError, "not an allowlisted maintenance target"):
            self.propose_with(READINESS_WORKFLOW, path=".github/workflows/other.yml")
        with self.assertRaisesRegex(ContractError, "not an allowlisted maintenance target"):
            self.propose_with("# notes\n", path="AGENTS.md")

    def test_maintenance_cannot_reference_or_share_with_rules(self):
        document = self.propose_with(READINESS_WORKFLOW)
        remediation_change = next(c for c in document["changes"] if c["owner"]["type"] == "remediation")
        safe_rule = next(r for r in document["remediations"] if r["remediation_class"] == SAFE)
        maintenance_change = f"readiness.ci-check@{WORKFLOW}"

        def tamper(fn):
            doc = copy.deepcopy(document)
            fn(doc)
            return doc

        cases = {
            "maintenance claims a remediation change":
                lambda d: d["maintenance_actions"][0]["change_ids"].append(remediation_change["id"]),
            "rule claims a maintenance change":
                lambda d: next(r for r in d["remediations"] if r["rule_id"] == safe_rule["rule_id"])["change_ids"]
                .append(maintenance_change),
            "maintenance change owned by rules":
                lambda d: self.action(d, maintenance_change).update(owner={"type": "remediation", "rules": [safe_rule["rule_id"]]}),
            "not attributed to agentic-dev":
                lambda d: d["maintenance_actions"][0].update(source={"type": "agent-ready", "contract": "x"}),
            "downgraded class":
                lambda d: d["maintenance_actions"][0].update({"class": HUMAN}),
        }
        for label, fn in cases.items():
            with self.subTest(label), self.assertRaises(ContractError):
                check_document(tamper(fn), SPEC)
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(tamper(lambda d: d["maintenance_actions"][0].update(rule_id="feedback.ci.tests")), SCHEMA)

    def test_constructor_shape(self):
        self.assertEqual(maintenance_action("readiness.x", title="t", reason="r", change_ids=["b", "a"])["change_ids"],
                         ["a", "b"])


if __name__ == "__main__":
    unittest.main()
