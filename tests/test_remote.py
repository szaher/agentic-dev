from __future__ import annotations

import json
import os
import tempfile
import unittest
from unittest.mock import patch

from agentic_dev_env.remote import add, get, list_profiles, remove, status


class RemoteProfileTests(unittest.TestCase):
    def test_profile_round_trip_without_secrets(self):
        with tempfile.TemporaryDirectory() as config:
            with patch.dict(os.environ, {"AGENTIC_DEV_ENV_CONFIG_DIR": config}):
                profile = add(
                    "gpu-lab", "gpu.example.test",
                    user="saad", port=2222,
                    identity_file="~/.ssh/id_ed25519",
                    workdir="/srv/project",
                )
                self.assertEqual(profile["user"], "saad")
                self.assertNotIn("password", profile)
                self.assertEqual(get("gpu-lab")["host"], "gpu.example.test")
                self.assertEqual(len(list_profiles()), 1)
                data = status()
                self.assertEqual(data["document_type"], "agentic.remotes")
                raw = json.dumps(data)
                self.assertNotIn("PRIVATE KEY", raw)
                remove("gpu-lab")
                self.assertEqual(list_profiles(), [])

    def test_port_validation(self):
        with tempfile.TemporaryDirectory() as config:
            with patch.dict(os.environ, {"AGENTIC_DEV_ENV_CONFIG_DIR": config}):
                with self.assertRaises(ValueError):
                    add("bad", "host", port=70000)


if __name__ == "__main__":
    unittest.main()
