# Optional capabilities

`agentic-dev` keeps expensive, security-sensitive, or task-specific tools out of the default workstation setup. These are modeled as **optional capabilities**.

Browser support is the first capability pack.

## Principle

```text
detect need
    ↓
recommend capability
    ↓
explain evidence
    ↓
human explicitly enables it
    ↓
configure selected provider only
```

Repository detection never enables a browser.

## Browser capabilities

| Capability | Default provider | Best for |
|---|---|---|
| `browser-automation` | Playwright MCP | deterministic UI navigation, forms, end-to-end testing, web-app validation |
| `browser-debug` | Chrome DevTools MCP | console/network inspection, traces, frontend performance debugging |
| `browser-agent` | Browser Use | broader autonomous multi-step browser workflows and web research |

Playwright MCP uses structured accessibility snapshots and is the default browser automation provider. Upstream: https://github.com/microsoft/playwright-mcp

Chrome DevTools MCP exposes browser debugging and performance tooling. Upstream: https://github.com/ChromeDevTools/chrome-devtools-mcp

Browser Use provides a browser-control CLI and Agent Skill aimed at coding agents. Upstream: https://github.com/browser-use/browser-use

## Discover

```bash
agentic capabilities list
agentic capabilities status
```

## Repo/task-aware suggestions

```bash
agentic capabilities suggest .
```

Task context improves the recommendation:

```bash
agentic capabilities suggest . \
  --task "run the UI and verify the checkout form"
```

A frontend repo or Playwright test configuration can recommend `browser-automation`.

A task mentioning network traces, console failures, or page-load performance can recommend `browser-debug`.

A task explicitly involving multi-site web research or portals can recommend `browser-agent`.

Suggestions are read-only. The output ends by telling the user that nothing was enabled.

Machine-readable form:

```bash
agentic capabilities suggest . --task "debug page load performance" --json
```

## Enable browser automation

Safe default: an isolated Playwright browser context.

```bash
agentic capabilities enable browser-automation \
  --target both \
  --mode isolated
```

Targets currently supported for MCP browser providers:

```text
claude
codex
both
```

This configures the official MCP server commands:

```text
npx @playwright/mcp@latest --isolated
```

Playwright upstream documents `--isolated` as an ephemeral session: closing the browser discards session storage.

### Persistent browser profile

```bash
agentic capabilities enable browser-automation \
  --target claude \
  --mode persistent
```

Persistent mode lets Playwright MCP use its normal per-workspace persistent profile.

### Existing authenticated browser

This is deliberately explicit:

```bash
agentic capabilities enable browser-automation \
  --target claude \
  --mode existing-browser
```

This configures Playwright MCP with `--extension`. The Playwright browser extension must be installed separately.

Existing-browser mode can expose logged-in sessions, cookies, page contents, and actions available to that browser session. Do not use it as the default.

## Enable browser debugging

```bash
agentic capabilities enable browser-debug \
  --target both \
  --mode isolated
```

The provider is Chrome DevTools MCP:

```text
npx -y chrome-devtools-mcp@latest --isolated
```

For a lightweight headless setup:

```bash
agentic capabilities enable browser-debug \
  --target codex \
  --mode headless
```

which uses the provider's `--slim --headless` mode.

## Enable Browser Use

```bash
agentic capabilities enable browser-agent
```

This installs/upgrades Browser Use through `uv` with Python 3.12 and invokes its official skill installer.

Browser Use is intended as the advanced autonomous option rather than the default UI-testing provider.

## Disable

```bash
agentic capabilities disable browser-automation
agentic capabilities disable browser-debug
agentic capabilities disable browser-agent
```

For MCP providers, agentic-dev removes the MCP registration it manages.

For Browser Use, disabling removes it from agentic-dev's enabled capability state but deliberately leaves the CLI installed. Package removal is a separate workstation-management action.

## Security boundary

Browser capabilities are opt-in because they can expose materially more than source code.

Use these defaults:

- prefer `isolated` for routine testing;
- do not attach to an authenticated personal/work browser unless the task actually requires it;
- do not enable multiple overlapping browser providers by default;
- inspect the target agent's permissions before combining browser access with write-capable external systems;
- treat browser-visible secrets, cookies, SSO sessions, and internal pages as sensitive.

## Future capability packs

Browser establishes the capability abstraction. Other optional packs can follow the same model without bloating the default install:

```text
database
kubernetes-cluster
cloud
observability
desktop
external-services
```

AgentFlow or another orchestration layer can later declare a required capability such as `browser-automation`; `agentic-dev` remains the owner of installing and reporting that capability.
