"""Tests for the compatibility engine.

Run with:  python -m unittest discover -s tests

These are the tests that matter most in the project. The catalogue tests guard
data; these guard *reasoning*, and reasoning is where a tool that gives advice
does real damage when it is wrong. Two failure modes are worth more attention
than the rest:

* saying nothing when something is wrong, which makes the tool useless;
* saying something confident when there is no evidence, which makes it harmful.

The second is why so much of this file is about hardware rules being skipped.
"""

from __future__ import annotations

import unittest

from lsc import engine
from lsc.conditions import (
    AllOf,
    AnyOf,
    Context,
    GpuVendor,
    Has,
    Not,
    RamBelowGb,
    describe,
    is_pre_turing_nvidia,
    parse_version,
)
from lsc.data.catalog import CATEGORIES, COMPONENTS_BY_ID, default_selections
from lsc.data.rules import RULES, RULES_BY_ID, rules_needing_hardware
from lsc.models import Build, Component, Issue


def build_with(**selections: str) -> Build:
    """A default build with some choices overridden."""
    return Build(selections={**default_selections(), **selections})


def rule_ids(issues: list[Issue]) -> set[str]:
    return {issue.rule_id for issue in issues}


# A machine with one NVIDIA card and nothing else interesting, used wherever a
# test needs a real reading rather than a particular one.
def machine(**overrides) -> dict:
    profile = {
        "source": "detected",
        "os": "Arch Linux",
        "kernel": "6.12.8-arch1-1",
        "cpu": {"brand": "AMD Ryzen 5 5600", "cores": 12, "arch": "x86_64"},
        "ram": {"total_gb": 32.0},
        "gpus": [{"vendor": "NVIDIA", "name": "GeForce RTX 4070"}],
        "drivers": [{"name": "nvidia_drm", "status": "Live"}],
        "disks": [],
        "network_cards": [],
    }
    profile.update(overrides)
    return profile


# ── Resolution: what a build implies ─────────────────────────────────────────


class TestResolution(unittest.TestCase):
    def test_a_plain_build_implies_nothing(self) -> None:
        resolution = engine.resolve(build_with())
        self.assertEqual(resolution.implied, {})
        self.assertEqual(resolution.contradictions, [])

    def test_a_requirement_is_pulled_in_when_its_slot_is_empty(self) -> None:
        """The Hardened profile requires the hardened kernel."""
        selections = default_selections()
        selections.pop("kernel")
        selections["security"] = "hardened"

        resolution = engine.resolve(Build(selections=selections))
        self.assertIn("linux-hardened", resolution.implied)
        self.assertEqual(resolution.implied["linux-hardened"], ("hardened",))

    def test_a_taken_slot_is_a_contradiction_not_an_implication(self) -> None:
        """This is the distinction the placeholder check could not make."""
        resolution = engine.resolve(build_with(security="hardened"))  # kernel=linux
        self.assertEqual(resolution.implied, {})
        self.assertEqual(
            resolution.contradictions, [("hardened", "linux-hardened", "linux")]
        )

    def test_resolution_is_transitive(self) -> None:
        """A requirement's own requirements are followed too.

        linux-cachyos requires the CachyOS base, so a build that only says
        "hardened kernel is not chosen, use CachyOS's" reaches the base through
        two hops. Built from the catalogue rather than a fixture so the test
        fails if that chain is ever broken.
        """
        selections = {"kernel": "linux-cachyos"}
        resolution = engine.resolve(Build(selections=selections))
        self.assertIn("cachyos", resolution.implied)
        self.assertEqual(resolution.implied["cachyos"], ("linux-cachyos",))

    def test_resolution_terminates_on_a_cycle(self) -> None:
        """Two components requiring each other must not hang the engine.

        No such pair exists in the catalogue today, and a test that only passes
        because the data happens to be acyclic is not testing anything — so this
        one builds the cycle by hand.
        """
        original = dict(COMPONENTS_BY_ID)
        try:
            COMPONENTS_BY_ID["cycle-a"] = Component(
                id="cycle-a", name="A", summary="", description="", requires=("cycle-b",)
            )
            COMPONENTS_BY_ID["cycle-b"] = Component(
                id="cycle-b", name="B", summary="", description="", requires=("cycle-a",)
            )
            resolution = engine.resolve(Build(selections={"x": "cycle-a"}))
            self.assertIn("cycle-a", resolution.effective)
        finally:
            COMPONENTS_BY_ID.clear()
            COMPONENTS_BY_ID.update(original)


