"""Tests for the rule language itself.

Two things are being guarded here, and both of them are claims the project
makes out loud.

The first is that unknown is a real answer. Kleene's logic is not obvious — a
false inside an AND still settles the whole thing even when its neighbours are
unknown — and the entire "we could not check this" feature rests on getting it
right, so the truth tables are written out rather than reasoned about.

The second is that the rules are data. lsc/compat/conditions.py claims a condition
survives the round trip to JSON and back, which is what makes moving the rules
into TOML a loader rather than a rewrite. A claim like that is worth nothing
unless something checks it, so every node type the language knows is round
tripped, and a test fails if a new node type is added without one.
"""

from __future__ import annotations

import json
import unittest

from lsc.compat.conditions import (
    FALSE,
    TRUE,
    UNKNOWN,
    AllOf,
    AnyOf,
    AnySelected,
    CategoryEmpty,
    CategoryIs,
    Condition,
    Fact,
    HasTag,
    Not,
    Selected,
    VersionAtLeast,
    VersionBelow,
    node_kinds,
    parse_version,
)
from lsc.compat.facts import World
from lsc.models import Build


def world(**overrides) -> World:
    """A world with exactly the contents a test cares about."""
    defaults = {
        "build": Build(),
        "selected": frozenset({"hyprland", "nvidia"}),
        "selections": {"desktop": "hyprland", "gpu": "nvidia", "display": None},
        "tags": frozenset({"wayland", "tiling"}),
        "facts": {"kernel.version": "6.12", "hardware.ram_gb": 32.0},
        "bindings": {},
    }
    defaults.update(overrides)
    return World(**defaults)


# A condition that is always undecided, so the truth tables can be written
# without depending on any particular fact being absent.
UNDECIDED = Fact("nothing.knows.this", "eq", 1)


class TestSelectionConditions(unittest.TestCase):
    def test_selected(self) -> None:
        self.assertIs(Selected("hyprland").evaluate(world()), TRUE)
        self.assertIs(Selected("sway").evaluate(world()), FALSE)

    def test_any_selected(self) -> None:
        self.assertIs(AnySelected("sway", "nvidia").evaluate(world()), TRUE)
        self.assertIs(AnySelected("sway", "i3").evaluate(world()), FALSE)

    def test_category_is_and_empty(self) -> None:
        self.assertIs(CategoryIs("desktop", "hyprland").evaluate(world()), TRUE)
        self.assertIs(CategoryIs("desktop", "sway").evaluate(world()), FALSE)
        self.assertIs(CategoryEmpty("display").evaluate(world()), TRUE)
        self.assertIs(CategoryEmpty("desktop").evaluate(world()), FALSE)

    def test_has_tag(self) -> None:
        self.assertIs(HasTag("wayland").evaluate(world()), TRUE)
        self.assertIs(HasTag("x11").evaluate(world()), FALSE)

    def test_selection_conditions_are_never_undecided(self) -> None:
        """The composer always knows what is and is not selected.

        Only hardware can be unknown. If a selection condition ever returned
        UNKNOWN it would mean the build itself had become unreadable, and a
        rule would start hedging about something nobody needs it to hedge on.
        """
        empty = world(selected=frozenset(), selections={}, tags=frozenset())
        for condition in (
            Selected("hyprland"),
            AnySelected("hyprland", "sway"),
            CategoryIs("desktop", "hyprland"),
            CategoryEmpty("desktop"),
            HasTag("wayland"),
        ):
            with self.subTest(condition=type(condition).__name__):
                self.assertIsNot(condition.evaluate(empty), UNKNOWN)


