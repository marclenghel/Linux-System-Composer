"""Hardware detection on Linux.

Sources, all readable without root:

    os / kernel     /etc/os-release, uname -r
    cpu             /proc/cpuinfo
    ram             /proc/meminfo
    motherboard     /sys/class/dmi/id/board_vendor + board_name
    disks           /sys/block/*
    gpus            /sys/bus/pci/devices/* (lspci only to improve the names)
    drivers         /proc/modules
    network         /sys/class/net/* (ip link only as a fallback)

One deliberate departure from the Rust prototype: it ran `sudo pacman -S
pciutils` when lspci was missing. This does not. A tool asked to *look at* the
machine must not install packages as a side effect, least of all with root —
and a project whose README promises a safety layer cannot open by silently
elevating. Reading the PCI bus out of /sys needs neither lspci nor root, so
the dependency was not necessary in the first place.
"""

from __future__ import annotations

import os.path

from lsc.detect._shell import list_dir, read_first_line, read_text, run, which

# PCI vendor ids. The PCI class code says a device is a display controller;
# these say who made it. Assigned by PCI-SIG and effectively permanent.
_PCI_VENDORS = {
    "0x10de": "NVIDIA",
    "0x1002": "AMD",
    "0x1022": "AMD",
    "0x8086": "Intel",
    "0x106b": "Apple",
    "0x1af4": "Virtio",
    "0x15ad": "VMware",
    "0x1414": "Microsoft",
}

# PCI base class 0x03 is "display controller" — VGA, 3D, and everything else
# that drives a screen.
_DISPLAY_CLASS_PREFIX = "0x03"


def os_name() -> str:
    """The distribution's own name, e.g. "Arch Linux" or "Ubuntu 24.04 LTS"."""
    release = read_text("/etc/os-release")
    if release:
        for line in release.splitlines():
            if line.startswith("PRETTY_NAME="):
                return line.partition("=")[2].strip().strip('"')
    return "Linux"


def kernel() -> str:
    return run("uname", "-r") or "Unknown"


def cpu() -> dict:
    """CPU brand and logical core count from /proc/cpuinfo.

    Counting "processor" lines gives logical cores including hyperthreading,
    which is what the Rust version reported through sysinfo.
    """
    info = read_text("/proc/cpuinfo") or ""
    brand = "Unknown"
    cores = 0

    for line in info.splitlines():
        if line.startswith("processor"):
            cores += 1
        elif brand == "Unknown":
            # x86 calls it "model name"; ARM boards use "Hardware" or
            # "Model" and often have no brand string at all.
            for key in ("model name", "Hardware", "Model"):
                if line.startswith(key):
                    value = line.partition(":")[2].strip()
                    if value:
                        brand = value
                    break

    return {"brand": brand, "cores": cores}


def ram_gb() -> float:
    """Total memory in GiB, from MemTotal in /proc/meminfo (which is in kB)."""
    meminfo = read_text("/proc/meminfo") or ""
    for line in meminfo.splitlines():
        if line.startswith("MemTotal:"):
            parts = line.split()
            if len(parts) >= 2 and parts[1].isdigit():
                return int(parts[1]) / (1024 * 1024)
    return 0.0


def motherboard() -> str:
    """Board vendor and model from DMI.

    /sys/class/dmi/id is the same data dmidecode reports, except these two
    files are world-readable, so this needs no root.
    """
    vendor = read_first_line("/sys/class/dmi/id/board_vendor") or ""
    name = read_first_line("/sys/class/dmi/id/board_name") or ""
    combined = f"{vendor} {name}".strip()
    return combined or "Unknown"


def disks() -> list[dict]:
    """Physical disks from /sys/block.

    Walking /sys/block instead of mounted filesystems is what stops one drive
    with four partitions being reported four times — the deduplication the
    Rust version needed a HashSet for is structural here.
    """
    found = []
    for name in list_dir("/sys/block"):
        # loop devices, ramdisks, and device-mapper nodes are not hardware.
        if name.startswith(("loop", "ram", "dm-", "zram", "md")):
            continue

        base = f"/sys/block/{name}"

        # The size file is in 512-byte sectors regardless of the real sector size.
        sectors = read_first_line(f"{base}/size")
        if not sectors or not sectors.isdigit():
            continue
        size_gb = int(sectors) * 512 / 1_000_000_000
        if size_gb < 0.1:
            continue

        found.append(
            {
                "name": f"/dev/{name}",
                "size_gb": round(size_gb, 1),
                "disk_type": _disk_type(name, base),
                "model": read_first_line(f"{base}/device/model") or "",
            }
        )
    return found


