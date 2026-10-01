#!/usr/bin/env bash
set -Eeuo pipefail

# Smart, conservative per-repository bootstrap for agentic development.

BOLD='\033[1m'; GREEN='\033[0;32m'; YELLOW='\033[0;33m'; BLUE='\033[0;34m'; RED='\033[0;31m'; RESET='\033[0m'
TARGET="."
CHECK_ONLY=0
NO_CODEGRAPH=0
NO_SERENA=0
NO_INSTRUCTIONS=0
NO_INSTALL_LANGUAGE_DEPS=0
NO_RUNTIME_INSTALL=0
INSTALL_PROJECT_DEPS=0
TASK=""
NO_SKILLS=0
SKILLS_YES=0
SKILLS_SHARED=0
SKILLS_TARGET="both"

usage() {
  cat <<'USAGE'
Usage: saad-tool-repo-init.sh [repo-path] [options]

Options:
  --check                     Read-only discovery/readiness report.
  --no-codegraph              Skip CodeGraph initialization.
  --no-serena                 Skip Serena project creation/indexing.
  --no-instructions           Do not create local AGENTS.md / CLAUDE.md.
  --no-install-language-deps  Do not install missing runtime/LSP prerequisites.
  --no-runtime-install        Do not install repo-declared runtime versions.
  --install-project-deps      Run the detected project dependency install command.
  --task TEXT                 Task context used to rank recommended Agent Skills.
  --no-skills                 Skip skill recommendation/activation.
  --skills-yes                Activate recommended skills without prompting.
  --skills-shared             Make selected skills commit-worthy instead of local-only.
  --skills-target TARGET      both, claude, or codex (default: both).
  -h, --help                  Show help.
USAGE
}

positional=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --check) CHECK_ONLY=1 ;;
    --no-codegraph) NO_CODEGRAPH=1 ;;
    --no-serena) NO_SERENA=1 ;;
    --no-instructions) NO_INSTRUCTIONS=1 ;;
    --no-install-language-deps) NO_INSTALL_LANGUAGE_DEPS=1 ;;
    --no-runtime-install) NO_RUNTIME_INSTALL=1 ;;
    --install-project-deps) INSTALL_PROJECT_DEPS=1 ;;
    --task) shift; TASK="${1:-}" ;;
    --no-skills) NO_SKILLS=1 ;;
    --skills-yes) SKILLS_YES=1 ;;
    --skills-shared) SKILLS_SHARED=1 ;;
    --skills-target) shift; SKILLS_TARGET="${1:-both}" ;;
    -h|--help) usage; exit 0 ;;
    -*) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
    *) [[ "$positional" -eq 0 ]] || { echo "Only one repo path may be supplied." >&2; exit 2; }; TARGET="$1"; positional=1 ;;
  esac
  shift
done

info()    { printf "\n${BLUE}${BOLD}==>${RESET} %s\n" "$*"; }
success() { printf "${GREEN}✓${RESET} %s\n" "$*"; }
warn()    { printf "${YELLOW}!${RESET} %s\n" "$*"; }
fail()    { printf "${RED}✗${RESET} %s\n" "$*" >&2; exit 1; }
have()    { command -v "$1" >/dev/null 2>&1; }

[[ -d "$TARGET" ]] || fail "Repository path does not exist: $TARGET"
REPO="$(cd "$TARGET" && pwd -P)"
cd "$REPO"
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || fail "$REPO is not inside a Git working tree."
REPO="$(git rev-parse --show-toplevel)"
cd "$REPO"
REPO_NAME="$(basename "$REPO")"
case "$SKILLS_TARGET" in both|claude|codex) ;; *) fail "--skills-target must be one of: both, claude, codex" ;; esac

LANGUAGES=(); SERENA_LANGUAGES=(); FRAMEWORKS=(); PACKAGE_MANAGERS=(); TOOLS=(); MISSING=()
add_unique() {
  local array="$1" value="$2" current
  eval "current=\" \${${array}[*]-} \""
  [[ "$current" == *" $value "* ]] && return 0
  eval "$array+=(\"\$value\")"
}
add_lang(){ add_unique LANGUAGES "$1"; }
add_serena(){ add_unique SERENA_LANGUAGES "$1"; }
add_framework(){ add_unique FRAMEWORKS "$1"; }
add_pm(){ add_unique PACKAGE_MANAGERS "$1"; }
add_tool(){ add_unique TOOLS "$1"; }
missing(){ add_unique MISSING "$1"; }

