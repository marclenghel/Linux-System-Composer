"""Tests for the hardware detector.

Almost everything here runs against captured fixture text rather than a real
machine, so the Windows parser is tested on Linux and the Linux parser on
Windows. That matters for a project that has to work on three platforms but is
developed on one — the parsing bugs you cannot reproduce are the parsing bugs
for the platform you are not sitting at.

The one test that does touch the real machine only asserts that detection
returns a complete, well-typed report. It cannot assert *what* is in it,
because that depends on whose computer is running the tests.
"""

from __future__ import annotations

import unittest

from lsc.data import hardware
from lsc.data.catalog import default_selections
from lsc.data.rules import RULES
from lsc.detect import SOURCE_DETECTED, detect, normalise_arch
from lsc.detect import linux as linux_detect
from lsc.detect import windows as windows_detect
from lsc.compat.facts import HardwareFacts, build_world
from lsc.models import Build

# Captured from `powershell` on a real Windows 11 machine, trimmed to two of
# each list. The single-GPU case below is the interesting one: PowerShell
# unwraps one-element arrays into a bare object.
WINDOWS_JSON = {
    "os": "Microsoft Windows 11 Pro",
    "kernel": "10.0.26200",
    "cpu_brand": "11th Gen Intel(R) Core(TM) i9-11900 @ 2.50GHz",
    "cpu_cores": 16,
    "ram_bytes": 17004879872.0,
    "board": "ASUSTeK COMPUTER INC. PRIME Z590-V",
    "disks": [
        {"name": "ADATA SU650", "size": 480103981056.0, "media": "SSD", "bus": "SATA"},
        {"name": "WD Blue SN570", "size": 1000204886016.0, "media": "SSD", "bus": "NVMe"},
    ],
    "gpus": {"name": "NVIDIA GeForce RTX 3060"},
    "drivers": [{"name": "ACPI", "status": "Running"}],
    "nics": [
        {"name": "Intel(R) Ethernet Connection I219-V", "mac": "7C-10-C9-40-9C-4E"},
        {"name": "Tailscale Tunnel", "mac": "00:00:00:00:00:00"},
    ],
}


class TestWindowsParser(unittest.TestCase):
    def setUp(self) -> None:
        self.report = windows_detect.parse(WINDOWS_JSON)

    def test_scalar_fields(self) -> None:
        self.assertEqual(self.report["os"], "Microsoft Windows 11 Pro")
        self.assertEqual(self.report["kernel"], "10.0.26200")
        self.assertEqual(self.report["cpu"]["cores"], 16)
        self.assertEqual(self.report["motherboard"], "ASUSTeK COMPUTER INC. PRIME Z590-V")

    def test_ram_is_gibibytes_not_gigabytes(self) -> None:
        # 17_004_879_872 bytes is 15.84 GiB but 17.0 GB. Memory is quoted in
        # GiB by every tool a Linux user will compare this against.
        self.assertAlmostEqual(self.report["ram"]["total_gb"], 15.84, places=1)

    def test_single_gpu_object_becomes_a_list(self) -> None:
        """The shape trap: one GPU arrives as an object, two as an array."""
        self.assertEqual(len(self.report["gpus"]), 1)
        self.assertEqual(self.report["gpus"][0]["vendor"], "NVIDIA")

    def test_nvme_beats_ssd(self) -> None:
        types = [disk["disk_type"] for disk in self.report["disks"]]
        self.assertEqual(types, ["SSD", "NVMe"])

    def test_disk_size_is_gigabytes(self) -> None:
        # Drives are sold and labelled in GB, so a "480 GB" SSD should read 480.
        self.assertAlmostEqual(self.report["disks"][0]["size_gb"], 480.1, places=1)

    def test_blank_mac_adapters_are_dropped(self) -> None:
        macs = [card["mac_address"] for card in self.report["network_cards"]]
        self.assertEqual(macs, ["7c:10:c9:40:9c:4e"])

    def test_mac_is_normalised_to_the_unix_form(self) -> None:
        """Windows uses 7C-10-C9; Linux and macOS use 7c:10:c9."""
        self.assertEqual(self.report["network_cards"][0]["mac_address"], "7c:10:c9:40:9c:4e")

    def test_missing_fields_do_not_raise(self) -> None:
        report = windows_detect.parse({})
        self.assertEqual(report["cpu"]["cores"], 0)
        self.assertEqual(report["disks"], [])
        self.assertEqual(report["motherboard"], "Unknown")


class TestVendorFromName(unittest.TestCase):
    def test_known_vendors(self) -> None:
        cases = {
            "NVIDIA GeForce RTX 3060": "NVIDIA",
            "AMD Radeon RX 7900 XTX": "AMD",
            "Intel(R) UHD Graphics 750": "Intel",
            "Apple M3 Pro": "Apple",
            "VMware SVGA 3D": "Virtual",
            "Some Unknown Card": "Unknown",
        }
        for name, expected in cases.items():
            with self.subTest(name=name):
                self.assertEqual(windows_detect.vendor_from_name(name), expected)

    def test_geforce_without_the_word_nvidia(self) -> None:
        """Windows sometimes reports just "GeForce GTX 1080"."""
        self.assertEqual(windows_detect.vendor_from_name("GeForce GTX 1080"), "NVIDIA")


