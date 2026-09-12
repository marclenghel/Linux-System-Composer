"""Tests for the evaluator.

These are about the machinery rather than the knowledge: graph walking,
identity, ordering, templating, and the line between "this is fine" and "I
could not tell". The knowledge itself is tested in test_rules.py.

The cases worth reading are the transitive ones. The catalogue nowhere says
that the Hardened security profile conflicts with the proprietary NVIDIA
driver — it says Hardened needs linux-hardened, and separately that
linux-hardened refuses to sit beside nvidia. An engine that only looks one hop
finds nothing wrong with that build.
"""

from __future__ import annotations

import unittest

from lsc import compat
from lsc.compat.conditions import AllOf, Fact, Selected
from lsc.compat.engine import (
    CONFLICT_PAIRS,
    Rule,
    evaluate,
    render,
    requirement_closure,
)
from lsc.models import Build, Suggestion
from tests import fixtures


class TestRequirementClosure(unittest.TestCase):
    def test_a_selected_component_is_its_own_root(self) -> None:
        closure = requirement_closure(frozenset({"hyprland"}))
        self.assertEqual(closure["hyprland"], ("hyprland",))

    def test_one_hop(self) -> None:
        closure = requirement_closure(frozenset({"hyprland"}))
        self.assertEqual(closure["wayland"], ("hyprland", "wayland"))

    def test_the_chain_is_kept_not_just_the_destination(self) -> None:
        """hardened -> linux-hardened is what makes the NVIDIA clash explainable."""
        closure = requirement_closure(frozenset({"hardened"}))
        self.assertEqual(closure["linux-hardened"], ("hardened", "linux-hardened"))

    def test_a_satisfied_requirement_is_still_in_the_closure(self) -> None:
        closure = requirement_closure(frozenset({"hyprland", "wayland"}))
        self.assertIn("wayland", closure)
        self.assertEqual(closure["wayland"], ("wayland",))

    def test_it_terminates_on_a_cycle(self) -> None:
        """The catalogue has no mutual requirement today.

        An engine that only works because of that is an engine with a bug in
        it, so the guard is tested rather than assumed. If this ever hangs, the
        visited set has been removed.
        """
        closure = requirement_closure(frozenset({"hardened", "linux-hardened", "hyprland"}))
        self.assertIn("linux-hardened", closure)


class TestTransitiveReasoning(unittest.TestCase):
    def setUp(self) -> None:
        # Hardened pulls in linux-hardened; linux-hardened refuses NVIDIA.
        # Nothing in the catalogue mentions the two together.
        self.report = evaluate(fixtures.build(security="hardened", gpu="nvidia"))

    def test_the_transitive_conflict_is_found(self) -> None:
        keys = {issue.key for issue in self.report.issues}
        self.assertIn("conflict:linux-hardened+nvidia", keys)

    def test_the_explanation_names_the_route(self) -> None:
        issue = next(i for i in self.report.issues if i.key == "conflict:linux-hardened+nvidia")
        self.assertIn("Hardened", issue.detail)
        self.assertIn("pulled in by", issue.detail)

    def test_the_build_is_not_installable(self) -> None:
        self.assertFalse(self.report.installable())

    def test_the_missing_requirement_is_reported_too(self) -> None:
        """Both problems, not just the first one found."""
        keys = {issue.key for issue in self.report.issues}
        self.assertIn("requires:hardened->linux-hardened", keys)


