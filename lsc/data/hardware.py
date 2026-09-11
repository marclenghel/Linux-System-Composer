"""A stand-in hardware profile.

IMPORTANT: nothing here touches the real machine. This is sample data shaped
*exactly* like the JSON the Rust prototype produced, so that porting the real
detector is a drop-in replacement rather than a rewrite of every screen that
displays hardware.

The port plan, roughly:

    legacy/rust-hardware-detect/src/main.rs   ->   lsc/detect/
        uname -r, /proc/cpuinfo, /proc/meminfo      -> platform/linux.py
        system_profiler, sysctl, kextstat           -> platform/macos.py
        WMI via PowerShell                          -> platform/windows.py

Once that exists, `load_profile()` below stops returning SAMPLE_PROFILE and
starts returning a real reading, and no screen has to change.
"""

from __future__ import annotations

from typing import Any

# Where the current profile came from. The UI shows this prominently so nobody
# mistakes sample data for a real reading during a demo.
SOURCE_SAMPLE = "sample"
SOURCE_DETECTED = "detected"


# The field names match the Rust HardwareReport struct one for one:
#   os, kernel, cpu{brand,cores,arch}, ram{total_gb}, motherboard,
#   disks[{name,size_gb,disk_type}], gpus[{vendor,name}],
#   drivers[{name,status}], network_cards[{name,mac_address}]
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


def load_profile() -> dict[str, Any]:
    """Return the hardware profile the UI should display.

    Returns sample data today. When the detector is ported this becomes a real
    reading with `source` set to SOURCE_DETECTED, and every screen that already
    reads this dict keeps working unchanged.
    """
    return SAMPLE_PROFILE


def suggestions_for(profile: dict[str, Any]) -> list[tuple[str, str, str]]:
    """Turn a hardware profile into catalogue suggestions.

    Returns (category_id, component_id, reason) triples. This is the seam where
    detection meets composition — the moment the detector is real, these become
    genuine recommendations instead of an illustration of the idea.

    Kept deliberately crude: matching on vendor strings is not a compatibility
    engine, and pretending otherwise would be the wrong foundation to build a
    year of work on.
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

    return suggestions
