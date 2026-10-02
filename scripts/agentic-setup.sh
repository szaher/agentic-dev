#!/usr/bin/env bash
set -Eeuo pipefail

if [[ "$(uname -s)" == "Linux" ]]; then
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
  exec /usr/bin/env bash "$SCRIPT_DIR/agentic-setup-linux.sh" "$@"
fi

# One-time macOS bootstrap for a high-quality local coding-agent workstation.
# Safe to rerun. Homebrew must already be installed.
#
# Philosophy:
# - install a small universal foundation once;
# - optionally pre-install language/toolchain support;
# - let `agentic repo init` detect repo-specific needs later.

BOLD='\033[1m'; GREEN='\033[0;32m'; YELLOW='\033[0;33m'; BLUE='\033[0;34m'; RED='\033[0;31m'; RESET='\033[0m'

CONFIGURE_AGENTS=0
SKIP_BREW_UPDATE=0
LANGUAGE_SPEC=""
SCAN_ROOT=""
ALL_LANGUAGES=0
NO_GLOBAL_INSTRUCTIONS=0

usage() {
  cat <<'USAGE'
Usage: agentic setup [options]

Options:
  --configure-agents        Configure detected coding agents for Serena/CodeGraph.
  --languages LIST          Pre-install language support, comma separated.
                            Example: python,go,rust,node,java,cpp,terraform
  --all-languages           Install the common language/toolchain set.
  --scan-root PATH          Detect languages used by Git repos below PATH and install
                            the matching language/toolchain support.
  --skip-brew-update        Skip `brew update`.
  --no-global-instructions  Do not install/update the managed Claude/Codex tool policy.
  -h, --help                Show help.

Examples:
  agentic-setup.sh
  agentic-setup.sh --languages python,go,rust,node
  agentic-setup.sh --scan-root ~/saad/projects
  agentic-setup.sh --all-languages --configure-agents
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --configure-agents) CONFIGURE_AGENTS=1 ;;
    --languages) shift; LANGUAGE_SPEC="${1:-}" ;;
    --all-languages) ALL_LANGUAGES=1 ;;
    --scan-root) shift; SCAN_ROOT="${1:-}" ;;
    --skip-brew-update) SKIP_BREW_UPDATE=1 ;;
    --no-global-instructions) NO_GLOBAL_INSTRUCTIONS=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

info()    { printf "\n${BLUE}${BOLD}==>${RESET} %s\n" "$*"; }
success() { printf "${GREEN}✓${RESET} %s\n" "$*"; }
warn()    { printf "${YELLOW}!${RESET} %s\n" "$*"; }
fail()    { printf "${RED}✗${RESET} %s\n" "$*" >&2; exit 1; }
have()    { command -v "$1" >/dev/null 2>&1; }

[[ "$(uname -s)" == "Darwin" ]] || fail "This script is intended for macOS."
have brew || fail "Homebrew is required."

brew_install_if_available() {
  local formula="$1"
  if brew list --formula "$formula" >/dev/null 2>&1; then
    success "$formula already installed"
  elif brew info "$formula" >/dev/null 2>&1; then
    brew install "$formula"
  else
    warn "Homebrew formula not available: $formula"
    return 1
  fi
}

npm_global_if_missing() {
  local command_name="$1" package="$2"
  if have "$command_name"; then
    success "$command_name already available"
  elif have npm; then
    npm install -g "$package"
  else
    warn "npm is not available; cannot install $package"
    return 1
  fi
}

if [[ "$SKIP_BREW_UPDATE" -eq 0 ]]; then
  info "Updating Homebrew metadata"
  brew update
fi

BASE_PACKAGES=(
  git gh git-delta ripgrep fd fzf jq yq bat eza just direnv mise uv ast-grep
  shellcheck shfmt hyperfine watchexec repomix
)

info "Installing universal CLI foundation"
for package in "${BASE_PACKAGES[@]}"; do
  brew_install_if_available "$package" || true
done

export PATH="$HOME/.local/bin:$PATH"
ZSHRC="$HOME/.zshrc"; touch "$ZSHRC"
append_once() {
  local marker="$1" line="$2"
  if ! grep -Fq "$marker" "$ZSHRC"; then
    printf '\n# %s\n%s\n' "$marker" "$line" >> "$ZSHRC"
    success "Configured $marker"
  fi
}

info "Configuring zsh"
append_once "saad-dev: local bin" 'export PATH="$HOME/.local/bin:$PATH"'
append_once "saad-dev: mise" 'eval "$(mise activate zsh)"'
append_once "saad-dev: direnv" 'eval "$(direnv hook zsh)"'
append_once "saad-dev: fzf" 'source <(fzf --zsh)'

eval "$(mise activate bash)"

info "Installing Node.js LTS through mise"
mise use --global node@lts
success "Node $(node --version)"

info "Installing/updating Serena"
if uv tool list 2>/dev/null | grep -q '^serena-agent '; then uv tool upgrade serena-agent; else uv tool install -p 3.13 serena-agent; fi
if have serena; then
  [[ -f "$HOME/.serena/serena_config.yml" ]] || serena init
  success "Serena ready"