class TestConflicts(unittest.TestCase):
    def test_a_conflict_is_one_relationship_not_two_issues(self) -> None:
        """SELinux and Arch each declare the clash; the user sees one issue."""
        report = evaluate(fixtures.build(security="selinux"))
        conflicts = [i for i in report.issues if i.key.startswith("conflict:")]
        self.assertEqual(len(conflicts), 1, [i.title for i in conflicts])

    def test_conflict_pairs_are_unordered(self) -> None:
        """nvidia and nouveau each name the other; that is one edge.

        The old check collapsed the duplicate by splitting the issue title on
        the words "conflicts with". Modelling the relationship as an unordered
        pair makes the duplicate impossible instead of removing it later.
        """
        self.assertIn(frozenset({"nvidia", "nouveau"}), CONFLICT_PAIRS)
        matching = [p for p in CONFLICT_PAIRS if p == frozenset({"nvidia", "nouveau"})]
        self.assertEqual(len(matching), 1)

    def test_the_key_does_not_depend_on_the_wording(self) -> None:
        """Rewording or translating a title must not resurrect a duplicate."""
        report = evaluate(fixtures.build(security="selinux"))
        issue = next(i for i in report.issues if i.key.startswith("conflict:"))
        self.assertEqual(issue.key, "conflict:arch+selinux")
        self.assertNotIn(issue.title, issue.key)


class TestRequirements(unittest.TestCase):
    def test_a_missing_requirement_blocks_the_build(self) -> None:
        # linux-cachyos needs the CachyOS repositories; the default base is Arch.
        report = evaluate(fixtures.build(kernel="linux-cachyos"))
        self.assertFalse(report.installable())

    def test_a_missing_requirement_carries_an_applicable_suggestion(self) -> None:
        report = evaluate(fixtures.build(kernel="linux-cachyos"))
        issue = next(i for i in report.issues if i.key.startswith("requires:"))
        self.assertEqual(issue.suggestion, Suggestion("base", "cachyos"))


class TestUnansweredCategories(unittest.TestCase):
    def test_an_unanswered_question_is_a_warning(self) -> None:
        report = evaluate(fixtures.build_without("kernel"))
        keys = {i.key for i in report.issues}
        self.assertIn("unanswered:kernel", keys)

    def test_an_optional_category_may_be_empty(self) -> None:
        """A headless build has no display server, and that is not a problem."""
        report = evaluate(fixtures.build_without("display", desktop="headless"))
        self.assertEqual([i.key for i in report.issues if i.key.startswith("unanswered:")], [])


class TestUnknownIsReportedNotSwallowed(unittest.TestCase):
    def test_hardware_rules_are_unchecked_without_a_scan(self) -> None:
        report = evaluate(fixtures.build(gpu="nvidia"))
        self.assertFalse(report.hardware_known)
        self.assertTrue(report.unchecked)

    def test_a_scan_decides_them(self) -> None:
        report = evaluate(fixtures.build(gpu="nvidia"), fixtures.NVIDIA_AMPERE)
        self.assertTrue(report.hardware_known)
        undecided = {rule_id for rule_id, _needs in report.unchecked}
        self.assertNotIn("nvidia-driver-without-nvidia-gpu", undecided)

    def test_the_sample_profile_is_refused(self) -> None:
        """The decision from lsc/compat/facts.py, enforced.

        Firing hardware rules against the fixture would put "your GeForce RTX
        4070 Ti" on screen for someone sitting at a different machine.
        """
        from lsc.data.hardware import sample_profile

        report = evaluate(fixtures.build(gpu="nvidia"), sample_profile())
        self.assertFalse(report.hardware_known)

    def test_an_unrecognised_card_leaves_the_model_rules_undecided(self) -> None:
        """A card newer than the lookup table must not be declared too old."""
        report = evaluate(fixtures.build(gpu="nvidia-open"), fixtures.UNRECOGNISED_GPU)
        undecided = {rule_id for rule_id, _needs in report.unchecked}
        self.assertIn("nvidia-open-needs-turing", undecided)
        self.assertTrue(report.installable())

    def test_the_reason_given_is_the_actionable_one(self) -> None:
        """With nothing scanned, "scan the machine" beats "unrecognised card"."""
        report = evaluate(fixtures.build(gpu="nvidia-open"))
        reasons = dict(report.unchecked)
        self.assertEqual(reasons["nvidia-open-needs-turing"], "a hardware scan")


