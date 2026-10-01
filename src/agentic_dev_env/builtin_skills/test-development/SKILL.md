---
name: test-development
description: Build focused regression coverage and a verification strategy that matches repository conventions.
---

# Test Development

Before adding tests, identify the failure mode and the narrowest observable contract that proves it.

Prefer a regression test that fails before the fix and passes after it. Reuse existing fixtures/helpers and avoid testing implementation details unless they are the contract.

Run focused tests first, then the repository's broader suite when warranted.