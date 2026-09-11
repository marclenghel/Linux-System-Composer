"""Hardware detection on macOS.

Sources:

    os / kernel     sw_vers, uname -r (the Darwin version, not the macOS one)
    cpu / ram       sysctl
    model           system_profiler SPHardwareDataType
    disks           system_profiler SPStorageDataType
    gpus            system_profiler SPDisplaysDataType
    drivers         kextstat
    network         networksetup -listallhardwareports

system_profiler is asked for JSON rather than its default text layout, which
removes the line-by-line "does this line contain a colon" parsing the Rust
prototype needed. It is slow — a couple of seconds — so each data type is
requested once and only when needed.

A note the prototype also made: kextstat is deprecated from macOS 12 onward,
where Apple moved to System Extensions. When it is missing, the driver list
comes back empty rather than the reading failing.
"""

from __future__ import annotations

import json
from typing import Any

from lsc.detect._shell import after_colon, run
from lsc.detect.windows import vendor_from_name


def os_name() -> str:
    """e.g. "macOS 14.4.1". sw_vers is the user-facing version."""
    name = run("sw_vers", "-productName") or "macOS"
    version = run("sw_vers", "-productVersion") or ""
    return f"{name} {version}".strip()


def kernel() -> str:
    """The Darwin kernel version, which is not the macOS version.

    macOS 14 reports Darwin 23.x. Both numbers are useful and they are not
    interchangeable, so this reports the kernel and os_name reports the other.
    """
    return run("uname", "-r") or "Unknown"


def cpu() -> dict:
    brand = run("sysctl", "-n", "machdep.cpu.brand_string") or "Unknown"
    cores = run("sysctl", "-n", "hw.logicalcpu") or "0"
    return {"brand": brand.strip(), "cores": int(cores) if cores.isdigit() else 0}


def ram_gb() -> float:
    total = run("sysctl", "-n", "hw.memsize")
    if total and total.isdigit():
        return round(int(total) / (1024**3), 2)
    return 0.0


def motherboard() -> str:
    """The Mac model.

    Macs have no separately identifiable motherboard, so the model identifier
    is the closest equivalent and the more useful answer anyway.
    """
    data = _profiler("SPHardwareDataType")
    for item in data:
        for key in ("machine_model", "machine_name"):
            if item.get(key):
                return str(item[key])
    return "Apple Mac (model unknown)"


def disks() -> list[dict]:
    found = []
    for item in _profiler("SPStorageDataType"):
        size = item.get("size_in_bytes")
        if not isinstance(size, (int, float)) or size < 100_000_000:
            continue

        medium = item.get("physical_drive", {})
        found.append(
            {
                "name": str(item.get("_name", "Unknown")),
                "size_gb": round(float(size) / 1_000_000_000, 1),
                "disk_type": _disk_type(medium),
            }
        )
    return found


def _disk_type(physical_drive: dict[str, Any]) -> str:
    protocol = str(physical_drive.get("device_name", "")).upper()
    medium = str(physical_drive.get("medium_type", "")).lower()

    if "NVME" in protocol or "APPLE SSD" in protocol:
        return "NVMe"
    if "ssd" in medium or "solid" in medium:
        return "SSD"
    if "rotational" in medium:
        return "HDD"
    return "Unknown"


def gpus() -> list[dict]:
    found = []
    for item in _profiler("SPDisplaysDataType"):
        name = item.get("sppci_model") or item.get("_name")
        if not name:
            continue
        found.append({"vendor": vendor_from_name(str(name)), "name": str(name)})
    return found


def drivers() -> list[dict]:
    """Loaded kernel extensions.

    kextstat columns: Index Refs Address Size Wired Name (Version) <Linked>.
    The name is at index 5.
    """
    output = run("kextstat", "-l")
    if not output:
        return []

    found = []
    for line in output.splitlines():
        parts = line.split()
        if len(parts) >= 6:
            found.append({"name": parts[5], "status": "Loaded"})
    return found


def network_cards() -> list[dict]:
    """Interfaces from networksetup.

    Output repeats in blocks:

        Hardware Port: Wi-Fi
        Device: en0
        Ethernet Address: a4:c3:f0:11:22:33

    Interfaces with no address report "(null)" and are skipped.
    """
    output = run("networksetup", "-listallhardwareports")
    if not output:
        return []

    found = []
    device: str | None = None
    for line in output.splitlines():
        lowered = line.lower()
        if lowered.startswith("device:"):
            device = after_colon(line)
        elif lowered.startswith("ethernet address:") and device:
            mac = after_colon(line)
            if mac and mac != "(null)":
                found.append({"name": device, "mac_address": mac})
            device = None
    return found


def _profiler(data_type: str) -> list[dict[str, Any]]:
    """Ask system_profiler for one data type as JSON.

    Returns an empty list on any failure, which keeps a missing or changed
    data type from taking down the whole reading.
    """
    output = run("system_profiler", "-json", data_type, timeout=30.0)
    if not output:
        return []
    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        return []

    items = data.get(data_type, []) if isinstance(data, dict) else []
    return [item for item in items if isinstance(item, dict)]
