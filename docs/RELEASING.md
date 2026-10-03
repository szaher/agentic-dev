# Releasing Agentic Dev to PyPI

Agentic Dev is published as the `agentic-dev` Python distribution.

## Release gate

Before publishing:

```bash
make check
python -m build
python -m twine check dist/*
```

CI additionally installs both the wheel and source distribution into clean virtual environments and smoke-tests the installed `agentic` CLI plus bundled bootstrap assets.

## Trusted Publishing

PyPI Trusted Publishing should be configured for:

```text
PyPI project:       agentic-dev
GitHub owner:       szaher
GitHub repository:  agentic-dev
Workflow:           publish.yml
Environment:        pypi
```

The GitHub `pypi` environment should require manual approval.

No long-lived PyPI API token is required.

## Publish flow

1. Merge a release-ready commit to `main`.
2. Confirm main CI is green.
3. Ensure the version in `pyproject.toml` and `agentic_dev.__version__` match.
4. Create a GitHub Release for that version.
5. The release workflow builds the wheel and sdist in a separate build job.
6. The publish job downloads those exact artifacts and publishes them through PyPI Trusted Publishing.

## When to release

Roadmap milestones (`M16`, `M17`, …) are development checkpoints, not releases
(see "Milestones and releases" in `docs/ROADMAP.md`). Finishing a milestone does
not publish anything. Its work lands on `main`, and `CHANGELOG.md` collects it under
one **Unreleased** section. Publish only when at least one of these is true:

- there is a complete user journey worth installing;
- an external consumer needs a stable contract;
- users need a bug or security fix;
- enough meaningful functionality has accumulated that upgrading is worthwhile.

The public version is chosen only when a release is prepared. Between releases,
`main` is not assigned the next public release version, and unreleased source and
artifact builds must stay distinguishable from the last published release (for
example a local development identifier such as `X.Y.Z+dev` on top of the last
release). Consumers such as AgentFlow decide compatibility from
`agentic contracts --json`, never from the version. A release PR changes
`pyproject.toml`, `agentic_dev.__version__`, the installed-artifact version checks
in `.github/workflows/ci.yml`, and the `CHANGELOG.md` heading (with the release
date) together, and nothing else.

The readiness CLI exit codes (`ready apply`/`diff`, `verify`, `make`) are part of
the external automation surface. A release must not change them except
intentionally and compatibly, with a CHANGELOG entry.

## Consumer smoke test

After publication, from a clean environment, install **from PyPI** (not from the
repository or a workflow artifact):

```bash
uv tool install agentic-dev==X.Y.Z
agentic --version
agentic doctor --json
agentic skills list
```

In a Git repository, run the readiness lifecycle:

```bash
agentic ready assess .
agentic ready plan . --target structured
agentic ready make . --target structured --dry-run
agentic ready verify . --target structured
agentic ready diff . --ci-check   # must pin agentic-dev==X.Y.Z, spec version, spec sha256
```

Then commit the generated `.github/workflows/agentic-readiness.yml` in a
throwaway GitHub repository and confirm the workflow installs `X.Y.Z` from PyPI
and passes.
Also push a regression (for example `git rm AGENTS.md`) and confirm the check
fails with exit code `1`. Runners can see a stale PyPI index for a few minutes
after publication (`No matching distribution found for agentic-dev==X.Y.Z`);
that is not a release failure, so re-run the job.

A temporary Git repository should also successfully run:

```bash
agentic repo init . --check --no-codegraph --no-serena --no-instructions --no-skills --no-install-language-deps --no-runtime-install
```