# ── Conflicts, including the ones that arrive through a requirement ──────────


class TestConflicts(unittest.TestCase):
    def test_direct_conflict_is_an_error(self) -> None:
        build = build_with(kernel="linux-hardened", gpu="nvidia")
        issues = [i for i in engine.check(build) if i.rule_id == "conflict"]
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].severity, "error")

    def test_conflict_through_an_implied_component_is_found(self) -> None:
        """The headline result of milestone 3.

        Nobody selected linux-hardened. The Hardened security profile requires
        it, and it refuses the proprietary NVIDIA driver. The old check compared
        only what was literally selected and reported nothing at all.
        """
        selections = default_selections()
        selections.pop("kernel")
        selections.update({"security": "hardened", "gpu": "nvidia"})

        issues = [i for i in engine.check(Build(selections=selections))
                  if i.rule_id == "conflict"]
        self.assertEqual(len(issues), 1, [i.title for i in issues])
        self.assertFalse(engine.build_is_installable(issues))

    def test_an_implied_conflict_explains_where_it_came_from(self) -> None:
        """An error about a component the user never chose has to say why."""
        selections = default_selections()
        selections.pop("kernel")
        selections.update({"security": "hardened", "gpu": "nvidia"})

        issue = next(
            i for i in engine.check(Build(selections=selections)) if i.rule_id == "conflict"
        )
        self.assertIn("not selected directly", issue.detail)
        self.assertIn("Hardened", issue.detail)
        # And the fix must name a decision the user can actually revisit, not the
        # implied component they have no control over.
        self.assertIn("Hardened", issue.fix)

    def test_a_conflict_is_reported_once_from_either_side(self) -> None:
        build = build_with(security="selinux")
        issues = [i for i in engine.check(build) if i.rule_id == "conflict"]
        self.assertEqual(len(issues), 1, [i.title for i in issues])


# ── Gaps and contradictions ──────────────────────────────────────────────────


class TestRequirements(unittest.TestCase):
    def test_contradiction_names_both_decisions(self) -> None:
        build = build_with(desktop="i3")  # i3 needs Xorg; display is Wayland
        issue = next(
            i for i in engine.check(build) if i.rule_id == "requirement-contradiction"
        )
        self.assertEqual(issue.severity, "error")
        self.assertIn("i3", issue.title)
        self.assertIn("Wayland", issue.title)
        self.assertIn("Xorg", issue.title)

    def test_gap_is_a_warning_not_an_error(self) -> None:
        """Nothing blocks an implied requirement, so it must not block the build."""
        selections = default_selections()
        selections.pop("kernel")
        selections["security"] = "hardened"

        issues = engine.check(Build(selections=selections))
        gap = next(i for i in issues if i.rule_id == "requirement-implied")
        self.assertEqual(gap.severity, "warning")

    def test_unanswered_category_is_reported_once(self) -> None:
        selections = default_selections()
        selections.pop("audio")
        issues = [
            i for i in engine.check(Build(selections=selections))
            if i.rule_id == "category-unanswered"
        ]
        self.assertEqual(len(issues), 1)

    def test_optional_category_is_not_an_unanswered_question(self) -> None:
        optional = [c.id for c in CATEGORIES if c.optional]
        self.assertIn("display", optional, "this test assumes display is optional")

        selections = default_selections()
        selections.pop("display")
        selections["desktop"] = "headless"
        issues = [
            i for i in engine.check(Build(selections=selections))
            if i.rule_id == "category-unanswered"
        ]
        self.assertEqual(issues, [])


