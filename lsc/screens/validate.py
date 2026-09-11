"""The validation screen — what your choices imply.

The banner is not decoration. Everything shown here comes from checks.py, which
is a forty-line walk over three tuple fields, and calling that a compatibility
engine would be a lie. Saying so on screen costs one line and keeps the project
honest about where the remaining work is.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Static

from lsc import checks, content
from lsc.models import Build, Issue
from lsc.widgets.panel import panel

_SEVERITY = {
    "error": ("✕", "$error", "error"),
    "warning": ("⚠", "$warning", "warning"),
    "info": ("i", "$text-accent", "info"),
}


class ValidateScreen(VerticalScroll):
    """Runs the placeholder check over the build and lists what it found."""

    def __init__(self, build: Build) -> None:
        super().__init__()
        self.build = build

    def compose(self) -> ComposeResult:
        yield Static(f"⚠  {content.VALIDATE_PLACEHOLDER_BANNER}", classes="banner banner-warn")
        yield Static("", id="verdict", classes="verdict")
        yield VerticalScroll(id="issues")

    def on_mount(self) -> None:
        self.refresh_view()

    def refresh_view(self) -> None:
        """Re-run the check and redraw. Called whenever the build changes."""
        issues = checks.check(self.build)
        counts = checks.summarise(issues)

        self.query_one("#verdict", Static).update(_verdict(issues, counts))

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

    installable = checks.build_is_installable(issues)
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


def _issue_panel(issue: Issue) -> Static:
    """One issue as a bordered panel.

    The severity goes on as a CSS class rather than being styled here, so the
    colours all live in one place in app.tcss.
    """
    icon, _colour, _label = _SEVERITY.get(issue.severity, ("•", "$text-muted", "note"))
    body = f"{issue.detail}\n\n[$text-muted]Fix[/]  {issue.fix}"
    return panel(f"{icon}  {issue.title}", body, classes=f"panel issue {issue.severity}")