else
  warn "Serena not visible on PATH yet; restart the shell."
fi

info "Installing/updating CodeGraph"
if have codegraph; then
  codegraph upgrade || warn "CodeGraph upgrade failed; keeping current version."
else
  tmp_installer="$(mktemp)"; trap 'rm -f "${tmp_installer:-}"' EXIT
  curl -fsSL https://raw.githubusercontent.com/colbymchenry/codegraph/main/install.sh -o "$tmp_installer"
  /bin/sh "$tmp_installer"
  rm -f "$tmp_installer"; trap - EXIT
fi

info "Preparing Context7"
npx --yes ctx7 --help >/dev/null 2>&1 || true

normalize_language() {
  local value
  value="$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')"
  case "$value" in
    js|javascript|ts|typescript|nodejs) echo node ;;
    c|c++|clang|clangd) echo cpp ;;
    golang) echo go ;;
    rs) echo rust ;;
    py) echo python ;;
    tf|tofu|opentofu) echo terraform ;;
    sh|bash|zsh) echo shell ;;
    k8s|kubernetes|helm|kustomize) echo kubernetes ;;
    *) echo "$value" ;;
  esac
}

LANGS=()
add_lang() {
  local l; l="$(normalize_language "$1")"
  [[ -n "$l" ]] || return 0
  local x; for x in "${LANGS[@]:-}"; do [[ "$x" == "$l" ]] && return 0; done
  LANGS+=("$l")
}

scan_languages() {
  local root="$1"
  [[ -d "$root" ]] || { warn "Scan root does not exist: $root"; return; }
  info "Scanning repositories under $root"
  while IFS= read -r gitdir; do
    local repo="${gitdir%/.git}"
    [[ -f "$repo/pyproject.toml" || -f "$repo/requirements.txt" ]] && add_lang python
    [[ -f "$repo/go.mod" ]] && add_lang go
    [[ -f "$repo/Cargo.toml" ]] && add_lang rust
    [[ -f "$repo/package.json" ]] && add_lang node
    [[ -f "$repo/pom.xml" || -f "$repo/build.gradle" || -f "$repo/build.gradle.kts" ]] && add_lang java
    [[ -f "$repo/CMakeLists.txt" || -f "$repo/meson.build" ]] && add_lang cpp
    [[ -f "$repo/Gemfile" ]] && add_lang ruby
    [[ -f "$repo/composer.json" ]] && add_lang php
    [[ -f "$repo/Package.swift" ]] && add_lang swift
    find "$repo" -maxdepth 2 -type f -name '*.tf' -print -quit 2>/dev/null | grep -q . && add_lang terraform || true
    [[ -f "$repo/Chart.yaml" || -f "$repo/kustomization.yaml" || -d "$repo/charts" ]] && add_lang kubernetes
  done < <(fd --hidden --type d --max-depth 5 '^\.git$' "$root" 2>/dev/null)
}

install_language_support() {
  local lang="$1"
  info "Language/toolchain support: $lang"
  case "$lang" in
    python)
      success "Python agent support uses uv/uvx; project-specific Python versions are handled per repo"
      ;;
    node)
      have node || mise use --global node@lts
      npm_global_if_missing typescript-language-server typescript-language-server || true
      npm_global_if_missing yaml-language-server yaml-language-server || true
      ;;
    go)
      brew_install_if_available go || true
      brew_install_if_available gopls || true
      ;;
    rust)
      if ! have rustup; then brew_install_if_available rustup || brew_install_if_available rust || true; fi
      if have rustup; then
        rustup toolchain list | grep -q '^stable' || rustup toolchain install stable
        rustup default stable >/dev/null 2>&1 || true
        rustup component add rust-analyzer rustfmt clippy || true
      elif ! have rust-analyzer; then
        brew_install_if_available rust-analyzer || true
      fi
      ;;
    java)
      have java || brew_install_if_available openjdk || true
      brew_install_if_available jdtls || true
      ;;
    kotlin)
      brew_install_if_available kotlin || true
      brew_install_if_available kotlin-language-server || true
      ;;
    cpp)
      have clangd || brew_install_if_available llvm || true
      brew_install_if_available cmake || true
      brew_install_if_available ninja || true
      ;;
    ruby)
      have ruby || brew_install_if_available ruby || true
      if have gem && ! have ruby-lsp; then gem install ruby-lsp || warn "Could not install ruby-lsp"; fi
      ;;
    php)
      have php || brew_install_if_available php || true
      have composer || brew_install_if_available composer || true
      ;;
    swift)
      xcrun --find sourcekit-lsp >/dev/null 2>&1 || warn "Swift detected: install Xcode Command Line Tools/Xcode for sourcekit-lsp"
      ;;
    terraform)
      brew_install_if_available terraform-ls || true
      if ! have terraform && ! have tofu; then warn "Terraform repo support needs terraform or tofu on PATH; install the runtime you actually use."; fi
      ;;
    shell)
      brew_install_if_available shellcheck || true; brew_install_if_available shfmt || true
      ;;
    kubernetes)
      brew_install_if_available kubectl || true
      brew_install_if_available helm || true
      brew_install_if_available kustomize || true
      ;;
    protobuf)
      brew_install_if_available protobuf || true; brew_install_if_available buf || true
      ;;
    lua)
      brew_install_if_available lua || true; brew_install_if_available lua-language-server || true
      ;;
    *) warn "No automatic installer defined for language/tool group: $lang" ;;
  esac
}

