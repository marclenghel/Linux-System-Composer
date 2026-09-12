"""The rule language: conditions expressed as data.

A rule in this project is not a Python function. It is a tree of small frozen
records that the evaluator walks, and that choice is the one decision in
milestone 3 that would have been expensive to get wrong.

Why not lambdas, which would be shorter to write? Because a lambda cannot be
written to a TOML file. The README promises a data layer holding compatibility
rules, and a rule set that only exists as Python is a rule set that has to be
rewritten the day it moves out of Python. A tree of records survives the round
trip to JSON and back — tests/test_conditions.py proves that it does rather
than asserting it — so moving the rules into files later is a loader, not a
rewrite of the evaluator.

Why not strings of Python handed to eval()? Because that gives every rule file
the power to run anything on the machine, in a project whose README promises a
safety layer.

Three-valued logic, and UNKNOWN is the interesting value. "Is the graphics card
older than Turing?" has no answer until the machine has actually been scanned,
and answering FALSE there would quietly pass a build that is about to fail. So
unknown propagates the way Kleene's logic says it should, and the evaluator
reports an undecidable rule as unchecked instead of dropping it.

The three values are Python's own None/True/False rather than an enum, because
None already means "no answer" everywhere else in the language and because
`result is UNKNOWN` reads better than any wrapper would.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, Optional

if TYPE_CHECKING:  # pragma: no cover - only needed for type checking
    from lsc.facts import World

Truth = Optional[bool]

TRUE: Truth = True
FALSE: Truth = False
UNKNOWN: Truth = None


# ── the base type and the node registry ───────────────────────────────────────


class Condition:
    """One node of a condition tree.

    Subclasses are frozen dataclasses, so a condition is hashable, comparable,
    and safe to share between rules — a rule set is a constant, and a constant
    that can be mutated by accident is a bug waiting for a demo.
    """

    kind: ClassVar[str] = ""

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if not cls.kind:
            return
        if cls.kind in _NODES:
            raise ValueError(f"two condition types claim kind {cls.kind!r}")
        _NODES[cls.kind] = cls

    def evaluate(self, world: World) -> Truth:
        raise NotImplementedError

    def to_dict(self) -> dict[str, Any]:
        raise NotImplementedError

    # component_ids and fact_keys exist for the integrity tests rather than for
    # the evaluator. A rule naming a component the catalogue does not have is
    # dead knowledge, and the only way to notice is to ask every node what it
    # refers to.

    def component_ids(self) -> tuple[str, ...]:
        return ()

    def fact_keys(self) -> tuple[str, ...]:
        return ()

    def children(self) -> tuple[Condition, ...]:
        return ()

    def walk(self) -> tuple[Condition, ...]:
        """This node and every node beneath it."""
        found: list[Condition] = [self]
        for child in self.children():
            found.extend(child.walk())
        return tuple(found)

    @staticmethod
    def from_dict(data: dict[str, Any]) -> Condition:
        """Rebuild a condition from its serialised form."""
        kind = data.get("kind")
        node_type = _NODES.get(kind or "")
        if node_type is None:
            raise ValueError(f"unknown condition kind {kind!r}")
        return node_type._load(data)

    @classmethod
    def _load(cls, data: dict[str, Any]) -> Condition:
        raise NotImplementedError


_NODES: dict[str, type[Condition]] = {}


# ── what the build contains ───────────────────────────────────────────────────


@dataclass(frozen=True)
class Selected(Condition):
    """True when this component id is one of the user's choices."""

    kind: ClassVar[str] = "selected"
    component_id: str

    def evaluate(self, world: World) -> Truth:
        return self.component_id in world.selected

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "component_id": self.component_id}

    @classmethod
    def _load(cls, data: dict[str, Any]) -> Selected:
        return cls(data["component_id"])

    def component_ids(self) -> tuple[str, ...]:
        return (self.component_id,)


@dataclass(frozen=True)
class AnySelected(Condition):
    """True when at least one of these component ids is selected."""

    kind: ClassVar[str] = "any_selected"
    options: tuple[str, ...]

    def __init__(self, *options: str) -> None:
        object.__setattr__(self, "options", tuple(options))

    def evaluate(self, world: World) -> Truth:
        return any(option in world.selected for option in self.options)

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "options": list(self.options)}

    @classmethod
    def _load(cls, data: dict[str, Any]) -> AnySelected:
        return cls(*data["options"])

    def component_ids(self) -> tuple[str, ...]:
        return self.options


