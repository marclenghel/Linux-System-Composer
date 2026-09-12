"""The compatibility engine: the thing the README calls the heart of the project.

It does four things the placeholder it replaces could not.

**It follows the graph instead of looking one hop.** Selecting the Hardened
security profile pulls in the hardened kernel, and the hardened kernel refuses
to sit next to the proprietary NVIDIA driver. Nothing in the build says
"hardened conflicts with nvidia" — the engine works it out by walking the
requires edges and keeping the path it walked, so the issue can explain the
route rather than just announcing the destination.

**It evaluates conditions, not fields.** "IF hyprland AND nvidia THEN..." is a
rule, and rules live in lsc/data/rules.py as data. See lsc/conditions.py for
why they are data and not functions.

**It reasons about versions and about hardware.** A component can state what it
provides (a kernel series, a driver branch) and the detector states what the
machine is, and a rule compares the two with the same operator either way.

**It never reports a problem without a way forward.** Every issue carries a
sentence for a person and, where one exists, a Suggestion a program could
apply. That is the README's actual promise: explain incompatibilities rather
than refuse them.

Nothing here imports Textual, and nothing here writes to the system.
"""

from __future__ import annotations

import string
from dataclasses import dataclass
from typing import Any, Mapping

from lsc.conditions import TRUE, UNKNOWN, Condition
from lsc.data.catalog import CATEGORIES, COMPONENTS_BY_ID, component_name
from lsc.facts import World, build_world
from lsc.models import Build, Issue, Suggestion

SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}


# ── a rule ────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Rule:
    """One piece of compatibility knowledge, written down as data.

    `title`, `detail` and `fix` are templates. They are rendered against the
    world's bindings, so a rule can say "{gpu.name} is {gpu.architecture}" and
    get "GeForce GTX 1060 is Pascal" without any rule ever running Python.

    `needs` is what would have to be known for this rule to reach an answer.
    It is only ever shown when the rule evaluates to UNKNOWN, and it is the
    difference between a tool that silently skips a check and one that tells
    you which checks it could not make.
    """

    id: str
    severity: str                                 # error | warning | info
    when: Condition
    title: str
    detail: str
    fix: str
    suggest: Suggestion | None = None
    reference: str = ""
    needs: str = "a hardware scan"

    def components(self) -> tuple[str, ...]:
        """Every component id this rule talks about.

        Derived from the condition rather than listed by hand, because a list
        kept in step with a condition by hand is a list that stops being in
        step with it.
        """
        found: list[str] = []
        for node in self.when.walk():
            found.extend(node.component_ids())
        if self.suggest is not None:
            found.append(self.suggest.component_id)
        return tuple(dict.fromkeys(found))

    def fact_keys(self) -> tuple[str, ...]:
        """Every fact this rule's condition consults."""
        found: list[str] = []
        for node in self.when.walk():
            found.extend(node.fact_keys())
        return tuple(dict.fromkeys(found))

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.id,
            "severity": self.severity,
            "when": self.when.to_dict(),
            "title": self.title,
            "detail": self.detail,
            "fix": self.fix,
            "needs": self.needs,
        }
        if self.suggest is not None:
            data["suggest"] = {
                "category_id": self.suggest.category_id,
                "component_id": self.suggest.component_id,
            }
        if self.reference:
            data["reference"] = self.reference
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Rule:
        suggest = data.get("suggest")
        return cls(
            id=data["id"],
            severity=data["severity"],
            when=Condition.from_dict(data["when"]),
            title=data["title"],
            detail=data["detail"],
            fix=data["fix"],
            suggest=Suggestion(suggest["category_id"], suggest["component_id"])
            if suggest
            else None,
            reference=data.get("reference", ""),
            needs=data.get("needs", "a hardware scan"),
        )