# ── Version reasoning ────────────────────────────────────────────────────────


class TestKernelFloors(unittest.TestCase):
    """The README's `kernel_min`, made real.

    Quiet with today's catalogue — every floor is met — so these tests are what
    keep the mechanism from rotting while it waits to be needed.
    """

    def test_parse_version_survives_distro_suffixes(self) -> None:
        self.assertEqual(parse_version("6.12.8-arch1-1"), (6, 12, 8))
        self.assertEqual(parse_version("6.6"), (6, 6))
        self.assertEqual(parse_version("v6.1"), (6, 1))
        self.assertEqual(parse_version("unknown"), ())
        self.assertEqual(parse_version(None), ())

    def test_the_current_catalogue_meets_every_floor(self) -> None:
        """No build made of catalogue defaults should trip a kernel floor.

        If this starts failing, the catalogue has gained a component that needs a
        newer kernel than one of the kernels on offer — which is information, not
        a bug in the engine.
        """
        for kernel in ("linux", "linux-lts", "linux-zen"):
            for desktop in ("hyprland", "niri", "kde"):
                build = build_with(kernel=kernel, desktop=desktop, display="wayland")
                floors = [i for i in engine.check(build) if i.rule_id == "kernel-floor"]
                self.assertEqual(floors, [], f"{kernel}+{desktop}: {floors}")

    def test_a_floor_above_the_kernel_is_reported(self) -> None:
        """The mechanism itself, proven with a component built for the purpose.

        Injected rather than invented in the catalogue: making a real component
        claim a kernel it does not need would be putting a false fact into the
        project's knowledge base to make a test pass.
        """
        original = dict(COMPONENTS_BY_ID)
        try:
            COMPONENTS_BY_ID["needs-tomorrow"] = Component(
                id="needs-tomorrow",
                name="Needs Tomorrow",
                summary="",
                description="",
                kernel_min="99.0",
            )
            build = Build(selections={"kernel": "linux-lts", "test": "needs-tomorrow"})
            issues = [i for i in engine.check(build) if i.rule_id == "kernel-floor"]
            self.assertEqual(len(issues), 1, [i.title for i in issues])
            self.assertEqual(issues[0].severity, "warning")
            self.assertIn("99.0", issues[0].title)
            # It must name the kernel it compared against, or the warning is
            # unactionable.
            self.assertIn("6.12", issues[0].detail)
        finally:
            COMPONENTS_BY_ID.clear()
            COMPONENTS_BY_ID.update(original)

    def test_no_kernel_means_no_version_claims(self) -> None:
        """With no kernel chosen there is nothing to compare, so say nothing."""
        selections = default_selections()
        selections.pop("kernel")
        issues = [
            i for i in engine.check(Build(selections=selections))
            if i.rule_id == "kernel-floor"
        ]
        self.assertEqual(issues, [])


# ── Hardware awareness, and its limits ───────────────────────────────────────


