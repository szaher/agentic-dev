from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentic_dev_env import providers
from agentic_dev_env.lifecycle import update_status
from agentic_dev_env.migrations import migrate, state
from agentic_dev_env.remotes import add as add_remote, document as remote_document, execute as remote_exec, inspect as remote_inspect
from agentic_dev_env.skills import activate, load_registry, skill_content
from agentic_dev_env.trust import define_profile


class ProviderLifecycleTests(unittest.TestCase):
    def config(self):
        return tempfile.TemporaryDirectory()

    def provider_fixture(self, root: Path) -> Path:
        skill = root / "skills" / "external-review" / "SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text(
            "---\nname: external-review\ndescription: External review workflow.\n---\n\n# Review\n"
        )
        digest = hashlib.sha256(skill.read_bytes()).hexdigest()
        manifest = {
            "schema_version": "1",
            "name": "demo-provider",
            "version": "1.2.3",
            "description": "Demo provider",
            "compatibility": {"agentic_min": "0.1.0"},
            "skills": [{
                "name": "external-review",
                "path": "skills/external-review/SKILL.md",
                "description": "External review workflow.",
                "category": "workflow",
                "task_keywords": ["external review"],
                "sha256": digest,
            }],
            "capabilities": [{
                "name": "provider-echo",
                "description": "Print provider output",
                "category": "demo",
                "required_permissions": ["repo.read"],
                "command": ["printf", "provider-ok"],
            }],
        }
        path = root / "provider.json"
        path.write_text(json.dumps(manifest))
        return path

    def test_provider_add_integrates_external_skill_and_capability(self):
        with self.config() as cfg, tempfile.TemporaryDirectory() as fixture, tempfile.TemporaryDirectory() as repo:
            with patch.dict(os.environ, {"AGENTIC_DEV_ENV_CONFIG_DIR": cfg}):
                manifest = self.provider_fixture(Path(fixture))
                installed = providers.add_provider(manifest)
                self.assertEqual(installed["providers"][0]["name"], "demo-provider")
                self.assertFalse(installed["providers"][0]["signed"])

                names = {skill.name for skill in load_registry()}
                self.assertIn("external-review", names)
                self.assertIn("# Review", skill_content("external-review"))

                subprocess.run(["git", "init", "-q", repo], check=True)
                paths = activate(Path(repo), ["external-review"], target="claude")
                self.assertTrue((paths[0] / "SKILL.md").exists())

                result = providers.run_provider_capability(
                    "demo-provider", "provider-echo", [], path=repo, profile="safe"
                )
                self.assertTrue(result["success"])
                self.assertIn("provider-ok", result["stdout"])

    def test_provider_hash_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as fixture:
            manifest = self.provider_fixture(Path(fixture))
            data = json.loads(manifest.read_text())
            data["skills"][0]["sha256"] = "0" * 64
            manifest.write_text(json.dumps(data))
            with self.assertRaises(ValueError):
                providers.load_manifest(manifest)

    def test_provider_path_traversal_name_is_rejected(self):
        with tempfile.TemporaryDirectory() as fixture:
            manifest = self.provider_fixture(Path(fixture))
            data = json.loads(manifest.read_text())
            data["name"] = "../escape"
            manifest.write_text(json.dumps(data))
            with self.assertRaises(ValueError):
                providers.load_manifest(manifest)

    @patch("agentic_dev_env.providers.shutil.which", return_value=None)
    def test_declared_signature_requires_minisign(self, which):
        with tempfile.TemporaryDirectory() as fixture:
            manifest = self.provider_fixture(Path(fixture))
            sig = Path(fixture) / "provider.minisig"
            sig.write_text("fake")
            data = json.loads(manifest.read_text())
            data["metadata"] = {
                "signature": {
                    "type": "minisign",
                    "public_key": "RWQfake",
                    "file": "provider.minisig",
                }
            }
            manifest.write_text(json.dumps(data))
            with self.assertRaises(ValueError):
                providers.add_provider(manifest)

    def test_migration_state_initializes_schema(self):
        with self.config() as cfg:
            with patch.dict(os.environ, {"AGENTIC_DEV_ENV_CONFIG_DIR": cfg}):
                self.assertEqual(state()["schema_version"], 0)
                result = migrate()
                self.assertEqual(result["schema_version"], 1)
                self.assertEqual(state()["schema_version"], 1)

    def test_update_status_without_install_metadata_is_safe(self):
        with self.config() as cfg:
            with patch.dict(os.environ, {"AGENTIC_DEV_ENV_CONFIG_DIR": cfg}):
                result = update_status()
                self.assertFalse(result["source_available"])
                self.assertIsNone(result["update_available"])

    def test_remote_profile_storage_and_permissions(self):
        with self.config() as cfg:
            with patch.dict(os.environ, {"AGENTIC_DEV_ENV_CONFIG_DIR": cfg}):
                add_remote("dev", "example.test", user="saad", port=2222, path="/srv/repo")
                doc = remote_document()
                self.assertEqual(doc["remotes"][0]["name"], "dev")
                self.assertEqual(doc["remotes"][0]["port"], 2222)

                with self.assertRaises(PermissionError):
                    remote_inspect("dev", profile="safe")
                with self.assertRaises(PermissionError):
                    remote_exec("dev", "git status", profile="development")

                define_profile("remote-runner", ["remote.exec"], "Explicit remote command execution")
                with patch("agentic_dev_env.remotes.subprocess.run") as run:
                    run.return_value = subprocess.CompletedProcess(
                        args=[], returncode=0, stdout="ok\n", stderr=""
                    )
                    result = remote_exec("dev", "git status", profile="remote-runner")
                    self.assertTrue(result["success"])
                    argv = run.call_args.args[0]
                    self.assertIn("BatchMode=yes", argv)
                    self.assertIn("saad@example.test", argv)


if __name__ == "__main__":
    unittest.main()
