"""Ready-made builds the user can start from.

A preset is just a set of selections with a name attached — deliberately the
same shape as a saved build, because "share a system blueprint" from the README
is the same feature as "load a preset", only the file comes from someone else.
"""

from __future__ import annotations

from lsc.models import Preset

PRESETS: tuple[Preset, ...] = (
    Preset(
        id="gaming",
        name="Gaming",
        tagline="Latency and frame rate first",
        description=(
            "A tuned kernel, the proprietary graphics driver, and a compositor that "
            "does not get in the way. Btrfs is here for a reason: when a driver update "
            "breaks your setup the night before a session, you roll back instead of "
            "debugging."
        ),
        selections={
            "base": "cachyos",
            "kernel": "linux-cachyos",
            "bootloader": "systemd-boot",
            "filesystem": "btrfs",
            "gpu": "nvidia-open",
            "display": "wayland",
            "desktop": "kde",
            "audio": "pipewire",
            "security": "baseline",
        },
    ),
    Preset(
        id="developer",
        name="Developer",
        tagline="Stable underneath, fast on top",
        description=(
            "Boring where it should be boring. Snapshots before every system update, "
            "open graphics drivers so kernel upgrades never block, and a desktop that "
            "handles multiple monitors at different scales without arguing."
        ),
        selections={
            "base": "arch",
            "kernel": "linux",
            "bootloader": "grub",
            "filesystem": "btrfs",
            "gpu": "mesa",
            "display": "wayland",
            "desktop": "hyprland",
            "audio": "pipewire",
            "security": "apparmor",
        },
    ),
    Preset(
        id="minimal",
        name="Minimal",
        tagline="As little as will still boot and do the job",
        description=(
            "No desktop, no sound server, no surprises. For servers, build machines, "
            "and old hardware. Useful as a teaching example too: it is the shortest "
            "path from firmware to a usable shell."
        ),
        selections={
            "base": "arch",
            "kernel": "linux-lts",
            "bootloader": "systemd-boot",
            "filesystem": "ext4",
            "gpu": "vm-guest",
            # No display server at all — the stack diagram shows the gap, which is
            # the point: a headless build really does stop below this layer.
            "desktop": "headless",
            "audio": "alsa",
            "security": "baseline",
        },
    ),
    Preset(
        id="hardened",
        name="Security Hardened",
        tagline="Assume the machine is a target",
        description=(
            "A hardened kernel, mandatory access control, per-application sandboxing, "
            "and a filesystem that can prove its own data has not changed underneath "
            "you. Expect friction — that is the point, and the composer should tell "
            "you where the friction will be before you install anything."
        ),
        selections={
            "base": "arch",
            "kernel": "linux-hardened",
            "bootloader": "grub",
            "filesystem": "btrfs",
            "gpu": "mesa",
            "display": "wayland",
            "desktop": "gnome",
            "audio": "pipewire",
            "security": "hardened",
        },
    ),
)

PRESETS_BY_ID: dict[str, Preset] = {p.id: p for p in PRESETS}
