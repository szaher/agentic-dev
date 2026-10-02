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

import jsonschema

sys.path.insert(0, str(Path(__file__).resolve().parent))
from readiness_fixtures import SCENARIOS, materialize  # noqa: E402

from agentic_dev.readiness import load_spec  # noqa: E402
from agentic_dev.readiness.remediation import (  # noqa: E402
    ALLOWED, HUMAN, SAFE, SAFE_GENERATORS, UNSUPPORTED, UNSUPPORTED_REASONS,
    ContractError, block_format, check_action, check_document, digest, propose, render_block,
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
        return next(i for i in document["items"] if i["rule_id"] == rule_id)

    def action(self, document: dict, action_id: str) -> dict:
        return next(a for a in document["actions"] if a["id"] == action_id)


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
        }
        action.update(overrides)
        return action

    def test_check_action_rejects_unsafe_actions(self):
        check_action(self.valid_action())
        bad = {
            "escape": {"path": "../outside.md"},
            "absolute": {"path": "/etc/passwd.md"},
            "git": {"path": ".git/info/exclude", "format": "hash"},
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
                check_action(action)


class ProposalTests(RemediationCase):
    def test_all_documents_satisfy_schema_and_invariants(self):
        for name in SCENARIOS:
            for target in ("structured", "autonomous"):
                with self.subTest(scenario=name, target=target):
                    document = propose(self.workspace / name, target=target)
                    jsonschema.validate(document, SCHEMA)
                    check_document(document)
                    self.assertEqual(document["mode"], "preview")
                    for item in document["items"]:
                        self.assertIn(item["remediation_class"], ALLOWED[item["spec_classification"]])

    def test_commands_and_gitignore_are_safe_automatic_with_provenance(self):
        document = propose(self.workspace / "foundational-python", target="structured")
        commands = self.action(document, "readiness.commands@AGENTS.md")
        self.assertEqual(commands["target"], {"exists": False, "sha256": None, "tracked": False})
        self.assertEqual(commands["prelude"], "# Agent instructions\n")
        self.assertIn("- Test: `uv run pytest` (from `pyproject.toml`)", commands["content"])
        self.assertIn({"kind": "evidence", "type": "command.test", "value": "uv run pytest",
                       "source": "pyproject.toml"}, commands["provenance"])
        self.assertEqual(commands["rules"], ["context.agent_instructions", "context.agent_instructions.commands"])
        for rule_id in commands["rules"]:
            self.assertEqual(self.item(document, rule_id)["action_ids"], [commands["id"]])
        ignored = self.action(document, "readiness.secrets-ignored@.gitignore")
        self.assertEqual(ignored["provenance"][0]["kind"], "spec")
        self.assertIn(".env.*\n", ignored["content"])

    def test_existing_instruction_file_is_extended_not_replaced(self):
        root = self.workspace / "ambiguous-policy"
        document = propose(root, target="autonomous")
        self.assertFalse(any(a["path"] == "AGENTS.md" and not a["target"]["exists"] for a in document["actions"]))
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
        self.assertEqual(document["actions"],
                         [a for a in document["actions"] if a["id"] != "readiness.commands@AGENTS.md"])

    def test_policy_rules_are_human_decisions_with_candidates(self):
        document = propose(self.workspace / "ambiguous-policy", target="optimized")
        boundaries = self.item(document, "constraints.architecture_boundaries")
        self.assertEqual((boundaries["status"], boundaries["remediation_class"]), ("unknown", HUMAN))
        self.assertEqual(boundaries["action_ids"], [])
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
        self.assertTrue(all(SPEC.rank(i["required_from"]) <= SPEC.rank("structured") for i in structured["items"]))
        self.assertGreater(len(propose(self.workspace / "foundational-python", target="autonomous")["items"]),
                           len(structured["items"]))
        met = propose(self.workspace / "autonomous-node", target="autonomous")
        self.assertTrue(met["maturity"]["target_met"])
        self.assertFalse([i for i in met["items"] if i["severity"] == "required"])

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
            item = next(i for i in doc["items"] if i["spec_classification"] == "assisted")
            item.update(remediation_class=SAFE, action_ids=[doc["actions"][0]["id"]], decision=None)

        def safe_without_actions(doc):
            next(i for i in doc["items"] if i["remediation_class"] == SAFE)["action_ids"] = []

        def decision_with_actions(doc):
            next(i for i in doc["items"] if i["remediation_class"] == HUMAN)["action_ids"] = [doc["actions"][0]["id"]]

        def missing_decision(doc):
            next(i for i in doc["items"] if i["remediation_class"] == HUMAN)["decision"] = None

        def orphan_action(doc):
            doc["actions"].append({**doc["actions"][0], "id": "readiness.orphan@AGENTS.md", "block_id": "readiness.orphan"})

        def no_provenance(doc):
            doc["actions"][0]["provenance"] = []

        for label, fn in {
            "assisted upgraded to safe": upgrade,
            "safe without actions": safe_without_actions,
            "non-safe with actions": decision_with_actions,
            "human decision without a decision": missing_decision,
            "unreferenced action": orphan_action,
            "action without provenance": no_provenance,
        }.items():
            with self.subTest(label), self.assertRaises(ContractError):
                check_document(tamper(fn))

    def test_schema_rejects_upgrades_too(self):
        document = self.document()
        item = next(i for i in document["items"] if i["spec_classification"] == "human-required")
        item.update(remediation_class=SAFE, action_ids=[document["actions"][0]["id"]], decision=None)
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(document, SCHEMA)


if __name__ == "__main__":
    unittest.main()