@dataclass(frozen=True)
class CategoryIs(Condition):
    """True when a category's answer is exactly this component."""

    kind: ClassVar[str] = "category_is"
    category_id: str
    component_id: str

    def evaluate(self, world: World) -> Truth:
        return world.selections.get(self.category_id) == self.component_id

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "category_id": self.category_id,
            "component_id": self.component_id,
        }

    @classmethod
    def _load(cls, data: dict[str, Any]) -> CategoryIs:
        return cls(data["category_id"], data["component_id"])

    def component_ids(self) -> tuple[str, ...]:
        return (self.component_id,)


@dataclass(frozen=True)
class CategoryEmpty(Condition):
    """True when a category has no answer at all."""

    kind: ClassVar[str] = "category_empty"
    category_id: str

    def evaluate(self, world: World) -> Truth:
        return world.selections.get(self.category_id) is None

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "category_id": self.category_id}

    @classmethod
    def _load(cls, data: dict[str, Any]) -> CategoryEmpty:
        return cls(data["category_id"])


@dataclass(frozen=True)
class HasTag(Condition):
    """True when any selected component carries this tag.

    Tags are how a rule generalises. "Any Wayland compositor" is a question the
    catalogue can already answer, and asking it by tag means adding a new
    compositor later does not mean editing every rule about compositors.
    """

    kind: ClassVar[str] = "has_tag"
    tag: str

    def evaluate(self, world: World) -> Truth:
        return self.tag in world.tags

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "tag": self.tag}

    @classmethod
    def _load(cls, data: dict[str, Any]) -> HasTag:
        return cls(data["tag"])


# ── what the world knows ──────────────────────────────────────────────────────


OPERATORS = {
    "eq": lambda value, wanted: value == wanted,
    "ne": lambda value, wanted: value != wanted,
    "lt": lambda value, wanted: value < wanted,
    "lte": lambda value, wanted: value <= wanted,
    "gt": lambda value, wanted: value > wanted,
    "gte": lambda value, wanted: value >= wanted,
    "in": lambda value, wanted: value in wanted,
    "contains": lambda value, wanted: wanted in value,
}


@dataclass(frozen=True)
class Fact(Condition):
    """Compare one fact about the world against a value.

    A missing fact is UNKNOWN, never False. hardware.ram_gb is absent because
    nothing has scanned the machine yet, not because the machine has no memory,
    and the difference between those two is the difference between an honest
    warning and a made-up one.
    """

    kind: ClassVar[str] = "fact"
    key: str
    op: str
    value: Any

    def __post_init__(self) -> None:
        if self.op not in OPERATORS:
            raise ValueError(f"unknown operator {self.op!r} in fact {self.key!r}")

    def evaluate(self, world: World) -> Truth:
        if self.key not in world.facts:
            return UNKNOWN
        actual = world.facts[self.key]
        if actual is None:
            return UNKNOWN
        try:
            return bool(OPERATORS[self.op](actual, self.value))
        except TypeError:
            # Comparing a string against a number means the fact is not the
            # shape the rule expected. That is a bug in the rule, but at
            # runtime the honest answer is still "cannot tell" rather than a
            # traceback in front of a class.
            return UNKNOWN

    def to_dict(self) -> dict[str, Any]:
        value = list(self.value) if isinstance(self.value, tuple) else self.value
        return {"kind": self.kind, "key": self.key, "op": self.op, "value": value}

    @classmethod
    def _load(cls, data: dict[str, Any]) -> Fact:
        value = data["value"]
        return cls(data["key"], data["op"], tuple(value) if isinstance(value, list) else value)

    def fact_keys(self) -> tuple[str, ...]:
        return (self.key,)


# ── versions ──────────────────────────────────────────────────────────────────

_NUMBERS = re.compile(r"\d+")


def parse_version(text: Any) -> tuple[int, ...] | None:
    """Turn a version string into something comparable, or None.

    Kernel versions arrive dressed up: "6.12.8-arch1-1", "6.6.87.1-microsoft".
    Everything after the first dash is packaging rather than version, so it is
    cut before the numbers are read — otherwise "6.12.8-arch1" would sort above
    "6.12.9" on the strength of its build number.
    """
    if text is None:
        return None
    head = str(text).split("-", 1)[0]
    numbers = _NUMBERS.findall(head)
    if not numbers:
        return None
    return tuple(int(number) for number in numbers)


def compare_versions(left: tuple[int, ...], right: tuple[int, ...]) -> int:
    """-1, 0 or 1. Missing trailing components count as zero, so 6.6 == 6.6.0."""
    width = max(len(left), len(right))
    padded_left = left + (0,) * (width - len(left))
    padded_right = right + (0,) * (width - len(right))
    if padded_left < padded_right:
        return -1
    return 0 if padded_left == padded_right else 1


