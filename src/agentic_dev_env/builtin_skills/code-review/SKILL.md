---
name: code-review
description: Review changes for correctness, regressions, contracts, security boundaries, tests, and unintended scope.
---

# Code Review

Review the diff in context, not only line-by-line.

Prioritize:
1. correctness and broken invariants;
2. compatibility/API/behavior changes;
3. security, authorization, data-loss, and concurrency risks;
4. missing regression tests;
5. operational and upgrade impact;
6. maintainability issues that materially affect future changes.

Verify suspicious claims against callers, tests, and repository contracts. Avoid style-only noise when automated tooling can decide it.