find_any() {
  local pattern="$1" depth="${2:-4}"
  if have fd; then
    fd --type f --glob "$pattern" --max-depth "$depth" . 2>/dev/null | head -n1 | grep -q .
  else
    find . \( -path './.git' -o -path './node_modules' -o -path './vendor' -o -path './.venv' -o -path './target' \) -prune -o \
      -type f -name "$pattern" -print 2>/dev/null | head -n1 | grep -q .
  fi
}

if [[ -f pyproject.toml || -f requirements.txt || -f setup.py || -f setup.cfg ]] || find_any '*.py'; then add_lang python; add_serena python; fi
if [[ -f go.mod ]] || find_any '*.go'; then add_lang go; add_serena go; fi
if [[ -f Cargo.toml ]] || find_any '*.rs'; then add_lang rust; add_serena rust; fi

if [[ -f deno.json || -f deno.jsonc ]]; then
  add_lang deno; add_serena deno; add_pm deno
elif [[ -f package.json ]]; then
  add_lang node
  if grep -Eq '"@angular/core"' package.json; then add_framework angular; add_serena angular
  elif grep -Eq '"svelte"' package.json; then add_framework svelte; add_serena svelte
  elif grep -Eq '"vue"' package.json; then add_framework vue; add_serena vue
  else add_serena typescript
  fi
fi

if [[ -f pom.xml || -f build.gradle || -f build.gradle.kts || -f gradlew ]]; then add_lang java; add_serena java; fi
if find_any '*.kt' || find_any '*.kts'; then add_lang kotlin; add_serena kotlin; fi
if [[ -f CMakeLists.txt || -f meson.build ]] || find_any '*.cpp' || find_any '*.cc' || find_any '*.c'; then add_lang cpp; add_serena cpp; fi
if [[ -f Gemfile ]] || find_any '*.rb'; then add_lang ruby; add_serena ruby; fi
if [[ -f composer.json ]] || find_any '*.php'; then add_lang php; add_serena php; fi
if [[ -f Package.swift ]] || find_any '*.swift'; then add_lang swift; add_serena swift; fi
if find_any '*.tf' 3; then add_lang terraform; add_serena terraform; fi
if find_any '*.sh' 3; then add_lang shell; add_serena bash; fi
if find_any '*.lua'; then add_lang lua; add_serena lua; fi
if find_any '*.zig'; then add_lang zig; add_serena zig; fi

[[ -f uv.lock ]] && add_pm uv
[[ -f poetry.lock ]] && add_pm poetry
[[ -f pdm.lock ]] && add_pm pdm
[[ -f pnpm-lock.yaml ]] && add_pm pnpm
[[ -f yarn.lock ]] && add_pm yarn
[[ -f bun.lock || -f bun.lockb ]] && add_pm bun
[[ -f package-lock.json ]] && add_pm npm
[[ -f Cargo.toml ]] && add_pm cargo
[[ -f go.mod ]] && add_pm go-modules
[[ -f Gemfile ]] && add_pm bundler
[[ -f composer.json ]] && add_pm composer
[[ -f gradlew ]] && add_pm gradle-wrapper
[[ -f mvnw ]] && add_pm maven-wrapper
[[ -f pom.xml && ! -f mvnw ]] && add_pm maven
[[ -f build.gradle || -f build.gradle.kts ]] && add_pm gradle

[[ -f Dockerfile || -f docker-compose.yml || -f compose.yml ]] && add_tool containers
[[ -f Chart.yaml || -d charts ]] && add_tool helm
[[ -f kustomization.yaml || -f kustomization.yml ]] && add_tool kustomize
find_any '*.proto' && add_tool protobuf || true
(find_any '*.bzl' || [[ -f WORKSPACE || -f MODULE.bazel ]]) && add_tool bazel || true
[[ -d .github/workflows ]] && add_tool github-actions
[[ -f ansible.cfg || -f requirements.yml ]] && add_tool ansible

brew_install() {
  local formula="$1"
  have brew || { warn "Homebrew unavailable; cannot install $formula"; return 1; }
  brew list --formula "$formula" >/dev/null 2>&1 && return 0
  brew info "$formula" >/dev/null 2>&1 || { warn "Homebrew formula unavailable: $formula"; return 1; }
  brew install "$formula"
}
can_install(){ [[ "$CHECK_ONLY" -eq 0 && "$NO_INSTALL_LANGUAGE_DEPS" -eq 0 ]]; }

