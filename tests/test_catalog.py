"""Integrity checks for the catalogue.

Run with:  python -m unittest discover -s tests

These are not tests of the interface. They guard the data, which is where the
project's actual value is and where a typo is easiest to make and hardest to
spot — a `requires` pointing at a component id that does not exist would
otherwise show up as a mysterious permanent error in Validate.
"""

from __future__ import annotations

import unittest

from lsc import compat, generate
from lsc.compat.conditions import parse_version
from lsc.data.catalog import (
    CATEGORIES,
    CATEGORIES_BY_ID,
    CATEGORY_BY_LAYER,
    COMPONENTS_BY_ID,
    LAYERS,
    default_selections,
)
from lsc.data.presets import PRESETS
from lsc.models import Build


class TestCatalogueIntegrity(unittest.TestCase):
    def test_component_ids_are_unique(self) -> None:
        seen: dict[str, str] = {}
        for category in CATEGORIES:
            for component in category.components:
                self.assertNotIn(
                    component.id,
                    seen,
                    f"{component.id} appears in both {seen.get(component.id)} "
                    f"and {category.id}",
                )
                seen[component.id] = category.id

    def test_no_dangling_relationships(self) -> None:
        """Every requires/conflicts/recommends id must name a real component."""
        for category in CATEGORIES:
            for component in category.components:
                for field in ("requires", "conflicts", "recommends"):
                    for other_id in getattr(component, field):
                        self.assertIn(
                            other_id,
                            COMPONENTS_BY_ID,
                            f"{component.id}.{field} points at unknown '{other_id}'",
                        )

    def test_nothing_conflicts_with_itself(self) -> None:
        for component in COMPONENTS_BY_ID.values():
            self.assertNotIn(component.id, component.conflicts)
            self.assertNotIn(component.id, component.requires)

    def test_defaults_exist_and_are_clean(self) -> None:
        """The build a new user lands on must not open with errors."""
        for category in CATEGORIES:
            if category.default is not None:
                self.assertIsNotNone(
                    category.get(category.default),
                    f"{category.id} defaults to unknown '{category.default}'",
                )

        issues = compat.check(Build(selections=default_selections()))
        errors = [issue for issue in issues if issue.severity == "error"]
        self.assertEqual(errors, [], "the default build must be installable")

    def test_every_category_has_components(self) -> None:
        for category in CATEGORIES:
            self.assertTrue(category.components, f"{category.id} is empty")


class TestStackDiagramCoverage(unittest.TestCase):
    def test_every_category_layer_is_drawable(self) -> None:
        """A category whose layer the diagram does not know about is invisible.

        base and security are the deliberate exceptions — they are drawn as
        cross-cutting bands, not as layers.
        """
        drawn = {layer.id for layer in LAYERS} | {"base", "security"}
        for category in CATEGORIES:
            self.assertIn(
                category.layer, drawn, f"{category.id} has layer '{category.layer}'"
            )

    def test_one_category_per_layer_at_most(self) -> None:
        self.assertEqual(
            len(CATEGORY_BY_LAYER),
            len({c.layer for c in CATEGORIES}),
            "two categories claim the same layer, so one would never be drawn",
        )


class TestPresets(unittest.TestCase):
    def test_presets_reference_real_components(self) -> None:
        for preset in PRESETS:
            for category_id, component_id in preset.selections.items():
                self.assertIn(component_id, COMPONENTS_BY_ID, f"{preset.id}/{category_id}")

    def test_presets_install(self) -> None:
        """A preset that ships with an error in it is a bug in the preset."""
        for preset in PRESETS:
            issues = compat.check(Build(name=preset.id, selections=dict(preset.selections)))
            errors = [issue.title for issue in issues if issue.severity == "error"]
            self.assertEqual(errors, [], f"preset '{preset.id}' has errors: {errors}")

    def test_a_preset_broken_by_the_machine_always_says_how_to_fix_it(self) -> None:
        """A preset *can* be wrong for a machine, and that is the point.

        The Gaming preset picks the open NVIDIA modules, which is right on the
        card most people buying a gaming machine own and an outright error on a
        GTX 1060. Asserting that no preset ever errors on any hardware would be
        asserting the tool has nothing useful to say.

        What must hold is weaker and more useful: when hardware turns a shipped
        preset into an error, the user did not choose any of it, so the engine
        owes them a way out that a program could apply on their behalf.
        """
        from tests import fixtures

        for preset in PRESETS:
            build = Build(name=preset.id, selections=dict(preset.selections))
            for machine, profile in fixtures.MACHINES.items():
                report = compat.evaluate(build, profile)
                for issue in report.issues:
                    if issue.severity != "error":
                        continue
                    with self.subTest(preset=preset.id, machine=machine, issue=issue.key):
                        self.assertIsNotNone(
                            issue.suggestion,
                            f"{preset.id} on {machine} errors with no applicable fix",
                        )

    def test_every_preset_is_clean_before_any_machine_is_known(self) -> None:
        """Whatever hardware later says, a preset must be sound on its own terms."""
        for preset in PRESETS:
            build = Build(name=preset.id, selections=dict(preset.selections))
            with self.subTest(preset=preset.id):
                self.assertTrue(compat.evaluate(build).installable())


