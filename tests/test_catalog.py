"""Integrity checks for the catalogue.

Run with:  python -m unittest discover -s tests

These are not tests of the interface. They guard the data, which is where the
project's actual value is and where a typo is easiest to make and hardest to
spot — a `requires` pointing at a component id that does not exist would
otherwise show up as a mysterious permanent error in Validate.
"""

from __future__ import annotations

import unittest

from lsc import engine, export
from lsc.conditions import parse_version
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

        issues = engine.check(Build(selections=default_selections()))
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
            issues = engine.check(Build(name=preset.id, selections=dict(preset.selections)))
            errors = [issue.title for issue in issues if issue.severity == "error"]
            self.assertEqual(errors, [], f"preset '{preset.id}' has errors: {errors}")


class TestExport(unittest.TestCase):
    def test_every_export_renders_for_every_preset(self) -> None:
        for preset in PRESETS:
            build = Build(name=preset.id, selections=dict(preset.selections))
            for kind in ("packages", "install", "manifest"):
                text = export.render(kind, build)
                self.assertTrue(text.strip(), f"{preset.id}/{kind} rendered empty")

    def test_install_script_mentions_nvidia_modeset_when_needed(self) -> None:
        """The kernel parameter is the classic silently-missed step."""
        build = Build(selections={**default_selections(), "gpu": "nvidia"})
        self.assertIn("nvidia_drm.modeset=1", export.install_script(build))


class TestCatalogueAgainstTheEngine(unittest.TestCase):
    """The catalogue has to survive the engine, not just be well-formed.

    The engine's own behaviour is tested in test_engine.py. These two are about
    the data: a component whose relationships are wrong shows up here as a
    default build or a preset that cannot install.
    """

    def test_conflict_is_reported_once_not_twice(self) -> None:
        """SELinux and Arch each declare the clash; the user should see one issue."""
        build = Build(selections={**default_selections(), "security": "selinux"})
        conflicts = [i for i in engine.check(build) if i.rule_id == "conflict"]
        self.assertEqual(len(conflicts), 1, [i.title for i in conflicts])

    def test_contradicted_requirement_is_an_error(self) -> None:
        # linux-cachyos needs the CachyOS repositories; the default base is Arch,
        # so this is a contradiction rather than a gap.
        build = Build(selections={**default_selections(), "kernel": "linux-cachyos"})
        self.assertFalse(engine.build_is_installable(engine.check(build)))

    def test_optional_category_may_be_empty(self) -> None:
        """A headless build has no display server, and that is not a problem."""
        selections = default_selections()
        selections.pop("display")
        selections["desktop"] = "headless"
        warnings = [i for i in engine.check(Build(selections=selections)) if i.severity == "warning"]
        self.assertEqual(warnings, [])

    def test_every_kernel_declares_a_version(self) -> None:
        """The engine cannot compare a kernel_min against a kernel with no version."""
        kernel = CATEGORIES_BY_ID["kernel"]
        for component in kernel.components:
            self.assertTrue(
                component.version,
                f"{component.id} has no version, so kernel_min checks go quiet",
            )

    def test_kernel_minimums_are_readable(self) -> None:
        for component in COMPONENTS_BY_ID.values():
            if component.kernel_min:
                self.assertTrue(
                    parse_version(component.kernel_min),
                    f"{component.id}.kernel_min is not a version",
                )


if __name__ == "__main__":
    unittest.main()
