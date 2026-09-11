"""Bordered boxes and hanging-indent bullets — used often enough to share."""

from __future__ import annotations

from textual.containers import Horizontal, Vertical
from textual.widget import Widget
from textual.widgets import Static


def panel(title: str, body: str, classes: str = "panel") -> Static:
    """A titled box holding a single block of text.

    `border_title` has to be set on the instance rather than passed to the
    constructor, which is the only reason this helper exists.
    """
    widget = Static(body, classes=classes)
    widget.border_title = title
    return widget


class Box(Vertical):
    """A titled box that holds other widgets rather than one string."""

    def __init__(self, title: str, *children: Widget, classes: str = "panel") -> None:
        super().__init__(*children, classes=classes)
        self._title = title

    def on_mount(self) -> None:
        self.border_title = self._title


def bullet(marker: str, marker_style: str, text: str) -> Horizontal:
    """One list item whose wrapped lines line up under the first one.

    A Static cannot hang its own indent, so the marker and the text live in
    separate columns and the text wraps inside its own.
    """
    return Horizontal(
        Static(f"[{marker_style}]{marker}[/]", classes="bullet-marker"),
        Static(text, classes="bullet-text"),
        classes="bullet-row",
    )
