from __future__ import annotations

import unittest

from agentic_dev.session_permissions import (
    compose,
    enforcement,
    validate_bounds,
    validate_ceilings,
)


class PermissionModelTests(unittest.TestCase):
    def test_dimensions_resolve_independently(self):
        effective, blockers = compose(
            "build", "implementer", {}, {"implementer": {"network": "off"}}
        )
        self.assertEqual(blockers, [])
        self.assertEqual(effective["filesystem"]["level"], "workspace-write")
        self.assertEqual(effective["network"]["level"], "off")

    def test_profile_ceiling_blocks_required_access(self):
        effective, blockers = compose(
            "build", "implementer", {}, {"implementer": {"filesystem": "read-only"}}
        )
        self.assertEqual(effective["filesystem"]["level"], "read-only")
        self.assertEqual(
            blockers[0].document(),
            {
                "invocation": "build",
                "dimension": "filesystem",
                "code": "permission-conflict",
                "detail": "minimum workspace-write exceeds profile ceiling read-only",
            },
        )

    def test_request_ceiling_blocks_its_own_minimum(self):
        _, blockers = compose(
            "build",
            "implementer",
            {
                "network": {"minimum": "on", "maximum": "off"},
            },
            {},
        )
        self.assertEqual(blockers[0].dimension, "network")

    def test_reviewer_cannot_request_write(self):
        for key in ("minimum", "maximum"):
            with (
                self.subTest(key=key),
                self.assertRaisesRegex(ValueError, "reviewers cannot"),
            ):
                validate_bounds("reviewer", {"filesystem": {key: "workspace-write"}})

    def test_unknown_input_rejected(self):
        with self.assertRaisesRegex(ValueError, "unknown permission dimensions"):
            validate_bounds("implementer", {"browser": {}})
        with self.assertRaisesRegex(ValueError, "unknown permission roles"):
            validate_ceilings({"agentflow-stage": {}})
        with self.assertRaisesRegex(ValueError, "unknown network permission level"):
            validate_bounds("implementer", {"network": {"maximum": "maybe"}})

    def test_missing_enforcement_evidence_blocks(self):
        effective, _ = compose("build", "implementer", {}, {})
        result, blockers = enforcement(
            "build", effective, {"filesystem": {"workspace-write": "enforceable"}}
        )
        self.assertEqual(result["filesystem"]["status"], "enforceable")
        self.assertEqual(result["network"]["status"], "unknown")
        self.assertEqual(
            [(item.dimension, item.code) for item in blockers],
            [("network", "permission-unenforceable")],
        )


if __name__ == "__main__":
    unittest.main()
