#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
BIN_DIR="${AGENTIC_DEV_ENV_BIN_DIR:-$HOME/.local/bin}"
CONFIG_DIR="${AGENTIC_DEV_ENV_CONFIG_DIR:-$HOME/.config/agentic-dev-env}"
PYTHON_APP_DIR="$CONFIG_DIR/python"

mkdir -p "$BIN_DIR" "$CONFIG_DIR/templates" "$PYTHON_APP_DIR"

install -m 0755 "$ROOT/scripts/setup-coding-agent-env.sh" "$BIN_DIR/setup-coding-agent-env.sh"
install -m 0755 "$ROOT/scripts/setup-linux-agent-env.sh" "$BIN_DIR/setup-linux-agent-env.sh"
install -m 0755 "$ROOT/scripts/saad-tool-repo-init.sh" "$BIN_DIR/saad-tool-repo-init.sh"
install -m 0644 "$ROOT/templates/global-agent-policy.md" "$CONFIG_DIR/templates/global-agent-policy.md"

rm -rf "$PYTHON_APP_DIR/agentic_dev_env"
cp -R "$ROOT/src/agentic_dev_env" "$PYTHON_APP_DIR/agentic_dev_env"

cat > "$BIN_DIR/agentic" <<'WRAPPER'
#!/usr/bin/env bash
set -Eeuo pipefail
APP_DIR="${AGENTIC_DEV_ENV_CONFIG_DIR:-$HOME/.config/agentic-dev-env}/python"
export PYTHONPATH="$APP_DIR${PYTHONPATH:+:$PYTHONPATH}"

for candidate in python3.13 python3.12 python3.11 python3; do
  if command -v "$candidate" >/dev/null 2>&1; then
    if "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)' 2>/dev/null; then
      exec "$candidate" -m agentic_dev_env.cli "$@"
    fi
  fi
done

if command -v uv >/dev/null 2>&1; then
  exec uv run --no-project --python 3.11 python -m agentic_dev_env.cli "$@"
fi

echo "agentic requires Python 3.11+ or uv. Run setup-coding-agent-env.sh first." >&2
exit 2
WRAPPER
chmod +x "$BIN_DIR/agentic"

ln -sfn "$BIN_DIR/setup-coding-agent-env.sh" "$BIN_DIR/agentic-dev-setup"
ln -sfn "$BIN_DIR/saad-tool-repo-init.sh" "$BIN_DIR/agentic-repo-init"

SHELL_NAME="$(basename "${SHELL:-sh}")"
case "$SHELL_NAME" in
  zsh) SHELL_RC="$HOME/.zshrc" ;;
  bash) SHELL_RC="$HOME/.bashrc" ;;
  *) SHELL_RC="$HOME/.profile" ;;
esac
touch "$SHELL_RC"
if ! grep -Fq '# agentic-dev-env: local bin' "$SHELL_RC"; then
  printf '\n# agentic-dev-env: local bin\nexport PATH="$HOME/.local/bin:$PATH"\n' >> "$SHELL_RC"
fi

VERSION="$(awk -F'"' '/^version = / {print $2; exit}' "$ROOT/pyproject.toml")"
ROOT_JSON="$(printf '%s' "$ROOT" | sed 's/\\/\\\\/g; s/"/\\"/g')"
cat > "$CONFIG_DIR/install.json" <<EOF_META
{
  "schema_version": "1",
  "source_root": "$ROOT_JSON",
  "installed_version": "$VERSION"
}
EOF_META

cat <<EOF2
Installed agentic-dev-env.

Primary CLI:
  agentic

Compatibility commands:
  setup-coding-agent-env.sh
  saad-tool-repo-init.sh
  agentic-dev-setup
  agentic-repo-init

Next:
  restart your shell (or source $SHELL_RC)
  agentic-dev-setup --scan-root ~/projects --configure-agents
  agentic doctor
  agentic compatibility
EOF2
