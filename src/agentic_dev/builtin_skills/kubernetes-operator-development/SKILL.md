---
name: kubernetes-operator-development
description: Develop Kubernetes operators/controllers with reconciliation, CRD, RBAC, and controller-runtime discipline.
---

# Kubernetes Operator Development

Trace the reconcile loop, watched resources, ownership, predicates, finalizers, status updates, RBAC, and tests before changing behavior.

Reconciliation must be idempotent and retry-safe. Distinguish desired state from observed state. Treat API/CRD changes as compatibility-sensitive.

For CRD changes, inspect schema generation, conversion/defaulting, versioning, generated manifests, and upgrade impact. Verify controller tests and generated artifacts through project-native commands.