@dataclass(frozen=True)
class VersionAtLeast(Condition):
    """True when the version in a fact is this version or newer."""

    kind: ClassVar[str] = "version_at_least"
    key: str
    version: str

    def evaluate(self, world: World) -> Truth:
        actual = parse_version(world.facts.get(self.key))
        wanted = parse_version(self.version)
        if actual is None or wanted is None:
            return UNKNOWN
        return compare_versions(actual, wanted) >= 0

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "key": self.key, "version": self.version}

    @classmethod
    def _load(cls, data: dict[str, Any]) -> VersionAtLeast:
        return cls(data["key"], data["version"])

    def fact_keys(self) -> tuple[str, ...]:
        return (self.key,)


@dataclass(frozen=True)
class VersionBelow(Condition):
    """True when the version in a fact is older than this one.

    This is the README's own example — "kernel_min": "6.6" — written as
    something the evaluator can actually check.
    """

    kind: ClassVar[str] = "version_below"
    key: str
    version: str

    def evaluate(self, world: World) -> Truth:
        actual = parse_version(world.facts.get(self.key))
        wanted = parse_version(self.version)
        if actual is None or wanted is None:
            return UNKNOWN
        return compare_versions(actual, wanted) < 0

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "key": self.key, "version": self.version}

    @classmethod
    def _load(cls, data: dict[str, Any]) -> VersionBelow:
        return cls(data["key"], data["version"])

    def fact_keys(self) -> tuple[str, ...]:
        return (self.key,)


# ── combining conditions ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class AllOf(Condition):
    """Every condition must hold.

    One FALSE settles it even when the rest are unknown: "you did not select
    Hyprland" makes the whole Hyprland rule irrelevant no matter what is known
    about the graphics card. That short circuit is exactly why the logic has to
    be Kleene's rather than "unknown poisons everything".
    """

    kind: ClassVar[str] = "all_of"
    conditions: tuple[Condition, ...]

    def __init__(self, *conditions: Condition) -> None:
        # Written as *args because a rule reads far better as
        # AllOf(Selected("hyprland"), Selected("nvidia")) than as a list.
        object.__setattr__(self, "conditions", tuple(conditions))

    def evaluate(self, world: World) -> Truth:
        results = [condition.evaluate(world) for condition in self.conditions]
        if any(result is FALSE for result in results):
            return FALSE
        if any(result is UNKNOWN for result in results):
            return UNKNOWN
        return TRUE

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "conditions": [c.to_dict() for c in self.conditions]}

    @classmethod
    def _load(cls, data: dict[str, Any]) -> AllOf:
        return cls(*(Condition.from_dict(item) for item in data["conditions"]))

    def children(self) -> tuple[Condition, ...]:
        return self.conditions


@dataclass(frozen=True)
class AnyOf(Condition):
    """At least one condition must hold. One TRUE settles it."""

    kind: ClassVar[str] = "any_of"
    conditions: tuple[Condition, ...]

    def __init__(self, *conditions: Condition) -> None:
        object.__setattr__(self, "conditions", tuple(conditions))

    def evaluate(self, world: World) -> Truth:
        results = [condition.evaluate(world) for condition in self.conditions]
        if any(result is TRUE for result in results):
            return TRUE
        if any(result is UNKNOWN for result in results):
            return UNKNOWN
        return FALSE

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "conditions": [c.to_dict() for c in self.conditions]}

    @classmethod
    def _load(cls, data: dict[str, Any]) -> AnyOf:
        return cls(*(Condition.from_dict(item) for item in data["conditions"]))

    def children(self) -> tuple[Condition, ...]:
        return self.conditions


@dataclass(frozen=True)
class Not(Condition):
    """Negation. The negation of "I don't know" is still "I don't know"."""

    kind: ClassVar[str] = "not"
    condition: Condition

    def evaluate(self, world: World) -> Truth:
        result = self.condition.evaluate(world)
        return UNKNOWN if result is UNKNOWN else not result

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "condition": self.condition.to_dict()}

    @classmethod
    def _load(cls, data: dict[str, Any]) -> Not:
        return cls(Condition.from_dict(data["condition"]))

    def children(self) -> tuple[Condition, ...]:
        return (self.condition,)


def node_kinds() -> tuple[str, ...]:
    """Every condition type the language knows, for the round-trip test."""
    return tuple(sorted(_NODES))
