from __future__ import annotations

import json
import os
import re
import secrets
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .capabilities import required_permissions, status as capability_status
from .detect import repo_root
from .execution import run as run_execution
from .paths import config_dir
from .trust import check as trust_check


READ_SQL_PREFIXES = ("select", "show", "describe", "desc", "explain", "pragma")
READ_CLUSTER_VERBS = {
    "get", "describe", "logs", "top", "api-resources", "api-versions",
    "version", "cluster-info", "auth", "explain",
}


def _capture(argv: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, cwd=cwd, capture_output=True, text=True, check=False)


def _enabled(name: str) -> None:
    if not capability_status().get(name, {}).get("enabled"):
        raise RuntimeError(f"{name} capability is not enabled")


def _trusted(name: str, *, profile: str | None = None, root: str | Path | None = None) -> str:
    allowed, missing, selected = trust_check(
        required_permissions(name),
        profile_name=profile,
        root=root,
    )
    if not allowed:
        raise PermissionError(
            f"trust profile '{selected.name}' missing permissions: {', '.join(missing)}"
        )
    return selected.name


def status(path: str | Path = ".") -> dict[str, Any]:
    root = repo_root(path)
    tools = {}
    for name in (
        "sqlite3", "psql", "mysql",
        "kubectl", "oc", "helm", "kustomize",
        "aws", "az", "gcloud",
        "otelcol", "otelcol-contrib",
        "docker", "podman",
    ):
        binary = shutil.which(name)
        tools[name] = {"available": bool(binary), "path": binary}

    cluster: dict[str, Any] = {"context": None, "namespace": None, "tool": None}
    cluster_tool = shutil.which("kubectl") or shutil.which("oc")
    if cluster_tool:
        cluster["tool"] = Path(cluster_tool).name
        current = _capture([cluster_tool, "config", "current-context"])
        if current.returncode == 0:
            cluster["context"] = current.stdout.strip() or None
        namespace = _capture([
            cluster_tool, "config", "view", "--minify",
            "--output", "jsonpath={..namespace}",
        ])
        if namespace.returncode == 0:
            cluster["namespace"] = namespace.stdout.strip() or "default"

    otel_vars = sorted(
        key for key in os.environ
        if key.startswith("OTEL_")
    )

    return {
        "schema_version": "1",
        "document_type": "agentic.infrastructure-status",
        "repository": str(root),
        "tools": tools,
        "cluster": cluster,
        "cloud": {
            "aws_profile": os.environ.get("AWS_PROFILE"),
            "azure_configured": bool(shutil.which("az")),
            "gcp_configured": bool(shutil.which("gcloud")),
        },
        "observability": {
            "otel_environment_variables": otel_vars,
            "collector_available": bool(shutil.which("otelcol") or shutil.which("otelcol-contrib")),
            "config_files": [
                str(p.relative_to(root))
                for p in [
                    root / "otel-collector-config.yaml",
                    root / "otelcol.yaml",
                    root / "collector.yaml",
                ]
                if p.exists()
            ],
        },
    }


def _sql_is_read_only(query: str) -> bool:
    stripped = re.sub(r"^\s*(?:--[^\n]*\n\s*)*", "", query).strip().lower()
    return any(stripped.startswith(prefix + " ") or stripped == prefix for prefix in READ_SQL_PREFIXES)


