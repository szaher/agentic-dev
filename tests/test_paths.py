from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentic_dev.paths import (
    config_dir,
    migrate_legacy_config,
    prepare_runtime_state,
)


class PathMigrationTests(unittest.TestCase):
    def test_default_legacy_config_is_copied_without_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            legacy = root / "agentic-dev-env"
            current = root / "agentic-dev"
            legacy.mkdir()
            current.mkdir()

            (legacy / "capabilities.json").write_text('{"enabled":{"secret-scan":{}}}\n')
            (legacy / "trust.json").write_text('{"source":"legacy"}\n')
            (current / "trust.json").write_text('{"source":"current"}\n')
            (legacy / "providers" / "demo" / "source").mkdir(parents=True)
            (legacy / "providers" / "demo" / "source" / "agentic-provider.json").write_text(
                '{"schema_version":"1","name":"demo","version":"1","description":"demo"}\n'
            )
            (legacy / "python").mkdir()
            (legacy / "python" / "old-package.py").write_text("legacy\n")

            with patch.dict(os.environ, {}, clear=True), \
                 patch("agentic_dev.paths.legacy_default_config_dir", return_value=legacy), \
                 patch("agentic_dev.paths.default_config_dir", return_value=current):
                result = migrate_legacy_config()

                self.assertTrue(result["performed"])
                self.assertTrue((current / "capabilities.json").exists())
                self.assertEqual(
                    json.loads((current / "trust.json").read_text())["source"],
                    "current",
                )
                self.assertTrue(
                    (current / "providers" / "demo" / "source" / "agentic-provider.json").exists()
                )
                self.assertFalse((current / "python").exists())
                self.assertTrue(legacy.exists())
                self.assertTrue((current / ".migration-from-agentic-dev-env-v1.json").exists())

                again = migrate_legacy_config()
                self.assertFalse(again["performed"])

    def test_legacy_config_environment_variable_remains_supported(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {}, clear=True):
                os.environ["AGENTIC_DEV_ENV_CONFIG_DIR"] = tmp
                result = prepare_runtime_state()
                self.assertFalse(result["performed"])
                self.assertEqual(os.environ["AGENTIC_DEV_CONFIG_DIR"], tmp)
                self.assertEqual(config_dir(), Path(tmp))


if __name__ == "__main__":
    unittest.main()
