#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"

"$ROOT/scripts/setup-coding-agent-env.sh" --help >/dev/null
"$ROOT/scripts/saad-tool-repo-init.sh" --help >/dev/null

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

git -C "$tmp" init -q
cat > "$tmp/pyproject.toml" <<'PY'
[project]
name = "fixture"
version = "0.0.0"
dependencies = []

[tool.pytest.ini_options]
testpaths = ["tests"]

[tool.ruff]
line-length = 100
PY
mkdir -p "$tmp/src/fixture" "$tmp/tests"
printf 'def add(a: int, b: int) -> int:\n    return a + b\n' > "$tmp/src/fixture/__init__.py"
printf 'fn main() {}\n' > "$tmp/main.rs"
printf '[package]\nname="fixture"\nversion="0.0.0"\nedition="2021"\n' > "$tmp/Cargo.toml"

output="$($ROOT/scripts/saad-tool-repo-init.sh "$tmp" --check --no-codegraph --no-serena --no-instructions 2>&1)"

grep -q 'python' <<<"$output"
grep -q 'rust' <<<"$output"
grep -q 'cargo test' <<<"$output"
grep -q 'cargo build' <<<"$output"

test ! -e "$tmp/.saad-agent"
test ! -e "$tmp/.serena"
test ! -e "$tmp/.codegraph"

echo "smoke tests passed"
