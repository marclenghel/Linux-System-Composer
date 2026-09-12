"""Hardware profiles: the real reading, and the fixture that stands in for it.

The detector lives in lsc/detect/ and is the Python port of the Rust
prototype. This module is the seam the screens talk to, so nothing in the
interface needs to know whether it is looking at a real machine or a fixture —
only at the `source` field, which says which.

The sample profile is kept for three reasons: the interface has something to
draw in the fraction of a second before the scan finishes, the tests do not
need a particular machine to run on, and a demo can be given from a laptop
that is not the one being described.

This module used to carry a suggestions_for() that matched vendor substrings
and returned advice. Milestone 3 deleted it. Turning "the string said NVIDIA"
into "use the open modules" is a compatibility judgement, and compatibility
judgements now live in lsc/data/rules.py where they can state their condition,
explain themselves, and be tested. The Hardware screen asks the engine.
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
]


# Field for field, this is the Rust HardwareReport struct: os, kernel,
# cpu{brand,cores,arch}, ram{total_gb}, motherboard, disks[], gpus[],
# drivers[], network_cards[]. Keeping the shapes identical is what made the
# port a drop-in rather than a rewrite of every screen.
SAMPLE_PROFILE: dict[str, Any] = {
    "source": SOURCE_SAMPLE,
    "platform": "linux",
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
