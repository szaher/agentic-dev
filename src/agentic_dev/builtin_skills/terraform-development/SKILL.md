---
name: terraform-development
description: Change Terraform/OpenTofu infrastructure with state-aware planning, module discipline, and validation.
---

# Terraform Development

Inspect module boundaries, provider/version constraints, state/backend assumptions, and environment layering before editing.

Avoid changes that force replacement unless intended. Treat state moves/imports and provider upgrades explicitly.

Run format/validate and inspect a plan in the correct environment before claiming the change is safe. Never apply infrastructure unless explicitly requested and authorized.