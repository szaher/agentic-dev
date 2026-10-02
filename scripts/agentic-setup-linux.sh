#!/usr/bin/env bash
set -Eeuo pipefail

CONFIGURE_AGENTS=0
LANGUAGE_SPEC=''
SCAN_ROOT=''
ALL_LANGUAGES=0
NO_GLOBAL_INSTRUCTIONS=0

info() { printf '\n==> %s\n' "$*"; }
warn() { printf '! %s\n' "$*" >&2; }
have() { command -v "$1" >/dev/null 2>&1; }

usage() {
  cat <<'USAGE'
Usage: agentic setup [options]
Linux/WSL workstation bootstrap.

  --configure-agents
  --languages LIST
  --all-languages
  --scan-root PATH
  --skip-brew-update        Accepted for compatibility; ignored.
  --no-global-instructions
  -h, --help
USAGE
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --configure-agents) CONFIGURE_AGENTS=1 ;;
    --languages) shift; LANGUAGE_SPEC="$1" ;;
    --all-languages) ALL_LANGUAGES=1 ;;
    --scan-root) shift; SCAN_ROOT="$1" ;;
    --skip-brew-update) : ;;
    --no-global-instructions) NO_GLOBAL_INSTRUCTIONS=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

[ "$(uname -s)" = Linux ] || { echo 'Linux bootstrap invoked on non-Linux host.' >&2; exit 1; }
PLATFORM=linux
grep -qi microsoft /proc/version 2>/dev/null && PLATFORM=wsl || true
info "Platform: $PLATFORM"

SUDO=''
if [ "$(id -u)" -ne 0 ] && have sudo; then SUDO=sudo; fi

pkg_install() {
  if have brew; then brew install "$@" || true; return; fi
  if have apt-get; then
    $SUDO apt-get update -y
    DEBIAN_FRONTEND=noninteractive $SUDO apt-get install -y "$@" || true
    return
  fi
  if have dnf; then $SUDO dnf install -y "$@" || true; return; fi
  if have pacman; then $SUDO pacman -Sy --needed --noconfirm "$@" || true; return; fi
  warn 'No supported package manager found (brew/apt/dnf/pacman).'
}

info 'Installing portable CLI foundation'
if have apt-get; then
  pkg_install git curl ca-certificates python3 python3-venv ripgrep fd-find fzf jq bat shellcheck shfmt direnv openssh-client
elif have dnf; then
  pkg_install git curl ca-certificates python3 ripgrep fd-find fzf jq bat shellcheck shfmt direnv openssh-clients
elif have pacman; then
  pkg_install git curl ca-certificates python ripgrep fd fzf jq bat shellcheck shfmt direnv openssh
else
  pkg_install git curl python3 ripgrep fd fzf jq bat shellcheck shfmt direnv
fi

mkdir -p "$HOME/.local/bin"
if ! have fd && have fdfind; then ln -sfn "$(command -v fdfind)" "$HOME/.local/bin/fd"; fi
if ! have bat && have batcat; then ln -sfn "$(command -v batcat)" "$HOME/.local/bin/bat"; fi
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"

if ! have uv; then
  info 'Installing uv'
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi

if ! have mise; then
  info 'Installing mise'
  curl https://mise.run | sh
fi
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"

if have mise; then mise use --global node@lts || warn 'Node.js setup through mise failed'; fi
if have npm; then
  have ast-grep || npm install -g @ast-grep/cli || true
  have repomix || npm install -g repomix || true
fi

if have uv; then
  if uv tool list 2>/dev/null | grep -q '^serena-agent '; then uv tool upgrade serena-agent || true;
  else uv tool install serena-agent || true; fi
fi

if ! have codegraph; then
  info 'Installing CodeGraph'
  tmp_installer=$(mktemp)
  curl -fsSL https://raw.githubusercontent.com/colbymchenry/codegraph/main/install.sh -o "$tmp_installer"
  /bin/sh "$tmp_installer" || warn 'CodeGraph installation failed'
  rm -f "$tmp_installer"
fi

