---
name: debugging
description: Use an evidence-driven reproduce-narrow-isolate-fix-verify debugging workflow.
---

# Debugging

Do not edit from the first plausible hypothesis.

1. Reproduce or establish concrete evidence.
2. Reduce the failure to the smallest responsible path.
3. Inspect logs/state/callers and compare working vs failing behavior.
4. Form a falsifiable hypothesis.
5. Make the smallest causal fix.
6. Add or update a regression test.
7. Re-run the original reproduction and relevant broader checks.

Record uncertainty when the root cause cannot be proven.