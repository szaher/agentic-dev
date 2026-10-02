---
name: database-migrations
description: Change database schemas/data safely with compatibility windows, rollback thinking, and migration tests.
---

# Database Migrations

Determine the migration framework, deployment ordering, and whether old/new application versions may overlap.

Prefer expand/contract for compatibility-sensitive changes. Treat destructive changes, long locks, rewrites, backfills, defaults, indexes, and uniqueness constraints as operational risks.

Test both migration application and application behavior against the migrated schema. Never silently edit an already-released migration unless the repo explicitly permits it.