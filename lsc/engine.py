"""The compatibility engine — milestone 3, and the reason this project exists.

What replaced the placeholder, and why it is worth more than a longer walk over
the same three tuple fields:

**It resolves before it judges.** Selecting the Hardened security profile pulls
in the hardened kernel, because that profile declares it as a requirement. The
hardened kernel refuses the proprietary NVIDIA driver. The old check never saw
that, because it only compared what the user had literally selected, and
`linux-hardened` was not in that list. The engine first computes the *effective
set* — every selection plus everything those selections drag in behind them,
transitively — and only then looks for problems. The conflict now surfaces, with
the chain that produced it spelled out, which is the difference between "these
two cannot go together" and an error nobody can act on.

**It can tell a gap from a contradiction.** "Hyprland requires Wayland and you
have not chosen a display server" is a gap; the answer is to choose one.
"Hyprland requires Wayland and you chose Xorg" is a contradiction; one of two
decisions has to be abandoned, and which one is the user's call. The placeholder
printed the same sentence for both.

**It reasons about versions.** Components may declare the oldest kernel they
will run on, and kernel components carry the version of their series, so a floor
can actually be compared against something instead of being decoration.

**It knows about the machine, when there is one.** Rules may ask what GPU is in
this computer, how much memory it has, or which modules are loaded right now —
and are skipped entirely when nothing has been detected, rather than drawing
conclusions from an absence. See the note at the top of conditions.py.

**The knowledge is separable from the evaluation.** Conditional facts live in
data/rules.py as data. This module contains no Linux knowledge at all: every
sentence a user reads comes either from the catalogue or from a rule.

What it still does not do, stated plainly because the README's status section
depends on it being accurate: there is no package-level dependency solving (the
graph is components, not packages), no notion of a rule's confidence, and the
kernel versions in the catalogue are written down by hand and go stale.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from lsc.conditions import Context, parse_version
from lsc.data.catalog import CATEGORIES, COMPONENTS_BY_ID, component_name
from lsc.data.rules import RULES, Rule, rules_needing_hardware
from lsc.models import Build, Issue

SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}

# Which category a component id belongs to, built once at import time. The
# placeholder rebuilt this by scanning every category on every lookup.
CATEGORY_OF: dict[str, str] = {
    component.id: category.id
    for category in CATEGORIES
    for component in category.components
}
CATEGORY_NAME: dict[str, str] = {category.id: category.name for category in CATEGORIES}


# ── Resolution ────────────────────────────────────────────────────────────────


@dataclass
class Resolution:
    """The build, worked out.

    `effective` maps a component id to the chain of requirements that brought it
    in: an empty tuple for something the user chose, `("hardened",)` for
    something pulled in by the Hardened profile. Keeping the chain rather than a
    bare flag is what lets an issue explain itself.
    """

    effective: dict[str, tuple[str, ...]] = field(default_factory=dict)
    contradictions: list[tuple[str, str, str]] = field(default_factory=list)
    gaps: list[tuple[str, str]] = field(default_factory=list)

    @property
    def implied(self) -> dict[str, tuple[str, ...]]:
        """Only the components nobody chose — the ones the engine worked out."""
        return {cid: chain for cid, chain in self.effective.items() if chain}


def resolve(build: Build) -> Resolution:
    """Expand a build into everything it actually implies.

    Breadth-first over `requires`, so the chain recorded for an implied
    component is the shortest one that explains it. Three things can happen to a
    requirement:

    * the category it belongs to already holds exactly it — satisfied, nothing
      to say;
    * the category holds something else — a contradiction, which no amount of
      resolving can fix, so it is recorded and not followed;
    * the category is empty — the requirement is implied, added to the effective
      set, and its own requirements are followed in turn.
    """
    resolution = Resolution()
    for component_id in build.selections.values():
        if component_id in COMPONENTS_BY_ID:
            resolution.effective[component_id] = ()

    # (component id, the chain that led here). Seeded with the user's choices.
    queue: list[tuple[str, tuple[str, ...]]] = [
        (component_id, ()) for component_id in resolution.effective
    ]

    while queue:
        component_id, chain = queue.pop(0)
        component = COMPONENTS_BY_ID.get(component_id)
        if component is None:
            continue

        for required_id in component.requires:
            if required_id in resolution.effective:
                continue

            category_id = CATEGORY_OF.get(required_id)
            if category_id is None:
                # Guarded by tests/test_catalog.py; skip rather than crash.
                continue

            chosen = build.selections.get(category_id)
            if chosen and chosen != required_id:
                resolution.contradictions.append((component_id, required_id, chosen))
                continue

            if not chosen:
                resolution.gaps.append((component_id, required_id))

            next_chain = chain + (component_id,)
            resolution.effective[required_id] = next_chain
            queue.append((required_id, next_chain))

    return resolution


# ── Context ───────────────────────────────────────────────────────────────────


def build_context(
    build: Build,
    resolution: Resolution,
    hardware: Mapping[str, Any] | None = None,
    hardware_is_real: bool = False,
) -> Context:
    """Assemble everything the rules are allowed to look at."""
    tags: set[str] = set()
    for component_id in resolution.effective:
        component = COMPONENTS_BY_ID.get(component_id)
        if component is not None:
            tags.update(component.tags)

    return Context(
        selections=dict(build.selections),
        effective=dict(resolution.effective),
        tags=frozenset(tags),
        kernel_version=_kernel_version(resolution),
        hardware=hardware,
        hardware_is_real=hardware_is_real,
    )


def _kernel_version(resolution: Resolution) -> tuple[int, ...] | None:
    """The version of the kernel this build would run, if it is known.

    Read from the catalogue rather than from the machine: the question a rule
    asks is about the system being composed, not the system doing the composing.
    """
    for component_id in resolution.effective:
        if CATEGORY_OF.get(component_id) != "kernel":
            continue
        component = COMPONENTS_BY_ID.get(component_id)
        if component is not None and component.version:
            parsed = parse_version(component.version)
            return parsed or None
    return None


# ── The pass itself ───────────────────────────────────────────────────────────


def check(
    build: Build,
    hardware: Mapping[str, Any] | None = None,
    hardware_is_real: bool = False,
) -> list[Issue]:
    """Evaluate a build and return everything worth telling the user, worst first.

    `hardware` is optional and defaults to nothing, which is deliberate: a
    caller that has not detected a machine gets an answer about the build alone,
    and the hardware-conditioned rules stay out of it. Passing the *sample*
    profile with `hardware_is_real=False` is the same as passing nothing — the
    fixture must never be mistaken for a reading.
    """
    resolution = resolve(build)
    ctx = build_context(build, resolution, hardware, hardware_is_real)

    issues: list[Issue] = []
    issues.extend(_unanswered_categories(build))
    issues.extend(_contradictions(resolution))
    issues.extend(_gaps(resolution))
    issues.extend(_conflicts(resolution))
    issues.extend(_kernel_floors(resolution, ctx))
    issues.extend(_recommendations(build, resolution))
    issues.extend(evaluate_rules(ctx))

    issues = _deduplicate(issues)
    issues.sort(key=lambda issue: (SEVERITY_ORDER.get(issue.severity, 9), issue.title))
    return issues


def evaluate_rules(ctx: Context) -> list[Issue]:
    """Run the curated rule set against a context.

    A rule whose conditions ask about the machine is skipped when no machine has
    been read. That is the one piece of control flow in this function, and it is
    here rather than inside the conditions because a rule is the unit that can
    honestly be said to apply or not.
    """
    issues: list[Issue] = []
    for rule in RULES:
        if rule.when.needs_hardware and not ctx.hardware_is_real:
            continue
        if not rule.when.holds(ctx):
            continue
        issues.append(
            Issue(
                severity=rule.severity,
                title=rule.title,
                detail=rule.detail,
                fix=rule.fix,
                rule_id=rule.id,
                components=rule.components,
            )
        )
    return issues


# ── Issue sources, one per kind of problem ───────────────────────────────────


def _unanswered_categories(build: Build) -> list[Issue]:
    """A question the user has not answered, unless empty is a valid answer."""
    issues: list[Issue] = []
    for category in CATEGORIES:
        if build.selections.get(category.id) or category.optional:
            continue
        issues.append(
            Issue(
                severity="warning",
                title=f"No {category.name.lower()} selected",
                detail=(
                    f"{category.question} Nothing is chosen, so this layer of the "
                    "stack is empty."
                ),
                fix=f"Open Compose and pick something under {category.name}.",
                rule_id="category-unanswered",
                components=(),
            )
        )
    return issues


def _contradictions(resolution: Resolution) -> list[Issue]:
    """Two decisions that cannot both stand.

    The interesting half of requirement checking, and the half the placeholder
    could not express: the requirement is not merely absent, its slot is taken
    by something incompatible, so telling the user to "select it" would be
    telling them to undo a choice they made on purpose.
    """
    issues: list[Issue] = []
    for source_id, required_id, chosen_id in resolution.contradictions:
        category_id = CATEGORY_OF.get(required_id, "")
        category = CATEGORY_NAME.get(category_id, "the catalogue")
        issues.append(
            Issue(
                severity="error",
                title=(
                    f"{component_name(source_id)} needs "
                    f"{component_name(required_id)}, but you chose "
                    f"{component_name(chosen_id)}"
                ),
                detail=(
                    f"{component_name(source_id)} only works with "
                    f"{component_name(required_id)}, and {category} is currently "
                    f"set to {component_name(chosen_id)}. These are two decisions "
                    "that cannot both stand — this is not a missing package, it is "
                    "a choice that has to be made."
                ),
                fix=(
                    f"Either change {category} to {component_name(required_id)}, or "
                    f"replace {component_name(source_id)} with something that works "
                    f"with {component_name(chosen_id)}."
                ),
                rule_id="requirement-contradiction",
                components=(source_id, required_id, chosen_id),
            )
        )
    return issues


def _gaps(resolution: Resolution) -> list[Issue]:
    """A requirement that nothing blocks — the build just has not said it yet."""
    issues: list[Issue] = []
    for source_id, required_id in resolution.gaps:
        category_id = CATEGORY_OF.get(required_id, "")
        category = CATEGORY_NAME.get(category_id, "the catalogue")
        issues.append(
            Issue(
                severity="warning",
                title=(
                    f"{component_name(source_id)} implies "
                    f"{component_name(required_id)}"
                ),
                detail=(
                    f"{component_name(source_id)} requires "
                    f"{component_name(required_id)}, and nothing is selected under "
                    f"{category}, so the build will pull it in. Nothing is wrong "
                    "here; it is worth seeing rather than discovering in the "
                    "generated package list."
                ),
                fix=(
                    f"Select {component_name(required_id)} under {category} to make "
                    "the decision explicit, or leave it and let the build imply it."
                ),
                rule_id="requirement-implied",
                components=(source_id, required_id),
            )
        )
    return issues


def _conflicts(resolution: Resolution) -> list[Issue]:
    """Two components in the effective set that refuse each other.

    Because this runs over the effective set rather than the selections, it
    catches the conflicts that arrive through a requirement — and when it does,
    the explanation names the chain, so the user can see why a component they
    never chose is in the argument.
    """
    issues: list[Issue] = []
    seen: set[frozenset[str]] = set()

    for component_id, chain in resolution.effective.items():
        component = COMPONENTS_BY_ID.get(component_id)
        if component is None:
            continue
        for other_id in component.conflicts:
            if other_id not in resolution.effective:
                continue
            pair = frozenset({component_id, other_id})
            if pair in seen:
                continue
            seen.add(pair)

            other_chain = resolution.effective.get(other_id, ())
            issues.append(
                Issue(
                    severity="error",
                    title=(
                        f"{component_name(component_id)} conflicts with "
                        f"{component_name(other_id)}"
                    ),
                    detail=(
                        f"{_describe_presence(component_id, chain)} "
                        f"{_describe_presence(other_id, other_chain)} "
                        "They cannot be installed together."
                    ),
                    fix=_conflict_fix(component_id, chain, other_id, other_chain),
                    rule_id="conflict",
                    components=(component_id, other_id),
                )
            )
    return issues


def _describe_presence(component_id: str, chain: tuple[str, ...]) -> str:
    """One sentence on why a component is in the build at all."""
    name = component_name(component_id)
    if not chain:
        return f"{name} is selected."
    path = " → ".join(component_name(link) for link in chain)
    return f"{name} is not selected directly — it is required by {path}."


def _conflict_fix(
    component_id: str,
    chain: tuple[str, ...],
    other_id: str,
    other_chain: tuple[str, ...],
) -> str:
    """What to actually change, which depends on which side was chosen.

    Telling someone to "drop linux-hardened" is useless when they never selected
    it. The thing to drop is whatever pulled it in.
    """
    left = chain[0] if chain else component_id
    right = other_chain[0] if other_chain else other_id
    if left == right:
        return (
            f"Both come from {component_name(left)}. That selection cannot be "
            "satisfied as it stands — replace it."
        )
    return (
        f"Change one of the two decisions behind this: {component_name(left)} or "
        f"{component_name(right)}."
    )


def _kernel_floors(resolution: Resolution, ctx: Context) -> list[Issue]:
    """Components that want a newer kernel than this build provides.

    The README's `kernel_min` made real. Quiet by design: it says nothing while
    every floor is met, which with the current catalogue is the normal case. It
    earns its place the first time a component needs something newer than the
    LTS series, and it is exercised directly by the tests so it does not rot
    while it waits.
    """
    if ctx.kernel_version is None:
        return []

    issues: list[Issue] = []
    for component_id in resolution.effective:
        component = COMPONENTS_BY_ID.get(component_id)
        if component is None or not component.kernel_min:
            continue
        floor = parse_version(component.kernel_min)
        if not floor or ctx.kernel_version >= floor:
            continue

        running = ".".join(str(part) for part in ctx.kernel_version)
        issues.append(
            Issue(
                severity="warning",
                title=(
                    f"{component.name} wants kernel {component.kernel_min} or newer"
                ),
                detail=(
                    f"This build's kernel is {running}, which is older than the "
                    f"{component.kernel_min} {component.name} expects. It will "
                    "probably still start; the features it relies on the kernel for "
                    "are the parts that will be missing, and they fail quietly."
                ),
                fix=(
                    "Choose a newer kernel, or a component that does not ask for "
                    "one."
                ),
                rule_id="kernel-floor",
                components=(component_id,),
            )
        )
    return issues


def _recommendations(build: Build, resolution: Resolution) -> list[Issue]:
    """Pairings that are not required but are what the documentation assumes.

    Category-aware, unlike the placeholder: if the recommended component's slot
    is already filled by something else, saying "consider it" is wrong — the
    user has to be told what they would be giving up.
    """
    issues: list[Issue] = []
    for component_id in resolution.effective:
        component = COMPONENTS_BY_ID.get(component_id)
        if component is None:
            continue
        for recommended_id in component.recommends:
            if recommended_id in resolution.effective:
                continue
            category_id = CATEGORY_OF.get(recommended_id, "")
            category = CATEGORY_NAME.get(category_id, "the catalogue")
            chosen = build.selections.get(category_id)

            if chosen:
                detail = (
                    f"{component.name} is most often run with "
                    f"{component_name(recommended_id)}, and this build uses "
                    f"{component_name(chosen)} instead. That is a legitimate "
                    "choice — it just means less of the documentation you find "
                    "will match what you have."
                )
                fix = (
                    f"Switch {category} to {component_name(recommended_id)} for the "
                    f"well-trodden path, or keep {component_name(chosen)} knowingly."
                )
            else:
                detail = (
                    f"{component.name} works without it, but "
                    f"{component_name(recommended_id)} is the combination most "
                    "people run and most documentation assumes."
                )
                fix = f"Consider {component_name(recommended_id)} under {category}."

            issues.append(
                Issue(
                    severity="info",
                    title=(
                        f"{component.name} pairs well with "
                        f"{component_name(recommended_id)}"
                    ),
                    detail=detail,
                    fix=fix,
                    rule_id="recommendation",
                    components=(component_id, recommended_id),
                )
            )
    return issues


# ── Presenting the result ─────────────────────────────────────────────────────


def _deduplicate(issues: Iterable[Issue]) -> list[Issue]:
    """One issue per (rule, subject).

    Keyed on the rule id and the unordered set of components rather than on the
    wording, so a conflict reported from both directions collapses without the
    string surgery the placeholder needed to do.
    """
    seen: set[tuple[str, frozenset[str], str]] = set()
    unique: list[Issue] = []
    for issue in issues:
        key = (issue.rule_id, frozenset(issue.components), issue.title)
        if key in seen:
            continue
        seen.add(key)
        unique.append(issue)
    return unique


def summarise(issues: Iterable[Issue]) -> dict[str, int]:
    """Count issues by severity, for the headline on the Validate screen."""
    counts = {"error": 0, "warning": 0, "info": 0}
    for issue in issues:
        if issue.severity in counts:
            counts[issue.severity] += 1
    return counts


def build_is_installable(issues: Iterable[Issue]) -> bool:
    """True when nothing outright blocks this build."""
    return not any(issue.severity == "error" for issue in issues)


@dataclass(frozen=True)
class Coverage:
    """How much of the rule set actually ran, so the screen can say so.

    A tool that gives advice should be able to state how much it looked at. With
    no hardware reading, roughly a third of the rules never run, and claiming a
    clean bill of health on that basis would be the same kind of overstatement
    the project has been careful to avoid elsewhere.
    """

    rules_total: int
    rules_evaluated: int
    rules_skipped: int
    implied: dict[str, tuple[str, ...]]

    @property
    def hardware_was_used(self) -> bool:
        return self.rules_skipped == 0


def coverage(build: Build, hardware_is_real: bool = False) -> Coverage:
    """Describe what a `check` of this build would and would not have examined."""
    needing_hardware = len(rules_needing_hardware())
    skipped = 0 if hardware_is_real else needing_hardware
    return Coverage(
        rules_total=len(RULES),
        rules_evaluated=len(RULES) - skipped,
        rules_skipped=skipped,
        implied=resolve(build).implied,
    )


def explain(rule_id: str) -> Rule | None:
    """The rule behind an issue, for a "why does it say that?" view."""
    from lsc.data.rules import RULES_BY_ID

    return RULES_BY_ID.get(rule_id)