class TestFacts(unittest.TestCase):
    def test_comparison_operators(self) -> None:
        self.assertIs(Fact("hardware.ram_gb", "gte", 16).evaluate(world()), TRUE)
        self.assertIs(Fact("hardware.ram_gb", "lt", 16).evaluate(world()), FALSE)
        self.assertIs(Fact("kernel.version", "eq", "6.12").evaluate(world()), TRUE)

    def test_in_and_contains_are_not_the_same_direction(self) -> None:
        facts = {"audio": "alsa", "modules": ("btrfs", "nvme")}
        self.assertIs(Fact("audio", "in", ("alsa", "pulseaudio")).evaluate(world(facts=facts)), TRUE)
        self.assertIs(Fact("modules", "contains", "btrfs").evaluate(world(facts=facts)), TRUE)
        self.assertIs(Fact("modules", "contains", "zfs").evaluate(world(facts=facts)), FALSE)

    def test_a_missing_fact_is_unknown_not_false(self) -> None:
        """The distinction the whole 'unchecked' feature is built on."""
        self.assertIs(Fact("hardware.gpu.nvidia_rank", "lt", 60).evaluate(world()), UNKNOWN)

    def test_a_null_fact_is_unknown(self) -> None:
        self.assertIs(Fact("k", "eq", 1).evaluate(world(facts={"k": None})), UNKNOWN)

    def test_comparing_incompatible_types_is_unknown_not_a_crash(self) -> None:
        undecidable = Fact("kernel.version", "lt", 6)
        self.assertIs(undecidable.evaluate(world()), UNKNOWN)

    def test_an_unknown_operator_is_refused_when_the_rule_is_written(self) -> None:
        """Better to fail at import than to quietly never fire."""
        with self.assertRaises(ValueError):
            Fact("hardware.ram_gb", "approximately", 16)


class TestVersions(unittest.TestCase):
    def test_packaging_suffixes_are_cut_before_the_numbers_are_read(self) -> None:
        self.assertEqual(parse_version("6.12.8-arch1-1"), (6, 12, 8))
        self.assertEqual(parse_version("6.6.87.1-microsoft-standard-WSL2"), (6, 6, 87, 1))
        self.assertEqual(parse_version("10.0.26200"), (10, 0, 26200))

    def test_a_build_number_cannot_outrank_a_real_version(self) -> None:
        """"6.12.8-arch1" must not sort above "6.12.9"."""
        self.assertLess(parse_version("6.12.8-arch1-1"), parse_version("6.12.9"))

    def test_unparseable_versions(self) -> None:
        self.assertIsNone(parse_version("Unknown"))
        self.assertIsNone(parse_version(None))

    def test_missing_components_count_as_zero(self) -> None:
        facts = {"kernel.version": "6.6"}
        self.assertIs(VersionAtLeast("kernel.version", "6.6.0").evaluate(world(facts=facts)), TRUE)
        self.assertIs(VersionBelow("kernel.version", "6.6.0").evaluate(world(facts=facts)), FALSE)

    def test_at_least_and_below(self) -> None:
        self.assertIs(VersionAtLeast("kernel.version", "6.6").evaluate(world()), TRUE)
        self.assertIs(VersionBelow("kernel.version", "6.6").evaluate(world()), FALSE)
        old = world(facts={"kernel.version": "6.1.70"})
        self.assertIs(VersionBelow("kernel.version", "6.6").evaluate(old), TRUE)

    def test_an_unreadable_version_is_unknown(self) -> None:
        unreadable = world(facts={"hardware.kernel": "Unknown"})
        self.assertIs(VersionBelow("hardware.kernel", "6.6").evaluate(unreadable), UNKNOWN)


class TestThreeValuedLogic(unittest.TestCase):
    """The truth tables, written out rather than reasoned about."""

    def test_all_of(self) -> None:
        cases = [
            ((TRUE, TRUE), TRUE),
            ((TRUE, FALSE), FALSE),
            ((TRUE, UNKNOWN), UNKNOWN),
            ((FALSE, UNKNOWN), FALSE),
            ((UNKNOWN, UNKNOWN), UNKNOWN),
        ]
        for inputs, expected in cases:
            with self.subTest(inputs=inputs):
                self.assertIs(AllOf(*map(_constant, inputs)).evaluate(world()), expected)

    def test_a_false_beats_an_unknown_in_all_of(self) -> None:
        """Why this matters: a rule about Hyprland must not report itself as
        unchecked on a build that has no Hyprland in it, however little is
        known about the graphics card."""
        condition = AllOf(Selected("sway"), UNDECIDED)
        self.assertIs(condition.evaluate(world()), FALSE)

    def test_any_of(self) -> None:
        cases = [
            ((FALSE, FALSE), FALSE),
            ((TRUE, FALSE), TRUE),
            ((TRUE, UNKNOWN), TRUE),
            ((FALSE, UNKNOWN), UNKNOWN),
            ((UNKNOWN, UNKNOWN), UNKNOWN),
        ]
        for inputs, expected in cases:
            with self.subTest(inputs=inputs):
                self.assertIs(AnyOf(*map(_constant, inputs)).evaluate(world()), expected)

    def test_not(self) -> None:
        self.assertIs(Not(Selected("hyprland")).evaluate(world()), FALSE)
        self.assertIs(Not(Selected("sway")).evaluate(world()), TRUE)
        self.assertIs(Not(UNDECIDED).evaluate(world()), UNKNOWN)

    def test_empty_combinators(self) -> None:
        """Vacuous truth, the same way every other language does it."""
        self.assertIs(AllOf().evaluate(world()), TRUE)
        self.assertIs(AnyOf().evaluate(world()), FALSE)