def database_exec(
    engine: str,
    query: str,
    *,
    path: str | Path = ".",
    database: str | None = None,
    sqlite_file: str | Path | None = None,
    write: bool = False,
    profile: str | None = None,
) -> dict[str, Any]:
    capability = "database-write" if write else "database-read"
    _enabled(capability)
    trust = _trusted(capability, profile=profile, root=path)
    if not write and not _sql_is_read_only(query):
        raise ValueError("read mode only accepts SELECT/SHOW/DESCRIBE/EXPLAIN/PRAGMA statements; use --write explicitly")

    engine = engine.lower()
    if engine == "sqlite":
        binary = shutil.which("sqlite3")
        if not binary:
            raise RuntimeError("sqlite3 is not installed")
        if not sqlite_file:
            raise ValueError("sqlite requires --sqlite-file")
        argv = [binary, "-json", str(Path(sqlite_file).expanduser()), query]
    elif engine == "postgres":
        binary = shutil.which("psql")
        if not binary:
            raise RuntimeError("psql is not installed")
        argv = [binary, "-X", "-A", "-t"]
        if database:
            argv += ["-d", database]
        argv += ["-c", query]
    elif engine == "mysql":
        binary = shutil.which("mysql")
        if not binary:
            raise RuntimeError("mysql is not installed")
        argv = [binary, "--batch", "--skip-column-names"]
        if database:
            argv += ["-D", database]
        argv += ["-e", query]
    else:
        raise ValueError("engine must be sqlite, postgres, or mysql")

    result = _capture(argv, cwd=repo_root(path))
    parsed: Any = None
    if engine == "sqlite" and result.stdout.strip():
        try:
            parsed = json.loads(result.stdout)
        except json.JSONDecodeError:
            parsed = None

    return {
        "schema_version": "1",
        "document_type": "agentic.database-result",
        "engine": engine,
        "mode": "write" if write else "read",
        "trust_profile": trust,
        "success": result.returncode == 0,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "result": parsed,
    }


def database_schema(
    engine: str,
    *,
    path: str | Path = ".",
    database: str | None = None,
    sqlite_file: str | Path | None = None,
    profile: str | None = None,
) -> dict[str, Any]:
    engine = engine.lower()
    if engine == "sqlite":
        _enabled("database-read")
        trust = _trusted("database-read", profile=profile, root=path)
        binary = shutil.which("sqlite3")
        if not binary:
            raise RuntimeError("sqlite3 is not installed")
        if not sqlite_file:
            raise ValueError("sqlite requires --sqlite-file")
        argv = [binary, str(Path(sqlite_file).expanduser()), ".schema"]
        result = _capture(argv, cwd=repo_root(path))
        return {
            "schema_version": "1",
            "document_type": "agentic.database-schema",
            "engine": engine,
            "trust_profile": trust,
            "success": result.returncode == 0,
            "schema": result.stdout,
            "stderr": result.stderr,
        }
    if engine == "postgres":
        query = "SELECT table_schema||'.'||table_name FROM information_schema.tables WHERE table_schema NOT IN ('pg_catalog','information_schema') ORDER BY 1"
    elif engine == "mysql":
        query = "SHOW TABLES"
    else:
        raise ValueError("engine must be sqlite, postgres, or mysql")
    result = database_exec(
        engine, query, path=path, database=database,
        profile=profile,
    )
    return {
        "schema_version": "1",
        "document_type": "agentic.database-schema",
        "engine": engine,
        "trust_profile": result["trust_profile"],
        "success": result["success"],
        "schema": result["stdout"],
        "stderr": result["stderr"],
    }


def migration_check(
    path: str | Path = ".",
    *,
    profile: str | None = None,
    backend: str | None = None,
) -> dict[str, Any]:
    root = repo_root(path)
    _enabled("database-read")
    trust = _trusted("database-read", profile=profile, root=root)
    command: str | None = None
    if (root / "alembic.ini").exists():
        command = "alembic check"
    elif (root / "manage.py").exists():
        command = "python manage.py makemigrations --check --dry-run"
    elif (root / "prisma" / "schema.prisma").exists():
        command = "npx prisma validate"
    if not command:
        raise RuntimeError("no supported migration/schema validation workflow detected")

    result = run_execution(
        command, root,
        backend=backend,
        profile=profile,
    )
    return {
        "schema_version": "1",
        "document_type": "agentic.database-migration-check",
        "trust_profile": trust,
        "command": command,
        "execution": result,
        "success": result["success"],
    }


def _db_state_dir() -> Path:
    return config_dir() / "infrastructure" / "databases"


def _db_state(name: str) -> Path:
    return _db_state_dir() / f"{name}.json"