if [[ "$ALL_LANGUAGES" -eq 1 ]]; then
  for l in python node go rust java cpp ruby php swift terraform shell kubernetes protobuf lua; do add_lang "$l"; done
fi
if [[ -n "$LANGUAGE_SPEC" ]]; then
  IFS=',' read -ra req_langs <<< "$LANGUAGE_SPEC"
  for l in "${req_langs[@]}"; do add_lang "$l"; done
fi
[[ -n "$SCAN_ROOT" ]] && scan_languages "$SCAN_ROOT"

if [[ ${#LANGS[@]} -gt 0 ]]; then
  info "Installing requested/detected language support: ${LANGS[*]}"
  for l in "${LANGS[@]}"; do install_language_support "$l"; done
fi

info "Applying useful Git defaults"
git config --global init.defaultBranch main
git config --global fetch.prune true
git config --global rerere.enabled true
git config --global merge.conflictstyle zdiff3
git config --global core.pager delta
git config --global interactive.diffFilter 'delta --color-only'
git config --global delta.navigate true
git config --global delta.line-numbers true

mkdir -p "$HOME/Developer" "$HOME/Developer/worktrees" "$HOME/.config/coding-agents"

install_global_agent_policy() {
  [[ "$NO_GLOBAL_INSTRUCTIONS" -eq 0 ]] || return 0

  local script_dir policy_file="" candidate tmp start_marker end_marker
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
  for candidate in \
    "${AGENTIC_DEV_POLICY_FILE:-}" \
    "$script_dir/../templates/global-agent-policy.md" \
    "$HOME/.config/agentic-dev/templates/global-agent-policy.md"; do
    [[ -n "$candidate" && -f "$candidate" ]] && { policy_file="$candidate"; break; }
  done

  if [[ -z "$policy_file" ]]; then
    warn "Global agent policy template not found; install the repo with ./install.sh first."
    return 0
  fi

  start_marker='<!-- agentic-dev:start -->'
  end_marker='<!-- agentic-dev:end -->'
  legacy_start_marker='<!-- agentic-dev-env:start -->'
  legacy_end_marker='<!-- agentic-dev-env:end -->'

  update_policy_file() {
    local target="$1"
    mkdir -p "$(dirname "$target")"
    touch "$target"
    tmp="$(mktemp)"
    awk \
      -v start="$start_marker" -v end="$end_marker" \
      -v legacy_start="$legacy_start_marker" -v legacy_end="$legacy_end_marker" '
      $0 == start || $0 == legacy_start { skipping=1; next }
      $0 == end || $0 == legacy_end { skipping=0; next }
      !skipping { print }
    ' "$target" > "$tmp"
    mv "$tmp" "$target"
    {
      printf '\n%s\n' "$start_marker"
      cat "$policy_file"
      printf '%s\n' "$end_marker"
    } >> "$target"
    success "Updated managed tool policy in $target"
  }

  have claude && update_policy_file "$HOME/.claude/CLAUDE.md"
  have codex && update_policy_file "$HOME/.codex/AGENTS.md"
}

if [[ "$CONFIGURE_AGENTS" -eq 1 ]]; then
  info "Configuring detected coding agents"
  if have serena; then
    have claude && serena setup claude-code || true
    have codex && serena setup codex || true
  fi
  have codegraph && codegraph install --target=auto --location=global --yes || true
  install_global_agent_policy
  if have agentic; then
    agentic integrations install all || warn "One or more native agent integrations need manual attention."
  else
    warn "Unified 'agentic' CLI not found; run ./install.sh before configuring native plugins/packages."
  fi
  warn "Context7 remains interactive: npx ctx7 setup --claude / --codex"
fi

info "Installed tool summary"
for cmd in git gh delta rg fd fzf jq yq bat eza just direnv mise uv ast-grep shellcheck shfmt hyperfine watchexec repomix node serena codegraph go gopls cargo rustup rust-analyzer java clangd terraform terraform-ls kubectl helm kustomize; do
  if have "$cmd"; then printf '  %-20s %s\n' "$cmd" "$(command -v "$cmd")"; fi
done

have gh && gh auth status >/dev/null 2>&1 || warn "GitHub CLI may need authentication: gh auth login"

cat <<'NEXT'

Setup complete.

Typical next steps:
  exec zsh
  gh auth login
  codegraph install
  npx ctx7 setup --claude
  npx ctx7 setup --codex
  agentic integrations status

Then, for each repository:
  agentic-repo-init.sh .
NEXT
