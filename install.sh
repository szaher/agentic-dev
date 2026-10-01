#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
BIN_DIR="${AGENTIC_DEV_ENV_BIN_DIR:-$HOME/.local/bin}"
CONFIG_DIR="${AGENTIC_DEV_ENV_CONFIG_DIR:-$HOME/.config/agentic-dev-env}"

mkdir -p "$BIN_DIR" "$CONFIG_DIR/templates"

install -m 0755 "$ROOT/scripts/setup-coding-agent-env.sh" "$BIN_DIR/setup-coding-agent-env.sh"
install -m 0755 "$ROOT/scripts/saad-tool-repo-init.sh" "$BIN_DIR/saad-tool-repo-init.sh"
install -m 0644 "$ROOT/templates/global-agent-policy.md" "$CONFIG_DIR/templates/global-agent-policy.md"

ln -sfn "$BIN_DIR/setup-coding-agent-env.sh" "$BIN_DIR/agentic-dev-setup"
ln -sfn "$BIN_DIR/saad-tool-repo-init.sh" "$BIN_DIR/agentic-repo-init"

ZSHRC="$HOME/.zshrc"
touch "$ZSHRC"
if ! grep -Fq '# agentic-dev-env: local bin' "$ZSHRC"; then
  printf '\n# agentic-dev-env: local bin\nexport PATH="$HOME/.local/bin:$PATH"\n' >> "$ZSHRC"
fi

cat <<EOF2
Installed agentic-dev-env.

Commands:
  setup-coding-agent-env.sh
  saad-tool-repo-init.sh

Aliases:
  agentic-dev-setup
  agentic-repo-init

Next:
  exec zsh
  agentic-dev-setup --scan-root ~/saad/projects --configure-agents
EOF2
