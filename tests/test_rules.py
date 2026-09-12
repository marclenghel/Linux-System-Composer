"""Tests for the rule set — the knowledge rather than the machinery.

Three kinds of check live here.

**Integrity.** A rule naming a component the catalogue does not have, or
suggesting a component that belongs to a different category, is dead knowledge:
it will never fire, or it will fire and offer advice that cannot be taken, and
neither shows up by reading the file.

**Coverage.** Every rule has to fire in at least one situation. A rule that can
never fire is the most expensive kind of mistake in a project like this,
because it looks exactly like a rule that works.

**The claim that the rules are data.** The whole rule set is written to JSON,
read back, and evaluated against every fixture. If the two disagree anywhere,
the promise that these rules could move into a TOML file without touching the
evaluator is not true.
"""

from __future__ import annotations

import json
import string
import unittest

from lsc.data.catalog import CATEGORIES, CATEGORIES_BY_ID, COMPONENTS_BY_ID
from lsc.data.rules import RULES, RULES_BY_ID
from lsc.engine import Rule, evaluate
from lsc.facts import World, build_world
from lsc.models import Build
from tests import fixtures

VALID_SEVERITIES = {"error", "warning", "info"}


# ── the situations every rule is measured against ─────────────────────────────
#
# One entry per interesting shape of build-and-machine. Adding a rule usually
# means adding the scenario that proves it fires, which is the intended cost.

# The one scenario that is supposed to find nothing: it is here to prove the
# engine stays quiet when there is nothing to say.
BASELINE = "default build, nothing scanned"

SCENARIOS: tuple[tuple[str, Build, dict | None], ...] = (
    (BASELINE, fixtures.build(), None),
    ("hyprland on nvidia", fixtures.build(desktop="hyprland", gpu="nvidia"), None),
    ("kde on nvidia over wayland", fixtures.build(gpu="nvidia"), None),
    ("open modules on a pascal card", fixtures.build(gpu="nvidia-open"), fixtures.NVIDIA_PASCAL),
    ("closed driver on an ampere card", fixtures.build(gpu="nvidia"), fixtures.NVIDIA_AMPERE),
    ("nvidia driver on an amd machine", fixtures.build(gpu="nvidia"), fixtures.AMD_DESKTOP),
    ("mesa on an nvidia-only machine", fixtures.build(gpu="mesa"), fixtures.NVIDIA_AMPERE),
    ("nvidia on an old running kernel", fixtures.build(gpu="nvidia"), fixtures.OLD_KERNEL_NVIDIA),
    ("wayland desktop with pulseaudio", fixtures.build(audio="pulseaudio"), None),
    ("zfs on a rolling kernel", fixtures.build(filesystem="zfs", kernel="linux"), None),
    (
        "two out-of-tree modules",
        fixtures.build(filesystem="zfs", kernel="linux-lts", gpu="nvidia"),
        None,
    ),
    ("btrfs without grub", fixtures.build(filesystem="btrfs"), None),
    ("btrfs with grub", fixtures.build(filesystem="btrfs", bootloader="grub"), None),
    ("apparmor", fixtures.build(security="apparmor"), None),
    ("manjaro base", fixtures.build(base="manjaro"), None),
    ("headless build that still names a display server", fixtures.build(desktop="headless"), None),
    ("i3 on xorg", fixtures.build(display="xorg", desktop="i3"), None),
    ("niri", fixtures.build(desktop="niri"), None),
    ("bare-metal driver inside a vm", fixtures.build(), fixtures.VIRTUAL_MACHINE),
    ("guest driver on real hardware", fixtures.build(gpu="vm-guest"), fixtures.AMD_DESKTOP),
    ("full desktop on 4 GB", fixtures.build(desktop="kde"), fixtures.LOW_MEMORY_LAPTOP),
    ("btrfs already loaded, ext4 chosen", fixtures.build(filesystem="ext4"), fixtures.BTRFS_IN_USE),
    ("arm board with a tuned x86 kernel", fixtures.build(kernel="linux-lts"), fixtures.ARM_BOARD),
    ("nouveau on a modern card", fixtures.build(gpu="nouveau"), fixtures.NVIDIA_AMPERE),
)


# Rules no build in the current catalogue can trigger, with the world that
# proves they work. Keeping the list explicit and short is the point: an entry
# here is a claim that the rule is real but the catalogue has nothing that
# breaks it, and that claim should have to be written down.
def _world_with(**facts) -> World:
    world = build_world(fixtures.build(desktop="hyprland"))
    return World(
        build=world.build,
        selected=world.selected,
        selections=world.selections,
        tags=world.tags,
        facts={**world.facts, **facts},
        bindings=world.bindings,
        hardware=world.hardware,
    )