class TestHardwareRules(unittest.TestCase):
    def test_hardware_rules_do_not_run_without_a_reading(self) -> None:
        """The most important test in the file.

        Every hardware rule must be inert when nothing has been detected. A tool
        that invents a conclusion from a missing measurement is worse than one
        that stays quiet.
        """
        build = build_with(gpu="nvidia-open")
        issues = engine.check(build, hardware=None, hardware_is_real=False)
        for rule in rules_needing_hardware():
            self.assertNotIn(rule.id, rule_ids(issues), rule.id)

    def test_the_sample_profile_is_not_a_machine(self) -> None:
        """Passing a profile with hardware_is_real=False must change nothing."""
        build = build_with(gpu="nvidia-open")
        without = engine.check(build, hardware=None, hardware_is_real=False)
        with_fixture = engine.check(build, hardware=machine(), hardware_is_real=False)
        self.assertEqual(rule_ids(without), rule_ids(with_fixture))

    def test_negated_hardware_conditions_stay_silent_too(self) -> None:
        """The trap `reads_hardware` exists to prevent.

        "An NVIDIA driver is selected but no NVIDIA GPU was detected" is phrased
        as a negative. Evaluated against an absent reading it would be true of
        every machine in the world.
        """
        rule = RULES_BY_ID["nvidia-driver-without-nvidia-gpu"]
        self.assertTrue(rule.when.needs_hardware)

        build = build_with(gpu="nvidia")
        issues = engine.check(build, hardware=None, hardware_is_real=False)
        self.assertNotIn("nvidia-driver-without-nvidia-gpu", rule_ids(issues))

    def test_open_modules_on_a_pre_turing_card_is_an_error(self) -> None:
        build = build_with(gpu="nvidia-open")
        profile = machine(gpus=[{"vendor": "NVIDIA", "name": "GeForce GTX 1060 6GB"}])
        issues = engine.check(build, profile, hardware_is_real=True)
        found = [i for i in issues if i.rule_id == "nvidia-open-pre-turing"]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].severity, "error")

    def test_open_modules_on_a_turing_card_is_fine(self) -> None:
        build = build_with(gpu="nvidia-open")
        for name in ("GeForce RTX 4070", "GeForce GTX 1650", "GeForce GTX 1660 Ti"):
            profile = machine(gpus=[{"vendor": "NVIDIA", "name": name}])
            issues = engine.check(build, profile, hardware_is_real=True)
            self.assertNotIn("nvidia-open-pre-turing", rule_ids(issues), name)

    def test_nvidia_driver_without_an_nvidia_card(self) -> None:
        build = build_with(gpu="nvidia")
        profile = machine(gpus=[{"vendor": "AMD", "name": "Radeon RX 7800 XT"}])
        issues = engine.check(build, profile, hardware_is_real=True)
        self.assertIn("nvidia-driver-without-nvidia-gpu", rule_ids(issues))

    def test_mesa_on_an_nvidia_only_machine(self) -> None:
        build = build_with(gpu="mesa")
        profile = machine(gpus=[{"vendor": "NVIDIA", "name": "GeForce RTX 4070"}])
        self.assertIn(
            "mesa-without-amd-or-intel",
            rule_ids(engine.check(build, profile, hardware_is_real=True)),
        )

    def test_mesa_is_fine_when_an_amd_card_is_present_too(self) -> None:
        build = build_with(gpu="mesa")
        profile = machine(
            gpus=[
                {"vendor": "NVIDIA", "name": "GeForce RTX 4070"},
                {"vendor": "AMD", "name": "Raphael integrated graphics"},
            ]
        )
        self.assertNotIn(
            "mesa-without-amd-or-intel",
            rule_ids(engine.check(build, profile, hardware_is_real=True)),
        )

    def test_tuned_kernel_on_arm_is_an_error(self) -> None:
        build = build_with(kernel="linux-zen", gpu="mesa")
        profile = machine(cpu={"brand": "Apple M2", "cores": 8, "arch": "aarch64"})
        issues = engine.check(build, profile, hardware_is_real=True)
        found = [i for i in issues if i.rule_id == "tuned-kernel-on-non-x86"]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].severity, "error")

    def test_unknown_architecture_does_not_produce_an_error(self) -> None:
        """Stated positively for exactly this case: a reading with no arch in it."""
        build = build_with(kernel="linux-zen", gpu="mesa")
        profile = machine(cpu={"brand": "Unknown", "cores": 0, "arch": ""})
        issues = engine.check(build, profile, hardware_is_real=True)
        self.assertNotIn("tuned-kernel-on-non-x86", rule_ids(issues))

    def test_low_memory_warns_about_a_full_desktop(self) -> None:
        build = build_with(desktop="kde", gpu="mesa")
        profile = machine(
            ram={"total_gb": 4.0}, gpus=[{"vendor": "INTEL", "name": "UHD Graphics 620"}]
        )
        self.assertIn(
            "full-desktop-on-little-ram",
            rule_ids(engine.check(build, profile, hardware_is_real=True)),
        )

    def test_a_loaded_module_is_evidence(self) -> None:
        build = build_with(filesystem="ext4", gpu="mesa")
        profile = machine(
            drivers=[{"name": "btrfs", "status": "Live"}],
            gpus=[{"vendor": "AMD", "name": "Radeon RX 7800 XT"}],
        )
        self.assertIn(
            "btrfs-detected-but-not-selected",
            rule_ids(engine.check(build, profile, hardware_is_real=True)),
        )


