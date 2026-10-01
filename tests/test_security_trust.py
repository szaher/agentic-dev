from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentic_dev_env import capabilities
from agentic_dev_env.trust import (
    check,
    current_profile_name,
    define_profile,
    document,
    set_current,
)


class SecurityTrustTests(unittest.TestCase):
    def make_repo(self) -> Path:
        root = Path(tempfile.mkdtemp())
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        return root

    def test_safe_profile_allows_local_security_scan(self):
        allowed, missing, profile = check(["repo.read", "security.scan", "secret.scan"])
        self.assertTrue(allowed)
        self.assertEqual(missing, [])
        self.assertEqual(profile.name, "safe")

    def test_safe_profile_blocks_authenticated_browser(self):
        allowed, missing, profile = check(["browser.authenticated"])
        self.assertFalse(allowed)
        self.assertIn("browser.authenticated", missing)
        self.assertEqual(profile.name, "safe")

    def test_custom_profile_round_trip(self):
        with tempfile.TemporaryDirectory() as config:
            with patch.dict(os.environ, {"AGENTIC_DEV_ENV_CONFIG_DIR": config}):
                define_profile("review-only", ["repo.read", "security.scan"], "Review profile")
                set_current("review-only")
                self.assertEqual(current_profile_name(), "review-only")
                data = document()
                self.assertTrue(data["profiles"]["review-only"]["selected"])
                self.assertFalse(data["profiles"]["review-only"]["builtin"])

    def test_repo_profile_is_local_excluded(self):
        root = self.make_repo()
        with tempfile.TemporaryDirectory() as config:
            with patch.dict(os.environ, {"AGENTIC_DEV_ENV_CONFIG_DIR": config}):
                set_current("development", root=root)
                self.assertEqual(current_profile_name(root), "development")
                exclude = subprocess.run(
                    ["git", "-C", str(root), "rev-parse", "--git-path", "info/exclude"],
                    check=True, capture_output=True, text=True,
                ).stdout.strip()
                p = Path(exclude)
                if not p.is_absolute():
                    p = root / p
                self.assertIn("/.agentic/", p.read_text())

    def test_security_suggestions_detect_source_and_iac(self):
        root = self.make_repo()
        (root / "main.py").write_text("print('hello')\n")
        (root / "main.tf").write_text('resource "x" "y" {}\n')
        context, recs = capabilities.suggest_for_repo(root, "security review before merge")
        names = {r.name for r in recs}
        self.assertIn("secret-scan", names)
        self.assertIn("dependency-vulnerability", names)
        self.assertIn("sast", names)
        self.assertIn("iac-misconfiguration", names)
        self.assertIn("sbom", names)

    @patch("agentic_dev_env.capabilities.shutil.which")
    @patch("agentic_dev_env.capabilities._capture")
    def test_trivy_result_is_normalized(self, capture, which):
        which.side_effect = lambda name: "/usr/bin/trivy" if name == "trivy" else None
        capture.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=json.dumps({
                "Results": [{
                    "Target": ".",
                    "Secrets": [{"RuleID": "x"}],
                    "Vulnerabilities": [{"VulnerabilityID": "CVE-x"}],
                }]
            }),
            stderr="",
        )
        root = self.make_repo()
        result = capabilities.run_capability("secret-scan", root)
        self.assertEqual(result["document_type"], "agentic.capability-result")
        self.assertTrue(result["success"])
        self.assertEqual(result["finding_count"], 2)
        self.assertEqual(result["trust_profile"], "safe")

    @patch("agentic_dev_env.capabilities.shutil.which")
    def test_sast_is_denied_under_safe_profile_before_execution(self, which):
        which.return_value = "/usr/bin/semgrep"
        root = self.make_repo()
        with self.assertRaises(PermissionError):
            capabilities.run_capability("sast", root)

    @patch("agentic_dev_env.capabilities._run", return_value=0)
    @patch("agentic_dev_env.capabilities.shutil.which")
    def test_enable_sast_under_development(self, which, run):
        which.side_effect = lambda name: "/usr/bin/semgrep" if name == "semgrep" else None
        with tempfile.TemporaryDirectory() as config:
            with patch.dict(os.environ, {"AGENTIC_DEV_ENV_CONFIG_DIR": config}):
                rc = capabilities.enable("sast", profile="development")
                self.assertEqual(rc, 0)
                state = capabilities.status()["sast"]
                self.assertTrue(state["enabled"])
                self.assertEqual(state["configuration"]["trust_profile"], "development")


if __name__ == "__main__":
    unittest.main()
