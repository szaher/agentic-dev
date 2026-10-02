"""Compatibility handshake (v0.16 slice 1): agentic contracts."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from importlib import resources
from pathlib import Path

import jsonschema

from agentic_dev.contracts import EXIT_CODES, FEATURES, REGISTRY, UnknownContract, document, schema
from agentic_dev.readiness import make as ready_make
from agentic_dev.readiness import verify as ready_verify

ROOT = Path(__file__).resolve().parents[1]
PACKAGED = resources.files("agentic_dev").joinpath("schemas")


class ContractsTests(unittest.TestCase):
    def test_document_validates_against_its_own_schema(self):
        data = document()
        jsonschema.validate(data, schema("contracts"))
        self.assertEqual(data["document_type"], "agentic.contracts")
        self.assertEqual(data["features"], sorted(set(FEATURES)))

    def test_every_contract_ships_a_valid_schema_naming_its_document_type(self):
        for contract in REGISTRY:
            with self.subTest(contract=contract.name):
                loaded = schema(contract.name, contract.version)
                jsonschema.Draft202012Validator.check_schema(loaded)
                const = loaded.get("properties", {}).get("document_type", {}).get("const")
                self.assertEqual([const] if const else [], list(contract.document_types))

    def test_every_packaged_schema_is_registered(self):
        shipped = sorted(p.name for p in PACKAGED.iterdir() if p.name.endswith(".schema.json"))
        self.assertEqual(shipped, sorted(c.schema_file for c in REGISTRY))

    def test_exit_codes_match_the_implementations(self):
        self.assertEqual(set(EXIT_CODES["ready verify"]), {str(c) for c in (
            ready_verify.EXIT_MET, ready_verify.EXIT_NOT_MET, ready_verify.EXIT_USAGE, ready_verify.EXIT_PIN_MISMATCH)})
        self.assertEqual(set(EXIT_CODES["ready make"]), {str(c) for c in (
            ready_make.EXIT_MET, ready_make.EXIT_CONFLICT, ready_make.EXIT_USAGE, ready_make.EXIT_ROLLED_BACK,
            ready_make.EXIT_STOPPED)})

    def test_unknown_contract(self):
        with self.assertRaises(UnknownContract):
            schema("nope")
        with self.assertRaises(UnknownContract):
            schema("verification-run", "2")

    def test_cli(self):
        env = {**os.environ, "PYTHONPATH": str(ROOT / "src"), "AGENTIC_DEV_CONFIG_DIR": tempfile.mkdtemp()}

        def cli(*args: str) -> subprocess.CompletedProcess[str]:
            return subprocess.run([sys.executable, "-m", "agentic_dev.cli", *args], env=env,
                                  capture_output=True, text=True, check=False)

        listed = cli("contracts", "--json")
        self.assertEqual(listed.returncode, 0, listed.stderr)
        self.assertEqual(json.loads(listed.stdout), document())
        printed = cli("contracts", "schema", "verification-run")
        self.assertEqual(json.loads(printed.stdout), schema("verification-run"))
        self.assertEqual(cli("contracts", "schema", "nope").returncode, 2)


if __name__ == "__main__":
    unittest.main()
