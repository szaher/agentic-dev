from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import jsonschema

from agentic_dev_env import capabilities
from agentic_dev_env.providers import (
    add_provider, installed, migrate, remove_provider, verify_provider,
)
from agentic_dev_env.skills import get_skill, skill_content


ROOT = Path(__file__).resolve().parents[1]


class ProviderEcosystemTests(unittest.TestCase):
    def make_provider(self, root: Path) -> Path:
        source = root / "provider"
        (source / "skills" / "demo").mkdir(parents=True)
        (source / "scripts").mkdir(parents=True)
        (source / "skills" / "demo" / "SKILL.md").write_text(
            "---\nname: provider-demo\ndescription: Provider demo\n---\n\n# Demo\n"
        )
        script = source / "scripts" / "capability.py"
        script.write_text(
            "import json, sys\n"
            "print(json.dumps({'provider': 'demo-provider', 'repo': sys.argv[1]}))\n"
        )
        migration = source / "scripts" / "migrate.py"
        migration.write_text(
            "import os\n"
            "from pathlib import Path\n"
            "state = Path(os.environ['AGENTIC_PROVIDER_STATE_DIR'])\n"
            "state.mkdir(parents=True, exist_ok=True)\n"
            "(state / 'migration-ran.txt').write_text('ok')\n"
        )
        manifest = {
            "schema_version": "1",
            "name": "demo-provider",
            "version": "1.0.0",
            "description": "Provider test fixture",
            "compatibility": {
                "agentic": ">=0.11.0,<1.0.0",
                "platforms": ["macos", "linux", "wsl", "windows"],
            },
            "requires": {"executables": ["python3"]},
            "skills": [{
                "name": "provider-demo",
                "description": "Provider skill",
                "category": "provider",
                "path": "skills/demo",
                "signals": ["language:python"],
                "task_keywords": ["provider demo"],
                "priority": 1,
            }],
            "capabilities": [{
                "name": "provider-demo-capability",
                "category": "provider",
                "provider": "demo-provider",
                "description": "Run demo provider capability",
                "risk": "Executes a provider-owned local command.",
                "targets": ["local"],
                "required_permissions": ["repo.read"],
                "command": ["python3", "scripts/capability.py", "{repo}"],
            }],
            "migrations": [{
                "version": "1",
                "command": ["python3", "scripts/migrate.py"],
            }],
        }
        (source / "agentic-provider.json").write_text(json.dumps(manifest, indent=2))
        return source

    def config(self):
        return tempfile.TemporaryDirectory()

    def test_manifest_schema_and_provider_contributions(self):
        with self.config() as config, tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"AGENTIC_DEV_ENV_CONFIG_DIR": config}):
                source = self.make_provider(Path(tmp))
                manifest = json.loads((source / "agentic-provider.json").read_text())
                schema = json.loads((ROOT / "schemas/provider-manifest-v1.schema.json").read_text())
                jsonschema.validate(manifest, schema)

                record = add_provider(str(source))
                self.assertEqual(record["name"], "demo-provider")
                self.assertTrue(verify_provider("demo-provider")["valid"])
                self.assertEqual(installed()[0]["version"], "1.0.0")

                skill = get_skill("provider-demo")
                self.assertEqual(skill.provider, "demo-provider")
                self.assertIn("# Demo", skill_content("provider-demo"))

                names = {item.name for item in capabilities.list_capabilities()}
                self.assertIn("provider-demo-capability", names)

                self.assertEqual(
                    capabilities.enable("provider-demo-capability", profile="safe"),
                    0,
                )
                repo = Path(tmp) / "repo"
                repo.mkdir()
                result = capabilities.run_capability(
                    "provider-demo-capability", repo, profile="safe"
                )
                self.assertTrue(result["success"])
                self.assertEqual(result["result"]["provider"], "demo-provider")
                self.assertEqual(result["result"]["repo"], str(repo.resolve()))

                migration_results = migrate("demo-provider", yes=True)
                self.assertEqual(migration_results[0]["returncode"], 0)
                self.assertTrue(verify_provider("demo-provider")["valid"])
                self.assertTrue(
                    (Path(config) / "providers" / "demo-provider" / "state" / "migration-ran.txt").exists()
                )

                remove_provider("demo-provider")
                self.assertEqual(installed(), [])

    def test_tamper_detection(self):
        with self.config() as config, tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"AGENTIC_DEV_ENV_CONFIG_DIR": config}):
                source = self.make_provider(Path(tmp))
                record = add_provider(str(source))
                installed_source = Path(config) / "providers" / record["name"] / "source"
                (installed_source / "skills" / "demo" / "SKILL.md").write_text("tampered\n")
                verification = verify_provider("demo-provider")
                self.assertFalse(verification["valid"])
                self.assertIn("content digest changed", verification["reasons"])

    def test_digest_pin_rejects_wrong_source(self):
        with self.config() as config, tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"AGENTIC_DEV_ENV_CONFIG_DIR": config}):
                source = self.make_provider(Path(tmp))
                with self.assertRaises(ValueError):
                    add_provider(str(source), expected_sha256="0" * 64)

    def test_migrations_require_explicit_yes(self):
        with self.config() as config, tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"AGENTIC_DEV_ENV_CONFIG_DIR": config}):
                source = self.make_provider(Path(tmp))
                add_provider(str(source))
                with self.assertRaises(PermissionError):
                    migrate("demo-provider", yes=False)


if __name__ == "__main__":
    unittest.main()