install_declared_runtimes() {
  [[ "$CHECK_ONLY" -eq 0 && "$NO_RUNTIME_INSTALL" -eq 0 ]] || return 0
  have mise || return 0
  if [[ -f .mise.toml || -f mise.toml || -f .tool-versions ]]; then mise install || warn "mise could not install all declared runtimes"; fi
  if [[ -f .python-version ]]; then local v; v="$(head -n1 .python-version | tr -d '[:space:]')"; [[ -n "$v" ]] && mise install "python@$v" || true; fi
  if [[ -f .node-version ]]; then local v; v="$(head -n1 .node-version | tr -d '[:space:]')"; [[ -n "$v" ]] && mise install "node@$v" || true
  elif [[ -f .nvmrc ]]; then local v; v="$(head -n1 .nvmrc | tr -d '[:space:]' | sed 's/^v//')"; [[ -n "$v" ]] && mise install "node@$v" || true; fi
}

ensure_language() {
  case "$1" in
    python) have uv || { missing uv; can_install && brew_install uv || true; } ;;
    node) have node || { missing node; can_install && have mise && mise use --global node@lts || true; }; have npm || missing npm ;;
    deno) have deno || { missing deno; can_install && brew_install deno || true; } ;;
    go) have go || { missing go; can_install && brew_install go || true; }; have gopls || { missing gopls; can_install && brew_install gopls || true; } ;;
    rust)
      have rustup || { missing rustup; can_install && brew_install rustup || true; }
      if have rustup && can_install; then rustup toolchain list | grep -q '^stable' || rustup toolchain install stable; rustup component add rust-analyzer rustfmt clippy || true; fi
      have rust-analyzer || { missing rust-analyzer; can_install && brew_install rust-analyzer || true; }
      ;;
    java) have java || { missing java; can_install && brew_install openjdk || true; } ;;
    kotlin) have kotlin || { missing kotlin; can_install && brew_install kotlin || true; } ;;
    cpp) have clangd || { missing clangd; can_install && brew_install llvm || true; }; [[ -f CMakeLists.txt ]] && ! have cmake && { missing cmake; can_install && brew_install cmake || true; } ;;
    ruby) have ruby || { missing ruby; can_install && brew_install ruby || true; }; have ruby-lsp || { missing ruby-lsp; can_install && have gem && gem install ruby-lsp || true; } ;;
    php) have php || { missing php; can_install && brew_install php || true; } ;;
    swift) xcrun --find sourcekit-lsp >/dev/null 2>&1 || missing sourcekit-lsp ;;
    terraform) have terraform || have tofu || { missing terraform/tofu; warn "Install the Terraform/OpenTofu runtime used by this repo."; }; have terraform-ls || { missing terraform-ls; can_install && brew_install terraform-ls || true; } ;;
    lua) have lua-language-server || { missing lua-language-server; can_install && brew_install lua-language-server || true; } ;;
    zig) have zig || { missing zig; can_install && brew_install zig || true; } ;;
  esac
}

ensure_package_manager() {
  case "$1" in
    poetry) have poetry || { missing poetry; can_install && have uv && uv tool install poetry || true; } ;;
    pdm) have pdm || { missing pdm; can_install && have uv && uv tool install pdm || true; } ;;
    pnpm) have pnpm || { missing pnpm; can_install && npm install -g pnpm || true; } ;;
    yarn) have yarn || { missing yarn; can_install && npm install -g yarn || true; } ;;
    bun) have bun || { missing bun; can_install && brew_install bun || true; } ;;
    bundler) have bundle || { missing bundler; can_install && have gem && gem install bundler || true; } ;;
    composer) have composer || { missing composer; can_install && brew_install composer || true; } ;;
    maven) have mvn || { missing maven; can_install && brew_install maven || true; } ;;
    gradle) have gradle || { missing gradle; can_install && brew_install gradle || true; } ;;
  esac
}