@dataclass(frozen=True)
class Report:
    """The result of evaluating a build: what was found, and what could not be."""

    issues: tuple[Issue, ...] = ()
    unchecked: tuple[tuple[str, str], ...] = ()   # (rule id, what it needed)
    rules_evaluated: int = 0
    hardware_known: bool = False

    def counts(self) -> dict[str, int]:
        counts = {"error": 0, "warning": 0, "info": 0}
        for issue in self.issues:
            if issue.severity in counts:
                counts[issue.severity] += 1
        return counts

    def installable(self) -> bool:
        return not any(issue.severity == "error" for issue in self.issues)


# ── the catalogue graph, computed once ────────────────────────────────────────


def _conflict_pairs() -> frozenset[frozenset[str]]:
    """Every conflict in the catalogue, as an unordered pair.

    This is the fix for the placeholder's worst hack. It used to notice that
    "A conflicts with B" and "B conflicts with A" were one problem by splitting
    the issue *title* on the words "conflicts with" — which worked, and would
    have broken the moment anyone reworded the sentence or translated it.

    A conflict is not a property of one component; it is a relationship between
    two, and a relationship between two things that has no direction is a set
    of size two. Modelling it that way makes the duplicate impossible instead
    of removing it afterwards.
    """
    pairs: set[frozenset[str]] = set()
    for component in COMPONENTS_BY_ID.values():
        for other_id in component.conflicts:
            pairs.add(frozenset({component.id, other_id}))
    return frozenset(pairs)


CONFLICT_PAIRS: frozenset[frozenset[str]] = _conflict_pairs()

CATEGORY_OF: dict[str, str] = {
    component.id: category.id
    for category in CATEGORIES
    for component in category.components
}


def category_name_of(component_id: str) -> str:
    """The display name of the category a component belongs to."""
    category_id = CATEGORY_OF.get(component_id)
    for category in CATEGORIES:
        if category.id == category_id:
            return category.name
    return "the catalogue"


def requirement_closure(selected: frozenset[str]) -> dict[str, tuple[str, ...]]:
    """Everything the build implies, and the chain of requires that implies it.

    Breadth-first, so the chain recorded for a component is the shortest route
    to it — the simplest true explanation rather than the first one found. The
    visited set is also what keeps a mutual requirement from looping forever;
    the catalogue has none today, and an engine that depends on that staying
    true is an engine with a bug in it.
    """
    closure: dict[str, tuple[str, ...]] = {}
    queue: list[tuple[str, tuple[str, ...]]] = []

    for component_id in sorted(selected):
        closure[component_id] = (component_id,)
        queue.append((component_id, (component_id,)))

    while queue:
        component_id, path = queue.pop(0)
        component = COMPONENTS_BY_ID.get(component_id)
        if component is None:
            continue
        for required_id in component.requires:
            if required_id in closure:
                continue
            next_path = path + (required_id,)
            closure[required_id] = next_path
            queue.append((required_id, next_path))

    return closure


def _chain(path: tuple[str, ...]) -> str:
    return " → ".join(component_name(component_id) for component_id in path)


# ── rendering a rule's message ────────────────────────────────────────────────


class _BindingFormatter(string.Formatter):
    """Resolves "{gpu.name}" as a single key rather than as attribute access.

    str.format would read "{gpu.name}" as "look up gpu, then take its .name".
    The bindings are a flat dictionary of dotted keys, so the lookup has to be
    overridden. A missing key renders as "?" instead of raising, because a
    template that names a binding the world does not have is a rule bug that
    should show up in the tests, not a crash during a demonstration.
    """

    def get_field(self, field_name: str, args: Any, kwargs: Any) -> tuple[Any, str]:
        return kwargs.get(field_name, "?"), field_name


_FORMATTER = _BindingFormatter()


def render(template: str, bindings: Mapping[str, Any]) -> str:
    """Fill a rule's template from the world's bindings."""
    try:
        return _FORMATTER.vformat(template, (), dict(bindings))
    except (IndexError, ValueError):
        # A malformed template is the rule author's mistake. Showing the raw
        # text is more useful than showing nothing, and the template test
        # catches it long before anyone sees this.
        return template