# ── The curated rules that need no machine ───────────────────────────────────


class TestBuildRules(unittest.TestCase):
    def test_nvidia_on_wayland_mentions_modesetting(self) -> None:
        build = build_with(gpu="nvidia", display="wayland")
        issue = next(
            i for i in engine.check(build) if i.rule_id == "nvidia-wayland-modeset"
        )
        self.assertIn("nvidia_drm.modeset=1", issue.fix)

    def test_hyprland_on_nvidia_is_flagged(self) -> None:
        build = build_with(desktop="hyprland", gpu="nvidia", display="wayland")
        self.assertIn("hyprland-nvidia", rule_ids(engine.check(build)))

    def test_hyprland_on_mesa_is_not_flagged(self) -> None:
        build = build_with(desktop="hyprland", gpu="mesa", display="wayland")
        self.assertNotIn("hyprland-nvidia", rule_ids(engine.check(build)))

    def test_pulseaudio_on_wayland_warns_about_screen_sharing(self) -> None:
        build = build_with(audio="pulseaudio", display="wayland")
        issue = next(
            i for i in engine.check(build)
            if i.rule_id == "pulseaudio-wayland-screen-sharing"
        )
        self.assertEqual(issue.severity, "warning")

    def test_zfs_on_a_rolling_kernel_warns(self) -> None:
        build = build_with(filesystem="zfs", kernel="linux")
        self.assertIn("zfs-on-a-rolling-kernel", rule_ids(engine.check(build)))

    def test_zfs_on_lts_does_not_warn(self) -> None:
        build = build_with(filesystem="zfs", kernel="linux-lts")
        self.assertNotIn("zfs-on-a-rolling-kernel", rule_ids(engine.check(build)))

    def test_headless_does_not_get_desktop_advice(self) -> None:
        """A server build must not be told its audio stack is bad for a desktop."""
        selections = default_selections()
        selections.pop("display")
        selections.update({"desktop": "headless", "audio": "alsa"})
        issues = rule_ids(engine.check(Build(selections=selections)))
        self.assertNotIn("alsa-on-a-desktop", issues)
        self.assertNotIn("hardened-desktop-friction", issues)


# ── Properties every rule has to have ────────────────────────────────────────