ensure_tool() {
  case "$1" in
    helm) have helm || { missing helm; can_install && brew_install helm || true; } ;;
    kustomize) have kustomize || { missing kustomize; can_install && brew_install kustomize || true; } ;;
    protobuf) have protoc || { missing protoc; can_install && brew_install protobuf || true; }; have buf || { missing buf; can_install && brew_install buf || true; } ;;
    bazel) have bazelisk || { missing bazelisk; can_install && brew_install bazelisk || true; } ;;
    github-actions) have actionlint || { missing actionlint; can_install && brew_install actionlint || true; } ;;
    ansible) have ansible || { missing ansible; can_install && brew_install ansible || true; } ;;
    containers) have docker || have podman || { missing docker/podman; warn "Container files detected; install the runtime you intend to use."; } ;;
  esac
}

install_declared_runtimes
for lang in "${LANGUAGES[@]:-}"; do ensure_language "$lang"; done
for pm in "${PACKAGE_MANAGERS[@]:-}"; do ensure_package_manager "$pm"; done
for tool in "${TOOLS[@]:-}"; do ensure_tool "$tool"; done

TEST_CMD=""; LINT_CMD=""; FORMAT_CMD=""; TYPECHECK_CMD=""; BUILD_CMD=""; INSTALL_CMD=""
make_has(){ local f; for f in Makefile makefile GNUmakefile; do [[ -f "$f" ]] && grep -Eq "^$1:[[:space:]]*" "$f" && return 0; done; return 1; }
make_has test && TEST_CMD="make test" || true
make_has lint && LINT_CMD="make lint" || true
if make_has fmt; then FORMAT_CMD="make fmt"; elif make_has format; then FORMAT_CMD="make format"; fi
make_has typecheck && TYPECHECK_CMD="make typecheck" || true
make_has build && BUILD_CMD="make build" || true

if [[ -f go.mod ]]; then [[ -n "$TEST_CMD" ]] || TEST_CMD="go test ./..."; [[ -n "$BUILD_CMD" ]] || BUILD_CMD="go build ./..."; [[ -n "$FORMAT_CMD" ]] || FORMAT_CMD="gofmt -w <changed-go-files>"; INSTALL_CMD="go mod download"; fi
if [[ -f Cargo.toml ]]; then [[ -n "$TEST_CMD" ]] || TEST_CMD="cargo test"; [[ -n "$BUILD_CMD" ]] || BUILD_CMD="cargo build"; [[ -n "$LINT_CMD" ]] || LINT_CMD="cargo clippy --all-targets --all-features"; [[ -n "$FORMAT_CMD" ]] || FORMAT_CMD="cargo fmt --all"; INSTALL_CMD="cargo fetch"; fi

if [[ -f pyproject.toml ]]; then
  grep -Eq 'pytest|\[tool\.pytest' pyproject.toml && [[ -z "$TEST_CMD" ]] && TEST_CMD="uv run pytest" || true
  if grep -Eq 'ruff|\[tool\.ruff' pyproject.toml; then [[ -n "$LINT_CMD" ]] || LINT_CMD="uv run ruff check ."; [[ -n "$FORMAT_CMD" ]] || FORMAT_CMD="uv run ruff format ."; fi
  grep -Eq 'mypy|\[tool\.mypy' pyproject.toml && [[ -z "$TYPECHECK_CMD" ]] && TYPECHECK_CMD="uv run mypy ." || true
  grep -Eq 'pyright|basedpyright' pyproject.toml && [[ -z "$TYPECHECK_CMD" ]] && TYPECHECK_CMD="uv run pyright" || true
  if [[ -f poetry.lock ]]; then INSTALL_CMD="poetry install"; elif [[ -f pdm.lock ]]; then INSTALL_CMD="pdm install"; else INSTALL_CMD="uv sync"; fi
elif [[ -f requirements.txt ]]; then INSTALL_CMD="uv venv && uv pip install -r requirements.txt"; fi

if [[ -f package.json ]] && have jq; then
  if [[ -f pnpm-lock.yaml ]]; then PM=pnpm; INSTALL_CMD="pnpm install --frozen-lockfile"
  elif [[ -f yarn.lock ]]; then PM=yarn; INSTALL_CMD="yarn install --immutable"
  elif [[ -f bun.lock || -f bun.lockb ]]; then PM=bun; INSTALL_CMD="bun install --frozen-lockfile"
  else PM=npm; INSTALL_CMD="npm ci"; fi
  script_cmd(){ local name="$1"; jq -e --arg n "$name" '.scripts[$n] // empty' package.json >/dev/null 2>&1 && { [[ "$PM" == npm ]] && echo "npm run $name" || echo "$PM $name"; }; }
  [[ -n "$TEST_CMD" ]] || TEST_CMD="$(script_cmd test || true)"
  [[ -n "$LINT_CMD" ]] || LINT_CMD="$(script_cmd lint || true)"
  [[ -n "$FORMAT_CMD" ]] || FORMAT_CMD="$(script_cmd format || true)"
  [[ -n "$TYPECHECK_CMD" ]] || TYPECHECK_CMD="$(script_cmd typecheck || true)"
  [[ -n "$BUILD_CMD" ]] || BUILD_CMD="$(script_cmd build || true)"