def _write_secret_state(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    path.chmod(0o600)


def database_local_start(
    engine: str,
    image: str,
    *,
    name: str | None = None,
    profile: str | None = None,
) -> dict[str, Any]:
    _enabled("database-local")
    trust = _trusted("database-local", profile=profile)
    runtime = shutil.which("docker") or shutil.which("podman")
    if not runtime:
        raise RuntimeError("Docker or Podman is required for local databases")
    engine = engine.lower()
    if engine not in {"postgres", "mysql"}:
        raise ValueError("local database engine must be postgres or mysql")
    if not image:
        raise ValueError("--image is required; agentic-dev does not guess database image versions")

    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", name or f"{engine}-{secrets.token_hex(3)}")
    password = secrets.token_urlsafe(24)
    port = "5432" if engine == "postgres" else "3306"
    env_lines = (
        [f"POSTGRES_PASSWORD={password}", "POSTGRES_USER=agentic", "POSTGRES_DB=agentic"]
        if engine == "postgres"
        else [f"MYSQL_ROOT_PASSWORD={password}", "MYSQL_DATABASE=agentic"]
    )

    fd, env_path = tempfile.mkstemp(prefix="agentic-db-", text=True)
    try:
        os.chmod(env_path, 0o600)
        with os.fdopen(fd, "w") as handle:
            handle.write("\n".join(env_lines) + "\n")
        argv = [
            runtime, "run", "-d", "--rm",
            "--name", slug,
            "--env-file", env_path,
            "-p", f"127.0.0.1::{port}",
            image,
        ]
        result = _capture(argv)
    finally:
        try:
            os.unlink(env_path)
        except OSError:
            pass

    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout).strip())

    port_result = _capture([runtime, "port", slug, f"{port}/tcp"])
    mapped = port_result.stdout.strip().rsplit(":", 1)[-1] if port_result.returncode == 0 else None
    state = {
        "engine": engine,
        "container": slug,
        "runtime": Path(runtime).name,
        "image": image,
        "host": "127.0.0.1",
        "port": int(mapped) if mapped and mapped.isdigit() else None,
        "user": "agentic" if engine == "postgres" else "root",
        "database": "agentic",
        "password": password,
        "trust_profile": trust,
    }
    state_path = _db_state(slug)
    _write_secret_state(state_path, state)
    return {
        "schema_version": "1",
        "document_type": "agentic.local-database",
        "name": slug,
        "engine": engine,
        "container": slug,
        "image": image,
        "host": state["host"],
        "port": state["port"],
        "user": state["user"],
        "database": state["database"],
        "credential_file": str(state_path),
        "password": "<redacted>",
    }


def database_local_show(name: str, *, show_secret: bool = False) -> dict[str, Any]:
    path = _db_state(name)
    if not path.exists():
        raise KeyError(f"unknown local database: {name}")
    data = json.loads(path.read_text())
    result = dict(data)
    if not show_secret:
        result["password"] = "<redacted>"
    result.update({
        "schema_version": "1",
        "document_type": "agentic.local-database",
        "credential_file": str(path),
    })
    return result


def database_local_list() -> dict[str, Any]:
    root = _db_state_dir()
    entries = []
    if root.exists():
        for path in sorted(root.glob("*.json")):
            data = json.loads(path.read_text())
            data["password"] = "<redacted>"
            data["name"] = path.stem
            entries.append(data)
    return {
        "schema_version": "1",
        "document_type": "agentic.local-databases",
        "databases": entries,
    }


def database_local_stop(name: str, *, profile: str | None = None) -> dict[str, Any]:
    _enabled("database-local")
    trust = _trusted("database-local", profile=profile)
    path = _db_state(name)
    if not path.exists():
        raise KeyError(f"unknown local database: {name}")
    state = json.loads(path.read_text())
    runtime = shutil.which(state["runtime"])
    if not runtime:
        raise RuntimeError(f"{state['runtime']} is not installed")
    result = _capture([runtime, "stop", state["container"]])
    if result.returncode == 0:
        path.unlink(missing_ok=True)
    return {
        "schema_version": "1",
        "document_type": "agentic.local-database-stop",
        "name": name,
        "trust_profile": trust,
        "success": result.returncode == 0,
        "stderr": result.stderr,
    }


