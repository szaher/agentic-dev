#!/usr/bin/env bash
set -Eeuo pipefail

BOLD='\033[1m'; GREEN='\033[0;32m'; YELLOW='\033[0;33m'; BLUE='\033[0;34m'; RED='\033[0;31m'; RESET='\033[0m'
CONFIGURE_AGENTS=0
LANGUAGE_SPEC=""
SCAN_ROOT=""
ALL_LANGUAGES=0
NO_GLOBAL_INSTRUCTIONS=0

usage() {
  cat <<'USAGE'
Usage: setup-linux-agent-env.sh [options]

Options:
  --configure-agents
  --languages LIST
  --all-languages
  --scan-root PATH
  --no-global-instructions
  --skip-brew-update          Accepted for cross-platform compatibility; ignored.
  -h, --help
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --configure-agents) CONFIGURE_AGENTS=1 ;;
    --languages) shift; LANGUAGE_SPEC="${1:-}" ;;
    --all-languages) ALL_LANGUAGES=1 ;;
    --scan-root) shift; SCAN_ROOT="${1:-}" ;;
    --no-global-instructions) NO_GLOBAL_INSTRUCTIONS=1 ;;
    --skip-brew-update) : ;;
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

[[ "$(uname -s)" == "Linux" ]] || fail "Linux setup called on a non-Linux system."

if grep -qiE '(microsoft|wsl)' /proc/version 2>/dev/null; then
  info "WSL detected"
fi

PKG=""
if have apt-get; then PKG="apt"
elif have dnf; then PKG="dnf"
elif have pacman; then PKG="pacman"
else warn "No supported package manager found (apt/dnf/pacman)."; fi

pkg_install() {
  local packages=("$@")
  [[ -n "$PKG" ]] || return 1
  case "$PKG" in
    apt)
      sudo apt-get update -qq
      sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y "${packages[@]}"
      ;;
    dnf) sudo dnf install -y "${packages[@]}" ;;
    pacman) sudo pacman -Sy --needed --noconfirm "${packages[@]}" ;;
  esac
}

info "Installing common Linux CLI foundation"
case "$PKG" in
  apt) pkg_install git curl ca-certificates jq fzf ripgrep shellcheck shfmt python3 python3-venv python3-pip nodejs npm || true ;;
  dnf) pkg_install git curl ca-certificates jq fzf ripgrep ShellCheck shfmt python3 python3-pip nodejs npm || true ;;
  pacman) pkg_install git curl ca-certificates jq fzf ripgrep shellcheck shfmt python python-pip nodejs npm || true ;;
esac

mkdir -p "$HOME/.local/bin"
export PATH="$HOME/.local/bin:$PATH"

if ! have uv; then
  info "Installing uv from its official installer"
  tmp="$(mktemp)"
  trap 'rm -f "${tmp:-}"' EXIT
  curl -LsSf https://astral.sh/uv/install.sh -o "$tmp"
  sh "$tmp"
  rm -f "$tmp"; trap - EXIT
fi

if ! have mise; then
  warn "mise is not installed. Install it from https://mise.jdx.dev/ for runtime-version management."
fi

if have uv; then
  info "Installing/updating Serena"
  if uv tool list 2>/dev/null | grep -q '^serena-agent '; then
    uv tool upgrade serena-agent || true
  else
    uv tool install -p 3.13 serena-agent || uv tool install serena-agent || true
  fi
  have serena && [[ -f "$HOME/.serena/serena_config.yml" ]] || { have serena && serena init || true; }
fi

if ! have codegraph; then
  info "Installing CodeGraph"
  tmp="$(mktemp)"
  trap 'rm -f "${tmp:-}"' EXIT
  curl -fsSL https://raw.githubusercontent.com/colbymchenry/codegraph/main/install.sh -o "$tmp"
  sh "$tmp" || warn "CodeGraph installer failed"
  rm -f "$tmp"; trap - EXIT
fi

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
  local l x
  l="$(normalize_language "$1")"
  [[ -n "$l" ]] || return 0
  for x in "${LANGS[@]:-}"; do [[ "$x" == "$l" ]] && return 0; done
  LANGS+=("$l")
}