install_language() {
  case "$1" in
    python) : ;;
    node) have node || { have mise && mise use --global node@lts; } ;;
    go) pkg_install golang-go go ;;
    rust)
      if ! have rustup; then curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y || true; fi
      have rustup && rustup component add rust-analyzer rustfmt clippy || true
      ;;
    java) pkg_install default-jdk java-17-openjdk ;;
    cpp) pkg_install clang cmake ninja-build ninja ;;
    shell) pkg_install shellcheck shfmt ;;
    terraform) warn 'Install Terraform/OpenTofu and terraform-ls from your vendor/distro repository.' ;;
    kubernetes) warn 'Install kubectl/oc/helm from your vendor/distro repository when needed.' ;;
    *) warn "No automatic Linux installer for $1" ;;
  esac
}

if [ "$ALL_LANGUAGES" -eq 1 ]; then LANGUAGE_SPEC='python,node,go,rust,java,cpp,terraform,shell,kubernetes'; fi
if [ -n "$SCAN_ROOT" ] && [ -d "$SCAN_ROOT" ]; then
  detected=''
  find "$SCAN_ROOT" -maxdepth 5 -type f \( -name pyproject.toml -o -name requirements.txt \) -print -quit | grep -q . && detected="$detected,python" || true
  find "$SCAN_ROOT" -maxdepth 5 -type f -name go.mod -print -quit | grep -q . && detected="$detected,go" || true
  find "$SCAN_ROOT" -maxdepth 5 -type f -name Cargo.toml -print -quit | grep -q . && detected="$detected,rust" || true
  find "$SCAN_ROOT" -maxdepth 5 -type f -name package.json -print -quit | grep -q . && detected="$detected,node" || true
  LANGUAGE_SPEC="$LANGUAGE_SPEC$detected"
fi
if [ -n "$LANGUAGE_SPEC" ]; then
  oldifs=$IFS; IFS=','
  for lang in $LANGUAGE_SPEC; do [ -n "$lang" ] && install_language "$lang"; done
  IFS=$oldifs
fi

if have git; then
  git config --global init.defaultBranch main
  git config --global fetch.prune true
  git config --global rerere.enabled true
  git config --global merge.conflictstyle zdiff3
fi

install_policy_file() {
  target="$1"
  policy="$2"
  start='<!-- agentic-dev:start -->'
  end='<!-- agentic-dev:end -->'
  legacy_start='<!-- agentic-dev-env:start -->'
  legacy_end='<!-- agentic-dev-env:end -->'
  mkdir -p "$(dirname "$target")"
  touch "$target"
  tmp=$(mktemp)
  awk -v start="$start" -v end="$end" -v legacy_start="$legacy_start" -v legacy_end="$legacy_end" '
    $0 == start || $0 == legacy_start {skip=1; next}
    $0 == end || $0 == legacy_end {skip=0; next}
    !skip {print}
  ' "$target" > "$tmp"
  mv "$tmp" "$target"
  {
    printf '\n%s\n' "$start"
    cat "$policy"
    printf '%s\n' "$end"
  } >> "$target"
}

if [ "$NO_GLOBAL_INSTRUCTIONS" -eq 0 ]; then
  policy="$HOME/.config/agentic-dev/templates/global-agent-policy.md"
  if [ -f "$policy" ]; then
    have claude && install_policy_file "$HOME/.claude/CLAUDE.md" "$policy"
    have codex && install_policy_file "$HOME/.codex/AGENTS.md" "$policy"
  fi
fi

if [ "$CONFIGURE_AGENTS" -eq 1 ]; then
  have serena && have claude && serena setup claude-code || true
  have serena && have codex && serena setup codex || true
  have codegraph && codegraph install --target=auto --location=global --yes || true
  have agentic && agentic integrations install all || true
fi

info 'Installed tool summary'
for cmd in git ssh rg fd fzf jq bat shellcheck shfmt direnv mise uv node npm ast-grep repomix serena codegraph; do
  have "$cmd" && printf '  %-20s %s\n' "$cmd" "$(command -v "$cmd")"
done

echo
echo 'Linux/WSL setup complete.'
echo 'Reload your shell, then run: agentic doctor'
