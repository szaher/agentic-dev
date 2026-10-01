---
name: go-engineering
description: Apply idiomatic Go development practices with module-aware implementation, tests, interfaces, and tooling.
---

# Go Engineering

Read `go.mod`, package boundaries, interfaces, tests, and existing error conventions first.

Prefer:
- small interfaces defined near consumers;
- explicit errors and wrapped context;
- table-driven tests when they fit existing style;
- standard library solutions before adding dependencies.

Run `gofmt`, focused `go test`, broader `go test ./...`, and the repository's lint/build wrappers.