class TestLspciParsing(unittest.TestCase):
    def test_split_quoted_fields(self) -> None:
        line = (
            '01:00.0 "VGA compatible controller" "NVIDIA Corporation" '
            '"GA106 [GeForce RTX 3060]" -r a1 "ASUSTeK" "Device 88a1"'
        )
        fields = linux_detect._split_quoted(line)
        self.assertEqual(fields[0], "01:00.0")
        self.assertEqual(fields[1], "VGA compatible controller")
        self.assertEqual(fields[3], "GA106 [GeForce RTX 3060]")

    def test_square_brackets_survive(self) -> None:
        """The prototype hunted for [brackets] by hand and could panic on them.

        With -mm the model is already its own quoted field, brackets included,
        so there is nothing to search for.
        """
        line = '00:02.0 "VGA compatible controller" "Intel" "AlderLake-S GT1 [UHD 730]"'
        self.assertEqual(linux_detect._split_quoted(line)[3], "AlderLake-S GT1 [UHD 730]")


class TestArchNormalisation(unittest.TestCase):
    def test_platform_spellings_map_to_the_linux_one(self) -> None:
        cases = {
            "AMD64": "x86_64",
            "x86_64": "x86_64",
            "ARM64": "aarch64",
            "aarch64": "aarch64",
            "": "unknown",
        }
        for machine, expected in cases.items():
            with self.subTest(machine=machine):
                self.assertEqual(normalise_arch(machine), expected)


class TestDetectionFeedingTheEngine(unittest.TestCase):
    """The seam where a reading becomes advice.

    This used to test hardware.suggestions_for, which matched vendor substrings
    and returned tuples. That function is gone: turning "the string said NVIDIA"
    into "use the open modules" is a compatibility judgement, and those live in
    the rule set now. What is left to check here is that a detector report is
    actually usable by the engine - the field names line up, and a real reading
    turns hardware rules from undecided into decided.
    """

    def test_a_detector_report_normalises_into_hardware_facts(self) -> None:
        report = windows_detect.parse(WINDOWS_JSON)
        report["source"] = SOURCE_DETECTED
        report["platform"] = "windows"

        facts = HardwareFacts.from_profile(report)
        self.assertIsNotNone(facts)
        self.assertEqual(facts.cpu_cores, 16)
        self.assertEqual(len(facts.gpus), 1)

    def test_the_model_string_a_detector_produces_resolves_to_a_generation(self) -> None:
        """The whole point of the port meeting the engine.

        The Windows detector reports "NVIDIA GeForce RTX 3060"; the engine has
        to get "Ampere" out of that, or no rule can reason about the card.
        """
        report = windows_detect.parse(WINDOWS_JSON)
        report["source"] = SOURCE_DETECTED
        facts = HardwareFacts.from_profile(report)
        self.assertEqual(facts.gpus[0].architecture, "Ampere")
        self.assertGreaterEqual(facts.best_nvidia_rank(), 60)

    def test_the_sample_profile_is_not_mistaken_for_a_reading(self) -> None:
        """Rules must not describe a machine nobody has looked at."""
        self.assertIsNone(HardwareFacts.from_profile(hardware.sample_profile()))

    def test_a_missing_profile_is_unknown_rather_than_empty(self) -> None:
        self.assertIsNone(HardwareFacts.from_profile(None))

    def test_every_detected_field_the_rules_ask_for_is_present(self) -> None:
        """A rule naming a fact the detector never fills in can never fire."""
        report = windows_detect.parse(WINDOWS_JSON)
        report["source"] = SOURCE_DETECTED
        report["platform"] = "windows"
        world = build_world(Build(selections=default_selections()), report)

        for rule in RULES:
            for key in rule.fact_keys():
                if not key.startswith("hardware."):
                    continue
                with self.subTest(rule=rule.id, fact=key):
                    self.assertIn(key, world.facts)


class TestLiveDetection(unittest.TestCase):
    """Runs against whatever machine the tests are on.

    Takes a few seconds on Windows because it queries CIM. It cannot assert
    what the hardware *is*, only that reading it produces a complete report
    and does not raise — which is the contract the rest of the app relies on.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.report = detect()

    def test_report_has_every_promised_field(self) -> None:
        for key in (
            "source", "platform", "os", "kernel", "cpu", "ram", "motherboard",
            "disks", "gpus", "drivers", "network_cards",
        ):
            self.assertIn(key, self.report)

    def test_field_types(self) -> None:
        self.assertIsInstance(self.report["cpu"]["cores"], int)
        self.assertIsInstance(self.report["ram"]["total_gb"], float)
        for key in ("disks", "gpus", "drivers", "network_cards"):
            self.assertIsInstance(self.report[key], list)

    def test_marked_as_detected_not_sample(self) -> None:
        """The interface decides which banner to show from this one field.

        The engine reads it too, and refuses to reason about hardware unless it
        says "detected" - so this field is what separates a rule describing
        your machine from a rule describing an example.
        """
        self.assertEqual(self.report["source"], SOURCE_DETECTED)
        self.assertIn("detected_at", self.report)

    def test_a_real_reading_lets_the_engine_decide_hardware_rules(self) -> None:
        """End to end: this machine, whatever it is, produces usable facts."""
        facts = HardwareFacts.from_profile(self.report)
        self.assertIsNotNone(facts)
        self.assertIn(facts.platform, {"linux", "macos", "windows"})

    def test_arch_is_reported_in_linux_spelling(self) -> None:
        self.assertNotIn(self.report["cpu"]["arch"], ("AMD64", "ARM64"))

    def test_detection_did_not_partially_fail(self) -> None:
        """Not a hard requirement of the contract, but worth knowing about."""
        self.assertIsNone(
            self.report.get("error"),
            f"detection reported: {self.report.get('error')}",
        )


if __name__ == "__main__":
    unittest.main()
