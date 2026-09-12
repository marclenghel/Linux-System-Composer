"""The hardware screen — what we are building on.

The screen draws the sample profile immediately, then scans the real machine
in a background thread and swaps the result in when it arrives. Detection
takes a few seconds on Windows, and an interface that freezes for three
seconds on startup reads as broken even when it is working.

The banner always says which of the two you are looking at. That mattered when
the numbers were a fixture, and it matters more now that they are real: at a
glance you should never be unsure whether the RTX 3060 on screen is in this
machine or in an example.
"""

from __future__ import annotations

from typing import Any

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.message import Message
from textual.widgets import Button, DataTable, Static

from lsc import checks, content
from lsc.data import hardware
from lsc.data.catalog import CATEGORIES_BY_ID, COMPONENTS_BY_ID
from lsc.models import Build
from lsc.widgets.panel import panel


class HardwareScreen(VerticalScroll):
    """Live view of the machine, with the sample profile as a placeholder."""

    class Scanned(Message):
        """A reading finished. Carries it up so Validate can use it too.

        The hardware is read once, here, and everything that needs it is told.
        Two screens each running their own scan would double the cost and could
        disagree with each other about what machine they are on.
        """

        def __init__(self, profile: dict[str, Any]) -> None:
            self.profile = profile
            super().__init__()

    def __init__(self, build: Build) -> None:
        super().__init__()
        # The screen needs the build because its advice is the compatibility
        # engine's advice, and the engine reasons about a machine *and* a build
        # together - "use the open modules" only means something relative to
        # what is currently selected.
        self.build = build
        self.profile: dict[str, Any] = hardware.sample_profile()
        self.scanning = False

    # ── layout ────────────────────────────────────────────────────────────────
    #
    # Built once and updated in place. Rebuilding the widget tree on every scan
    # would lose scroll position and table state for no benefit.

    def compose(self) -> ComposeResult:
        yield Static("", id="hw-banner", classes="banner")

        with Horizontal(classes="preset-bar"):
            yield Button("Scan this machine", id="hw-scan", variant="primary")
            yield Static("", id="hw-scan-note", classes="preset-label wide")

        yield Static(content.HARDWARE_INTRO, classes="intro")
        yield panel("System", "", classes="panel")

        with Horizontal(classes="two-up"):
            yield _table("disks", "Storage", ("Device", "Size", "Type"))
            yield _table("gpus", "Graphics", ("Vendor", "Model"))

        with Horizontal(classes="two-up"):
            yield _table("network", "Network", ("Interface", "MAC address"))
            yield panel("Loaded modules", "", classes="panel")

        yield panel("What this implies for the build", "", classes="panel")

    def on_mount(self) -> None:
        # Draw the fixture straight away so the screen is never empty, then go
        # and read the real thing.
        self._apply(self.profile)
        self.scan()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "hw-scan":
            self.scan()

    def refresh_suggestions(self) -> None:
        """Re-run the advice against the current build.

        The hardware has not changed, but what it implies has: "use the open
        modules" stops being worth saying the moment the user selects them.
        Called by the app when Compose reports a change, so this screen never
        needs to know the composer exists.
        """
        self._panel("What this implies for the build").update(
            _suggestions_body(self.build, self.profile)
        )

    # ── scanning ──────────────────────────────────────────────────────────────

    @work(thread=True, exclusive=True)
    def scan(self) -> None:
        """Read the machine on a worker thread.

        exclusive=True means pressing the button twice cancels the first scan
        rather than running two at once.
        """
        self.app.call_from_thread(self._set_scanning, True)
        profile = hardware.detect_profile()
        self.app.call_from_thread(self._set_scanning, False)
        self.app.call_from_thread(self._apply, profile)
        self.app.call_from_thread(lambda: self.post_message(self.Scanned(profile)))

    def _set_scanning(self, scanning: bool) -> None:
        self.scanning = scanning
        button = self.query_one("#hw-scan", Button)
        button.disabled = scanning
        button.label = "Scanning…" if scanning else "Scan this machine"
        self.query_one("#hw-scan-note", Static).update(
            "[$text-muted]Reading CPU, memory, disks, graphics, drivers "
            "and network…[/]"
            if scanning
            else ""
        )

    # ── rendering ─────────────────────────────────────────────────────────────

    def _apply(self, profile: dict[str, Any]) -> None:
        """Put a profile on screen. Called for the fixture and for real scans."""
        self.profile = profile

        self._apply_banner(profile)
        self._panel("System").update(_system_body(profile))
        self._panel("Loaded modules").update(_drivers_body(profile))
        self._panel("What this implies for the build").update(
            _suggestions_body(self.build, profile)
        )

        disks = self.query_one("#disks", DataTable)
        disks.clear()
        for disk in profile.get("disks", []):
            disks.add_row(disk["name"], f"{disk['size_gb']:,.1f} GB", disk["disk_type"])

        gpus = self.query_one("#gpus", DataTable)
        gpus.clear()
        for gpu in profile.get("gpus", []):
            gpus.add_row(gpu["vendor"], gpu["name"])

        network = self.query_one("#network", DataTable)
        network.clear()
        for card in profile.get("network_cards", []):
            network.add_row(card["name"], card["mac_address"])

    def _apply_banner(self, profile: dict[str, Any]) -> None:
        banner = self.query_one("#hw-banner", Static)

        if profile.get("source") == hardware.SOURCE_SAMPLE:
            banner.set_classes("banner banner-warn")
            banner.update(f"⚠  {content.HARDWARE_SAMPLE_BANNER}")
            return

        # A real reading that partly failed is still a real reading; say what
        # went wrong rather than quietly showing "Unknown" everywhere.
        if profile.get("error"):
            banner.set_classes("banner banner-warn")
            banner.update(
                f"⚠  {content.HARDWARE_PARTIAL_BANNER}\n   {profile['error']}"
            )
            return

        banner.set_classes("banner banner-ok")
        banner.update(
            f"✓  {content.HARDWARE_DETECTED_BANNER} "
            f"[$text-muted]at {profile.get('detected_at', '—')}[/]"
        )

    def _panel(self, title: str) -> Static:
        """Find one of the titled panels by its border title.

        The panels have no ids because their titles are already unique, and a
        second identifier that has to be kept in step with the first is a bug
        waiting to happen.
        """
        for widget in self.query(Static):
            if getattr(widget, "border_title", None) == title:
                return widget
        raise LookupError(f"no panel titled {title!r}")


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
        ("Processor", cpu.get("brand", "unknown")),
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


