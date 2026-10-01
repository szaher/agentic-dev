# Tool catalog

This toolkit intentionally combines several narrow tools instead of trying to make one tool answer every coding question.

## Core code-intelligence stack

| Tool | Why it matters | Upstream |
|---|---|---|
| ripgrep (`rg`) | Fast literal/regex search across a repository. This is the cheapest path for exact text. | https://github.com/BurntSushi/ripgrep |
| fd | Fast file discovery with practical defaults. | https://github.com/sharkdp/fd |
| ast-grep | AST-aware structural search and transformations. Useful when text search is too weak and a full semantic engine is unnecessary. | https://ast-grep.github.io/ |
| Serena | MCP coding toolkit with symbol-level semantic retrieval, references, implementations, diagnostics, editing, and refactoring. | https://github.com/oraios/serena |
| CodeGraph | Local pre-indexed code knowledge graph for architecture exploration, callers/callees, dependency paths, and impact analysis. | https://github.com/colbymchenry/codegraph |
| Context7 | Pulls current/version-aware external library documentation into agent context. | https://github.com/upstash/context7 |
| Repomix | Packs repositories into AI-friendly snapshots for broad or cross-repo analysis. | https://github.com/yamadashy/repomix |

## Runtime and environment management

| Tool | Why it matters | Upstream |
|---|---|---|
| mise | Manages project-specific language/runtime/tool versions and environment activation. | https://mise.jdx.dev/ |
| uv | Fast Python package/environment/tool manager used by Serena and Python projects. | https://docs.astral.sh/uv/ |
| direnv | Loads per-directory environment variables automatically. | https://direnv.net/ |
| Node.js | Required by many JavaScript/TypeScript tools and `npx`-based integrations such as Context7 setup. | https://nodejs.org/ |

## Git and repository workflow

| Tool | Why it matters | Upstream |
|---|---|---|
| Git | Version control, branches, worktrees, history, and recovery boundary. | https://git-scm.com/ |
| GitHub CLI (`gh`) | PR, issue, auth, workflow, release, and repository operations from the terminal. | https://cli.github.com/ |
| delta | Readable Git diff/pager output. | https://github.com/dandavison/delta |

Git worktrees are built into Git and are strongly recommended for running multiple write-capable coding agents in parallel.

## Shell and data utilities

| Tool | Why it matters | Upstream |
|---|---|---|
| fzf | Interactive fuzzy selection for files/history/results. | https://github.com/junegunn/fzf |
| jq | Deterministic JSON queries and transforms. | https://jqlang.github.io/jq/ |
| yq | YAML/XML/TOML/property queries and transforms. | https://github.com/mikefarah/yq |
| bat | Source/file viewing with syntax highlighting. | https://github.com/sharkdp/bat |
| eza | Modern directory listing useful for quick repo inspection. | https://github.com/eza-community/eza |
| just | Small command runner for stable project tasks. | https://github.com/casey/just |
| ShellCheck | Static analysis for shell scripts. | https://www.shellcheck.net/ |
| shfmt | Deterministic shell formatter. | https://github.com/mvdan/sh |
| hyperfine | Command benchmarking. Useful when validating performance claims. | https://github.com/sharkdp/hyperfine |
| watchexec | Re-run commands when files change. Useful for tight local feedback loops. | https://github.com/watchexec/watchexec |

## Language/toolchain support installed on demand

The machine bootstrap can preinstall these ecosystems, and the repository initializer can install missing support only when a detected repo needs it.

| Ecosystem | Tooling prepared | Upstream |
|---|---|---|
| Python | `uv`; Serena launches/uses its Python language-server backend as needed | https://docs.astral.sh/uv/ |
| Go | Go + `gopls` | https://go.dev/ / https://go.dev/gopls/ |
| Rust | `rustup`, `rust-analyzer`, `rustfmt`, `clippy` | https://rustup.rs/ / https://rust-analyzer.github.io/ |
| Node/TypeScript | Node.js, TypeScript language server, YAML language server | https://nodejs.org/ / https://github.com/typescript-language-server/typescript-language-server |
| Java | OpenJDK; JDT LS when available | https://openjdk.org/ / https://github.com/eclipse-jdtls/eclipse.jdt.ls |
| Kotlin | Kotlin + Kotlin language server when available | https://kotlinlang.org/ / https://github.com/fwcd/kotlin-language-server |
| C/C++ | LLVM/`clangd`, CMake/Ninja when the repo uses them | https://clangd.llvm.org/ / https://cmake.org/ |
| Ruby | Ruby + `ruby-lsp` | https://www.ruby-lang.org/ / https://github.com/Shopify/ruby-lsp |
| PHP | PHP + Composer where needed | https://www.php.net/ / https://getcomposer.org/ |
| Swift | `sourcekit-lsp` from Xcode/Xcode Command Line Tools | https://www.swift.org/documentation/articles/zero-to-swift-nvim.html |
| Terraform | Terraform + `terraform-ls` | https://developer.hashicorp.com/terraform / https://github.com/hashicorp/terraform-ls |
| Lua | Lua + Lua Language Server | https://www.lua.org/ / https://github.com/LuaLS/lua-language-server |
| Zig | Zig toolchain | https://ziglang.org/ |

## Infrastructure/repository tooling installed on demand

| Repo signal | Tooling | Upstream |
|---|---|---|
| Kubernetes manifests | `kubectl` | https://kubernetes.io/docs/reference/kubectl/ |
| Helm charts | Helm | https://helm.sh/ |
| Kustomize | Kustomize | https://kubectl.docs.kubernetes.io/references/kustomize/ |
| Protobuf | `protoc` + Buf | https://protobuf.dev/ / https://buf.build/ |
| Bazel | Bazelisk | https://github.com/bazelbuild/bazelisk |
| GitHub Actions | actionlint | https://github.com/rhysd/actionlint |
| Ansible | Ansible | https://www.ansible.com/ |
| Containers | Detect Docker/Podman, but do not auto-install a desktop/runtime | https://www.docker.com/ / https://podman.io/ |

## Why the overlap is intentional

A few tools appear to solve similar problems, but they operate at different levels:

- `rg` sees text.
- `ast-grep` sees syntax structure.
- Serena sees language-server semantics and symbols.
- CodeGraph sees repository relationships and paths.
- Context7 sees external documentation.
- Repomix creates a broad snapshot when narrow retrieval is no longer enough.

The global agent policy tells Claude Code and Codex which level to use first.