fi

[[ -f gradlew ]] && { [[ -n "$TEST_CMD" ]] || TEST_CMD="./gradlew test"; [[ -n "$BUILD_CMD" ]] || BUILD_CMD="./gradlew build"; INSTALL_CMD="./gradlew dependencies"; }
[[ -f mvnw ]] && { [[ -n "$TEST_CMD" ]] || TEST_CMD="./mvnw test"; [[ -n "$BUILD_CMD" ]] || BUILD_CMD="./mvnw package"; INSTALL_CMD="./mvnw dependency:go-offline"; }
[[ -f Gemfile ]] && INSTALL_CMD="bundle install"
[[ -f composer.json ]] && INSTALL_CMD="composer install"
[[ -f deno.json || -f deno.jsonc ]] && { [[ -n "$TEST_CMD" ]] || TEST_CMD="deno test"; [[ -n "$LINT_CMD" ]] || LINT_CMD="deno lint"; [[ -n "$FORMAT_CMD" ]] || FORMAT_CMD="deno fmt"; }

info "Repository discovery"
printf '  %-18s %s\n' Repository "$REPO_NAME" Path "$REPO" Languages "${LANGUAGES[*]:-not confidently detected}" 'Serena languages' "${SERENA_LANGUAGES[*]:-none}" Frameworks "${FRAMEWORKS[*]:-none}" 'Package managers' "${PACKAGE_MANAGERS[*]:-none}" 'Extra tools' "${TOOLS[*]:-none}"

info "Detected repository commands"
printf '  %-12s %s\n' install "${INSTALL_CMD:-not detected}" test "${TEST_CMD:-not detected}" lint "${LINT_CMD:-not detected}" format "${FORMAT_CMD:-not detected}" typecheck "${TYPECHECK_CMD:-not detected}" build "${BUILD_CMD:-not detected}"

ensure_local_exclude(){ local entry="$1" f; f="$(git rev-parse --git-path info/exclude)"; mkdir -p "$(dirname "$f")"; touch "$f"; grep -Fxq "$entry" "$f" || printf '%s\n' "$entry" >> "$f"; }

write_local_context(){
  local path="$1"
  [[ -e "$path" ]] && { warn "$path already exists; leaving it untouched."; return; }
  cat > "$path" <<EOF2
# Local Repository Context

Generated locally by agentic-dev-env. Shared tool-routing policy belongs in the user-level Claude/Codex instructions.

- Repository: $REPO_NAME
- Languages: ${LANGUAGES[*]:-not confidently detected}
- Serena languages: ${SERENA_LANGUAGES[*]:-none}
- Frameworks: ${FRAMEWORKS[*]:-none}
- Package managers: ${PACKAGE_MANAGERS[*]:-none}
- Auxiliary tools: ${TOOLS[*]:-none}

## Commands

- Install: ${INSTALL_CMD:-inspect the repository}
- Test: ${TEST_CMD:-inspect the repository}
- Lint: ${LINT_CMD:-inspect the repository}
- Format: ${FORMAT_CMD:-inspect the repository}
- Typecheck: ${TYPECHECK_CMD:-inspect the repository}
- Build: ${BUILD_CMD:-inspect the repository}

Prefer existing repository wrappers and conventions. Preserve unrelated changes. Do not commit local intelligence indexes unless the repository explicitly chooses to track them.
EOF2
  ensure_local_exclude "/$path"
  success "Created local $path"
}

if [[ "$CHECK_ONLY" -eq 0 ]]; then
  info "Configuring repository intelligence"
  for e in '/.codegraph/' '/.serena/' '/.saad-agent/' '/repomix-output.xml' '/repomix-output.md'; do ensure_local_exclude "$e"; done
  mkdir -p .saad-agent
  cat > .saad-agent/repo.env <<EOF2
