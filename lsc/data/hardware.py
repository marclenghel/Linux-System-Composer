"""Hardware profiles: the real reading, and the fixture that stands in for it.

The detector lives in lsc/detect/ and is the Python port of the Rust
prototype. This module is the seam the screens talk to, so nothing in the
interface needs to know whether it is looking at a real machine or a fixture —
only at the `source` field, which says which.

The sample profile is kept for three reasons: the interface has something to
draw in the fraction of a second before the scan finishes, the tests do not
need a particular machine to run on, and a demo can be given from a laptop
that is not the one being described.
"""

from __future__ import annotations

import copy
from typing import Any

from lsc.detect import SOURCE_DETECTED, SOURCE_SAMPLE, detect

__all__ = [
    "SOURCE_DETECTED",
    "SOURCE_SAMPLE",
    "detect_profile",
    "sample_profile",
    "suggestions_for",
]


# Field for field, this is the Rust HardwareReport struct: os, kernel,
# cpu{brand,cores,arch}, ram{total_gb}, motherboard, disks[], gpus[],
# drivers[], network_cards[]. Keeping the shapes identical is what made the
# port a drop-in rather than a rewrite of every screen.
SAMPLE_PROFILE: dict[str, Any] = {
    "source": SOURCE_SAMPLE,
    "os": "Arch Linux",
    "kernel": "6.12.8-arch1-1",
    "cpu": {
        "brand": "AMD Ryzen 7 7800X3D 8-Core Processor",
        "cores": 16,
        "arch": "x86_64",
    },
    "ram": {"total_gb": 31.24},
    "motherboard": "ASUS TUF GAMING B650-PLUS WIFI",
    "disks": [
        {"name": "/dev/nvme0n1", "size_gb": 931.5, "disk_type": "NVMe"},
        {"name": "/dev/sda", "size_gb": 1863.0, "disk_type": "HDD"},
    ],
    "gpus": [
        {"vendor": "NVIDIA", "name": "GeForce RTX 4070 Ti"},
        {"vendor": "AMD", "name": "Raphael integrated graphics"},
    ],
    "drivers": [
        {"name": "nvidia_drm", "status": "Live"},
        {"name": "nvidia_modeset", "status": "Live"},
        {"name": "amdgpu", "status": "Live"},
        {"name": "btrfs", "status": "Live"},
        {"name": "snd_hda_intel", "status": "Live"},
        {"name": "iwlwifi", "status": "Live"},
        {"name": "nvme", "status": "Live"},
        {"name": "xhci_pci", "status": "Live"},
    ],
    "network_cards": [
        {"name": "enp5s0", "mac_address": "2c:f0:5d:11:a4:9b"},
        {"name": "wlp4s0", "mac_address": "b0:3c:dc:7e:02:14"},
    ],
}


def sample_profile() -> dict[str, Any]:
    """The fixture. A deep copy, so a screen cannot edit the constant."""
    return copy.deepcopy(SAMPLE_PROFILE)


def detect_profile() -> dict[str, Any]:
    """Read the real machine.

    Takes a few seconds on Windows, so callers should run it off the UI
    thread. Never raises — see lsc/detect/__init__.py.
    """
    return detect()


def suggestions_for(profile: dict[str, Any]) -> list[tuple[str, str, str]]:
    """Turn a hardware profile into catalogue suggestions.

    Returns (category_id, component_id, reason) triples — the seam where
    detection meets composition.

    Still crude on purpose. Matching vendor strings is not a compatibility
    engine, and now that the readings are real it matters more, not less, that
    this is not mistaken for one. Milestone 3 replaces it with rules that can
    say *why* under what conditions.
    """
    suggestions: list[tuple[str, str, str]] = []
    vendors = {gpu.get("vendor", "").upper() for gpu in profile.get("gpus", [])}

    if "NVIDIA" in vendors:
        suggestions.append(
            (
                "gpu",
                "nvidia-open",
                "An NVIDIA GPU was reported, and the open kernel modules are the "
                "vendor's recommended driver on RTX 20-series and newer.",
            )
        )
    elif vendors & {"AMD", "INTEL"}:
        suggestions.append(
            (
                "gpu",
                "mesa",
                "Only AMD/Intel graphics were reported, which the in-kernel Mesa "
                "stack handles with no driver installation at all.",
            )
        )
    elif "VIRTUAL" in vendors:
        suggestions.append(
            (
                "gpu",
                "vm-guest",
                "This looks like a virtual machine, so the paravirtualised guest "
                "drivers are the right choice.",
            )
        )

    loaded = {driver.get("name", "") for driver in profile.get("drivers", [])}
    if "btrfs" in loaded:
        suggestions.append(
            (
                "filesystem",
                "btrfs",
                "The btrfs module is already loaded, so this machine is very likely "
                "running it today.",
            )
        )

    ram_gb = profile.get("ram", {}).get("total_gb", 0)
    if ram_gb and ram_gb < 8:
        suggestions.append(
            (
                "desktop",
                "xfce",
                f"Only {ram_gb:.0f} GB of RAM was reported — a lighter desktop will "
                "leave more of it for your actual work.",
            )
        )

    arch = profile.get("cpu", {}).get("arch", "")
    if arch == "aarch64":
        suggestions.append(
            (
                "kernel",
                "linux",
                "This is an ARM machine. The tuned x86 kernels do not apply, so "
                "mainline is the choice that exists.",
            )
        )

    return suggestions