def _suggestions_body(build: Build, profile: dict[str, Any]) -> str:
    """The detection-to-composition seam.

    This used to be a vendor-string match with a disclaimer printed underneath
    saying it was not a compatibility engine. It is now the compatibility
    engine: the same rules the Validate tab runs, narrowed to the ones that end
    in a change this screen could actually make to the build.
    """
    report = checks.evaluate(build, profile)
    actionable = [issue for issue in report.issues if issue.suggestion is not None]

    if not actionable:
        if not report.hardware_known:
            return f"[$text-muted]{content.HARDWARE_SUGGESTIONS_NEED_SCAN}[/]"
        return f"[$text-muted]{content.HARDWARE_SUGGESTIONS_EMPTY}[/]"

    lines = []
    for issue in actionable:
        category = CATEGORIES_BY_ID.get(issue.suggestion.category_id)
        component = COMPONENTS_BY_ID.get(issue.suggestion.component_id)
        if category is None or component is None:
            continue
        lines.append(
            f"[$text-accent]→[/] [$text-muted]{category.name}:[/] [b]{component.name}[/b]\n"
            f"   [$text-muted]{issue.title}[/]\n"
            f"   [$text-muted italic]rule: {issue.rule_id}[/]"
        )

    # Saying how many rules are still waiting on a reading is the honest
    # counterpart to showing the ones that fired.
    if report.unchecked and not report.hardware_known:
        lines.append("")
        lines.append(
            f"[$text-muted italic]{len(report.unchecked)} further rules need a "
            "reading of this machine before they can say anything.[/]"
        )
    return "\n".join(lines)
