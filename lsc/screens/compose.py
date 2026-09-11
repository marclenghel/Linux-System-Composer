"""The composer — the screen the whole project is named after.

Three panes: the decisions on the left, the options for the current decision in
the middle, and on the right the consequences — a full description of what is
highlighted, and the stack diagram showing where it lands.

The screen never mutates anything except the Build, and it announces every
change with a BuildChanged message so the Validate and Export tabs can catch
up without this module having to know they exist.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.widgets import Button, OptionList, Static
from textual.widgets.option_list import Option

from lsc import content
from lsc.data.catalog import (
    CATEGORIES,
    CATEGORIES_BY_ID,
    component_name,
    default_selections,
)
from lsc.data.presets import PRESETS, PRESETS_BY_ID
from lsc.models import Build, Category, Component
from lsc.widgets.stack_diagram import StackDiagram

_MATURITY_LABEL = {
    "modern": "modern",
    "legacy": "legacy",
    "experimental": "experimental",
}


class ComposeScreen(Vertical):
    """Pick one component per category and watch the stack fill in."""

    class BuildChanged(Message):
        """The build was modified. Bubbles up to the app."""

    def __init__(self, build: Build) -> None:
        super().__init__()
        self.build = build
        # add_options() fires highlight events; this stops them being treated as
        # user input while a list is being rebuilt underneath.
        self._repopulating = False

    # ── layout ────────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        with Horizontal(classes="preset-bar"):
            yield Static("[$text-muted]Start from:[/]", classes="preset-label")
            for preset in PRESETS:
                yield Button(preset.name, id=f"preset-{preset.id}", classes="preset-button")
            yield Button("Reset", id="preset-reset", variant="default", classes="preset-button")

        with Horizontal(classes="compose-body"):
            with Vertical(classes="col-categories"):
                categories = OptionList(id="categories", classes="panel")
                categories.border_title = "Decisions"
                yield categories

            with Vertical(classes="col-components"):
                yield Static("", id="question", classes="question")
                components = OptionList(id="components", classes="panel")
                components.border_title = "Options"
                yield components

            with VerticalScroll(classes="col-detail"):
                yield StackDiagram(id="stack")
                detail = Static("", id="detail", classes="panel")
                detail.border_title = "Details"
                yield detail

        yield Static(content.COMPOSE_HELP, classes="hint")

    def on_mount(self) -> None:
        self._fill_categories()
        self._show_category(CATEGORIES[0])

    # ── events ────────────────────────────────────────────────────────────────

    def on_option_list_option_highlighted(
        self, event: OptionList.OptionHighlighted
    ) -> None:
        if self._repopulating:
            return
        if event.option_list.id == "categories":
            category = self._current_category()
            if category is not None:
                self._show_category(category)
        elif event.option_list.id == "components":
            self._show_detail(self._current_component())

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_list.id == "categories":
            # Enter on a decision moves focus to its options, which is what
            # people try first.
            self.query_one("#components", OptionList).focus()
            return

        category = self._current_category()
        component = self._current_component()
        if category is None or component is None:
            return

        self.build.select(category.id, component.id)
        self._fill_categories(keep_position=True)
        self._fill_components(category)
        self._refresh_stack(category)
        self.post_message(self.BuildChanged())

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        if not button_id.startswith("preset-"):
            return

        preset_id = button_id.removeprefix("preset-")
        if preset_id == "reset":
            self.reset()
        else:
            preset = PRESETS_BY_ID.get(preset_id)
            if preset is not None:
                self.apply_selections(f"{preset.id}-system", preset.selections)

    # ── public API, used by the preset buttons and the app's key bindings ─────

    def apply_selections(self, name: str, selections: dict[str, str]) -> None:
        """Replace the whole build and redraw every pane."""
        self.build.name = name
        self.build.selections = dict(selections)

        category = self._current_category() or CATEGORIES[0]
        self._fill_categories(keep_position=True)
        self._show_category(category)
        self.post_message(self.BuildChanged())

    def reset(self) -> None:
        """Back to each category's declared default."""
        self.apply_selections("untitled-system", default_selections())

    # ── populating the panes ──────────────────────────────────────────────────

    def _fill_categories(self, keep_position: bool = False) -> None:
        """Rebuild the decisions list so each row shows its current answer."""
        option_list = self.query_one("#categories", OptionList)
        position = option_list.highlighted if keep_position else 0

        self._repopulating = True
        option_list.clear_options()
        option_list.add_options(
            [
                Option(self._category_prompt(category), id=category.id)
                for category in CATEGORIES
            ]
        )
        if position is not None and 0 <= position < len(CATEGORIES):
            option_list.highlighted = position
        self._repopulating = False

    def _fill_components(self, category: Category) -> None:
        option_list = self.query_one("#components", OptionList)
        selected_id = self.build.selected_id(category.id)

        self._repopulating = True
        option_list.clear_options()
        option_list.add_options(
            [
                Option(self._component_prompt(component, selected_id), id=component.id)
                for component in category.components
            ]
        )
        # Land on whatever is currently chosen rather than at the top.
        for index, component in enumerate(category.components):
            if component.id == selected_id:
                option_list.highlighted = index
                break
        self._repopulating = False

    def _show_category(self, category: Category) -> None:
        self.query_one("#question", Static).update(
            f"[b $text-accent]{category.question}[/]\n[$text-muted]{category.description}[/]"
        )
        self._fill_components(category)
        self._refresh_stack(category)
        self._show_detail(self._current_component())

    def _show_detail(self, component: Component | None) -> None:
        detail = self.query_one("#detail", Static)
        detail.update(
            _detail_body(component, self.build) if component else "[$text-muted]—[/]"
        )

    def _refresh_stack(self, category: Category | None) -> None:
        self.query_one("#stack", StackDiagram).show(
            self.build, category.id if category else None
        )

    # ── prompts ───────────────────────────────────────────────────────────────

    def _category_prompt(self, category: Category) -> str:
        component = category.get(self.build.selected_id(category.id))
        if component is None:
            value = "[$text-muted italic]not set[/]"
        else:
            value = f"[b]{component.name}[/b]"
        return f"[$text-muted]{category.name}[/]\n  {value}"

    def _component_prompt(self, component: Component, selected_id: str | None) -> str:
        chosen = component.id == selected_id
        marker = "[$text-accent]●[/]" if chosen else "[$text-muted]○[/]"
        name = f"[b $text-accent]{component.name}[/]" if chosen else f"[b]{component.name}[/]"
        badge = ""
        if component.maturity in _MATURITY_LABEL:
            badge = f"  [$text-muted italic]{_MATURITY_LABEL[component.maturity]}[/]"
        return f"{marker} {name}{badge}\n  [$text-muted]{component.summary}[/]"

    # ── current position helpers ──────────────────────────────────────────────

    def _current_category(self) -> Category | None:
        option_id = _highlighted_id(self.query_one("#categories", OptionList))
        return CATEGORIES_BY_ID.get(option_id) if option_id else None

    def _current_component(self) -> Component | None:
        category = self._current_category()
        if category is None:
            return None
        option_id = _highlighted_id(self.query_one("#components", OptionList))
        return category.get(option_id)


