# External providers

External providers let organizations extend agentic-dev-env without importing third-party Python code into the control plane.

A provider is a declarative JSON manifest plus optional Agent Skills.

## Manifest

```json
{
  "schema_version": "1",
  "name": "example-provider",
  "version": "1.0.0",
  "description": "Organization-specific engineering workflows",
  "compatibility": {
    "agentic_min": "0.12.0",
    "platforms": ["Darwin", "Linux"]
  },
  "skills": [
    {
      "name": "internal-api-review",
      "path": "skills/internal-api-review/SKILL.md",
      "description": "Review internal APIs",
      "category": "workflow",
      "signals": ["repo-type:api"],
      "task_keywords": ["internal api"],
      "sha256": "<sha256>"
    }
  ],
  "capabilities": [
    {
      "name": "internal-lint",
      "description": "Run the organization linter",
      "category": "quality",
      "required_permissions": ["repo.read"],
      "command": ["internal-lint", "--repo", "{repo}"]
    }
  ]
}
```

Schema:

```text
schemas/provider-manifest-v1.schema.json
```

## Validate and install

```bash
agentic providers validate ./provider.json --json
agentic providers add ./provider.json
agentic providers list
```

Declared skill files are copied into agentic-dev-env's provider store and pinned by SHA-256. They then participate in the normal skill catalog:

```bash
agentic skills list
agentic skills suggest .
agentic skills add internal-api-review --target all
```

Provider Python code is never imported.

## External capabilities

Provider capabilities are explicit argv arrays, not shell strings. `{repo}` is the only built-in substitution.

They do **not** run automatically during capability suggestions or repository initialization.

Run one explicitly:

```bash
agentic providers run example-provider internal-lint \
  --profile safe \
  --json
```

The declared trust permissions are checked before execution.

## Signed provider manifests

A provider can require Minisign verification:

```json
{
  "metadata": {
    "signature": {
      "type": "minisign",
      "public_key": "RWQ...",
      "file": "provider.minisig"
    }
  }
}
```

If signature metadata is present:

- `minisign` must be installed;
- the source manifest must verify;
- installation fails on verification failure;
- the original signature is retained as provenance;
- the installed normalized manifest records the SHA-256 of the source manifest and that signature verification succeeded.

Unsigned providers remain supported and are displayed as unsigned. This is intentional for local/private workflows where users control the provider directory directly.

## Remove

```bash
agentic providers remove example-provider
```

Removing a provider removes its catalog source. Skills already copied into a repository remain managed repository files until explicitly removed through `agentic skills remove`.
