---
name: api-design
description: Design and evolve APIs with explicit contracts, compatibility, validation, errors, and consumer impact.
---

# API Design

Start from the consumer-visible contract: request, response, errors, authentication/authorization, idempotency, pagination, and versioning.

For an existing API, identify callers and compatibility constraints before implementation. Avoid leaking internal persistence/domain structures into the public contract.

Add contract-focused tests and update API docs/schema when the repo owns them.