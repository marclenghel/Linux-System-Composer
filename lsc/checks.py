"""A deliberately naive compatibility check.

This is NOT the compatibility engine from the README. It walks the
requires/conflicts/recommends fields of the selected components and reports
what it finds — nothing more. There is no version reasoning, no transitive
resolution, no hardware awareness, and no notion of a rule having a condition.

It exists so the Validate screen has something true to display, and so the
shape of an Issue is settled before the real engine is written against it.
Everything here is expected to be thrown away in milestone 3.
"""

from __future__ import annotations

from lsc.data.catalog import CATEGORIES, CATEGORIES_BY_ID, COMPONENTS_BY_ID, component_name
from lsc.models import Build, Issue

SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}


def check(build: Build) -> list[Issue]:
    """Return every issue this naive pass can find, worst first."""
    issues: list[Issue] = []
    selected = build.selected_ids()

    for category in CATEGORIES:
        component_id = build.selected_id(category.id)

        # An unanswered question is a warning, unless the category says an empty
        # answer is legitimate (a headless build has no display server).
        if component_id is None:
            if not category.optional:
                issues.append(
                    Issue(
                        severity="warning",
                        title=f"No {category.name.lower()} selected",
                        detail=(
                            f"{category.question} Nothing is chosen, so this layer of "
                            "the stack is empty."
                        ),
                        fix=f"Open Compose and pick something under {category.name}.",
                    )
                )
            continue

        component = COMPONENTS_BY_ID.get(component_id)
        if component is None:
            continue

        issues.extend(_check_requires(component, selected))
        issues.extend(_check_conflicts(component, selected))
        issues.extend(_check_recommends(component, selected))

    # Two components can declare the same conflict about each other, which would
    # otherwise be reported twice from opposite directions.
    issues = _deduplicate(issues)
    issues.sort(key=lambda issue: SEVERITY_ORDER.get(issue.severity, 9))
    return issues


def _check_requires(component, selected: set[str]) -> list[Issue]:
    found = []
    for required_id in component.requires:
        if required_id in selected:
            continue
        required_category = _category_of(required_id)
        found.append(
            Issue(
                severity="error",
                title=f"{component.name} requires {component_name(required_id)}",
                detail=(
                    f"{component.name} does not work without "
                    f"{component_name(required_id)}, and the current build does not "
                    "include it."
                ),
                fix=(
                    f"Select {component_name(required_id)} under "
                    f"{required_category}, or choose a different "
                    f"{_category_of_component(component)}."
                ),
            )
        )
    return found


def _check_conflicts(component, selected: set[str]) -> list[Issue]:
    found = []
    for conflicting_id in component.conflicts:
        if conflicting_id not in selected:
            continue
        found.append(
            Issue(
                severity="error",
                title=(
                    f"{component.name} conflicts with {component_name(conflicting_id)}"
                ),
                detail=(
                    f"Both {component.name} and {component_name(conflicting_id)} are "
                    "in this build, and they cannot be installed together."
                ),
                fix=(
                    f"Drop one of them — replace {component.name} or replace "
                    f"{component_name(conflicting_id)}."
                ),
            )
        )
    return found


def _check_recommends(component, selected: set[str]) -> list[Issue]:
    found = []
    for recommended_id in component.recommends:
        if recommended_id in selected:
            continue
        found.append(
            Issue(
                severity="info",
                title=(
                    f"{component.name} pairs well with {component_name(recommended_id)}"
                ),
                detail=(
                    f"{component.name} works without it, but "
                    f"{component_name(recommended_id)} is the combination most people "
                    "run and most documentation assumes."
                ),
                fix=(
                    f"Consider {component_name(recommended_id)} under "
                    f"{_category_of(recommended_id)}."
                ),
            )
        )
    return found


# ── helpers ───────────────────────────────────────────────────────────────────


def _category_of(component_id: str) -> str:
    """Which category a component id belongs to, by display name."""
    for category in CATEGORIES:
        if any(c.id == component_id for c in category.components):
            return category.name
    return "the catalogue"


def _category_of_component(component) -> str:
    return _category_of(component.id).lower()


def _deduplicate(issues: list[Issue]) -> list[Issue]:
    """Collapse the same conflict reported from both sides.

    "A conflicts with B" and "B conflicts with A" are one problem. Sorting the
    two names gives both directions the same key.
    """
    seen: set[tuple[str, frozenset[str]]] = set()
    unique: list[Issue] = []
    for issue in issues:
        key = (issue.severity, frozenset(issue.title.replace(" conflicts with ", "|").split("|")))
        if key in seen:
            continue
        seen.add(key)
        unique.append(issue)
    return unique


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
