"""Hardware detection on Windows.

The Rust prototype started PowerShell five separate times — kernel, board,
GPUs, drivers, network — and each start costs the better part of a second
before any work happens. This asks one script for everything and gets JSON
back, which turns several seconds into roughly one.

Two other changes from the prototype:

  * Get-CimInstance instead of Get-WmiObject. Same data; Get-WmiObject is
    deprecated and slower.
  * Output as JSON instead of `Format-List`. Format-List produces text laid
    out for a human to read, which then has to be parsed back — and it is the
    reason the prototype needed careful "split on the first colon" handling
    for MAC addresses.

Windows is not a target platform for the composer itself. It is supported
because it is where this project is being developed, and because being able to
read a real machine while writing the code is worth a great deal.
"""

from __future__ import annotations

import json
from typing import Any

from lsc.detect._shell import powershell

# One script, one process, everything at once. $ErrorActionPreference stops a
# single unavailable class from taking the whole reading down with it.
_PROBE = r"""
$ErrorActionPreference = 'SilentlyContinue'
$ProgressPreference = 'SilentlyContinue'

$os    = Get-CimInstance Win32_OperatingSystem
$sys   = Get-CimInstance Win32_ComputerSystem
$board = Get-CimInstance Win32_BaseBoard
$cpu   = Get-CimInstance Win32_Processor | Select-Object -First 1

# Get-PhysicalDisk knows about SSD vs HDD and NVMe vs SATA; Win32_DiskDrive
# does not, and reports every drive as "Fixed hard disk media". Prefer the
# former and fall back when the Storage module is unavailable.
$disks = @(Get-PhysicalDisk | ForEach-Object {
    [PSCustomObject]@{
        name  = $_.FriendlyName
        size  = [double]$_.Size
        media = [string]$_.MediaType
        bus   = [string]$_.BusType
    }
})
if ($disks.Count -eq 0) {
    $disks = @(Get-CimInstance Win32_DiskDrive | ForEach-Object {
        [PSCustomObject]@{
            name  = $_.Model
            size  = [double]$_.Size
            media = ''
            bus   = [string]$_.InterfaceType
        }
    })
}

[PSCustomObject]@{
    os        = [string]$os.Caption
    kernel    = [string]$os.Version
    cpu_brand = [string]$cpu.Name
    cpu_cores = [int]$cpu.NumberOfLogicalProcessors
    ram_bytes = [double]$sys.TotalPhysicalMemory
    board     = (@($board.Manufacturer, $board.Product) -join ' ').Trim()
    disks     = $disks
    gpus      = @(Get-CimInstance Win32_VideoController | ForEach-Object {
        [PSCustomObject]@{ name = [string]$_.Name }
    })
    drivers   = @(Get-CimInstance Win32_SystemDriver |
        Where-Object { $_.State -eq 'Running' } | ForEach-Object {
        [PSCustomObject]@{ name = [string]$_.Name; status = [string]$_.State }
    })
    nics      = @(Get-CimInstance Win32_NetworkAdapter |
        Where-Object { $_.PhysicalAdapter -and $_.MACAddress } | ForEach-Object {
        [PSCustomObject]@{ name = [string]$_.Name; mac = [string]$_.MACAddress }
    })
} | ConvertTo-Json -Depth 4 -Compress
"""


