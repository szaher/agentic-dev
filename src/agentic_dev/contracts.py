"""Machine-readable compatibility handshake: ``agentic contracts --json``.

Consumers such as AgentFlow decide compatibility from the contracts and
features listed here, never from ``agentic --version``. Every contract version
ships its JSON Schema inside the package (``agentic_dev/schemas``), so an
installed artifact can validate its own output: ``agentic contracts schema NAME``.

Adding a contract version or a feature is additive. Removing one, or changing
a listed exit code, is a breaking change for consumers.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import resources
from typing import Any

SCHEMA_VERSION = "1"
DOCUMENT_TYPE = "agentic.contracts"


@dataclass(frozen=True)
class Contract:
    name: str
    version: str
    document_types: tuple[str, ...]

    @property
    def schema_file(self) -> str:
        return f"{self.name}-v{self.version}.schema.json"


REGISTRY: tuple[Contract, ...] = (
    Contract("contracts", "1", ("agentic.contracts",)),
    Contract("doctor", "1", ("agentic.doctor",)),
    Contract("repo-inspection", "1", ("agentic.repo-inspection",)),
    Contract("verification-plan", "1", ("agentic.verification-plan",)),
    Contract("verification-run", "1", ("agentic.verification-run",)),
    Contract("execution-result", "1", ("agentic.execution-result",)),
    Contract("infrastructure-status", "1", ("agentic.infrastructure-status",)),
    Contract("metric-event", "1", ("agentic.metric-event",)),
    Contract("metric-record", "1", ("agentic.metric-record",)),
    Contract("provider-manifest", "1", ()),
    Contract("readiness-assessment", "1", ("agentic.readiness-assessment",)),
    Contract("readiness-explanation", "1", ("agentic.readiness-explanation",)),
    Contract("readiness-plan", "1", ("agentic.readiness-plan",)),
    Contract("readiness-remediation", "1", ("agentic.readiness-remediation",)),
    Contract("readiness-verification", "1", ("agentic.readiness-verification",)),
    Contract("readiness-make", "1", ("agentic.readiness-make",)),
    Contract("worktree", "1", ("agentic.worktree",)),
    Contract("worktree-list", "1", ("agentic.worktrees",)),
    Contract("worktree-status", "1", ("agentic.worktree-status",)),
    Contract("worktree-clean", "1", ("agentic.worktree-clean",)),
    Contract("capability-status", "1", ()),
    Contract("instruction-block", "1", ("agentic.instruction-block",)),
    Contract("instruction-block-list", "1", ("agentic.instruction-blocks",)),
    Contract("providers", "1", ("agentic.providers",)),
    Contract("provider-source", "1", ("agentic.provider-source",)),
    Contract("provider-install", "1", ("agentic.provider-install",)),
    Contract("skills-activation", "1", ("agentic.skills-activation",)),
    Contract("repository-profile", "1", ("agentic.repository-profile",)),
    Contract("session-request", "1", ("agentic.session-request",)),
    Contract("session-plan", "1", ("agentic.session-plan",)),
    Contract("session-record", "1", ("agentic.session-record",)),
)

FEATURES: tuple[str, ...] = (
    "commands.canonical-discovery",
    "instructions.managed-block",
    "metrics.record-report",
    "providers.inspect",
    "providers.install-pinned",
    "readiness.scope-ci",
    "readiness.spec-pin",
    "repo-inspection.discovered-commands",
    "skills.activation-dry-run",
    "skills.activation-report",
    "session.permission-dimensions",
    "session.plan-read-only",
    "session.prepare-revalidated",
    "verification.change-aware",
    "verification.explicit-commands",
    "verification.full-kind-filter",
    "verification.no-checks-status",
    "worktree.lifecycle",
)

# Process exit codes are part of the automation contract.
EXIT_CODES: dict[str, dict[str, str]] = {
    "verify run": {"0": "passed", "1": "failed, or no-checks", "2": "usage error"},
    "instructions block": {"0": "ok (created, appended, replaced, unchanged, removed, absent)",
                           "1": "conflict or refused (nothing written)", "2": "usage error", "3": "rolled back"},
    "metrics record": {"0": "recorded, or metrics disabled (recorded=false)", "2": "usage error"},
    "worktree create": {"0": "created", "2": "error (path or branch exists, bad base): nothing created"},
    "worktree clean": {"0": "removed",
                       "2": "refused (uncommitted changes without --force, primary worktree) or error: nothing removed"},
    "capabilities status": {"0": "reported"},
    "providers add": {"0": "installed (replaces a provider of the same name)", "2": "error (nothing installed)"},
    "providers inspect": {"0": "described", "2": "error"},
    "skills add": {"0": "ok (written or unchanged)", "1": "conflict: an unmanaged SKILL.md was left in place (or would be, with --dry-run)",
                   "2": "usage error (unknown skill)"},
    "ready diff": {"0": "ok", "1": "conflict (nothing written)", "2": "usage error", "3": "rolled back"},
    "ready apply": {"0": "ok", "1": "conflict (nothing written)", "2": "usage error", "3": "rolled back"},
    "ready verify": {"0": "target met", "1": "target not met", "2": "usage or spec error",
                     "3": "spec pin mismatch"},
    "ready make": {"0": "target met", "1": "conflict", "2": "usage error", "3": "rolled back",
                   "4": "stopped: human decision, no safe progress, or round limit"},
    "session plan": {"0": "ready plan", "1": "blocked plan; no mutation", "2": "invalid request or profile"},
    "session prepare": {"0": "prepared record", "1": "blocked plan; no mutation",
                        "2": "invalid plan or workspace", "3": "SESSION_PLAN_STALE; no mutation",
                        "4": "skill placement conflict or I/O failure",
                        "5": "SESSION_WORKSPACE_DIRTY; no Agentic Dev placement"},
}


class UnknownContract(KeyError):
    pass


def _schemas():
    return resources.files("agentic_dev").joinpath("schemas")


def schema(name: str, version: str = "1") -> dict[str, Any]:
    """The packaged JSON Schema for one contract version."""

    contract = next((c for c in REGISTRY if c.name == name and c.version == version), None)
    if contract is None:
        raise UnknownContract(f"unknown contract {name!r} version {version!r}")
    return json.loads(_schemas().joinpath(contract.schema_file).read_text(encoding="utf-8"))


def document() -> dict[str, Any]:
    from . import __version__

    contracts: dict[str, list[str]] = {}
    for contract in REGISTRY:
        contracts.setdefault(contract.name, []).append(contract.version)
    return {
        "schema_version": SCHEMA_VERSION,
        "document_type": DOCUMENT_TYPE,
        "agentic_version": __version__,
        "contracts": {name: sorted(versions) for name, versions in sorted(contracts.items())},
        "document_types": {
            f"{c.name}@{c.version}": list(c.document_types) for c in sorted(REGISTRY, key=lambda c: (c.name, c.version))
        },
        "features": sorted(FEATURES),
        "exit_codes": {command: dict(codes) for command, codes in sorted(EXIT_CODES.items())},
    }