def _constant(value):
    """A condition that always returns the value given."""
    if value is TRUE:
        return Selected("hyprland")
    if value is FALSE:
        return Selected("sway")
    return UNDECIDED


# ── the claim that the rules are data ─────────────────────────────────────────

ONE_OF_EVERY_KIND: dict[str, Condition] = {
    "selected": Selected("hyprland"),
    "any_selected": AnySelected("nvidia", "nvidia-open"),
    "category_is": CategoryIs("gpu", "nvidia"),
    "category_empty": CategoryEmpty("display"),
    "has_tag": HasTag("wayland"),
    "fact": Fact("hardware.ram_gb", "lt", 8),
    "version_at_least": VersionAtLeast("kernel.version", "6.6"),
    "version_below": VersionBelow("hardware.kernel", "6.6"),
    "all_of": AllOf(Selected("hyprland"), Not(Selected("sway"))),
    "any_of": AnyOf(Selected("kde"), Selected("gnome")),
    "not": Not(Fact("hardware.is_virtual", "eq", True)),
}


class TestSerialisation(unittest.TestCase):
    def test_every_node_type_survives_a_round_trip_through_json(self) -> None:
        for kind, condition in ONE_OF_EVERY_KIND.items():
            with self.subTest(kind=kind):
                text = json.dumps(condition.to_dict())
                rebuilt = Condition.from_dict(json.loads(text))
                self.assertEqual(rebuilt, condition)

    def test_a_new_node_type_cannot_be_added_without_a_round_trip_test(self) -> None:
        """The test that keeps the other one honest.

        Without this, adding a condition type and forgetting to cover it would
        silently weaken the guarantee that the rules can move to a file.
        """
        self.assertEqual(sorted(ONE_OF_EVERY_KIND), sorted(node_kinds()))

    def test_a_rebuilt_condition_evaluates_identically(self) -> None:
        """Equality is not quite the point; behaving the same is."""
        for kind, condition in ONE_OF_EVERY_KIND.items():
            rebuilt = Condition.from_dict(json.loads(json.dumps(condition.to_dict())))
            with self.subTest(kind=kind):
                self.assertIs(rebuilt.evaluate(world()), condition.evaluate(world()))

    def test_nested_trees_survive(self) -> None:
        deep = AllOf(
            AnyOf(Selected("nvidia"), Selected("nvidia-open")),
            Not(AllOf(Selected("hyprland"), VersionBelow("kernel.version", "6.6"))),
        )
        self.assertEqual(Condition.from_dict(json.loads(json.dumps(deep.to_dict()))), deep)

    def test_an_unknown_kind_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            Condition.from_dict({"kind": "sudo_rm_rf"})

    def test_conditions_are_hashable_and_comparable(self) -> None:
        """Rules are constants; a constant that can be mutated is a trap."""
        self.assertEqual(Selected("nvidia"), Selected("nvidia"))
        self.assertEqual(len({Selected("nvidia"), Selected("nvidia")}), 1)


class TestIntrospection(unittest.TestCase):
    def test_a_tree_reports_every_component_it_names(self) -> None:
        tree = AllOf(Selected("hyprland"), AnySelected("nvidia", "nvidia-open"))
        found = {i for node in tree.walk() for i in node.component_ids()}
        self.assertEqual(found, {"hyprland", "nvidia", "nvidia-open"})

    def test_a_tree_reports_every_fact_it_consults(self) -> None:
        tree = AllOf(
            Fact("hardware.is_virtual", "eq", True),
            VersionBelow("hardware.kernel", "6.6"),
        )
        found = {k for node in tree.walk() for k in node.fact_keys()}
        self.assertEqual(found, {"hardware.is_virtual", "hardware.kernel"})


if __name__ == "__main__":
    unittest.main()