class TestRuleSetIntegrity(unittest.TestCase):
    def test_rule_ids_are_unique(self) -> None:
        ids = [rule.id for rule in RULES]
        self.assertEqual(len(ids), len(set(ids)))

    def test_every_rule_has_a_fix(self) -> None:
        """An explanation with no way forward is not advice — see models.Issue."""
        for rule in RULES:
            self.assertTrue(rule.fix.strip(), rule.id)
            self.assertTrue(rule.detail.strip(), rule.id)
            self.assertTrue(rule.title.strip(), rule.id)

    def test_every_severity_is_known(self) -> None:
        for rule in RULES:
            self.assertIn(rule.severity, ("error", "warning", "info"), rule.id)

    def test_every_rule_names_real_components(self) -> None:
        for rule in RULES:
            for component_id in rule.components:
                self.assertIn(component_id, COMPONENTS_BY_ID, f"{rule.id}: {component_id}")

    def test_every_rule_can_be_described(self) -> None:
        """A rule whose condition cannot be printed cannot be reviewed.

        Also catches a condition the vocabulary does not know how to describe:
        `describe` falls back to the bare class name, so a rule whose text is a
        single capitalised word has outgrown the printer.
        """
        for rule in RULES:
            text = describe(rule.when)
            self.assertTrue(text.strip(), rule.id)
            self.assertNotEqual(text, rule.when.__class__.__name__, rule.id)

    def test_every_rule_is_reachable(self) -> None:
        """Each rule must fire for at least one build the catalogue allows.

        A rule that can never fire is either a typo in a component id or a
        condition that contradicts itself, and both are invisible without this.

        Pairs of choices, not single ones: the rules worth writing are mostly
        about two decisions interacting — Hyprland *and* NVIDIA, PulseAudio *and*
        Wayland — so a sweep that varies one category at a time would declare
        those unreachable. It stops as soon as every rule has been seen, which in
        practice is long before the sweep is exhausted.
        """
        wanted = {rule.id for rule in RULES}
        fired: set[str] = set()
        profiles = [
            (None, False),
            (machine(), True),
            (machine(gpus=[{"vendor": "NVIDIA", "name": "GeForce GTX 1060"}]), True),
            (machine(gpus=[{"vendor": "AMD", "name": "Radeon RX 7800 XT"}]), True),
            (machine(ram={"total_gb": 4.0},
                     gpus=[{"vendor": "INTEL", "name": "UHD 620"}]), True),
            (machine(cpu={"brand": "Apple M2", "cores": 8, "arch": "aarch64"}), True),
            (machine(drivers=[{"name": "btrfs", "status": "Live"}]), True),
        ]

        choices = [
            (category.id, component.id)
            for category in CATEGORIES
            for component in category.components
        ]

        for index, (first_category, first_component) in enumerate(choices):
            for second_category, second_component in choices[index + 1:]:
                if first_category == second_category:
                    continue
                build = build_with(
                    **{first_category: first_component, second_category: second_component}
                )
                for profile, is_real in profiles:
                    fired |= rule_ids(engine.check(build, profile, is_real))
                if wanted <= fired:
                    return

        self.assertEqual(wanted - fired, set(), f"rules that never fire: {wanted - fired}")


# ── Coverage reporting ───────────────────────────────────────────────────────


class TestCoverage(unittest.TestCase):
    def test_coverage_reports_skipped_hardware_rules(self) -> None:
        coverage = engine.coverage(build_with(), hardware_is_real=False)
        self.assertEqual(coverage.rules_total, len(RULES))
        self.assertEqual(coverage.rules_skipped, len(rules_needing_hardware()))
        self.assertFalse(coverage.hardware_was_used)

    def test_full_coverage_with_a_real_reading(self) -> None:
        coverage = engine.coverage(build_with(), hardware_is_real=True)
        self.assertEqual(coverage.rules_evaluated, coverage.rules_total)
        self.assertTrue(coverage.hardware_was_used)

    def test_some_rules_actually_need_hardware(self) -> None:
        """Guards the guard: if this were zero, the skip logic would be untested."""
        self.assertGreater(len(rules_needing_hardware()), 0)

    def test_coverage_lists_implied_components(self) -> None:
        selections = default_selections()
        selections.pop("kernel")
        selections["security"] = "hardened"
        coverage = engine.coverage(Build(selections=selections))
        self.assertIn("linux-hardened", coverage.implied)


# ── Conditions, tested directly ──────────────────────────────────────────────


