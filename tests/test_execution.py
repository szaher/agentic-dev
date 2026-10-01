from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentic_dev_env.execution import configure, run, status


class ExecutionBackendTests(unittest.TestCase):
    def repo(self) -> Path:
        root = Path(tempfile.mkdtemp())
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        return root

    def test_host_execution(self):
        root = self.repo()
        result = run("printf hello", root)
        self.assertTrue(result["success"])
        self.assertEqual(result["backend"], "host")
        self.assertEqual(result["stdout"], "hello")

    def test_container_requires_development_trust(self):
        root = self.repo()
        with self.assertRaises(PermissionError):
            run("true", root, backend="container", image="alpine:3.22")

    @patch("agentic_dev_env.execution._invoke")
    @patch("agentic_dev_env.execution.shutil.which")
    def test_container_defaults_to_no_network(self, which, invoke):
        root = self.repo()
        which.side_effect = lambda name: "/usr/bin/docker" if name == "docker" else None
        invoke.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="ok", stderr="")
        result = run(
            "pytest -q", root,
            backend="container", image="python:3.13",
            profile="development",
        )
        argv = invoke.call_args.args[0]
        self.assertIn("--network", argv)
        self.assertIn("none", argv)
        self.assertIn(f"{root}:/workspace", argv)
        self.assertEqual(result["metadata"]["image"], "python:3.13")

    @patch("agentic_dev_env.execution._invoke")
    @patch("agentic_dev_env.execution.shutil.which")
    def test_devcontainer_up_then_exec(self, which, invoke):
        root = self.repo()
        (root / ".devcontainer").mkdir()
        (root / ".devcontainer/devcontainer.json").write_text('{"image":"ubuntu:24.04"}\n')
        which.side_effect = lambda name: "/usr/bin/devcontainer" if name == "devcontainer" else None
        invoke.side_effect = [
            subprocess.CompletedProcess(args=[], returncode=0, stdout='{"outcome":"success"}', stderr=""),
            subprocess.CompletedProcess(args=[], returncode=0, stdout="done", stderr=""),
        ]
        result = run("make test", root, backend="devcontainer", profile="development")
        self.assertTrue(result["success"])
        first = invoke.call_args_list[0].args[0]
        second = invoke.call_args_list[1].args[0]
        self.assertEqual(first[:2], ["/usr/bin/devcontainer", "up"])
        self.assertEqual(second[:2], ["/usr/bin/devcontainer", "exec"])
        self.assertIn("--workspace-folder", second)

    @patch("agentic_dev_env.execution._invoke")
    @patch("agentic_dev_env.execution.shutil.which")
    def test_dagger_uses_no_apply_and_explicit_image(self, which, invoke):
        root = self.repo()
        which.side_effect = lambda name: "/usr/bin/dagger" if name == "dagger" else None
        invoke.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="ok", stderr="")
        result = run(
            "go test ./...", root,
            backend="dagger", image="golang:1.26",
            profile="development",
        )
        argv = invoke.call_args.args[0]
        self.assertIn("workspace", argv)
        self.assertIn("exec", argv)
        self.assertIn("--no-apply", argv)
        self.assertIn("--from=golang:1.26", argv)
        self.assertTrue(result["success"])

    def test_repo_config_is_local_and_requires_image_for_container(self):
        root = self.repo()
        with tempfile.TemporaryDirectory() as config:
            with patch.dict(os.environ, {"AGENTIC_DEV_ENV_CONFIG_DIR": config}):
                with self.assertRaises(ValueError):
                    configure(backend="container", path=root, repo_scope=True)
                data = configure(
                    backend="container", path=root,
                    image="python:3.13", repo_scope=True,
                )
                self.assertEqual(data["backend"], "container")
                state = status(root)
                self.assertEqual(state["selected"]["image"], "python:3.13")
                exclude_raw = subprocess.run(
                    ["git", "-C", str(root), "rev-parse", "--git-path", "info/exclude"],
                    check=True, capture_output=True, text=True,
                ).stdout.strip()
                exclude = Path(exclude_raw)
                if not exclude.is_absolute():
                    exclude = root / exclude
                self.assertIn("/.agentic/", exclude.read_text())


if __name__ == "__main__":
    unittest.main()
