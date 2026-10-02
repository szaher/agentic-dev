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
Workflow:           publish-to-pypi.yml
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

The first Agentic Dev package is intentionally a prerelease:

```text
0.14.0a1
```

This validates the renamed distribution/install path before the v0.14 Agent Ready milestone reaches a stable release.

## Consumer smoke test

After publication:

```bash
uv tool install --prerelease allow agentic-dev
agentic --version
agentic doctor --json
agentic skills list
```

A temporary Git repository should also successfully run:

```bash
agentic repo init . --check --no-codegraph --no-serena --no-instructions --no-skills --no-install-language-deps --no-runtime-install
```