class TestConditions(unittest.TestCase):
    def test_needs_hardware_propagates_through_combinators(self) -> None:
        self.assertFalse(Has("mesa").needs_hardware)
        self.assertTrue(GpuVendor("NVIDIA").needs_hardware)
        self.assertTrue(Not(GpuVendor("NVIDIA")).needs_hardware)
        self.assertTrue(AllOf(Has("mesa"), RamBelowGb(8)).needs_hardware)
        self.assertFalse(AllOf(Has("mesa"), Has("wayland")).needs_hardware)
        self.assertTrue(AnyOf(Has("mesa"), GpuVendor("AMD")).needs_hardware)
        self.assertFalse(AnyOf(Has("mesa"), Has("nvidia")).needs_hardware)

    def test_combinators_evaluate_as_expected(self) -> None:
        ctx = Context(effective={"mesa": (), "wayland": ()})
        self.assertTrue(AllOf(Has("mesa"), Has("wayland")).holds(ctx))
        self.assertFalse(AllOf(Has("mesa"), Has("nvidia")).holds(ctx))
        self.assertTrue(AnyOf(Has("nvidia"), Has("mesa")).holds(ctx))
        self.assertFalse(AnyOf(Has("nvidia"), Has("xorg")).holds(ctx))
        self.assertTrue(Not(Has("nvidia")).holds(ctx))

    def test_context_derives_hardware_facts(self) -> None:
        ctx = Context(hardware=machine(), hardware_is_real=True)
        self.assertEqual(ctx.gpu_vendors, frozenset({"NVIDIA"}))
        self.assertEqual(ctx.ram_gb, 32.0)
        self.assertEqual(ctx.cpu_arch, "x86_64")
        self.assertIn("nvidia_drm", ctx.modules)

    def test_context_survives_an_empty_profile(self) -> None:
        """Detection never raises, so it can hand over a profile full of holes."""
        ctx = Context(hardware={}, hardware_is_real=True)
        self.assertEqual(ctx.gpu_vendors, frozenset())
        self.assertIsNone(ctx.ram_gb)
        self.assertIsNone(ctx.cpu_arch)

    def test_pre_turing_detection(self) -> None:
        pre_turing = ("GeForce GTX 1080 Ti", "GeForce GTX 970", "GeForce GT 730",
                      "NVIDIA GeForce GTX 1060 6GB")
        turing_or_newer = ("GeForce RTX 2060", "GeForce RTX 4070 Ti",
                           "GeForce GTX 1650", "GeForce GTX 1660 SUPER",
                           "NVIDIA RTX A2000")
        for name in pre_turing:
            self.assertTrue(is_pre_turing_nvidia(name), name)
        for name in turing_or_newer:
            self.assertFalse(is_pre_turing_nvidia(name), name)

    def test_pre_turing_ignores_things_that_are_not_cards(self) -> None:
        for name in ("", "Raphael integrated graphics", "Radeon RX 7800 XT"):
            self.assertFalse(is_pre_turing_nvidia(name), name)


# ── Output shape ─────────────────────────────────────────────────────────────


class TestIssueOutput(unittest.TestCase):
    def test_issues_are_sorted_worst_first(self) -> None:
        selections = default_selections()
        selections.pop("kernel")
        selections.update({"security": "hardened", "gpu": "nvidia", "audio": "pulseaudio"})
        issues = engine.check(Build(selections=selections))

        order = {"error": 0, "warning": 1, "info": 2}
        severities = [order[i.severity] for i in issues]
        self.assertEqual(severities, sorted(severities))

    def test_every_issue_carries_a_rule_id(self) -> None:
        """Without it an issue cannot be traced to the knowledge behind it."""
        selections = default_selections()
        selections.update({"desktop": "i3", "audio": "pulseaudio"})
        for issue in engine.check(Build(selections=selections)):
            self.assertTrue(issue.rule_id, issue.title)

    def test_explain_finds_the_rule_behind_an_issue(self) -> None:
        build = build_with(audio="pulseaudio", display="wayland")
        issue = next(
            i for i in engine.check(build)
            if i.rule_id == "pulseaudio-wayland-screen-sharing"
        )
        rule = engine.explain(issue.rule_id)
        self.assertIsNotNone(rule)
        assert rule is not None
        self.assertEqual(rule.title, issue.title)

    def test_derived_issues_have_no_rule_object(self) -> None:
        """The generated issues are not curated rules, and explain() says so."""
        self.assertIsNone(engine.explain("conflict"))
        self.assertIsNone(engine.explain("category-unanswered"))

    def test_summarise_counts_by_severity(self) -> None:
        issues = [
            Issue("error", "a", "", "f"),
            Issue("warning", "b", "", "f"),
            Issue("warning", "c", "", "f"),
        ]
        self.assertEqual(
            engine.summarise(issues), {"error": 1, "warning": 2, "info": 0}
        )
        self.assertFalse(engine.build_is_installable(issues))


if __name__ == "__main__":
    unittest.main()
