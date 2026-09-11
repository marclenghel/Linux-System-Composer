"""The landing screen: what this is, how to drive it, and what is actually done.

The status section is the most important part of this screen. A project that
overstates how finished it is teaches nobody anything, and the gap between
"the interface exists" and "the system works" is the interesting part of the
story.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Static

from lsc import content
from lsc.widgets.panel import Box, bullet, panel

# Roadmap state -> (colour variable, the word shown next to the milestone).
_STATUS_STYLES = {
    "done": ("$success", "done"),
    "next": ("$warning", "next"),
    "planned": ("$text-muted", "planned"),
}


class OverviewScreen(VerticalScroll):
    """Scrollable introduction to the project."""

    def compose(self) -> ComposeResult:
        yield Static(_hero(), classes="hero")

        with Horizontal(classes="two-up"):
            yield panel("What this is", content.WHAT_THIS_IS)
            yield panel("Getting around", content.HOW_TO_USE)

        yield Box(
            content.STATUS_TITLE,
            Static("[b $text-success]Working now[/]", classes="bullet-heading"),
            *(bullet("✓", "$success", item) for item in content.STATUS_DONE),
            Static("[b $text-warning]Not built yet[/]", classes="bullet-heading spaced"),
            *(bullet("○", "$warning", item) for item in content.STATUS_NOT_DONE),
        )

        yield Box(
            "Roadmap",
            *(_milestone(*entry) for entry in content.ROADMAP),
        )


def _hero() -> str:
    return f"[$text-accent]{content.LOGO}[/]\n  [b]{content.TAGLINE}[/b]"


def _milestone(number: str, title: str, state: str, detail: str) -> Horizontal:
    colour, label = _STATUS_STYLES[state]
    return bullet(
        number,
        colour,
        f"[b]{title}[/b]  [{colour}]({label})[/]\n[$text-muted]{detail}[/]",
    )
