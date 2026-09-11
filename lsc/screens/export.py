"""The export screen — the build as files.

Three buttons, one read-only pane. Nothing is written anywhere: the point of
this screen at this stage is to answer "what would this produce?" so the shape
of the output can be argued about before any code writes it to a disk.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Static, TextArea

from lsc import content, export
from lsc.models import Build


class ExportScreen(Vertical):
    """Preview of the files this build would generate."""

    def __init__(self, build: Build) -> None:
        super().__init__()
        self.build = build
        self.current = content.EXPORT_FILES[0][0]

    def compose(self) -> ComposeResult:
        yield Static(f"⚠  {content.EXPORT_BANNER}", classes="banner banner-warn")

        with Horizontal(classes="file-bar"):
            for kind, filename, _description in content.EXPORT_FILES:
                yield Button(filename, id=f"file-{kind}", classes="file-button")

        yield Static("", id="file-caption", classes="hint")

        preview = TextArea(
            "",
            id="preview",
            read_only=True,
            show_line_numbers=True,
            soft_wrap=False,
            classes="panel",
        )
        preview.border_title = "Preview"
        yield preview

    def on_mount(self) -> None:
        self.refresh_view()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        if button_id.startswith("file-"):
            self.current = button_id.removeprefix("file-")
            self.refresh_view()

    def refresh_view(self) -> None:
        """Regenerate the preview. Called on mount and whenever the build changes."""
        text = export.render(self.current, self.build)

        preview = self.query_one("#preview", TextArea)
        preview.text = text
        preview.border_title = _filename(self.current)

        line_count = text.count("\n") + 1
        self.query_one("#file-caption", Static).update(
            f"[$text-muted]{_description(self.current)} — {line_count} lines, "
            f"not written to disk.[/]"
        )

        # Make the active file obvious without a separate selected-state widget.
        for kind, _filename_, _description_ in content.EXPORT_FILES:
            button = self.query_one(f"#file-{kind}", Button)
            button.variant = "primary" if kind == self.current else "default"


def _filename(kind: str) -> str:
    for candidate, filename, _description in content.EXPORT_FILES:
        if candidate == kind:
            return filename
    return kind


def _description(kind: str) -> str:
    for candidate, _filename_, description in content.EXPORT_FILES:
        if candidate == kind:
            return description
    return ""
