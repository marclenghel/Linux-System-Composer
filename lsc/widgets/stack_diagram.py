"""The stack diagram — the one visual that carries the whole idea.

Ten layers drawn top-down, each showing what the current build puts there.
Change a selection anywhere in the composer and the matching line redraws, so
the abstract claim "a Linux system is a stack of dependent layers" becomes
something you can watch happen.

Base system and security profile are drawn outside the stack on purpose: they
are not layers, they cut across all of them.
"""

from __future__ import annotations

from textual.widgets import Static

from lsc.data.catalog import CATEGORY_BY_LAYER, FIXED_LAYERS, LAYERS
from lsc.models import Build

# "Init & Services" is the longest layer name at 15 characters; the extra two
# columns keep a visible gap between the name and its value on every row.
_NAME_WIDTH = 17

_NOT_CHOSEN = "— not chosen —"


class StackDiagram(Static):
    """A live view of the build, drawn as the layer stack from the README."""

    DEFAULT_CSS = """
    StackDiagram {
        border: round $primary 50%;
        border-title-color: $text-accent;
        border-title-style: bold;
        padding: 0 1;
        height: auto;
    }
    """

    def on_mount(self) -> None:
        self.border_title = "System Stack"

    def show(self, build: Build, active_category_id: str | None = None) -> None:
        """Redraw for the given build, marking the layer being edited."""
        self.update(self._render_stack(build, active_category_id))

    # ── drawing ───────────────────────────────────────────────────────────────

    def _render_stack(self, build: Build, active_category_id: str | None) -> str:
        lines: list[str] = []

        # Cross-cutting band above the stack: which distribution this all sits on.
        lines.append(self._cross_cutting("base", build, active_category_id))
        lines.append("[dim]" + "╌" * (_NAME_WIDTH + 14) + "[/dim]")

        for layer in LAYERS:
            lines.append(self._layer_line(layer.id, layer.name, build, active_category_id))

        # Cross-cutting band below: the policy applied to everything above it.
        lines.append("[dim]" + "╌" * (_NAME_WIDTH + 14) + "[/dim]")
        lines.append(self._cross_cutting("security", build, active_category_id))

        return "\n".join(lines)

    def _layer_line(
        self,
        layer_id: str,
        layer_name: str,
        build: Build,
        active_category_id: str | None,
    ) -> str:
        category = CATEGORY_BY_LAYER.get(layer_id)
        is_active = category is not None and category.id == active_category_id

        # Layers with no decision behind them yet (hardware, init, applications).
        if layer_id in FIXED_LAYERS:
            return (
                f"[dim]  {layer_name:<{_NAME_WIDTH}}[/dim]"
                f"[dim italic]{FIXED_LAYERS[layer_id]}[/dim italic]"
            )

        if category is None:
            return f"[dim]  {layer_name:<{_NAME_WIDTH}}{_NOT_CHOSEN}[/dim]"

        component = category.get(build.selected_id(category.id))
        marker = "[$text-accent]▶[/] " if is_active else "  "

        if component is None:
            return f"{marker}[dim]{layer_name:<{_NAME_WIDTH}}{_NOT_CHOSEN}[/dim]"

        name_style = "$text-accent" if is_active else "$text-muted"
        value_style = "b $text-accent" if is_active else "b $text-primary"
        return (
            f"{marker}[{name_style}]{layer_name:<{_NAME_WIDTH}}[/]"
            f"[{value_style}]{component.name}[/]"
        )

    def _cross_cutting(
        self, category_id: str, build: Build, active_category_id: str | None
    ) -> str:
        """Draw base / security, which wrap the stack rather than sit inside it."""
        from lsc.data.catalog import CATEGORIES_BY_ID

        category = CATEGORIES_BY_ID[category_id]
        component = category.get(build.selected_id(category_id))
        is_active = category_id == active_category_id

        label = "Base" if category_id == "base" else "Security"
        marker = "[$text-accent]▶[/] " if is_active else "  "
        value = component.name if component else _NOT_CHOSEN
        value_style = "b $text-accent" if is_active else "b $text-secondary"

        return f"{marker}[$text-muted]{label:<{_NAME_WIDTH}}[/][{value_style}]{value}[/]"
