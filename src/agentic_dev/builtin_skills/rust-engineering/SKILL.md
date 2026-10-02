---
name: rust-engineering
description: Apply safe, idiomatic Rust/Cargo development with ownership-aware design and strong verification.
---

# Rust Engineering

Inspect `Cargo.toml`, crate boundaries, feature flags, error types, and tests first.

Prefer type-safe APIs and explicit ownership over cloning around compiler errors. Do not weaken safety or add `unwrap()` in production paths without a repo-supported reason.

Verify with the repo wrappers or `cargo fmt --all`, `cargo clippy --all-targets --all-features`, focused tests, then broader `cargo test`.