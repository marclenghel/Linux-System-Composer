"""The application shell: theme, tabs, key bindings, and the one Build.

Deliberately thin. The app owns the Build and wires the tabs together; every
piece of actual content lives in a screen module. That way the interesting
question — "what does this project know about Linux?" — is answered in
data/catalog.py rather than tangled up with widget plumbing.
"""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.theme import Theme
from textual.widgets import Footer, Header, TabbedContent, TabPane

from lsc import __version__, content
from lsc.data.catalog import default_selections
from lsc.models import Build
from lsc.screens.compose import ComposeScreen
from lsc.screens.export import ExportScreen
from lsc.screens.hardware import HardwareScreen
from lsc.screens.overview import OverviewScreen
from lsc.screens.validate import ValidateScreen

# A terminal is not a blank canvas — it has a background the user chose. This
# theme commits to a dark palette so the screenshots in the project write-up
# look the same on every machine.
COMPOSER_THEME = Theme(
    name="composer",
    primary="#5FD3A6",
    secondary="#7AA2F7",
    accent="#E6B450",
    warning="#E0AF68",
    error="#F7768E",
    success="#9ECE6A",
    foreground="#C0CAF5",
    background="#0F1117",
    surface="#171A21",
    panel="#1D212B",
    dark=True,
)

_TABS = (
    ("1", "tab-overview", "Overview"),
    ("2", "tab-hardware", "Hardware"),
    ("3", "tab-compose", "Compose"),
    ("4", "tab-validate", "Validate"),
    ("5", "tab-export", "Export"),
)


class ComposerApp(App[None]):
    """Linux System Composer."""

    CSS_PATH = "styles/app.tcss"
    TITLE = content.APP_NAME
    SUB_TITLE = content.FOOTER_NOTE

    BINDINGS = [
        Binding("1", "show_tab('tab-overview')", "Overview"),
        Binding("2", "show_tab('tab-hardware')", "Hardware"),
        Binding("3", "show_tab('tab-compose')", "Compose"),
        Binding("4", "show_tab('tab-validate')", "Validate"),
        Binding("5", "show_tab('tab-export')", "Export"),
        Binding("r", "reset_build", "Reset"),
        Binding("t", "cycle_theme", "Theme"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        # The single piece of mutable state in the whole application.
        self.build = Build(name="untitled-system", selections=default_selections())

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with TabbedContent(initial="tab-overview"):
            with TabPane("Overview", id="tab-overview"):
                yield OverviewScreen()
            with TabPane("Hardware", id="tab-hardware"):
                yield HardwareScreen()
            with TabPane("Compose", id="tab-compose"):
                yield ComposeScreen(self.build)
            with TabPane("Validate", id="tab-validate"):
                yield ValidateScreen(self.build)
            with TabPane("Export", id="tab-export"):
                yield ExportScreen(self.build)
        yield Footer()

    def on_mount(self) -> None:
        self.register_theme(COMPOSER_THEME)
        self.theme = "composer"

    # ── keeping the tabs in step ──────────────────────────────────────────────

    def on_compose_screen_build_changed(self, _event: ComposeScreen.BuildChanged) -> None:
        """Compose changed the build, so the screens that read it must catch up.

        Pushed rather than polled: Validate and Export never look at the build
        unless something tells them it moved.
        """
        self.query_one(ValidateScreen).refresh_view()
        self.query_one(ExportScreen).refresh_view()
        self.sub_title = f"{self.build.name} — {content.FOOTER_NOTE}"

    # ── actions ───────────────────────────────────────────────────────────────

    def action_show_tab(self, tab: str) -> None:
        self.query_one(TabbedContent).active = tab

    def action_reset_build(self) -> None:
        # ComposeScreen owns the redraw and posts BuildChanged itself, so the
        # other tabs refresh through the same path as a button press.
        self.query_one(ComposeScreen).reset()
        self.notify("Build reset to defaults.", timeout=3)

    def action_cycle_theme(self) -> None:
        """Toggle between the project theme and a light one, for projectors.

        Worth having: a dark terminal on a classroom projector is often
        unreadable from the back of the room.
        """
        self.theme = "textual-light" if self.theme == "composer" else "composer"


def run() -> None:
    ComposerApp().run()