scan_languages() {
  local root="$1" repo
  [[ -d "$root" ]] || return 0
  while IFS= read -r gitdir; do
    repo="${gitdir%/.git}"
    [[ -f "$repo/pyproject.toml" || -f "$repo/requirements.txt" ]] && add_lang python
    [[ -f "$repo/go.mod" ]] && add_lang go
    [[ -f "$repo/Cargo.toml" ]] && add_lang rust
    [[ -f "$repo/package.json" ]] && add_lang node
    [[ -f "$repo/pom.xml" || -f "$repo/build.gradle" || -f "$repo/build.gradle.kts" ]] && add_lang java
    [[ -f "$repo/CMakeLists.txt" ]] && add_lang cpp
    find "$repo" -maxdepth 2 -name '*.tf' -print -quit 2>/dev/null | grep -q . && add_lang terraform || true
    [[ -f "$repo/Chart.yaml" || -f "$repo/kustomization.yaml" ]] && add_lang kubernetes
  done < <(find "$root" -maxdepth 5 -type d -name .git -print 2>/dev/null)
}

install_language_support() {
  local lang="$1"
  case "$lang" in
    python) success "Python support uses uv" ;;
    node) have npm && { have typescript-language-server || sudo npm install -g typescript-language-server typescript || true; } ;;
    go)
      case "$PKG" in apt) pkg_install golang-go || true ;; dnf) pkg_install golang || true ;; pacman) pkg_install go || true ;; esac
      have go && go install golang.org/x/tools/gopls@latest || true
      ;;
    rust)
      if ! have rustup; then
        tmp="$(mktemp)"
        if curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs -o "$tmp"; then
          sh "$tmp" -y || true
        fi
        rm -f "$tmp"
        export PATH="$HOME/.cargo/bin:$PATH"
      fi
      have rustup && rustup component add rust-analyzer rustfmt clippy || true
      ;;
    java) case "$PKG" in apt) pkg_install default-jdk || true ;; dnf) pkg_install java-latest-openjdk-devel || true ;; pacman) pkg_install jdk-openjdk || true ;; esac ;;
    cpp) case "$PKG" in apt) pkg_install clang cmake ninja-build || true ;; dnf) pkg_install clang cmake ninja-build || true ;; pacman) pkg_install clang cmake ninja || true ;; esac ;;
    terraform) warn "Install Terraform/OpenTofu and terraform-ls using your organization-approved source." ;;
    kubernetes) warn "Install kubectl/oc/helm using your cluster/vendor-approved package source." ;;
    shell) success "Shell support installed with shellcheck/shfmt where available" ;;
    *) warn "No Linux automatic installer defined for: $lang" ;;
  esac
}

if [[ "$ALL_LANGUAGES" -eq 1 ]]; then
  for l in python node go rust java cpp terraform shell kubernetes; do add_lang "$l"; done
fi
if [[ -n "$LANGUAGE_SPEC" ]]; then
  IFS=',' read -ra req <<< "$LANGUAGE_SPEC"
  for l in "${req[@]}"; do add_lang "$l"; done
fi
[[ -n "$SCAN_ROOT" ]] && scan_languages "$SCAN_ROOT"
for l in "${LANGS[@]:-}"; do install_language_support "$l"; done

install_global_policy() {
  [[ "$NO_GLOBAL_INSTRUCTIONS" -eq 0 ]] || return 0
  local script_dir policy start end
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
  policy="${AGENTIC_DEV_ENV_POLICY_FILE:-$HOME/.config/agentic-dev-env/templates/global-agent-policy.md}"
  [[ -f "$policy" ]] || policy="$script_dir/../templates/global-agent-policy.md"
  [[ -f "$policy" ]] || { warn "Global policy template unavailable"; return 0; }
  start='<!-- agentic-dev-env:start -->'; end='<!-- agentic-dev-env:end -->'
  update_one() {
    local target="$1" tmp
    mkdir -p "$(dirname "$target")"; touch "$target"
    tmp="$(mktemp)"
    awk -v s="$start" -v e="$end" '$0==s{skip=1;next}$0==e{skip=0;next}!skip{print}' "$target" > "$tmp"
    mv "$tmp" "$target"
    { printf '\n%s\n' "$start"; cat "$policy"; printf '%s\n' "$end"; } >> "$target"
  }
  have claude && update_one "$HOME/.claude/CLAUDE.md"
  have codex && update_one "$HOME/.codex/AGENTS.md"
}

if [[ "$CONFIGURE_AGENTS" -eq 1 ]]; then
  install_global_policy
  have serena && have claude && serena setup claude-code || true
  have serena && have codex && serena setup codex || true
  have codegraph && codegraph install --target=auto --location=global --yes || true
  have agentic && agentic integrations install all || true
fi

info "Linux/WSL setup complete"
have agentic && agentic compatibility --json || true
