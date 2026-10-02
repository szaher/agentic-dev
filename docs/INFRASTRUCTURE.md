# Infrastructure capability packs

Infrastructure access is optional and trust-gated. The design favors named read operations over arbitrary privileged command execution.

## Capabilities

```text
database-read
database-write
database-local

cluster-read
cluster-write

cloud-read
cloud-write

observability-read
```

No built-in trust profile grants `cluster.write` or `cloud.write`.

## Status

```bash
agentic infra status --json
```

Status detects local CLIs and local configuration without mutating remote systems:

- sqlite3 / psql / mysql
- kubectl / oc / Helm / Kustomize
- AWS CLI / Azure CLI / gcloud
- OpenTelemetry Collector
- Docker / Podman
- current kube context/namespace from local kubeconfig
- presence of OTEL environment variables

## Database

Enable read access:

```bash
agentic capabilities enable database-read --profile development
```

Inspect schema:

```bash
agentic infra database schema sqlite --sqlite-file ./app.db --profile development --json
agentic infra database schema postgres --profile production-read --json
```

PostgreSQL and MySQL use the native client's existing environment/configuration. Credentials are not accepted as CLI flags by agentic-dev.

Read-only query mode permits only clearly read-oriented statement prefixes:

```text
SELECT
SHOW
DESCRIBE / DESC
EXPLAIN
PRAGMA
```

Example:

```bash
agentic infra database exec postgres \
  "SELECT count(*) FROM users" \
  --profile production-read --json
```

Mutation requires both `--write` and the `database-write` capability/permission:

```bash
agentic capabilities enable database-write --profile development

agentic infra database exec postgres \
  "UPDATE feature_flags SET enabled=true WHERE name='x'" \
  --write --profile development --json
```

### Migration validation

Detected workflows:

- Alembic: `alembic check`
- Django: `python manage.py makemigrations --check --dry-run`
- Prisma: `npx prisma validate`

```bash
agentic infra database migration-check --profile development --json
```

### Ephemeral local databases

Enable:

```bash
agentic capabilities enable database-local --profile development
```

Start with an explicit image:

```bash
agentic infra database local start postgres \
  --image postgres:18-alpine \
  --name feature-db \
  --profile development \
  --json
```

Agentic-dev-env generates a random password and passes it to Docker/Podman through a temporary mode-0600 env file. The generated credential is stored in a mode-0600 agentic-dev config file and is redacted from normal output.

```bash
agentic infra database local list --json
agentic infra database local show feature-db
agentic infra database local show feature-db --show-secret
agentic infra database local stop feature-db --profile development
```

## Kubernetes / OpenShift

Enable read:

```bash
agentic capabilities enable cluster-read --profile production-read
```

Examples:

```bash
agentic infra cluster run \
  --tool oc \
  --context my-context \
  --namespace openshift-ai \
  --profile production-read \
  get pods
```

Read-classified verbs include:

```text
get describe logs top api-resources api-versions version cluster-info auth explain
```

All other verbs are treated as mutation and require `cluster-write`.

There is intentionally no built-in profile granting cluster write. Create one deliberately if needed:

```bash
agentic trust define cluster-writer \
  --permission cluster.write \
  --description "Explicit cluster mutation"

agentic capabilities enable cluster-write --profile cluster-writer
```

## Cloud

Read mode exposes only a named identity operation:

```bash
agentic capabilities enable cloud-read --profile production-read

agentic infra cloud identity aws --profile production-read --json
agentic infra cloud identity azure --profile production-read --json
agentic infra cloud identity gcp --profile production-read --json
```

Agentic-dev-env deliberately does not label arbitrary AWS/Azure/GCP commands as read-only because that classification cannot be made safely from arbitrary CLI text.

Arbitrary cloud execution is therefore exposed only through the explicit write path and requires a custom `cloud.write` profile:

```bash
agentic trust define cloud-writer \
  --permission cloud.write \
  --description "Explicit cloud mutations"

agentic capabilities enable cloud-write --profile cloud-writer

agentic infra cloud write aws --profile cloud-writer -- \
  s3api put-bucket-tagging ...
```

## Observability / OpenTelemetry

Enable read access:

```bash
agentic capabilities enable observability-read --profile production-read
agentic infra observability status --profile production-read --json
```

The provider-neutral status reports:

- local OpenTelemetry Collector binary;
- common repo collector config files;
- OTEL environment variables.

Environment keys that look like headers/tokens/keys/passwords/secrets are redacted.

OpenTelemetry remains the common abstraction; provider-specific backends can be added through the provider ecosystem rather than making the core vendor-specific.

Upstream: https://opentelemetry.io/docs/
