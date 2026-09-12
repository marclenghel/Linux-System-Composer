"""Tests for the graphics model table.

Detection reports a string. A rule needs a capability. This table is the only
thing between the two, and it is a list of regular expressions where the order
matters, which is a combination that goes wrong quietly.

The cases below are all real product names, and most of them are here because
they collide with another entry. "GTX 1660" is Turing and "GTX 1060" is Pascal;
"Quadro RTX 4000" is Turing and "RTX 4090" is Ada. A pattern written in the
wrong order gets one of each pair wrong and nothing complains.
"""

from __future__ import annotations

import unittest

from lsc.data import gpus


class TestNvidiaGenerations(unittest.TestCase):
    def test_consumer_cards(self) -> None:
        cases = {
            "NVIDIA GeForce RTX 5090": "Blackwell",
            "NVIDIA GeForce RTX 4090": "Ada Lovelace",
            "NVIDIA GeForce RTX 3060": "Ampere",
            "NVIDIA GeForce RTX 2080 Ti": "Turing",
            "NVIDIA GeForce GTX 1060 6GB": "Pascal",
            "NVIDIA GeForce GTX 980 Ti": "Maxwell",
            "NVIDIA GeForce GTX 780": "Kepler",
            "NVIDIA GeForce GTX 560 Ti": "Fermi",
        }
        for name, architecture in cases.items():
            with self.subTest(name=name):
                self.assertEqual(gpus.identify(name).architecture, architecture)

    def test_the_1660_is_turing_and_the_1060_is_pascal(self) -> None:
        """The ordering trap inside one product line."""
        self.assertEqual(gpus.identify("GeForce GTX 1660 Ti").architecture, "Turing")
        self.assertEqual(gpus.identify("GeForce GTX 1060").architecture, "Pascal")

    def test_the_750_is_maxwell_and_the_760_is_kepler(self) -> None:
        """Two consecutive numbers, two different architectures."""
        self.assertEqual(gpus.identify("GeForce GTX 750 Ti").architecture, "Maxwell")
        self.assertEqual(gpus.identify("GeForce GTX 760").architecture, "Kepler")

    def test_workstation_names_reuse_consumer_numbers(self) -> None:
        """A Quadro RTX 4000 is Turing; an RTX 4090 is Ada."""
        self.assertEqual(gpus.identify("Quadro RTX 4000").architecture, "Turing")
        self.assertEqual(gpus.identify("NVIDIA GeForce RTX 4090").architecture, "Ada Lovelace")
        self.assertEqual(gpus.identify("NVIDIA RTX A4000").architecture, "Ampere")
        self.assertEqual(gpus.identify("RTX 2000 Ada Generation").architecture, "Ada Lovelace")

    def test_datacentre_cards(self) -> None:
        self.assertEqual(gpus.identify("NVIDIA A100-SXM4-40GB").architecture, "Ampere")
        self.assertEqual(gpus.identify("Tesla T4").architecture, "Turing")
        self.assertEqual(gpus.identify("Tesla V100-PCIE").architecture, "Volta")


class TestModelStringShapes(unittest.TestCase):
    def test_the_lspci_form_is_understood(self) -> None:
        """Linux reports the chip and the marketing name together."""
        self.assertEqual(gpus.identify("GA106 [GeForce RTX 3060]").architecture, "Ampere")
        self.assertEqual(gpus.identify("TU116 [GeForce GTX 1660]").architecture, "Turing")

    def test_punctuation_and_spacing_do_not_matter(self) -> None:
        for name in ("RTX3060", "RTX-3060", "RTX_3060", "rtx 3060"):
            with self.subTest(name=name):
                self.assertEqual(gpus.identify(name).architecture, "Ampere")

    def test_an_empty_string_is_not_a_card(self) -> None:
        self.assertIsNone(gpus.identify(""))


class TestOtherVendors(unittest.TestCase):
    def test_amd(self) -> None:
        cases = {
            "AMD Radeon RX 9070 XT": "RDNA 4",
            "AMD Radeon RX 7900 XTX": "RDNA 3",
            "AMD Radeon RX 6700 XT": "RDNA 2",
            "AMD Radeon RX 5700 XT": "RDNA",
            "AMD Radeon RX Vega 64": "GCN",
        }
        for name, architecture in cases.items():
            with self.subTest(name=name):
                self.assertEqual(gpus.identify(name).architecture, architecture)

    def test_intel(self) -> None:
        self.assertEqual(gpus.identify("Intel Arc A770").architecture, "Xe-HPG (Alchemist)")
        self.assertEqual(gpus.identify("Intel(R) UHD Graphics 750").architecture, "Gen")

    def test_virtual_display_adapters(self) -> None:
        for name in ("VMware SVGA 3D", "VirtualBox Graphics Adapter", "QXL paravirtual", "Microsoft Basic Display Adapter"):
            with self.subTest(name=name):
                self.assertEqual(gpus.identify(name).vendor, "Virtual")

    def test_vendors_are_reported_correctly(self) -> None:
        self.assertEqual(gpus.identify("NVIDIA GeForce RTX 3060").vendor, "NVIDIA")
        self.assertEqual(gpus.identify("AMD Radeon RX 7900 XTX").vendor, "AMD")
        self.assertEqual(gpus.identify("Intel Arc A770").vendor, "Intel")


class TestUnknownCards(unittest.TestCase):
    def test_a_card_the_table_has_never_heard_of(self) -> None:
        self.assertIsNone(gpus.identify("Matrox Millennium G550"))

    def test_an_nvidia_card_released_after_this_table_was_written(self) -> None:
        """Still recognisably NVIDIA, deliberately without a generation.

        Claiming an unknown rank is what lets the engine say "I cannot tell"
        rather than refusing a driver because a lookup table is out of date.
        """
        family = gpus.identify("NVIDIA GeForce RTX 7090")
        self.assertEqual(family.vendor, "NVIDIA")
        self.assertEqual(family.rank, gpus.UNKNOWN_RANK)


class TestOpenModuleSupport(unittest.TestCase):
    def test_turing_and_newer_are_supported(self) -> None:
        for name in ("GeForce RTX 3060", "GeForce RTX 2080", "GeForce GTX 1660"):
            with self.subTest(name=name):
                self.assertIs(gpus.supports_open_modules(gpus.identify(name).rank), True)

    def test_older_cards_are_not(self) -> None:
        for name in ("GeForce GTX 1060", "GeForce GTX 980", "GeForce GTX 780"):
            with self.subTest(name=name):
                self.assertIs(gpus.supports_open_modules(gpus.identify(name).rank), False)

    def test_an_unrecognised_card_is_not_a_no(self) -> None:
        self.assertIsNone(gpus.supports_open_modules(gpus.UNKNOWN_RANK))


class TestRanksAreOrdered(unittest.TestCase):
    def test_generations_sort_by_age(self) -> None:
        order = ["GTX 780", "GTX 980", "GTX 1080", "RTX 2080", "RTX 3080", "RTX 4080", "RTX 5080"]
        ranks = [gpus.identify(name).rank for name in order]
        self.assertEqual(ranks, sorted(ranks))

    def test_the_turing_threshold_is_where_the_open_modules_start(self) -> None:
        self.assertEqual(gpus.NVIDIA_OPEN_MIN_RANK, gpus.TURING)
        self.assertLess(gpus.PASCAL, gpus.TURING)
        self.assertGreater(gpus.AMPERE, gpus.TURING)


if __name__ == "__main__":
    unittest.main()