def _cluster_tool(tool: str) -> str:
    if tool == "auto":
        binary = shutil.which("kubectl") or shutil.which("oc")
    else:
        binary = shutil.which(tool)
    if not binary:
        raise RuntimeError(f"cluster CLI not installed: {tool}")
    return binary


def cluster_run(
    verb: str,
    args: list[str],
    *,
    tool: str = "auto",
    context: str | None = None,
    namespace: str | None = None,
    profile: str | None = None,
) -> dict[str, Any]:
    read = verb in READ_CLUSTER_VERBS
    capability = "cluster-read" if read else "cluster-write"
    _enabled(capability)
    trust = _trusted(capability, profile=profile)
    binary = _cluster_tool(tool)
    argv = [binary]
    if context:
        argv += ["--context", context]
    if namespace:
        argv += ["--namespace", namespace]
    argv += [verb, *args]
    result = _capture(argv)
    return {
        "schema_version": "1",
        "document_type": "agentic.cluster-result",
        "mode": "read" if read else "write",
        "tool": Path(binary).name,
        "verb": verb,
        "trust_profile": trust,
        "success": result.returncode == 0,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def cloud_identity(provider: str, *, profile: str | None = None) -> dict[str, Any]:
    _enabled("cloud-read")
    trust = _trusted("cloud-read", profile=profile)
    provider = provider.lower()
    if provider == "aws":
        binary = shutil.which("aws")
        argv = [binary, "sts", "get-caller-identity", "--output", "json"] if binary else []
    elif provider in {"azure", "az"}:
        binary = shutil.which("az")
        argv = [binary, "account", "show", "--output", "json"] if binary else []
        provider = "azure"
    elif provider in {"gcp", "gcloud"}:
        binary = shutil.which("gcloud")
        argv = [binary, "config", "list", "account,project", "--format=json"] if binary else []
        provider = "gcp"
    else:
        raise ValueError("provider must be aws, azure, or gcp")
    if not binary:
        raise RuntimeError(f"{provider} CLI is not installed")
    result = _capture(argv)
    payload: Any = None
    try:
        payload = json.loads(result.stdout) if result.stdout.strip() else None
    except json.JSONDecodeError:
        pass
    return {
        "schema_version": "1",
        "document_type": "agentic.cloud-identity",
        "provider": provider,
        "trust_profile": trust,
        "success": result.returncode == 0,
        "identity": payload,
        "stderr": result.stderr,
    }


def cloud_write(
    provider: str,
    args: list[str],
    *,
    profile: str | None = None,
) -> dict[str, Any]:
    _enabled("cloud-write")
    trust = _trusted("cloud-write", profile=profile)
    mapping = {"aws": "aws", "azure": "az", "az": "az", "gcp": "gcloud", "gcloud": "gcloud"}
    if provider not in mapping:
        raise ValueError("provider must be aws, azure, or gcp")
    binary = shutil.which(mapping[provider])
    if not binary:
        raise RuntimeError(f"{mapping[provider]} CLI is not installed")
    if not args:
        raise ValueError("cloud write requires provider arguments")
    result = _capture([binary, *args])
    return {
        "schema_version": "1",
        "document_type": "agentic.cloud-write-result",
        "provider": provider,
        "trust_profile": trust,
        "success": result.returncode == 0,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def observability_status(
    path: str | Path = ".",
    *,
    profile: str | None = None,
) -> dict[str, Any]:
    _enabled("observability-read")
    trust = _trusted("observability-read", profile=profile, root=path)
    root = repo_root(path)
    variables = {}
    for key in sorted(k for k in os.environ if k.startswith("OTEL_")):
        value = os.environ[key]
        if any(secret in key for secret in ("HEADER", "TOKEN", "KEY", "PASSWORD", "SECRET")):
            value = "<redacted>"
        variables[key] = value
    return {
        "schema_version": "1",
        "document_type": "agentic.observability-status",
        "trust_profile": trust,
        "collector": shutil.which("otelcol") or shutil.which("otelcol-contrib"),
        "environment": variables,
        "config_files": [
            str(p.relative_to(root))
            for p in (
                root / "otel-collector-config.yaml",
                root / "otelcol.yaml",
                root / "collector.yaml",
            )
            if p.exists()
        ],
    }