SYNTHETIC_WORLDS: dict[str, World] = {
    # Every kernel in the catalogue is already newer than 6.6, so the README's
    # own example constraint is satisfied by every available choice. The rule
    # is still real; it just has nothing to catch yet.
    "hyprland-kernel-floor": _world_with(**{"kernel.version": "6.1"}),
}


def fired_rule_ids() -> set[str]:
    """Every rule id that fires somewhere in SCENARIOS."""
    fired: set[str] = set()
    for _name, build, profile in SCENARIOS:
        for issue in evaluate(build, profile).issues:
            if issue.rule_id in RULES_BY_ID:
                fired.add(issue.rule_id)
    return fired


class TestRuleSetIntegrity(unittest.TestCase):
    def test_rule_ids_are_unique(self) -> None:
        ids = [rule.id for rule in RULES]
        self.assertEqual(len(ids), len(set(ids)), "two rules share an id")

    def test_every_rule_names_real_components(self) -> None:
        for rule in RULES:
            for component_id in rule.components():
                with self.subTest(rule=rule.id, component=component_id):
                    self.assertIn(component_id, COMPONENTS_BY_ID)

    def test_every_severity_is_one_the_interface_can_draw(self) -> None:
        for rule in RULES:
            with self.subTest(rule=rule.id):
                self.assertIn(rule.severity, VALID_SEVERITIES)

    def test_every_rule_says_what_to_do(self) -> None:
        """An issue with no way forward is a bug in the rule, not a result."""
        for rule in RULES:
            with self.subTest(rule=rule.id):
                self.assertTrue(rule.fix.strip())
                self.assertTrue(rule.detail.strip())
                self.assertTrue(rule.title.strip())

    def test_suggestions_point_at_the_category_the_component_is_in(self) -> None:
        """Otherwise applying the fix would write a component into the wrong slot."""
        for rule in RULES:
            if rule.suggest is None:
                continue
            with self.subTest(rule=rule.id):
                category = CATEGORIES_BY_ID.get(rule.suggest.category_id)
                self.assertIsNotNone(category, rule.suggest.category_id)
                self.assertIsNotNone(
                    category.get(rule.suggest.component_id),
                    f"{rule.suggest.component_id} is not in {rule.suggest.category_id}",
                )

    def test_a_hardware_rule_says_a_scan_is_what_it_needs(self) -> None:
        for rule in RULES:
            if not any(key.startswith("hardware.") for key in rule.fact_keys()):
                continue
            with self.subTest(rule=rule.id):
                self.assertTrue(rule.needs.strip())

    def test_references_are_urls_when_present(self) -> None:
        for rule in RULES:
            if rule.reference:
                with self.subTest(rule=rule.id):
                    self.assertTrue(rule.reference.startswith("https://"))


class TestTemplates(unittest.TestCase):
    def test_every_placeholder_is_a_binding_the_world_provides(self) -> None:
        """A rule that names a binding nothing supplies renders a bare "?".

        Checked where each rule actually fires rather than in the abstract,
        because "{gpu.name}" is perfectly valid in a rule that cannot fire
        until a graphics card has been detected.
        """
        for name, build, profile in SCENARIOS:
            world = build_world(build, profile)
            for issue in evaluate(build, profile).issues:
                rule = RULES_BY_ID.get(issue.rule_id)
                if rule is None:
                    continue
                for template in (rule.title, rule.detail, rule.fix):
                    for _text, field, _spec, _conv in string.Formatter().parse(template):
                        if field is None:
                            continue
                        with self.subTest(scenario=name, rule=rule.id, field=field):
                            self.assertIn(field, world.bindings)

    def test_no_rendered_message_leaks_a_brace(self) -> None:
        for _name, build, profile in SCENARIOS:
            for issue in evaluate(build, profile).issues:
                with self.subTest(issue=issue.key):
                    self.assertNotIn("{", issue.title + issue.detail + issue.fix)
                    self.assertNotIn("}", issue.title + issue.detail + issue.fix)


