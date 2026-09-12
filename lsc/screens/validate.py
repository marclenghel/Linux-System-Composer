"""The validation screen — what your choices imply.

Milestone 3 changed what this screen is allowed to claim. It used to carry a
warning banner saying the check behind it was a placeholder, because it was: a
walk over three tuple fields is not a compatibility engine and pretending
otherwise would have been the kind of overstatement this project has tried to
avoid. The banner is gone because the engine is real.

What replaced it is a coverage line, for the same reason the banner existed. The
engine has rules that can only run once a machine has been read, and on a build
with no detection behind it roughly a third of them are skipped. "No problems
found" means something different depending on how many rules actually ran, so the
screen says which case you are in rather than letting a green tick imply more
than it knows.
"""

from __future__ import annotations

from typing import Any, Mapping

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Static

from lsc import content, engine
from lsc.data.catalog import component_name
from lsc.models import Build, Issue
from lsc.widgets.panel import panel

# Icon, colour, and the word used when counting. "note" rather than "info"
# because the count is pluralised and "2 infos" is not English.
_SEVERITY = {
    "error": ("✕", "$error", "error"),
    "warning": ("⚠", "$warning", "warning"),
    "info": ("i", "$text-accent", "note"),
}


class ValidateScreen(VerticalScroll):
    """Runs the compatibility engine over the build and explains what it found."""

    def __init__(self, build: Build) -> None:
        super().__init__()
        self.build = build
        # Set by the app once the hardware scan comes back. Until then the
        # hardware-conditioned rules do not run, and the coverage line says so.
        self.hardware: Mapping[str, Any] | None = None
        self.hardware_is_real = False

    def compose(self) -> ComposeResult:
        yield Static("", id="verdict", classes="verdict")
        yield Static("", id="coverage", classes="banner")
        yield Static("", id="implied", classes="intro")
        yield VerticalScroll(id="issues")

    def on_mount(self) -> None:
        self.refresh_view()

    def set_hardware(self, profile: Mapping[str, Any], is_real: bool) -> None:
        """Hand the screen a machine, so the hardware rules can run.

        Called by the app when detection finishes. `is_real` is not decoration:
        passing the sample profile with it set would make the engine reason about
        a machine nobody looked at.
        """
        self.hardware = profile
        self.hardware_is_real = is_real
        self.refresh_view()

    def refresh_view(self) -> None:
        """Re-run the engine and redraw. Called whenever the build changes."""
        issues = engine.check(self.build, self.hardware, self.hardware_is_real)
        counts = engine.summarise(issues)
        coverage = engine.coverage(self.build, self.hardware_is_real)

        self.query_one("#verdict", Static).update(_verdict(issues, counts))

        banner = self.query_one("#coverage", Static)
        banner.set_classes(
            "banner banner-ok" if coverage.hardware_was_used else "banner banner-warn"
        )
        banner.update(_coverage_line(coverage))

        # Hidden rather than left blank: an empty line with a margin under it
        # reads as a rendering bug on the builds that imply nothing, which is
        # most of them.
        implied = self.query_one("#implied", Static)
        implied.display = bool(coverage.implied)
        implied.update(_implied_line(coverage))

        container = self.query_one("#issues", VerticalScroll)
        container.remove_children()
        if not issues:
            container.mount(panel("All clear", content.VALIDATE_CLEAN, classes="panel ok"))
            return
        container.mount_all(_issue_panel(issue) for issue in issues)


def _verdict(issues: list[Issue], counts: dict[str, int]) -> str:
    """The one-line headline above the list."""
    if not issues:
        return "[b $text-success]✓  This build holds together.[/]"

    installable = engine.build_is_installable(issues)
    headline = (
        "[b $text-warning]⚠  Installable, with notes.[/]"
        if installable
        else "[b $text-error]✕  This build will not install as it stands.[/]"
    )
    parts = [
        f"[{_SEVERITY[severity][1]}]{count} {_SEVERITY[severity][2]}"
        f"{'s' if count != 1 else ''}[/]"
        for severity, count in counts.items()
        if count
    ]
    return f"{headline}    [$text-muted]{'  ·  '.join(parts)}[/]"


def _coverage_line(coverage: engine.Coverage) -> str:
    """How much of the rule set ran, and why the rest did not."""
    if coverage.hardware_was_used:
        return (
            f"✓  {content.VALIDATE_COVERAGE_FULL}"
            f"  [$text-muted]{coverage.rules_evaluated} of "
            f"{coverage.rules_total} rules.[/]"
        )
    return (
        f"⚠  {content.VALIDATE_COVERAGE_PARTIAL}"
        f"  [$text-muted]{coverage.rules_evaluated} of {coverage.rules_total} "
        f"rules ran; {coverage.rules_skipped} need a hardware reading.[/]"
    )


def _implied_line(coverage: engine.Coverage) -> str:
    """The components nobody chose.

    Worth its own line rather than being buried in the issue list: "there is a
    hardened kernel in your build and you never asked for one" is the single most
    surprising thing the engine can tell you.
    """
    if not coverage.implied:
        return ""
    parts = [
        f"[b]{component_name(component_id)}[/b] "
        f"[$text-muted](required by {component_name(chain[0])})[/]"
        for component_id, chain in coverage.implied.items()
    ]
    return f"[$text-muted]{content.VALIDATE_IMPLIED}[/]  " + ",  ".join(parts)


def _issue_panel(issue: Issue) -> Static:
    """One issue as a bordered panel.

    The severity goes on as a CSS class rather than being styled here, so the
    colours all live in one place in app.tcss.
    """
    icon, _colour, _label = _SEVERITY.get(issue.severity, ("•", "$text-muted", "note"))
    body = f"{issue.detail}\n\n[$text-muted]Fix[/]  {issue.fix}"
    if issue.rule_id:
        body += f"\n[$text-muted italic]rule: {issue.rule_id}[/]"
    return panel(f"{icon}  {issue.title}", body, classes=f"panel issue {issue.severity}")
