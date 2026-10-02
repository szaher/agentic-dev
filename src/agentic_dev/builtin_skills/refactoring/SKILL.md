---
name: refactoring
description: Perform behavior-preserving structural change with dependency awareness and incremental verification.
---

# Refactoring

Define the behavior that must remain unchanged before moving code.

Use symbol/reference and dependency tools to map impact. Refactor in small mechanically verifiable steps; avoid mixing unrelated cleanup with behavior changes.

Keep tests green throughout where practical and review the final diff for accidental semantic change.