"""Fixture machines and fixture builds, shared by the engine and rule tests.

A rule engine is only as trustworthy as the situations it has been shown. These
are those situations: hardware profiles that look like real machines, written
out so a test can say "on this machine, that rule fires" without anyone having
to own the machine.

Every profile is marked as a detected reading, because that is what the engine
insists on before it will reason about hardware at all — see lsc/compat/facts.py.
"""

from __future__ import annotations

from typing import Any

from lsc.data.catalog import default_selections
from lsc.models import Build


def profile(**overrides: Any) -> dict[str, Any]:
    """A plausible detected machine, with anything you like replaced."""
    base: dict[str, Any] = {
        "source": "detected",
        "platform": "linux",
        "os": "Arch Linux",
        "kernel": "6.12.8-arch1-1",
        "cpu": {"brand": "AMD Ryzen 7 7800X3D", "cores": 16, "arch": "x86_64"},
        "ram": {"total_gb": 32.0},
        "motherboard": "ASUS TUF GAMING B650-PLUS",
        "disks": [{"name": "/dev/nvme0n1", "size_gb": 931.5, "disk_type": "NVMe"}],
        "gpus": [{"vendor": "AMD", "name": "Radeon RX 7900 XTX"}],
        "drivers": [{"name": "amdgpu", "status": "Live"}],
        "network_cards": [],
    }
    base.update(overrides)
    return base


# ── machines ──────────────────────────────────────────────────────────────────

AMD_DESKTOP = profile()

NVIDIA_AMPERE = profile(
    gpus=[{"vendor": "NVIDIA", "name": "GeForce RTX 3060"}],
    drivers=[{"name": "nvidia_drm", "status": "Live"}],
)

# The card the whole nvidia-open story is about: real, common, and one
# generation too old for the driver the vendor now recommends.
NVIDIA_PASCAL = profile(
    gpus=[{"vendor": "NVIDIA", "name": "GeForce GTX 1060 6GB"}],
    drivers=[{"name": "nvidia", "status": "Live"}],
)

OLD_KERNEL_NVIDIA = profile(
    kernel="6.1.70-1-lts",
    gpus=[{"vendor": "NVIDIA", "name": "GeForce RTX 3060"}],
)

VIRTUAL_MACHINE = profile(
    motherboard="QEMU Standard PC",
    gpus=[{"vendor": "Virtual", "name": "VMware SVGA 3D"}],
    drivers=[{"name": "virtio_pci", "status": "Live"}, {"name": "virtio_gpu", "status": "Live"}],
)

LOW_MEMORY_LAPTOP = profile(
    ram={"total_gb": 4.0},
    cpu={"brand": "Intel Core i3-5005U", "cores": 4, "arch": "x86_64"},
    gpus=[{"vendor": "Intel", "name": "HD Graphics 5500"}],
)

ARM_BOARD = profile(
    cpu={"brand": "Cortex-A76", "cores": 4, "arch": "aarch64"},
    gpus=[],
    drivers=[],
)

BTRFS_IN_USE = profile(
    drivers=[{"name": "btrfs", "status": "Live"}, {"name": "amdgpu", "status": "Live"}],
)

# A card released after the model table was last edited. The engine must answer
# "I don't know" about it rather than guessing, so it earns a fixture.
UNRECOGNISED_GPU = profile(
    gpus=[{"vendor": "NVIDIA", "name": "GeForce SomethingEntirelyNew"}],
)

MACHINES: dict[str, dict[str, Any]] = {
    "amd-desktop": AMD_DESKTOP,
    "nvidia-ampere": NVIDIA_AMPERE,
    "nvidia-pascal": NVIDIA_PASCAL,
    "old-kernel-nvidia": OLD_KERNEL_NVIDIA,
    "virtual-machine": VIRTUAL_MACHINE,
    "low-memory-laptop": LOW_MEMORY_LAPTOP,
    "arm-board": ARM_BOARD,
    "btrfs-in-use": BTRFS_IN_USE,
    "unrecognised-gpu": UNRECOGNISED_GPU,
}


# ── builds ────────────────────────────────────────────────────────────────────


def build(**overrides: str) -> Build:
    """The default build with individual categories replaced."""
    selections = default_selections()
    selections.update(overrides)
    return Build(name="fixture", selections=selections)


def build_without(category_id: str, **overrides: str) -> Build:
    """The default build with one category left unanswered."""
    made = build(**overrides)
    made.selections.pop(category_id, None)
    return made