# ── module-level helpers ──────────────────────────────────────────────────────


def _highlighted_id(option_list: OptionList) -> str | None:
    """The id of the highlighted option, or None if the list is empty.

    Reading the widget's own `highlighted` index rather than an event attribute
    keeps this working from anywhere, not just inside a message handler.
    """
    index = option_list.highlighted
    if index is None:
        return None
    try:
        return option_list.get_option_at_index(index).id
    except IndexError:
        return None


def _detail_body(component: Component, build: Build) -> str:
    """The full write-up for one component, plus its graph edges."""
    lines = [f"[b $text-accent]{component.name}[/]"]

    if component.maturity != "stable":
        lines.append(f"[$text-muted italic]{component.maturity}[/]")

    lines.append("")
    lines.append(component.description)
    lines.append("")

    selected = build.selected_ids()

    def relation(label: str, ids: tuple[str, ...], satisfied_marker: bool) -> str | None:
        if not ids:
            return None
        parts = []
        for other_id in ids:
            name = component_name(other_id)
            if not satisfied_marker:
                parts.append(name)
                continue
            # For requires/conflicts, say at a glance whether the current build
            # already satisfies (or trips) the relationship.
            in_build = other_id in selected
            colour = "$success" if in_build else "$text-muted"
            parts.append(f"[{colour}]{name}[/]")
        return f"[$text-muted]{label:<12}[/]" + " · ".join(parts)

    for line in (
        relation("Requires", component.requires, True),
        relation("Conflicts", component.conflicts, True),
        relation("Pairs with", component.recommends, True),
        relation("Tags", component.tags, False),
    ):
        if line:
            lines.append(line)

    if component.packages:
        lines.append("")
        lines.append("[$text-muted]Packages[/]")
        lines.append("  " + "\n  ".join(component.packages))

    return "\n".join(lines)