class TestExport(unittest.TestCase):
    def test_every_export_renders_for_every_preset(self) -> None:
        for preset in PRESETS:
            build = Build(name=preset.id, selections=dict(preset.selections))
            for kind in ("packages", "install", "manifest"):
                text = generate.render(kind, build)
                self.assertTrue(text.strip(), f"{preset.id}/{kind} rendered empty")

    def test_install_script_mentions_nvidia_modeset_when_needed(self) -> None:
        """The kernel parameter is the classic silently-missed step."""
        build = Build(selections={**default_selections(), "gpu": "nvidia"})
        self.assertIn("nvidia_drm.modeset=1", generate.install_script(build))


class TestCatalogueMeetsTheEngine(unittest.TestCase):
    """The catalogue's own data, checked against what the engine expects of it.

    Behaviour of the engine is tested in test_engine.py and the rule set in
    test_rules.py. What is left here is the catalogue's side of the contract.
    """

    def test_conflict_is_reported_once_not_twice(self) -> None:
        """SELinux and Arch each declare the clash; the user should see one issue."""
        build = Build(selections={**default_selections(), "security": "selinux"})
        conflicts = [i for i in compat.check(build) if i.key.startswith("conflict:")]
        self.assertEqual(len(conflicts), 1, [i.title for i in conflicts])

    def test_missing_requirement_is_an_error(self) -> None:
        # linux-cachyos needs the CachyOS repositories; the default base is Arch.
        build = Build(selections={**default_selections(), "kernel": "linux-cachyos"})
        self.assertFalse(compat.build_is_installable(compat.check(build)))

    def test_optional_category_may_be_empty(self) -> None:
        """A headless build has no display server, and that is not a problem."""
        selections = default_selections()
        selections.pop("display")
        selections["desktop"] = "headless"
        unanswered = [
            i for i in compat.check(Build(selections=selections))
            if i.key.startswith("unanswered:")
        ]
        self.assertEqual(unanswered, [])

    def test_every_provided_fact_is_a_dotted_key_and_a_string(self) -> None:
        """provides is a flat namespace shared with the detector's facts.

        A component quietly providing a non-string would compare strangely
        against a hardware fact rather than failing outright, which is the
        worst way for a rule to be wrong.
        """
        for component in COMPONENTS_BY_ID.values():
            for key, value in component.provides:
                with self.subTest(component=component.id, key=key):
                    self.assertIn(".", key, "a fact key should be namespaced")
                    self.assertIsInstance(value, str)

    def test_no_component_provides_a_hardware_fact(self) -> None:
        """The build must never be able to claim something about the machine."""
        for component in COMPONENTS_BY_ID.values():
            for key, _value in component.provides:
                with self.subTest(component=component.id, key=key):
                    self.assertFalse(key.startswith("hardware."))

    def test_every_kernel_states_a_version_and_a_channel(self) -> None:
        """Version rules are only as good as the floors the catalogue declares."""
        kernel_category = CATEGORIES_BY_ID["kernel"]
        for component in kernel_category.components:
            provided = dict(component.provides)
            with self.subTest(kernel=component.id):
                self.assertIn("kernel.version", provided)
                self.assertIn(provided.get("kernel.channel"), {"mainline", "lts"})

    def test_declared_kernel_floors_parse_as_versions(self) -> None:
        for component in CATEGORIES_BY_ID["kernel"].components:
            version = dict(component.provides).get("kernel.version")
            with self.subTest(kernel=component.id):
                self.assertIsNotNone(parse_version(version), version)


if __name__ == "__main__":
    unittest.main()
