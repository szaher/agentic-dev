# Agentic Development Tool Policy

Use the cheapest deterministic tool that can answer the question accurately. Do not spend model context reconstructing information that a code-intelligence or verification tool can provide directly.

## Repository navigation

- Exact text or filename lookup: use `rg` and `fd`.
- Structural syntax search or repeatable AST-aware edits: use `ast-grep`.
- Symbols, definitions, references, implementations, semantic rename/refactor, and diagnostics: use Serena.
- Call graph, dependency relationships, architecture paths, and change-impact/blast-radius analysis: use CodeGraph.
- Current external library/framework/API documentation: use Context7, matching the repository's actual version where possible.
- Whole-repository or cross-repository snapshots: use Repomix only when broad context is genuinely useful.

## Before a non-trivial change

1. Identify the relevant implementation and symbols.
2. Find callers, references, and affected interfaces.
3. Use CodeGraph when dependency or architectural impact matters.
4. Locate existing tests and project conventions.
5. Verify unfamiliar or version-sensitive external APIs with Context7.
6. Prefer the repository's existing wrappers and commands (`make`, `just`, package scripts, `mvnw`, `gradlew`, etc.).

## After editing

1. Format the changed code.
2. Run the repository's linter.
3. Run type checks or compiler checks where applicable.
4. Run focused tests first.
5. Run broader tests when the change warrants it.
6. Review `git diff` for unintended changes.
7. Do not claim correctness from Serena, CodeGraph, or search results alone; tests and compiler/tooling are the verification boundary.

## Efficiency rules

- Do not read entire large files when symbol-level retrieval is enough.
- Do not repeatedly grep for call relationships when CodeGraph can answer them.
- Do not use CodeGraph for simple string lookup.
- Do not use Context7 for repository-local source code.
- Do not generate Repomix snapshots for routine navigation.
- Avoid loading overlapping MCP tools when a normal CLI tool is simpler.
- Preserve unrelated working-tree changes.
- Prefer isolated Git worktrees when multiple agents operate concurrently.
