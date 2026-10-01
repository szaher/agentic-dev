# Contributing

The toolkit is intentionally conservative: detect existing project conventions, augment them, and avoid overwriting user or upstream configuration.

Before opening a pull request:

```bash
make check
```

Changes to language detection should include a small fixture or smoke-test case. Changes to installation behavior should remain idempotent and should not install project dependencies unless the user explicitly opts in.

Keep external tool setup aligned with upstream documentation. Avoid pinning generated configuration formats when the upstream tool provides its own setup command.
