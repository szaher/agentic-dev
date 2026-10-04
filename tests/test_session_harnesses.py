from __future__ import annotations

import subprocess
import unittest
from unittest.mock import patch

from agentic_dev.session_harnesses import inspect_harness


class HarnessPermissionFactsTests(unittest.TestCase):
    def inspect(self, version: str, platform: str = "Darwin") -> dict:
        with (
            patch(
                "agentic_dev.session_harnesses.shutil.which", return_value="/test/codex"
            ),
            patch(
                "agentic_dev.session_harnesses.subprocess.run",
                return_value=subprocess.CompletedProcess(
                    ["codex", "--version"], 0, version, ""
                ),
            ),
            patch("agentic_dev.session_harnesses.system", return_value=platform),
        ):
            return inspect_harness("codex")

    def test_probe_identity_requires_exact_version_and_platform(self):
        measured = self.inspect("codex-cli 0.154.0")
        fact = measured["permissions"]["filesystem"]["workspace-write"]
        self.assertEqual(fact["probe_id"], "macos-codex-0.154.0-2026-10-04")
        self.assertEqual(fact["status"], "unknown")
        self.assertIsNone(
            self.inspect("codex-cli 0.155.0")["permissions"]["filesystem"][
                "workspace-write"
            ]["probe_id"]
        )
        self.assertIsNone(
            self.inspect("codex-cli 0.154.0", "Linux")["permissions"]["filesystem"][
                "workspace-write"
            ]["probe_id"]
        )

    def test_unavailable_harness_has_no_positive_claim(self):
        with patch("agentic_dev.session_harnesses.shutil.which", return_value=None):
            fact = inspect_harness("pi")
        self.assertFalse(fact["available"])
        self.assertEqual(fact["permissions"]["network"]["off"]["status"], "unknown")
        self.assertIsNone(fact["permissions"]["network"]["off"]["probe_id"])

    def test_claude_probe_id_is_invalidated_by_update(self):
        def inspect(version: str) -> dict:
            with (
                patch(
                    "agentic_dev.session_harnesses.shutil.which",
                    return_value="/test/claude",
                ),
                patch(
                    "agentic_dev.session_harnesses.subprocess.run",
                    return_value=subprocess.CompletedProcess(
                        ["claude", "--version"], 0, version, ""
                    ),
                ),
                patch("agentic_dev.session_harnesses.system", return_value="Darwin"),
            ):
                return inspect_harness("claude")

        fact = inspect("2.1.289 (Claude Code)")["permissions"]["filesystem"][
            "workspace-write"
        ]
        self.assertEqual(fact["probe_id"], "macos-claude-2.1.289-2026-10-04")
        self.assertEqual(fact["status"], "unknown")
        stale = inspect("2.1.290 (Claude Code)")["permissions"]["filesystem"][
            "workspace-write"
        ]
        self.assertIsNone(stale["probe_id"])


if __name__ == "__main__":
    unittest.main()
