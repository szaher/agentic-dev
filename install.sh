#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
BIN_DIR="${AGENTIC_DEV_BIN_DIR:-${AGENTIC_DEV_ENV_BIN_DIR:-$HOME/.local/bin}}"
CONFIG_DIR="${AGENTIC_DEV_CONFIG_DIR:-${AGENTIC_DEV_ENV_CONFIG_DIR:-$HOME/.config/agentic-dev}}"
PYTHON_APP_DIR="$CONFIG_DIR/python"

mkdir -p "$BIN_DIR" "$CONFIG_DIR/templates" "$PYTHON_APP_DIR"

install -m 0755 "$ROOT/scripts/agentic-setup.sh" "$BIN_DIR/agentic-setup.sh"
install -m 0755 "$ROOT/scripts/agentic-setup-linux.sh" "$BIN_DIR/agentic-setup-linux.sh"
install -m 0755 "$ROOT/scripts/agentic-repo-init.sh" "$BIN_DIR/agentic-repo-init.sh"
install -m 0644 "$ROOT/templates/global-agent-policy.md" "$CONFIG_DIR/templates/global-agent-policy.md"

rm -rf "$PYTHON_APP_DIR/agentic_dev"
cp -R "$ROOT/src/agentic_dev" "$PYTHON_APP_DIR/agentic_dev"

cat > "$BIN_DIR/agentic" <<'WRAPPER'
#!/usr/bin/env bash
set -Eeuo pipefail
APP_DIR="${AGENTIC_DEV_CONFIG_DIR:-$HOME/.config/agentic-dev}/python"
export PYTHONPATH="$APP_DIR${PYTHONPATH:+:$PYTHONPATH}"

for candidate in python3.13 python3.12 python3.11 python3; do
  if command -v "$candidate" >/dev/null 2>&1; then
    if "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)' 2>/dev/null; then
      exec "$candidate" -m agentic_dev.cli "$@"
    fi
  fi
done

if command -v uv >/dev/null 2>&1; then
  exec uv run --no-project --python 3.11 python -m agentic_dev.cli "$@"
fi

echo "agentic requires Python 3.11+ or uv. Run 'agentic setup' after installing Agentic Dev." >&2
exit 2
WRAPPER
chmod +x "$BIN_DIR/agentic"

# One transition release of compatibility aliases for pre-rename source installs.
ln -sfn "$BIN_DIR/agentic-setup.sh" "$BIN_DIR/setup-coding-agent-env.sh"
ln -sfn "$BIN_DIR/agentic-setup-linux.sh" "$BIN_DIR/setup-coding-agent-env-linux.sh"
ln -sfn "$BIN_DIR/agentic-repo-init.sh" "$BIN_DIR/saad-tool-repo-init.sh"
ln -sfn "$BIN_DIR/agentic-setup.sh" "$BIN_DIR/agentic-dev-setup"
ln -sfn "$BIN_DIR/agentic-repo-init.sh" "$BIN_DIR/agentic-repo-init"


SHELL_RC="$HOME/.zshrc"
if [[ "$(uname -s)" == "Linux" && "${SHELL:-}" != *zsh ]]; then SHELL_RC="$HOME/.bashrc"; fi
touch "$SHELL_RC"
if ! grep -Fq '# agentic-dev: local bin' "$SHELL_RC"; then
  printf '\n# agentic-dev: local bin\nexport PATH="$HOME/.local/bin:$PATH"\n' >> "$SHELL_RC"
fi

cat <<EOF2
Installed Agentic Dev.

Primary CLI:
  agentic

Legacy helper aliases are installed for one transition release.
Use the canonical commands in new automation:
  agentic setup
  agentic repo init

Next:
  exec "${SHELL:-zsh}"
  agentic setup --scan-root ~/saad/projects --configure-agents
  agentic doctor
EOF2