# ── the evaluator ─────────────────────────────────────────────────────────────


def evaluate(
    build: Build,
    hardware_profile: Mapping[str, Any] | None = None,
    rules: tuple[Rule, ...] | None = None,
) -> Report:
    """Run every check over a build and return what was found.

    `rules` is injectable so the tests can evaluate a handful of rules in
    isolation; production callers leave it alone and get the whole rule set.
    """
    from lsc.data.rules import RULES

    rule_set = RULES if rules is None else rules
    world = build_world(build, hardware_profile)

    issues: list[Issue] = []
    issues.extend(_unanswered_categories(build))
    issues.extend(_graph_issues(world))

    unchecked: list[tuple[str, str]] = []
    for rule in rule_set:
        result = rule.when.evaluate(world)
        if result is TRUE:
            issues.append(_issue_from_rule(rule, world))
        elif result is UNKNOWN:
            unchecked.append((rule.id, _why_undecided(rule, world)))

    return Report(
        issues=tuple(_ordered(_deduplicate(issues))),
        unchecked=tuple(unchecked),
        rules_evaluated=len(rule_set),
        hardware_known=world.hardware_known,
    )


def _why_undecided(rule: Rule, world: World) -> str:
    """What would have to be known for this rule to reach an answer.

    A rule can be undecided for more than one reason at once — an unrecognised
    graphics model *and* no scan having happened. No scan is reported first
    because it is the one the user can do something about, and telling someone
    their GPU is unrecognised when nothing has looked at their GPU yet is worse
    than saying nothing.
    """
    if not world.hardware_known and any(
        key.startswith("hardware.") for key in rule.fact_keys()
    ):
        return "a hardware scan"
    return rule.needs


def _issue_from_rule(rule: Rule, world: World) -> Issue:
    return Issue(
        severity=rule.severity,
        title=render(rule.title, world.bindings),
        detail=render(rule.detail, world.bindings),
        fix=render(rule.fix, world.bindings),
        key=f"rule:{rule.id}",
        rule_id=rule.id,
        components=rule.components(),
        suggestion=rule.suggest,
        reference=rule.reference,
    )


def _unanswered_categories(build: Build) -> list[Issue]:
    """A question with no answer, unless an empty answer is a legitimate one."""
    found: list[Issue] = []
    for category in CATEGORIES:
        if build.selected_id(category.id) is not None or category.optional:
            continue
        found.append(
            Issue(
                severity="warning",
                title=f"No {category.name.lower()} selected",
                detail=(
                    f"{category.question} Nothing is chosen, so this layer of the "
                    "stack is empty."
                ),
                fix=f"Open Compose and pick something under {category.name}.",
                key=f"unanswered:{category.id}",
                rule_id="catalogue/unanswered",
            )
        )
    return found


def _graph_issues(world: World) -> list[Issue]:
    """Everything that follows from the catalogue's own relationships."""
    selected = world.selected
    closure = requirement_closure(selected)
    implied = {
        component_id: path
        for component_id, path in closure.items()
        if component_id not in selected
    }

    found: list[Issue] = []
    found.extend(_missing_requirements(implied))
    found.extend(_conflicts(selected, implied))
    found.extend(_unmet_recommendations(selected))
    return found


def _missing_requirements(implied: Mapping[str, tuple[str, ...]]) -> list[Issue]:
    """Components the build needs but does not contain.

    A chain longer than one hop is reported as a chain. "Hardened needs
    linux-hardened" is useful; "Hardened → linux-hardened, and linux-hardened
    is not in this build" is the sentence that actually tells someone what to
    do next.
    """
    found: list[Issue] = []
    for component_id, path in sorted(implied.items()):
        asker_id = path[-2]
        asker = component_name(asker_id)
        needed = component_name(component_id)
        route = (
            f"\n\nHow this build asks for it:  {_chain(path)}" if len(path) > 2 else ""
        )
        found.append(
            Issue(
                severity="error",
                title=f"{asker} requires {needed}",
                detail=(
                    f"{asker} does not work without {needed}, and the current build "
                    f"does not include it.{route}"
                ),
                fix=(
                    f"Select {needed} under {category_name_of(component_id)}, or "
                    f"choose a different {category_name_of(asker_id).lower()}."
                ),
                key=f"requires:{asker_id}->{component_id}",
                rule_id="catalogue/requires",
                components=(asker_id, component_id),
                suggestion=_suggestion_for(component_id),
            )
        )
    return found


