# Security capability pack

Security verification is optional and explicitly enabled. Repository/task detection may recommend a scan but never runs one automatically.

## Capabilities

| Capability | Provider | Purpose |
|---|---|---|
| `secret-scan` | Trivy | detect exposed secrets in repository files |
| `dependency-vulnerability` | Trivy | scan dependency metadata/lockfiles for known vulnerabilities |
| `sast` | Semgrep Community Edition | source-level static analysis |
| `iac-misconfiguration` | Trivy | scan Terraform, Kubernetes, Docker and related configuration |
| `container-image-scan` | Trivy | scan a named container image |
| `sbom` | Trivy | generate a CycloneDX SBOM |

Trivy's filesystem scanner supports vulnerability, secret, license, and misconfiguration scanners, and can emit JSON. Trivy can also generate CycloneDX or SPDX SBOMs from filesystem/image targets.

Semgrep Community Edition runs locally, supports community rule packs, and can emit JSON/SARIF without requiring a login.

## Enable

Local/read-oriented security checks fit the built-in `safe` trust profile:

```bash
agentic capabilities enable secret-scan
agentic capabilities enable dependency-vulnerability
agentic capabilities enable iac-misconfiguration
agentic capabilities enable sbom
```

SAST downloads rules and therefore requires broader network permission:

```bash
agentic capabilities enable sast --profile development
```

Container-image scanning may pull image metadata/layers:

```bash
agentic capabilities enable container-image-scan --profile development
```

## Run

```bash
agentic capabilities run secret-scan . --json
agentic capabilities run dependency-vulnerability . --json
agentic capabilities run sast . --profile development --json
agentic capabilities run iac-misconfiguration . --json
agentic capabilities run sbom . --json

agentic capabilities run container-image-scan . \
  --image quay.io/example/app:latest \
  --profile development \
  --json
```

Every run emits the normalized envelope:

```json
{
  "schema_version": "1",
  "document_type": "agentic.capability-result",
  "capability": "secret-scan",
  "provider": "trivy",
  "success": true,
  "returncode": 0,
  "finding_count": 0
}
```

The provider payload is retained in `result` so higher layers can inspect full findings without scraping terminal text.

## Network and privacy

The default design uses local CLIs. Trivy and Semgrep may download vulnerability databases, checks, or rule packs. The project does not configure managed/cloud source upload as part of these capabilities. Any future provider that uploads source or findings must declare that behavior and require explicit opt-in.

Upstream references:

- Trivy: https://trivy.dev/
- Trivy filesystem scanning: https://trivy.dev/docs/latest/target/filesystem/
- Trivy SBOM: https://trivy.dev/docs/latest/guide/supply-chain/sbom/
- Semgrep Community Edition: https://semgrep.dev/products/community-edition/
