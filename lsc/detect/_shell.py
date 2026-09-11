"""Running external commands and reading system files, safely.

Every detection path goes through here so the failure behaviour is identical
everywhere: a missing command, a permission error, or a hung process produces
None, never an exception and never a hang. Detection is best-effort by nature —
a laptop with no `ip` command should still report its CPU.
"""

from __future__ import annotations

import base64
import os
import shutil
import subprocess
import sys

# Detection runs in a UI thread. Nothing here may block for long, so every
# subprocess gets a hard ceiling. WMI queries on Windows are the slow ones.
DEFAULT_TIMEOUT = 20.0

# Stops a console window flashing over the TUI on every subprocess call.
_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def run(command: str, *args: str, timeout: float = DEFAULT_TIMEOUT) -> str | None:
    """Run a command and return its stdout, or None if anything went wrong.

    "Anything" genuinely means anything: command not found, non-zero exit,
    timeout, or output that is not decodable.
    """
    try:
        completed = subprocess.run(
            [command, *args],
            capture_output=True,
            timeout=timeout,
            creationflags=_NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    if completed.returncode != 0:
        return None

    # errors="replace" rather than strict: a single undecodable byte in a
    # device name should not lose the whole reading.
    return completed.stdout.decode("utf-8", errors="replace").strip()


def powershell(script: str, timeout: float = DEFAULT_TIMEOUT) -> str | None:
    """Run one PowerShell script and return its stdout.

    Starting PowerShell costs the better part of a second, so callers are
    expected to ask for everything they need in a single script rather than
    making one call per field — which is what the Rust prototype did, and why
    it took several seconds to produce a report.

    The script is passed base64-encoded via -EncodedCommand. That looks like
    an odd way to run a command, and it is the reliable one: a multi-line
    script handed to -Command has to survive Windows command line quoting
    rules and PowerShell's own parser, and quoting bugs there fail in ways
    that are very hard to read.
    """
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    return run(
        "powershell",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-EncodedCommand",
        encoded,
        timeout=timeout,
    )


def which(name: str) -> bool:
    """True if a command exists on PATH.

    shutil.which only looks it up rather than executing it, so unlike the Rust
    prototype's `cmd --version` probe this cannot be fooled by a program that
    exists but does not understand --version.
    """
    return shutil.which(name) is not None


def read_text(path: str) -> str | None:
    """Read a small system file, or None if it is missing or unreadable.

    Used for /proc and /sys, where files appear and disappear depending on
    kernel configuration and where reads can fail even when the path exists.
    """
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.read().strip()
    except OSError:
        return None


def read_first_line(path: str) -> str | None:
    content = read_text(path)
    if content is None:
        return None
    return content.splitlines()[0].strip() if content else None


def list_dir(path: str) -> list[str]:
    """Entries in a directory, or an empty list. Sorted for stable output."""
    try:
        return sorted(os.listdir(path))
    except OSError:
        return []


def after_colon(line: str) -> str:
    """The part of "Key : Value" after the first colon.

    Splitting on the *first* colon matters: a MAC address is mostly colons, so
    splitting on all of them destroys the value.
    """
    _, separator, value = line.partition(":")
    return value.strip() if separator else ""