class TestCoverage(unittest.TestCase):
    def test_every_rule_fires_somewhere(self) -> None:
        """A rule that can never fire looks exactly like one that works."""
        fired = fired_rule_ids() | set(SYNTHETIC_WORLDS)
        missing = sorted({rule.id for rule in RULES} - fired)
        self.assertEqual(missing, [], f"these rules never fire in any fixture: {missing}")

    def test_the_synthetic_worlds_actually_trigger_their_rules(self) -> None:
        for rule_id, world in SYNTHETIC_WORLDS.items():
            with self.subTest(rule=rule_id):
                self.assertIs(RULES_BY_ID[rule_id].when.evaluate(world), True)

    def test_nothing_is_listed_as_synthetic_that_a_real_build_can_trigger(self) -> None:
        """Keeps the exception list from quietly growing."""
        overlap = sorted(set(SYNTHETIC_WORLDS) & fired_rule_ids())
        self.assertEqual(overlap, [], f"these no longer need a synthetic world: {overlap}")

    def test_the_baseline_scenario_is_completely_clean(self) -> None:
        """The build a new user lands on must open with nothing to report.

        A composer whose own defaults trip its own rules teaches the user to
        ignore the rules, which is worse than having none.
        """
        report = evaluate(fixtures.build())
        self.assertEqual([i.title for i in report.issues], [])

    def test_every_other_scenario_is_doing_some_work(self) -> None:
        """A scenario that produces nothing is a scenario someone should delete."""
        for name, build, profile in SCENARIOS:
            if name == BASELINE:
                continue
            with self.subTest(scenario=name):
                report = evaluate(build, profile)
                self.assertTrue(report.issues, f"{name} produced no issues at all")


class TestRulesAreData(unittest.TestCase):
    def test_the_whole_rule_set_survives_a_round_trip_through_json(self) -> None:
        text = json.dumps([rule.to_dict() for rule in RULES])
        rebuilt = tuple(Rule.from_dict(item) for item in json.loads(text))
        self.assertEqual(len(rebuilt), len(RULES))
        for original, copy in zip(RULES, rebuilt):
            with self.subTest(rule=original.id):
                self.assertEqual(copy, original)

    def test_the_rebuilt_rule_set_produces_identical_results(self) -> None:
        """Equality of the records is not the promise; identical behaviour is.

        This is the test that makes "the rules could live in a TOML file"
        something the project has checked rather than something it hopes.
        """
        text = json.dumps([rule.to_dict() for rule in RULES])
        rebuilt = tuple(Rule.from_dict(item) for item in json.loads(text))

        for name, build, profile in SCENARIOS:
            with self.subTest(scenario=name):
                original = evaluate(build, profile, rules=RULES)
                copy = evaluate(build, profile, rules=rebuilt)
                self.assertEqual(
                    [(i.severity, i.key, i.title) for i in original.issues],
                    [(i.severity, i.key, i.title) for i in copy.issues],
                )
                self.assertEqual(original.unchecked, copy.unchecked)

    def test_the_serialised_form_is_plain_json_types_only(self) -> None:
        """Anything json.dumps refuses cannot go in a TOML file either."""
        for rule in RULES:
            with self.subTest(rule=rule.id):
                json.dumps(rule.to_dict())


class TestTheWorkedExample(unittest.TestCase):
    """The README promises this specific output. It should be a test."""

    def setUp(self) -> None:
        self.report = evaluate(fixtures.build(desktop="hyprland", gpu="nvidia"))
        self.issue = next(
            i for i in self.report.issues if i.rule_id == "hyprland-nvidia"
        )

    def test_hyprland_and_nvidia_produce_a_specific_warning(self) -> None:
        self.assertEqual(self.issue.severity, "warning")

    def test_it_names_drm_modeset(self) -> None:
        self.assertIn("nvidia_drm.modeset=1", self.issue.detail)

    def test_it_names_explicit_sync(self) -> None:
        self.assertIn("xplicit sync", self.issue.detail)

    def test_it_names_the_driver_version_that_matters(self) -> None:
        self.assertIn("555", self.issue.detail)

    def test_it_names_xwayland(self) -> None:
        self.assertIn("XWayland", self.issue.detail)

    def test_it_is_not_a_generic_conflict_message(self) -> None:
        self.assertNotIn("cannot be installed on the same system", self.issue.detail)

    def test_the_pairing_is_a_warning_not_a_refusal(self) -> None:
        """The README's promise is explanation, not prevention."""
        self.assertTrue(self.report.installable())


class TestEveryCategoryIsReachableByRules(unittest.TestCase):
    def test_the_rule_set_has_something_to_say_about_most_layers(self) -> None:
        """Not a hard requirement, but a silent layer is usually an oversight."""
        mentioned = {
            category_id
            for rule in RULES
            for category_id in (
                [rule.suggest.category_id] if rule.suggest else []
            )
        }
        for rule in RULES:
            for component_id in rule.components():
                for category in CATEGORIES:
                    if category.get(component_id) is not None:
                        mentioned.add(category.id)
        silent = sorted({c.id for c in CATEGORIES} - mentioned)
        self.assertEqual(silent, [], f"no rule mentions these layers at all: {silent}")


if __name__ == "__main__":
    unittest.main()
