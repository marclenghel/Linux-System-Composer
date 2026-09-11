"""Hardware detection — the Python port of the Rust prototype.

    legacy/rust-hardware-detect/src/main.rs   ->   this package

`detect()` produces exactly the dict shape the Hardware screen already
consumed as sample data, so wiring this in changed no screen code.

Design rules, all of them learned from the prototype:

  * Never fail. A machine with no `ip`, no lspci, no PowerShell, or a locked
    down /proc should still report whatever it can. Every field falls back to
    "Unknown" rather than raising, because a partial reading is useful and an
    exception is not.
  * Never modify the system. The prototype ran `sudo pacman -S pciutils` when
    lspci was missing; nothing here installs, writes, or elevates.
  * Never block for long. This runs from a UI thread, so every subprocess has
    a timeout and the slow platform (Windows) makes one call rather than five.
"""

from __future__ import annotations

import platform
import sys
import time
from typing import Any

SOURCE_SAMPLE = "sample"
SOURCE_DETECTED = "detected"


def detect() -> dict[str, Any]:
    """Read this machine and return a hardware report.

    The returned dict carries `source` and `detected_at` so the interface can
    state plainly where the numbers came from — a report should never be
    mistakable for the fixture it replaced.
    """
    report = _blank_report()

    try:
        if sys.platform == "win32":
            report.update(_detect_windows())
        elif sys.platform == "darwin":
            report.update(_detect_macos())
        else:
            report.update(_detect_linux())
    except Exception as error:  # noqa: BLE001
        # Detection touches a lot of loosely specified system interfaces. A
        # surprise on one unusual machine must degrade the report, never crash
        # the application, so the reason is recorded and the blank report with
        # whatever was filled in is returned.
        report["error"] = f"{type(error).__name__}: {error}"

    # Architecture comes from the interpreter on every platform: it is the one
    # field that needs no system call at all.
    report["cpu"]["arch"] = normalise_arch(platform.machine())
    report["source"] = SOURCE_DETECTED
    report["detected_at"] = time.strftime("%H:%M:%S")
    return report


# Windows and macOS spell the same architectures differently from Linux. The
# composer targets Linux, so everything is reported in Linux's spelling — the
# one that will appear in package names and in `pacman -Q` output.
_ARCH_NAMES = {
    "amd64": "x86_64",
    "x86_64": "x86_64",
    "arm64": "aarch64",
    "aarch64": "aarch64",
    "i386": "i686",
    "i686": "i686",
}


def normalise_arch(machine: str) -> str:
    """Report an architecture the way Linux names it."""
    return _ARCH_NAMES.get(machine.lower(), machine.lower() or "unknown")


def _blank_report() -> dict[str, Any]:
    """Every field the report promises, with empty values.

    Building the full shape up front means a platform module that fails
    halfway still returns something the screens can render.
    """
    return {
        "source": SOURCE_DETECTED,
        "os": "Unknown",
        "kernel": "Unknown",
        "cpu": {"brand": "Unknown", "cores": 0, "arch": "unknown"},
        "ram": {"total_gb": 0.0},
        "motherboard": "Unknown",
        "disks": [],
        "gpus": [],
        "drivers": [],
        "network_cards": [],
    }


def _detect_linux() -> dict[str, Any]:
    from lsc.detect import linux

    return {
        "os": linux.os_name(),
        "kernel": linux.kernel(),
        "cpu": linux.cpu(),
        "ram": {"total_gb": round(linux.ram_gb(), 2)},
        "motherboard": linux.motherboard(),
        "disks": linux.disks(),
        "gpus": linux.gpus(),
        "drivers": linux.drivers(),
        "network_cards": linux.network_cards(),
    }


def _detect_macos() -> dict[str, Any]:
    from lsc.detect import macos

    return {
        "os": macos.os_name(),
        "kernel": macos.kernel(),
        "cpu": macos.cpu(),
        "ram": {"total_gb": macos.ram_gb()},
        "motherboard": macos.motherboard(),
        "disks": macos.disks(),
        "gpus": macos.gpus(),
        "drivers": macos.drivers(),
        "network_cards": macos.network_cards(),
    }


def _detect_windows() -> dict[str, Any]:
    from lsc.detect import windows

    data = windows.probe()
    if data is None:
        return {"os": platform.system(), "kernel": platform.version()}
    return windows.parse(data)
