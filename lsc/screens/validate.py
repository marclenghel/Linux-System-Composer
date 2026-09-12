"""The validation screen — what your choices imply.

The placeholder banner that stood here through milestones 1 and 2 is gone: the
engine behind this screen is real now, and a warning saying otherwise would be
its own kind of dishonesty. What took its place is a scope note, which is a
different thing — it says what the engine does check and admits what it does
not, without apologising for being a stub it no longer is.

The part worth looking at is the "Not checked" panel. Rules that depend on the
machine cannot reach an answer until the machine has been read, and this screen
lists them rather than passing over them. A check that was skipped silently
looks exactly like a check that passed.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Static

from lsc import checks, content
from lsc.data.catalog import component_name
from lsc.engine import Report
from lsc.models import Build, Issue
from lsc.widgets.panel import panel

_SEVERITY = {
    "error": ("✕", "$text-error", "error"),
    "warning": ("⚠", "$text-warning", "warning"),
    "info": ("i", "$text-accent", "note"),
}


class ValidateScreen(VerticalScroll):
    """Runs the compatibility engine over the build and explains what it found."""

    def __init__(self, build: Build) -> None:
        super().__init__()
        self.build = build
        # Filled in by the app when a hardware scan finishes. None means
        # nothing has read this machine, which the engine treats as "unknown"
        # rather than as "nothing there".
        self.hardware_profile: dict | None = None

    def compose(self) -> ComposeResult:
        yield Static(f"i  {content.VALIDATE_SCOPE_NOTE}", classes="banner banner-note")
        yield Static("", id="verdict", classes="verdict")
        yield VerticalScroll(id="issues")

    def on_mount(self) -> None:
        self.refresh_view()

    def refresh_view(self) -> None:
        """Re-run the engine and redraw. Called whenever the build changes."""
        report = checks.evaluate(self.build, self.hardware_profile)

        self.query_one("#verdict", Static).update(_verdict(report))

        container = self.query_one("#issues", VerticalScroll)
        container.remove_children()

        if report.issues:
            container.mount_all(_issue_panel(issue) for issue in report.issues)
        else:
            container.mount(panel("All clear", content.VALIDATE_CLEAN, classes="panel ok"))

        if report.unchecked:
            container.mount(_unchecked_panel(report))

    def set_hardware(self, profile: dict | None) -> None:
        """Take a finished hardware reading and re-evaluate against it."""
        self.hardware_profile = profile
        self.refresh_view()


def _verdict(report: Report) -> str:
    """The one-line headline above the list."""
    counts = report.counts()
    parts = [
        f"[{_SEVERITY[severity][1]}]{count} {_SEVERITY[severity][2]}"
        f"{'s' if count != 1 else ''}[/]"
        for severity, count in counts.items()
        if count
    ]

    if not report.issues:
        headline = "[b $text-success]✓  This build holds together.[/]"
    elif report.installable():
        headline = "[b $text-warning]⚠  Installable, with notes.[/]"
    else:
        headline = "[b $text-error]✕  This build will not install as it stands.[/]"

    # Saying how many rules ran is not decoration: it is the difference between
    # "nothing is wrong" and "nothing was looked at".
    parts.append(f"[$text-muted]{report.rules_evaluated} rules[/]")
    if report.unchecked:
        parts.append(f"[$text-muted]{len(report.unchecked)} not checked[/]")

    return f"{headline}    [$text-muted]{'  ·  '.join(parts)}[/]"


def _issue_panel(issue: Issue) -> Static:
    """One issue as a bordered panel.

    The severity goes on as a CSS class rather than being styled here, so the
    colours all live in one place in app.tcss.
    """
    icon, _colour, _label = _SEVERITY.get(issue.severity, ("•", "$text-muted", "note"))

    lines = [issue.detail, "", f"[$text-muted]Fix[/]  {issue.fix}"]
    if issue.suggestion is not None:
        lines.append(
            f"[$text-muted]Apply[/]  set [b]{checks.category_name(issue.suggestion.category_id)}[/b] "
            f"to [b]{component_name(issue.suggestion.component_id)}[/b]"
        )
    if issue.reference:
        lines.append(f"[$text-muted]Read[/]  {issue.reference}")
    # The rule id is what makes an issue traceable back to the line of data
    # that produced it, which matters when someone asks "why is it saying this".
    if issue.rule_id:
        lines.append(f"[$text-muted italic]rule: {issue.rule_id}[/]")

    return _titled(
        f"{icon}  {issue.title}", "\n".join(lines), f"panel issue {issue.severity}"
    )


def _unchecked_panel(report: Report) -> Static:
    """The checks the engine could not make, and what would let it make them."""
    lines = [content.VALIDATE_UNCHECKED_INTRO, ""]
    for rule_id, needs in report.unchecked:
        lines.append(f"  [$text-muted]·[/] [b]{rule_id}[/b]  [$text-muted]needs {needs}[/]")
    if not report.hardware_known:
        lines.append("")
        lines.append(f"[$text-muted]{content.VALIDATE_SCAN_HINT}[/]")
    return _titled(content.VALIDATE_UNCHECKED_TITLE, "\n".join(lines), "panel unchecked")


def _titled(title: str, body: str, classes: str) -> Static:
    widget = Static(body, classes=classes)
    widget.border_title = title
    return widget
