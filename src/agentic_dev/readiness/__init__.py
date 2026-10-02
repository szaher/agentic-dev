"""Agent Ready assessment: evaluate a repository against the Agent Ready Spec.

The specification is owned by https://github.com/szaher/agent-ready. This
package vendors a pinned bundle of it and never modifies assessed repositories.
"""

from .assess import assess, explain_repository, explain_rule, plan
from .spec import BuiltinSpecSource, PathSpecSource, Spec, SpecError, SpecSource, load_spec, resolve

__all__ = [
    "BuiltinSpecSource",
    "PathSpecSource",
    "Spec",
    "SpecError",
    "SpecSource",
    "assess",
    "explain_repository",
    "explain_rule",
    "load_spec",
    "plan",
    "resolve",
]
