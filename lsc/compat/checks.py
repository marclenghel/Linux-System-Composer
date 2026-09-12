"""The public face of the compatibility engine.

Milestone 3 replaced what used to be here. This file was a forty-line walk over
the requires/conflicts/recommends tuples with no version reasoning, no
conditions, no transitivity and no idea what machine it was running on; the
engine that replaced it lives in lsc/compat/engine.py, the language its rules are
written in lives in lsc/compat/conditions.py, and the rules themselves live in
lsc/data/rules.py.

What stayed is this module's name and the shape of its functions, so no screen
had to be edited to gain any of it. That is the payoff for having kept the core
free of interface code: the whole heart of the project was swapped out
underneath five screens that did not notice.
"""

from __future__ import annotations

from typing import Any, Mapping

from lsc.data.catalog import CATEGORIES_BY_ID
from lsc.compat.engine import Report, evaluate
from lsc.models import Build, Issue

__all__ = [
    "Report",
    "build_is_installable",
    "category_name",
    "check",
    "evaluate",
    "summarise",
]


def check(build: Build, hardware_profile: Mapping[str, Any] | None = None) -> list[Issue]:
    """Every issue in this build, worst first.

    The hardware profile is optional and may be omitted entirely; rules that
    depend on the machine then evaluate to unknown rather than guessing. Use
    evaluate() instead when you also want to know *which* checks could not be
    made — the Validate screen does, because a check that was skipped silently
    is indistinguishable from one that passed.
    """
    return list(evaluate(build, hardware_profile).issues)


def summarise(issues: list[Issue]) -> dict[str, int]:
    """Count issues by severity, for the headline on the Validate screen."""
    counts = {"error": 0, "warning": 0, "info": 0}
    for issue in issues:
        if issue.severity in counts:
            counts[issue.severity] += 1
    return counts


def build_is_installable(issues: list[Issue]) -> bool:
    """True when nothing outright blocks this build."""
    return not any(issue.severity == "error" for issue in issues)


def category_name(category_id: str) -> str:
    category = CATEGORIES_BY_ID.get(category_id)
    return category.name if category else category_id
