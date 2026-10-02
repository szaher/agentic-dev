---
name: kubernetes-development
description: Make safe Kubernetes workload, manifest, Helm, Kustomize, RBAC, and rollout changes.
---

# Kubernetes Development

Identify whether YAML is source, generated output, Helm template, Kustomize base/overlay, or operator-managed before editing.

Check namespace, ownership, selectors, RBAC, resources, security context, upgrade behavior, and rollout implications. Never hand-edit generated manifests when a source generator exists.

Validate with repository tooling plus `kubectl --dry-run=client`, Helm template/lint, or Kustomize build as applicable.