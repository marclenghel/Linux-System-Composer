"""Core data types for Linux System Composer.

These are plain dataclasses with no behaviour attached on purpose: the whole
point of the project is that a Linux system is *data* (a graph of components
and the relationships between them) before it is ever a shell script.

Nothing in this module knows about the terminal, the UI, or any real machine.
That separation is what lets the compatibility engine and the hardware detector
be plugged in later without touching a single line of interface code.
"""

from __future__ import annotations

from dataclasses import dataclass, field


# ── Components and categories ─────────────────────────────────────────────────


@dataclass(frozen=True)
class Component:
    """One choosable piece of a Linux system: a kernel, a compositor, a
    filesystem, an audio server...

    `requires` / `conflicts` / `recommends` hold the ids of *other* components.
    They are the edges of the compatibility graph described in the README, and
    they are the only reason this project is more than a fancy package list.
    """

    id: str
    name: str
    summary: str                                  # one line, shown in the list
    description: str                              # a paragraph, shown in details
    tags: tuple[str, ...] = ()
    requires: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()
    recommends: tuple[str, ...] = ()
    packages: tuple[str, ...] = ()                # what a generated install would pull
    maturity: str = "stable"                      # stable | modern | legacy | experimental


@dataclass(frozen=True)
class Category:
    """A decision the user has to make, e.g. "which display server?".

    `layer` maps the category onto the stack diagram, so the visual and the
    catalogue never drift apart — add a category with a known layer and it
    shows up in the diagram automatically.
    """

    id: str
    name: str
    layer: str                                    # must match a Layer.id
    question: str                                 # the prompt shown above the list
    description: str                              # why this choice matters
    components: tuple[Component, ...] = ()
    default: str | None = None                    # component id pre-selected
    optional: bool = False                        # may legitimately be left empty

    def get(self, component_id: str | None) -> Component | None:
        """Look up one of this category's components by id."""
        if component_id is None:
            return None
        for component in self.components:
            if component.id == component_id:
                return component
        return None


@dataclass(frozen=True)
class Layer:
    """A horizontal band of the stack diagram, from hardware up to applications."""

    id: str
    name: str
    blurb: str


# ── The user's build ──────────────────────────────────────────────────────────


@dataclass
class Build:
    """The system the user is currently composing.

    This is the single piece of mutable state in the app. Every screen reads
    from it; only the composer writes to it. Keeping it this small is what will
    make "save / load / share a blueprint" a trivial feature later — it is one
    dict away from being a JSON file.
    """

    name: str = "untitled-system"
    selections: dict[str, str] = field(default_factory=dict)   # category id -> component id

    def select(self, category_id: str, component_id: str) -> None:
        self.selections[category_id] = component_id

    def selected_id(self, category_id: str) -> str | None:
        return self.selections.get(category_id)

    def is_selected(self, component_id: str) -> bool:
        return component_id in self.selections.values()

    def selected_ids(self) -> set[str]:
        """Every component id currently in the build — the input the
        compatibility engine will eventually run its rules against."""
        return set(self.selections.values())


# ── Validation output ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Issue:
    """Something the composer wants to tell the user about their build.

    `fix` is deliberately mandatory: the README's promise is that the tool
    *explains* incompatibilities instead of just refusing them, so an issue
    with no suggested way forward is considered a bug in the rule, not a
    valid result.
    """

    severity: str                                 # error | warning | info
    title: str
    detail: str
    fix: str


@dataclass(frozen=True)
class Preset:
    """A ready-made build the user can start from, e.g. "Gaming"."""

    id: str
    name: str
    tagline: str
    description: str
    selections: dict[str, str]