def probe() -> dict[str, Any] | None:
    """Run the single PowerShell script and return the parsed JSON."""
    output = powershell(_PROBE, timeout=45.0)
    if not output:
        return None
    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def parse(data: dict[str, Any]) -> dict[str, Any]:
    """Turn the probe's JSON into the report shape the rest of the app uses.

    Split out from `probe` so it can be tested against captured JSON on any
    platform, without a Windows machine or a PowerShell.
    """
    return {
        "os": data.get("os") or "Windows",
        "kernel": data.get("kernel") or "Unknown",
        "cpu": {
            "brand": (data.get("cpu_brand") or "Unknown").strip(),
            "cores": int(data.get("cpu_cores") or 0),
        },
        "ram": {"total_gb": _bytes_to_gib(data.get("ram_bytes"))},
        "motherboard": (data.get("board") or "").strip() or "Unknown",
        "disks": [_disk(entry) for entry in _as_list(data.get("disks"))],
        "gpus": [_gpu(entry) for entry in _as_list(data.get("gpus"))],
        "drivers": [
            {"name": entry.get("name", ""), "status": entry.get("status", "")}
            for entry in _as_list(data.get("drivers"))
            if entry.get("name")
        ],
        # Windows reports tunnel and offload adapters as physical. The ones
        # with an all-zero MAC are not real interfaces by any reading, so they
        # go; named virtual adapters (VPN clients and the like) are kept,
        # because filtering those on name guesses would be worse than showing
        # them.
        "network_cards": [
            {"name": entry.get("name", ""), "mac_address": _format_mac(entry["mac"])}
            for entry in _as_list(data.get("nics"))
            if entry.get("mac") and not _is_blank_mac(entry["mac"])
        ],
    }


# ── field helpers ─────────────────────────────────────────────────────────────


def _as_list(value: Any) -> list[dict[str, Any]]:
    """Normalise ConvertTo-Json's handling of collections.

    PowerShell unwraps a single-element array into a bare object, so a machine
    with one GPU and a machine with two produce different JSON shapes for the
    same field. Both arrive here as a list.
    """
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        return [value]
    return []


def _is_blank_mac(mac: str) -> bool:
    """True for 00:00:00:00:00:00, which means "no interface here"."""
    return set(str(mac).replace(":", "").replace("-", "")) <= {"0"}


def _format_mac(mac: str) -> str:
    """Lower-case, colon-separated — the form Linux and macOS report.

    Windows uses upper case and sometimes hyphens. Normalising here means the
    Network table looks the same wherever the reading was taken.
    """
    return str(mac).replace("-", ":").lower()


def _bytes_to_gib(value: Any) -> float:
    try:
        return round(float(value) / (1024**3), 2)
    except (TypeError, ValueError):
        return 0.0


def _disk(entry: dict[str, Any]) -> dict[str, Any]:
    try:
        size_gb = round(float(entry.get("size") or 0) / 1_000_000_000, 1)
    except (TypeError, ValueError):
        size_gb = 0.0

    return {
        "name": (entry.get("name") or "Unknown").strip(),
        "size_gb": size_gb,
        "disk_type": _disk_type(entry),
    }


def _disk_type(entry: dict[str, Any]) -> str:
    """NVMe beats SSD beats HDD.

    BusType is checked first because "NVMe" is a more useful answer than the
    "SSD" that MediaType would give for the same drive.
    """
    bus = str(entry.get("bus") or "").upper()
    media = str(entry.get("media") or "").upper()

    if "NVME" in bus:
        return "NVMe"
    if "SSD" in media or media == "4":
        return "SSD"
    if "HDD" in media or media == "3":
        return "HDD"
    if "USB" in bus:
        return "USB"
    return "Unknown"


def _gpu(entry: dict[str, Any]) -> dict[str, str]:
    name = (entry.get("name") or "Unknown").strip()
    return {"vendor": vendor_from_name(name), "name": name}


def vendor_from_name(name: str) -> str:
    """Guess the vendor from a marketing name.

    Necessary on Windows and macOS, where what you get back is a product name
    rather than a PCI vendor id. On Linux the vendor id is read directly and
    this guessing is not needed at all.
    """
    lowered = name.lower()
    if "nvidia" in lowered or "geforce" in lowered or "quadro" in lowered:
        return "NVIDIA"
    if "amd" in lowered or "radeon" in lowered or "advanced micro" in lowered:
        return "AMD"
    if "intel" in lowered:
        return "Intel"
    if "apple" in lowered:
        return "Apple"
    if any(word in lowered for word in ("virtualbox", "vmware", "hyper-v", "virtio")):
        return "Virtual"
    return "Unknown"
