"""The compatibility engine — milestone 3, and the heart of the project.

Four modules, in dependency order:

    conditions.py   the language      nodes, three-valued logic, JSON round trip
    facts.py        the world         a Build + a hardware reading -> facts
    engine.py       the interpreter   graph closure, evaluation, templating
    checks.py       the facade        what the screens call

The screens import this package and nothing below it, so the whole engine
could be replaced again — as it already was once, when milestone 3 swapped out
a forty-line walk over the catalogue — without a screen changing its imports.

The rules themselves are not here. They are knowledge, not machinery, and they
live with the rest of the knowledge in lsc/data/rules.py.
"""

from __future__ import annotations

from lsc.compat.checks import (
    Report,
    build_is_installable,
    category_name,
    check,
    evaluate,
    summarise,
)

__all__ = [
    "Report",
    "build_is_installable",
    "category_name",
    "check",
    "evaluate",
    "summarise",
]