class TestOrderingAndIdentity(unittest.TestCase):
    def test_worst_first(self) -> None:
        report = evaluate(fixtures.build(security="hardened", gpu="nvidia"))
        severities = [i.severity for i in report.issues]
        self.assertEqual(severities, sorted(severities, key={"error": 0, "warning": 1, "info": 2}.get))

    def test_the_order_is_stable_across_runs(self) -> None:
        build = fixtures.build(security="hardened", gpu="nvidia", desktop="hyprland")
        first = [i.key for i in evaluate(build).issues]
        second = [i.key for i in evaluate(build).issues]
        self.assertEqual(first, second)

    def test_every_issue_has_a_key(self) -> None:
        report = evaluate(fixtures.build(security="hardened", gpu="nvidia"))
        for issue in report.issues:
            with self.subTest(title=issue.title):
                self.assertTrue(issue.key)

    def test_keys_are_unique(self) -> None:
        report = evaluate(fixtures.build(security="hardened", gpu="nvidia"))
        keys = [i.key for i in report.issues]
        self.assertEqual(len(keys), len(set(keys)))


class TestTemplating(unittest.TestCase):
    def test_dotted_names_are_single_keys_not_attribute_lookups(self) -> None:
        self.assertEqual(render("{gpu.name} here", {"gpu.name": "RTX 3060"}), "RTX 3060 here")

    def test_a_missing_binding_renders_a_question_mark_rather_than_raising(self) -> None:
        self.assertEqual(render("{gpu.name}", {}), "?")

    def test_a_rule_message_is_filled_in_from_the_machine(self) -> None:
        report = evaluate(fixtures.build(gpu="nvidia-open"), fixtures.NVIDIA_PASCAL)
        issue = next(i for i in report.issues if i.rule_id == "nvidia-open-needs-turing")
        self.assertIn("GeForce GTX 1060 6GB", issue.title)
        self.assertIn("Pascal", issue.detail)


class TestRuleInjection(unittest.TestCase):
    """The evaluator takes a rule set, so a rule can be tested in isolation."""

    def test_only_the_rules_given_are_run(self) -> None:
        rule = Rule(
            id="test-only",
            severity="info",
            when=Selected("mesa"),
            title="fires",
            detail="d",
            fix="f",
        )
        report = evaluate(fixtures.build(), rules=(rule,))
        self.assertEqual(report.rules_evaluated, 1)
        self.assertIn("test-only", {i.rule_id for i in report.issues})

    def test_a_rule_whose_condition_is_undecided_is_not_reported_as_a_problem(self) -> None:
        rule = Rule(
            id="test-undecidable",
            severity="error",
            when=AllOf(Selected("mesa"), Fact("hardware.ram_gb", "lt", 8)),
            title="should not appear",
            detail="d",
            fix="f",
        )
        report = evaluate(fixtures.build(), rules=(rule,))
        self.assertEqual(report.issues, ())
        self.assertEqual(report.unchecked, (("test-undecidable", "a hardware scan"),))


class TestFacadeStillWorks(unittest.TestCase):
    """compat.py kept its shape so no screen had to change."""

    def test_check_returns_a_list_of_issues(self) -> None:
        issues = compat.check(fixtures.build())
        self.assertIsInstance(issues, list)

    def test_summarise_counts_by_severity(self) -> None:
        issues = compat.check(fixtures.build(security="hardened", gpu="nvidia"))
        counts = compat.summarise(issues)
        self.assertGreaterEqual(counts["error"], 1)

    def test_build_is_installable(self) -> None:
        self.assertTrue(compat.build_is_installable(compat.check(fixtures.build())))
        self.assertFalse(
            compat.build_is_installable(compat.check(fixtures.build(kernel="linux-cachyos")))
        )

    def test_check_works_without_being_given_any_hardware(self) -> None:
        self.assertIsInstance(compat.check(Build(selections={})), list)


if __name__ == "__main__":
    unittest.main()