def _disk_type(name: str, base: str) -> str:
    """NVMe, SSD, or HDD.

    queue/rotational is the kernel's own answer: 1 means spinning platters.
    The name check comes first because an NVMe drive is a more specific answer
    than "SSD".
    """
    if name.startswith("nvme"):
        return "NVMe"
    rotational = read_first_line(f"{base}/queue/rotational")
    if rotational == "1":
        return "HDD"
    if rotational == "0":
        return "SSD"
    return "Unknown"


def gpus() -> list[dict]:
    """Graphics cards, read straight off the PCI bus.

    /sys/bus/pci/devices/*/class holds a six-digit class code; anything
    starting 0x03 drives a display. That gives the vendor with certainty and
    with no external command. lspci, when present, is used only to upgrade the
    numeric device id into a human-readable model name.
    """
    names_by_slot = _lspci_names()
    found = []

    for slot in list_dir("/sys/bus/pci/devices"):
        base = f"/sys/bus/pci/devices/{slot}"

        class_code = read_first_line(f"{base}/class") or ""
        if not class_code.startswith(_DISPLAY_CLASS_PREFIX):
            continue

        vendor_id = (read_first_line(f"{base}/vendor") or "").lower()
        device_id = (read_first_line(f"{base}/device") or "").lower()
        vendor = _PCI_VENDORS.get(vendor_id, "Unknown")

        # lspci is keyed on the short slot form (01:00.0), /sys on the long
        # one (0000:01:00.0).
        short_slot = slot.split(":", 1)[1] if slot.count(":") == 2 else slot
        name = names_by_slot.get(short_slot)

        if not name:
            # No lspci: say what is actually known rather than inventing a model.
            name = f"PCI device {vendor_id}:{device_id}"
            if not which("lspci"):
                name += "  (install pciutils for the model name)"

        found.append({"vendor": vendor, "name": name})

    return found


def _lspci_names() -> dict[str, str]:
    """Model names per PCI slot, if lspci happens to be installed.

    Never installs it. A missing lspci costs nicer names and nothing else.
    """
    if not which("lspci"):
        return {}

    # -mm quotes every field, which removes the guesswork the Rust version had
    # to do splitting on colons and hunting for square brackets.
    output = run("lspci", "-mm")
    if not output:
        return {}

    names: dict[str, str] = {}
    for line in output.splitlines():
        fields = _split_quoted(line)
        # slot, class, vendor, device, ...
        if len(fields) >= 4 and fields[1].lower().startswith(
            ("vga", "display", "3d")
        ):
            names[fields[0]] = fields[3]
    return names


def _split_quoted(line: str) -> list[str]:
    """Split an `lspci -mm` line into its quoted fields.

    Format: 01:00.0 "VGA compatible controller" "NVIDIA Corporation" "GA106" ...
    The slot is bare, everything after it is quoted.
    """
    fields: list[str] = []
    rest = line.strip()

    slot, _, rest = rest.partition(" ")
    fields.append(slot)

    while '"' in rest:
        _, _, rest = rest.partition('"')
        value, _, rest = rest.partition('"')
        fields.append(value)

    return fields


def drivers() -> list[dict]:
    """Loaded kernel modules from /proc/modules.

    Columns: name, size, use count, used-by list, state, address.
    State is "Live", "Loading", or "Unloading".
    """
    content = read_text("/proc/modules")
    if not content:
        return []

    found = []
    for line in content.splitlines():
        parts = line.split()
        if len(parts) >= 5:
            found.append({"name": parts[0], "status": parts[4]})
    return found


def network_cards() -> list[dict]:
    """Network interfaces and their MAC addresses from /sys/class/net.

    Reading sysfs rather than parsing `ip link` output means no dependency on
    iproute2 and no text parsing. Interfaces with a `device` symlink are backed
    by real hardware, which filters out loopback, bridges, and virtual
    interfaces without having to special-case them by name.
    """
    found = []
    for name in list_dir("/sys/class/net"):
        base = f"/sys/class/net/{name}"

        if not os.path.exists(f"{base}/device"):
            continue

        mac = read_first_line(f"{base}/address")
        if not mac or mac == "00:00:00:00:00:00":
            continue

        found.append({"name": name, "mac_address": mac})

    return found or _network_cards_from_ip()


def _network_cards_from_ip() -> list[dict]:
    """Fallback for systems where /sys/class/net is not available.

    This is the approach the Rust prototype used everywhere; here it only runs
    if sysfs told us nothing, which in practice means a container.
    """
    output = run("ip", "link", "show")
    if not output:
        return []

    found = []
    current: str | None = None
    for line in output.splitlines():
        if line[:1].isdigit():
            parts = line.split(":", 2)
            if len(parts) >= 2:
                name = parts[1].strip()
                current = None if name == "lo" else name
        elif line.strip().startswith("link/ether") and current:
            parts = line.split()
            if len(parts) >= 2:
                found.append({"name": current, "mac_address": parts[1]})
            current = None
    return found
