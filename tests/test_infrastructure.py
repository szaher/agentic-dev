from __future__ import annotations

import json
import os
import stat
import subprocess
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from agentic_dev import capabilities
from agentic_dev.infrastructure import (
    cloud_identity,
    cloud_write,
    cluster_run,
    database_exec,
    database_local_show,
    database_local_start,
    observability_status,
)
from agentic_dev.trust import define_profile


class InfrastructureTests(unittest.TestCase):
    @contextmanager
    def config(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"AGENTIC_DEV_CONFIG_DIR": directory}, clear=False):
                yield Path(directory)

    def enable(self, name: str, profile: str):
        self.assertEqual(capabilities.enable(name, profile=profile), 0)

    def test_database_read_rejects_mutation_without_write_flag(self):
        with self.config():
            self.enable("database-read", "development")
            with self.assertRaises(ValueError):
                database_exec("sqlite", "DELETE FROM users", sqlite_file="db.sqlite", profile="development")

    @patch("agentic_dev.infrastructure._capture")
    @patch("agentic_dev.infrastructure.shutil.which")
    def test_database_read_uses_sqlite_json_mode(self, which, capture):
        which.side_effect = lambda name: "/usr/bin/sqlite3" if name == "sqlite3" else None
        capture.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout='[{"count":2}]\n', stderr=""
        )
        with self.config():
            self.enable("database-read", "development")
            data = database_exec(
                "sqlite", "SELECT count(*) AS count FROM users",
                sqlite_file="db.sqlite", profile="development",
            )
        self.assertTrue(data["success"])
        self.assertEqual(data["result"][0]["count"], 2)

    @patch("agentic_dev.infrastructure._capture")
    @patch("agentic_dev.infrastructure.shutil.which")
    def test_cluster_read_and_write_are_separate(self, which, capture):
        which.side_effect = lambda name: "/usr/bin/kubectl" if name == "kubectl" else None
        capture.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="pod/a\n", stderr="")
        with self.config():
            self.enable("cluster-read", "development")
            read = cluster_run("get", ["pods"], profile="development")
            self.assertEqual(read["mode"], "read")

            self.assertEqual(capabilities.enable("cluster-write", profile="development"), 3)
            define_profile("cluster-admin-local", ["cluster.write"], "Explicit cluster writer")
            self.enable("cluster-write", "cluster-admin-local")
            write = cluster_run(
                "apply", ["-f", "manifest.yaml"],
                profile="cluster-admin-local",
            )
            self.assertEqual(write["mode"], "write")

    @patch("agentic_dev.infrastructure._capture")
    @patch("agentic_dev.infrastructure.shutil.which")
    def test_cloud_identity_is_read_only_path(self, which, capture):
        which.side_effect = lambda name: "/usr/bin/aws" if name == "aws" else None
        capture.return_value = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout='{"Account":"123","Arn":"arn:aws:iam::123:user/test","UserId":"u"}',
            stderr="",
        )
        with self.config():
            self.enable("cloud-read", "production-read")
            result = cloud_identity("aws", profile="production-read")
        self.assertTrue(result["success"])
        self.assertEqual(result["identity"]["Account"], "123")

    @patch("agentic_dev.infrastructure._capture")
    @patch("agentic_dev.infrastructure.shutil.which")
    def test_cloud_write_requires_custom_write_permission(self, which, capture):
        which.side_effect = lambda name: "/usr/bin/aws" if name == "aws" else None
        capture.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="{}", stderr="")
        with self.config():
            self.assertEqual(capabilities.enable("cloud-write", profile="production-read"), 3)
            define_profile("cloud-writer", ["cloud.write"], "Explicit cloud mutation")
            self.enable("cloud-write", "cloud-writer")
            result = cloud_write(
                "aws", ["s3api", "put-bucket-tagging", "--bucket", "x"],
                profile="cloud-writer",
            )
        self.assertTrue(result["success"])

    def test_observability_redacts_secret_environment(self):
        with self.config():
            self.enable("observability-read", "development")
            with patch.dict(os.environ, {
                "OTEL_SERVICE_NAME": "checkout",
                "OTEL_EXPORTER_OTLP_HEADERS": "authorization=secret",
            }, clear=False):
                result = observability_status(".", profile="development")
        self.assertEqual(result["environment"]["OTEL_SERVICE_NAME"], "checkout")
        self.assertEqual(result["environment"]["OTEL_EXPORTER_OTLP_HEADERS"], "<redacted>")

    @patch("agentic_dev.infrastructure._capture")
    @patch("agentic_dev.infrastructure.shutil.which")
    def test_local_database_password_is_stored_mode_0600_and_redacted(self, which, capture):
        which.side_effect = lambda name: "/usr/bin/docker" if name == "docker" else None
        capture.side_effect = [
            subprocess.CompletedProcess(args=[], returncode=0, stdout="container-id\n", stderr=""),
            subprocess.CompletedProcess(args=[], returncode=0, stdout="127.0.0.1:49152\n", stderr=""),
        ]
        with self.config() as config:
            self.enable("database-local", "development")
            result = database_local_start(
                "postgres", "postgres:test",
                name="test-db", profile="development",
            )
            self.assertEqual(result["password"], "<redacted>")
            state = Path(result["credential_file"])
            self.assertTrue(state.exists())
            mode = stat.S_IMODE(state.stat().st_mode)
            self.assertEqual(mode, 0o600)
            shown = database_local_show("test-db")
            self.assertEqual(shown["password"], "<redacted>")
            secret = database_local_show("test-db", show_secret=True)
            self.assertNotEqual(secret["password"], "<redacted>")


if __name__ == "__main__":
    unittest.main()
