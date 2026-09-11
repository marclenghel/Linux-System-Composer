"""The hardware screen — what we are building on.

Everything displayed here comes from data/hardware.py, which currently returns
sample data. The banner at the top says so in as many words: a demo that lets
people mistake a fixture for a real reading is not a demo, it is a lie with a
progress bar.
"""

from __future__ import annotations

from typing import Any

from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import DataTable, Static

from lsc import content
from lsc.data import hardware
from lsc.data.catalog import CATEGORIES_BY_ID, COMPONENTS_BY_ID
from lsc.widgets.panel import panel


class HardwareScreen(VerticalScroll):
    """Read-only view of the current hardware profile."""

    def compose(self) -> ComposeResult:
        profile = hardware.load_profile()

        if profile.get("source") == hardware.SOURCE_SAMPLE:
            yield Static(f"⚠  {content.HARDWARE_SAMPLE_BANNER}", classes="banner banner-warn")

        yield Static(content.HARDWARE_INTRO, classes="intro")

        yield panel("System", _system_body(profile))

        with Horizontal(classes="two-up"):
            yield _table("disks", "Storage", ("Device", "Size", "Type"))
            yield _table("gpus", "Graphics", ("Vendor", "Model"))

        with Horizontal(classes="two-up"):
            yield _table("network", "Network", ("Interface", "MAC address"))
            yield panel("Loaded modules", _drivers_body(profile))

        yield panel("What this implies for the build", _suggestions_body(profile))

    def on_mount(self) -> None:
        profile = hardware.load_profile()

        disks = self.query_one("#disks", DataTable)
        for disk in profile.get("disks", []):
            disks.add_row(
                disk["name"], f"{disk['size_gb']:,.1f} GB", disk["disk_type"]
            )

        gpus = self.query_one("#gpus", DataTable)
        for gpu in profile.get("gpus", []):
            gpus.add_row(gpu["vendor"], gpu["name"])

        network = self.query_one("#network", DataTable)
        for card in profile.get("network_cards", []):
            network.add_row(card["name"], card["mac_address"])


# ── building blocks ───────────────────────────────────────────────────────────


def _table(table_id: str, title: str, columns: tuple[str, ...]) -> DataTable:
    table = DataTable(id=table_id, classes="panel")
    table.border_title = title
    table.cursor_type = "row"
    table.zebra_stripes = True
    table.add_columns(*columns)
    return table


def _system_body(profile: dict[str, Any]) -> str:
    cpu = profile.get("cpu", {})
    ram = profile.get("ram", {})
    rows = (
        ("Operating system", profile.get("os", "unknown")),
        ("Kernel", profile.get("kernel", "unknown")),
        ("Processor", f"{cpu.get('brand', 'unknown')}"),
        ("Cores / arch", f"{cpu.get('cores', '?')} logical · {cpu.get('arch', '?')}"),
        ("Memory", f"{ram.get('total_gb', 0):.1f} GB"),
        ("Motherboard", profile.get("motherboard", "unknown")),
    )
    return "\n".join(f"[$text-muted]{label:<18}[/][b]{value}[/b]" for label, value in rows)


def _drivers_body(profile: dict[str, Any]) -> str:
    drivers = profile.get("drivers", [])
    if not drivers:
        return "[$text-muted]None reported.[/]"

    lines = [f"[$text-muted]{len(drivers)} kernel modules loaded[/]", ""]
    for driver in drivers[:8]:
        lines.append(f"  [b]{driver['name']:<18}[/b][$success]{driver['status']}[/]")
    if len(drivers) > 8:
        lines.append(f"  [$text-muted]… and {len(drivers) - 8} more[/]")
    return "\n".join(lines)


def _suggestions_body(profile: dict[str, Any]) -> str:
    """Show the detection-to-composition seam.

    These are produced by a crude vendor-string match, not by a compatibility
    engine, and the closing line says so rather than letting the neat formatting
    imply more intelligence than there is.
    """
    suggestions = hardware.suggestions_for(profile)
    if not suggestions:
        return "[$text-muted]Nothing to suggest from this profile.[/]"

    lines = []
    for category_id, component_id, reason in suggestions:
        category = CATEGORIES_BY_ID.get(category_id)
        component = COMPONENTS_BY_ID.get(component_id)
        if category is None or component is None:
            continue
        lines.append(
            f"[$text-accent]→[/] [$text-muted]{category.name}:[/] [b]{component.name}[/b]\n"
            f"   [$text-muted]{reason}[/]"
        )

    lines.append("")
    lines.append(
        "[$text-muted italic]Matched on vendor strings alone. Milestone 3 replaces "
        "this with real rules.[/]"
    )
    return "\n".join(lines)
