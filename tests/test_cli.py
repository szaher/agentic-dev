from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentic_dev.cli import _helper_script, build_parser
from agentic_dev import integrations


class CliIntegrationTests(unittest.TestCase):
    def test_skills_accept_pi_and_all_targets(self):
        parser = build_parser()
        pi = parser.parse_args(["skills", "suggest", ".", "--target", "pi", "--no-prompt"])
        self.assertEqual(pi.target, "pi")
        all_targets = parser.parse_args(["skills", "add", "debugging", "--target", "all"])
        self.assertEqual(all_targets.target, "all")

    def test_repo_init_accepts_pi_target(self):
        parser = build_parser()
        args = parser.parse_args(["repo", "init", ".", "--skills-target", "pi", "--check"])
        self.assertEqual(args.skills_target, "pi")
        self.assertTrue(args.check)

    def test_repo_inspect_and_doctor_json_parse(self):
        parser = build_parser()
        inspect = parser.parse_args(["repo", "inspect", ".", "--task", "review API", "--json"])
        self.assertEqual(inspect.repo_command, "inspect")
        self.assertTrue(inspect.json)
        self.assertEqual(inspect.task, "review API")
        doctor = parser.parse_args(["doctor", "--json"])
        self.assertTrue(doctor.json)



    @patch("agentic_dev.cli.shutil.which", return_value=None)
    def test_bundled_helper_resolution(self, _which):
        with tempfile.TemporaryDirectory() as tmp:
            prefix = Path(tmp)
            helper = prefix / "share" / "agentic-dev" / "scripts" / "agentic-repo-init.sh"
            helper.parent.mkdir(parents=True)
            helper.write_text("#!/usr/bin/env bash\n")
            with patch("agentic_dev.cli.sys.prefix", str(prefix)):
                self.assertEqual(_helper_script("agentic-repo-init.sh"), helper)

    def test_metrics_commands_parse(self):
        parser = build_parser()
        enabled = parser.parse_args(["metrics", "enable"])
        self.assertEqual(enabled.metrics_command, "enable")

        summary = parser.parse_args(["metrics", "summary", "--since", "7d", "--path", "."])
        self.assertEqual(summary.since, "7d")
        self.assertEqual(summary.path, ".")

        event = parser.parse_args([
            "metrics", "record", "agentflow.stage",
            "--field", "stage=review",
            "--field", "outcome=passed",
            "--session-id", "run-1",
        ])
        self.assertEqual(event.event, "agentflow.stage")
        self.assertEqual(event.field, ["stage=review", "outcome=passed"])
        self.assertEqual(event.session_id, "run-1")

    def test_provider_and_remote_commands_parse(self):
        parser = build_parser()
        add_provider = parser.parse_args([
            "providers", "add", "./provider", "--sha256", "a" * 64
        ])
        self.assertEqual(add_provider.providers_command, "add")
        self.assertEqual(add_provider.source, "./provider")

        update = parser.parse_args(["update", "--yes"])
        self.assertTrue(update.yes)

        remote = parser.parse_args([
            "remote", "add", "lab", "lab.example.test",
            "--user", "saad", "--port", "2222",
        ])
        self.assertEqual(remote.remote_command, "add")
        self.assertEqual(remote.name, "lab")
        self.assertEqual(remote.port, 2222)

    def test_integrations_commands_parse(self):
        parser = build_parser()
        status = parser.parse_args(["integrations", "status"])
        self.assertEqual(status.integrations_command, "status")
        install = parser.parse_args(["integrations", "install", "all"])
        self.assertEqual(install.target, "all")

    @patch("agentic_dev.integrations.install_pi", return_value=0)
    @patch("agentic_dev.integrations.install_codex", return_value=0)
    @patch("agentic_dev.integrations.install_claude", return_value=0)
    @patch("agentic_dev.integrations.shutil.which")
    def test_install_all_skips_missing_agents(self, which, claude, codex, pi):
        which.side_effect = lambda name: "/bin/" + name if name in {"claude", "pi"} else None
        self.assertEqual(integrations.install("all"), 0)
        claude.assert_called_once()
        codex.assert_not_called()
        pi.assert_called_once()


if __name__ == "__main__":
    unittest.main()