REPO_NAME=$(printf '%q' "$REPO_NAME")
LANGUAGES=$(printf '%q' "${LANGUAGES[*]:-}")
SERENA_LANGUAGES=$(printf '%q' "${SERENA_LANGUAGES[*]:-}")
FRAMEWORKS=$(printf '%q' "${FRAMEWORKS[*]:-}")
PACKAGE_MANAGERS=$(printf '%q' "${PACKAGE_MANAGERS[*]:-}")
EXTRA_TOOLS=$(printf '%q' "${TOOLS[*]:-}")
INSTALL_CMD=$(printf '%q' "$INSTALL_CMD")
TEST_CMD=$(printf '%q' "$TEST_CMD")
LINT_CMD=$(printf '%q' "$LINT_CMD")
FORMAT_CMD=$(printf '%q' "$FORMAT_CMD")
TYPECHECK_CMD=$(printf '%q' "$TYPECHECK_CMD")
BUILD_CMD=$(printf '%q' "$BUILD_CMD")
EOF2

  if [[ "$NO_INSTRUCTIONS" -eq 0 ]]; then write_local_context AGENTS.md; write_local_context CLAUDE.md; fi
  if [[ "$INSTALL_PROJECT_DEPS" -eq 1 && -n "$INSTALL_CMD" ]]; then info "Installing project dependencies"; bash -lc "$INSTALL_CMD" || warn "Project dependency installation failed"; fi

  if [[ "$NO_CODEGRAPH" -eq 0 ]]; then
    if have codegraph; then [[ -d .codegraph ]] && success "CodeGraph already initialized" || codegraph init
    else warn "CodeGraph not installed; run setup-coding-agent-env.sh first."; fi
  fi

  if [[ "$NO_SERENA" -eq 0 ]]; then
    if have serena && [[ ${#SERENA_LANGUAGES[@]} -gt 0 ]]; then
      if [[ -f .serena/project.yml ]]; then serena project index "$REPO" || warn "Serena indexing failed"
      else
        args=(project create --index)
        for lang in "${SERENA_LANGUAGES[@]}"; do args+=(--language "$lang"); done
        args+=("$REPO")
        serena "${args[@]}" || warn "Serena project creation/indexing failed"
      fi
    elif [[ ${#SERENA_LANGUAGES[@]} -eq 0 ]]; then warn "No Serena-supported language confidently detected."
    else warn "Serena not installed; run setup-coding-agent-env.sh first."; fi
  fi
fi

info "Repository readiness"
for pair in 'ripgrep:rg' 'fd:fd' 'ast-grep:ast-grep' 'CodeGraph:codegraph' 'Repomix:repomix'; do label="${pair%%:*}"; cmd="${pair##*:}"; have "$cmd" && success "$label available" || warn "$label missing"; done
[[ -d .codegraph ]] && success "CodeGraph initialized" || warn "CodeGraph not initialized"
[[ -f .serena/project.yml ]] && success "Serena project configured" || warn "Serena project not configured"
[[ ${#MISSING[@]} -gt 0 ]] && warn "Missing/initially-missing support: ${MISSING[*]}"

if [[ "$NO_SERENA" -eq 0 && -f .serena/project.yml ]] && have serena; then
  info "Serena health check"
  serena project health-check "$REPO" && success "Serena ready" || warn "Serena health check failed"
fi

if [[ "$NO_SKILLS" -eq 0 ]]; then
  info "Context-aware Agent Skills"
  if have agentic; then
    skill_args=(skills suggest "$REPO" --target "$SKILLS_TARGET")
    [[ -n "$TASK" ]] && skill_args+=(--task "$TASK")
    [[ "$SKILLS_YES" -eq 1 ]] && skill_args+=(--yes)
    [[ "$SKILLS_SHARED" -eq 1 ]] && skill_args+=(--shared)
    [[ "$CHECK_ONLY" -eq 1 ]] && skill_args+=(--no-prompt)
    agentic "${skill_args[@]}" || warn "Skill recommendation reported an issue."
  else
    warn "Unified 'agentic' CLI is not installed; rerun ./install.sh to enable skill recommendations."
  fi
fi

cat <<EOF2

Repository initialization complete.

Useful commands:
  saad-tool-repo-init.sh . --check
  agentic skills suggest . --task "describe the work"
  agentic skills status .
  codegraph status
  serena project health-check "$REPO"
  repomix --compress
EOF2
