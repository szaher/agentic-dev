"""The live Codex probe must fail closed when any evidence is missing."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from shutil import copytree

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from probe_codex_exec_permissions import evaluate, recipe  # noqa: E402
from verify_codex_exec_evidence import verify_bundle  # noqa: E402


class CodexExecProbeTests(unittest.TestCase):
    def setUp(self):
        self.attempts = {
            "inside": "write_succeeded",
            "outside": "PermissionError: denied",
            "symlink": "PermissionError: denied",
            "tmpdir": "PermissionError: denied",
            "escalation": "PermissionError: denied",
            "hostname": "gaierror: denied",
            "numeric_ip": "PermissionError: [Errno 1] Operation not permitted",
        }
        self.side_effects = {
            "inside": True,
            "inside_matches_nonce": True,
            "outside": False,
            "symlink": False,
            "tmpdir": False,
            "escalation": False,
            "payload_unchanged": True,
            "project_config_unchanged": True,
            "repository_unchanged": False,
        }
        self.controls = {"hostname": "connected", "numeric_ip": "connected"}

    def checks(self, mode="workspace-write", *, observed=True, approval=False):
        return evaluate(
            mode,
            self.attempts if observed else None,
            self.side_effects,
            self.controls,
            True,
            approval,
            0,
        )

    def test_implementer_requires_observed_allowed_and_denied_effects(self):
        self.assertTrue(all(self.checks().values()))
        self.side_effects["outside"] = True
        self.assertFalse(self.checks()["outside_write_denied"])
        self.side_effects["outside"] = False
        self.attempts["numeric_ip"] = "connected"
        self.assertFalse(self.checks()["outbound_ip_denied"])

    def test_missing_tool_output_or_host_control_blocks_claim(self):
        self.assertFalse(self.checks(observed=False)["payload_command_observed"])
        self.controls["hostname"] = "gaierror"
        self.assertFalse(self.checks()["host_hostname_reachable"])

    def test_approval_event_blocks_no_escalation_claim(self):
        self.assertFalse(self.checks(approval=True)["escalation_denied"])

    def test_reviewer_requires_clean_repository_and_denied_inside_write(self):
        self.attempts["inside"] = "PermissionError: denied"
        self.side_effects["inside"] = False
        self.side_effects["inside_matches_nonce"] = False
        self.side_effects["repository_unchanged"] = True
        self.assertTrue(all(self.checks("read-only").values()))
        self.side_effects["repository_unchanged"] = False
        self.assertFalse(self.checks("read-only")["repository_unchanged"])

    def test_recipe_digest_ignores_disposable_workspace_path(self):
        host = {
            "entrypoint": {"path": "/codex.js", "digest": "sha256:entry"},
            "executable": {"path": "/codex", "digest": "sha256:binary"},
        }
        first = recipe("/codex", "workspace-write", Path("/one"), host)
        second = recipe("/codex", "workspace-write", Path("/two"), host)
        self.assertEqual(first["recipe_digest"], second["recipe_digest"])
        host["executable"]["digest"] = "sha256:changed"
        changed = recipe("/codex", "workspace-write", Path("/one"), host)
        self.assertNotEqual(first["recipe_digest"], changed["recipe_digest"])

    def test_committed_evidence_and_transcript_integrity(self):
        bundle = (
            Path(__file__).resolve().parents[1]
            / "evidence/codex/0.154.0-darwin-arm64"
        )
        verify_bundle(bundle)
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "bundle"
            copytree(bundle, copied)
            with (copied / "read-only.jsonl").open("a") as stream:
                stream.write("{}\n")
            with self.assertRaisesRegex(ValueError, "digest mismatch"):
                verify_bundle(copied)


if __name__ == "__main__":
    unittest.main()
