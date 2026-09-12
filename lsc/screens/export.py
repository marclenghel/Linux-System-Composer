"""The export screen — the build as files, and the files onto a disk.

Milestone 3 left this screen as a preview and said so in a banner. Milestone 4
gives it the button the banner was apologising for, and milestone 5 decides
whether that button is allowed to do anything.

The order the controls appear in is the order the safety argument runs in:

    target directory  ->  Dry run  ->  Write files  ->  Roll back

Dry run comes before Write in the tab order and in the layout because it is
the honest default: you can always see exactly what is about to happen before
it happens, and the dry run is computed by the same code that does the writing
rather than by a second implementation that might disagree.
"""

from __future__ import annotations

import pathlib

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Input, Static, TextArea

from lsc import content, generate
from lsc.models import Build
from lsc.safety import rollback
from lsc.safety.paths import resolve

# Where output goes unless the user says otherwise. Relative to the working
# directory rather than absolute: someone running the composer from their
# projects folder means "here", and an absolute default would take the decision
# away from them before they had seen the screen.
DEFAULT_TARGET = "./systems"


class ExportScreen(Vertical):
    """Preview of the files this build generates, and the controls that write them."""

    def __init__(self, build: Build) -> None:
        super().__init__()
        self.build = build
        self.current = content.EXPORT_FILES[0][0]
        # Set by the app when a hardware scan finishes, exactly as Validate
        # does it. Without one, the warnings embedded in the generated script
        # are the ones that do not depend on the machine.
        self.hardware_profile: dict | None = None

    def compose(self) -> ComposeResult:
        yield Static(content.EXPORT_BANNER, id="export-banner", classes="banner banner-note")

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

        with Horizontal(classes="write-bar"):
            yield Input(
                value=DEFAULT_TARGET,
                placeholder="directory to write into",
                id="target",
                classes="target-input",
            )
            yield Button("Dry run", id="dry-run", variant="default")
            yield Button("Write files", id="write", variant="primary")
            yield Button("Roll back", id="rollback", variant="warning")

        yield Static("", id="write-result", classes="hint")

    def on_mount(self) -> None:
        self.refresh_view()

    # ── the file switcher ─────────────────────────────────────────────────────

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        if button_id.startswith("file-"):
            self.current = button_id.removeprefix("file-")
            self.refresh_view()
        elif button_id == "dry-run":
            self.run_dry()
        elif button_id == "write":
            self.write_files()
        elif button_id == "rollback":
            self.roll_back()

    def refresh_view(self) -> None:
        """Regenerate the preview. Called on mount and whenever the build changes."""
        text = generate.render(self.current, self.build, self.hardware_profile)

        preview = self.query_one("#preview", TextArea)
        preview.text = text
        preview.border_title = _filename(self.current)

        line_count = text.count("\n") + 1
        self.query_one("#file-caption", Static).update(
            f"[$text-muted]{_description(self.current)} — {line_count} lines[/]"
        )

        for kind, _filename_, _description_ in content.EXPORT_FILES:
            button = self.query_one(f"#file-{kind}", Button)
            button.variant = "primary" if kind == self.current else "default"

        self.refresh_banner()

    def set_hardware(self, profile: dict) -> None:
        """A scan finished, so the embedded warnings can be sharpened."""
        self.hardware_profile = profile
        self.refresh_view()

    # ── writing ───────────────────────────────────────────────────────────────

    def target(self) -> pathlib.Path:
        raw = self.query_one("#target", Input).value.strip() or DEFAULT_TARGET
        return resolve(raw)

    def current_plan(self) -> generate.WritePlan:
        return generate.plan(self.build, self.target(), self.hardware_profile)

    def refresh_banner(self) -> None:
        """Say whether this build may be written, before anyone presses anything.

        The Write button is disabled rather than merely refused on press. A
        button that is going to say no should look like it is going to say no.
        """
        plan = self.current_plan()
        banner = self.query_one("#export-banner", Static)
        write_button = self.query_one("#write", Button)

        if plan.may_write:
            write_button.disabled = False
            banner.set_classes("banner banner-note")
            banner.update(content.EXPORT_READY.format(target=plan.target))
        else:
            write_button.disabled = True
            banner.set_classes("banner banner-warn")
            reasons = "  ".join(b.message for b in plan.preflight.blockers)
            banner.update(f"{content.EXPORT_BLOCKED}  {reasons}")

    def run_dry(self) -> None:
        plan = self.current_plan()
        self._report(plan.summary())
        if plan.may_write:
            self.notify("Dry run only — nothing was written.", timeout=4)
        else:
            self.notify("This build cannot be written yet.", severity="warning", timeout=5)

    def write_files(self) -> None:
        plan = self.current_plan()
        try:
            result = generate.apply(plan)
        except (generate.Refused, OSError) as error:
            self._report(f"Nothing was written.\n\n{error}")
            self.notify(str(error), severity="error", timeout=8)
            return

        self._report(result.summary() + "\n\n" + plan.summary())
        self.notify(
            f"Wrote {len(result.touched)} files to {result.target}", timeout=6
        )
        self.refresh_banner()

    def roll_back(self) -> None:
        try:
            result = rollback.roll_back(self.target())
        except (rollback.NothingToRollBack, OSError) as error:
            self._report(str(error))
            self.notify(str(error), severity="warning", timeout=8)
            return

        self._report(result.summary())
        self.notify(result.summary().splitlines()[0], timeout=6)
        self.refresh_banner()

    def _report(self, text: str) -> None:
        self.query_one("#write-result", Static).update(text)


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