def _conflicts(
    selected: frozenset[str], implied: Mapping[str, tuple[str, ...]]
) -> list[Issue]:
    """Two things that cannot be in the same system, however they got there.

    Both directly selected components and components dragged in by a
    requirement count, which is what turns "hardened and nvidia" — a pair the
    catalogue never mentions together — into an explained error.
    """
    present = set(selected) | set(implied)
    found: list[Issue] = []

    for pair in sorted(CONFLICT_PAIRS, key=lambda p: sorted(p)):
        if not pair <= present:
            continue
        left, right = sorted(pair)
        detail_parts = [
            f"{component_name(left)} and {component_name(right)} cannot be "
            "installed on the same system."
        ]
        for component_id in (left, right):
            path = implied.get(component_id)
            if path:
                detail_parts.append(
                    f"{component_name(component_id)} is not something you picked "
                    f"directly — it is pulled in by {component_name(path[0])}:  "
                    f"{_chain(path)}"
                )
        found.append(
            Issue(
                severity="error",
                title=f"{component_name(left)} conflicts with {component_name(right)}",
                detail="\n\n".join(detail_parts),
                fix=(
                    f"Drop one of them — replace {component_name(left)} under "
                    f"{category_name_of(left)}, or {component_name(right)} under "
                    f"{category_name_of(right)}."
                ),
                key=f"conflict:{left}+{right}",
                rule_id="catalogue/conflicts",
                components=(left, right),
            )
        )
    return found


def _unmet_recommendations(selected: frozenset[str]) -> list[Issue]:
    """Pairings that are not required but are what everyone else runs."""
    found: list[Issue] = []
    for component_id in sorted(selected):
        component = COMPONENTS_BY_ID.get(component_id)
        if component is None:
            continue
        for recommended_id in component.recommends:
            if recommended_id in selected:
                continue
            found.append(
                Issue(
                    severity="info",
                    title=(
                        f"{component.name} pairs well with "
                        f"{component_name(recommended_id)}"
                    ),
                    detail=(
                        f"{component.name} works without it, but "
                        f"{component_name(recommended_id)} is the combination most "
                        "people run and most documentation assumes."
                    ),
                    fix=(
                        f"Consider {component_name(recommended_id)} under "
                        f"{category_name_of(recommended_id)}."
                    ),
                    key=f"recommends:{component_id}->{recommended_id}",
                    rule_id="catalogue/recommends",
                    components=(component_id, recommended_id),
                    suggestion=_suggestion_for(recommended_id),
                )
            )
    return found


def _suggestion_for(component_id: str) -> Suggestion | None:
    """The machine-applicable form of "select this component"."""
    category_id = CATEGORY_OF.get(component_id)
    return Suggestion(category_id, component_id) if category_id else None


# ── ordering and identity ─────────────────────────────────────────────────────


def _deduplicate(issues: list[Issue]) -> list[Issue]:
    """One issue per key. Keys are assigned by whatever produced the issue, so
    this never has to look at the wording of a title."""
    seen: set[str] = set()
    unique: list[Issue] = []
    for issue in issues:
        identity = issue.key or f"{issue.severity}:{issue.title}"
        if identity in seen:
            continue
        seen.add(identity)
        unique.append(issue)
    return unique


def _ordered(issues: list[Issue]) -> list[Issue]:
    """Worst first, then stable by key so the list never reshuffles itself."""
    return sorted(
        issues,
        key=lambda issue: (SEVERITY_ORDER.get(issue.severity, 9), issue.key, issue.title),
    )
