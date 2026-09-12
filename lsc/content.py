"""Every piece of interface copy that is not component data.

Component descriptions live in data/catalog.py because they are domain
knowledge. Everything here is chrome: titles, banners, help text, the roadmap.
Keeping it in one file means the wording can be reviewed — or translated — in
one place instead of being hunted across nine screens.
"""

from __future__ import annotations

APP_NAME = "Linux System Composer"
TAGLINE = "Design a Linux system as a graph of components, not a pile of shell commands."

# Drawn on the overview screen. Kept narrow enough to survive an 80-column terminal.
LOGO = r"""
 ██╗     ███████╗ ██████╗
 ██║     ██╔════╝██╔════╝    Linux
 ██║     ███████╗██║         System
 ██║     ╚════██║██║         Composer
 ███████╗███████║╚██████╗
 ╚══════╝╚══════╝ ╚═════╝
"""

# ── Overview screen ───────────────────────────────────────────────────────────

WHAT_THIS_IS = (
    "Every layer of a Linux system depends on the layers under it and quietly "
    "rules out some of the layers above it. That knowledge is real, but it is "
    "scattered across wiki pages, forum threads, and other people's memory.\n\n"
    "This tool models those relationships directly: pick a component, see what it "
    "needs, see what it breaks, and get a configuration you can actually "
    "reproduce."
)

HOW_TO_USE = (
    "[b]Hardware[/b]   what you are building on\n"
    "[b]Compose[/b]    pick a component for each layer\n"
    "[b]Validate[/b]   see what your choices imply\n"
    "[b]Export[/b]     turn the build into files\n\n"
    "Move with [b]↑ ↓[/b], choose with [b]Enter[/b], switch tabs with [b]1[/b]–[b]5[/b] "
    "or [b]Tab[/b]."
)

# Honest status. A demo that overstates what is finished is worse than one that
# does not — so the interface says plainly which parts are real.
STATUS_TITLE = "Where this build actually stands"

STATUS_DONE = (
    "Interface, navigation, and the full component catalogue — 40 components "
    "across 9 categories, with their dependencies and conflicts already written "
    "down.",
    "The stack diagram, which redraws as you change the build.",
    "Preset builds, and the export preview that turns a build into file contents.",
    "Real hardware detection on Linux, macOS and Windows — the Rust prototype "
    "ported to Python, running in a background thread so nothing freezes.",
    "The compatibility engine. Conditional rules, version constraints, "
    "transitive resolution through the dependency graph, and rules that reason "
    "about the card actually in this machine — every one of them written as "
    "data rather than as code.",
    "Detection feeding composition: the Hardware screen's advice now comes from "
    "the same rules as Validate, and says under what condition it applies.",
)

STATUS_NOT_DONE = (
    "Writing anything to disk. Export shows you the files; it does not save "
    "them, and it certainly does not install anything.",
    "Package-level resolution. The engine reasons about components, not about "
    "individual packages and their versions — that is pacman's job, and this "
    "tool stops where pacman starts.",
    "A complete rule set. The rules are a curated set covering the interactions "
    "worth knowing about, not the whole of Linux. Validate lists the checks it "
    "could not make rather than staying quiet about them.",
)

ROADMAP = (
    ("1", "Interface and catalogue", "done", "Screens, navigation, 40 components with their relationships."),
    ("2", "Hardware detection", "done", "Linux via /proc and /sys, macOS via system_profiler, Windows via one CIM query."),
    ("3", "Compatibility engine", "done", "Rules as data: conditions, versions, hardware, transitive resolution."),
    ("4", "Config generation", "next", "Write package manifests, install scripts, and bootloader entries."),
    ("5", "Safety layer", "planned", "Dry runs, snapshots, rollback, and a boot fallback that works."),
)

# ── Hardware screen ───────────────────────────────────────────────────────────

HARDWARE_SAMPLE_BANNER = (
    "Sample data — this is the placeholder shown while the real scan runs. "
    "Press Scan this machine if it does not replace itself."
)

HARDWARE_DETECTED_BANNER = "Detected on this machine"

HARDWARE_PARTIAL_BANNER = (
    "Detection finished but something went wrong on the way. The fields it "
    "did read are shown; the rest say Unknown."
)

HARDWARE_INTRO = (
    "Detection feeds composition. The graphics model decides which NVIDIA "
    "driver will even bind, the memory decides whether a full desktop is "
    "sensible, and the modules already loaded tell you what this machine is "
    "running today."
)

HARDWARE_SUGGESTIONS_EMPTY = (
    "Nothing to suggest: every rule that depends on this machine is satisfied "
    "by the current build."
)

HARDWARE_SUGGESTIONS_NEED_SCAN = (
    "Nothing has read this machine yet, so the rules that depend on it cannot "
    "say anything. Press Scan this machine."
)

# ── Compose screen ────────────────────────────────────────────────────────────

COMPOSE_HELP = "↑ ↓ move   Enter select   Tab next pane   presets on the buttons above   r reset"

PRESETS_TITLE = "Start from a preset"

# ── Validate screen ───────────────────────────────────────────────────────────

# The placeholder banner that used to live here is gone, because the thing it
# warned about is finished. What replaces it is not a warning but a scope note:
# still honest about the limits, no longer apologising for being a stub.
VALIDATE_SCOPE_NOTE = (
    "Checks dependencies through the whole graph, conflicts, version floors, "
    "and what this machine can actually run. Rules are a curated set, not the "
    "whole of Linux — anything it could not check is listed below rather than "
    "passed over."
)

VALIDATE_UNCHECKED_TITLE = "Not checked"

VALIDATE_UNCHECKED_INTRO = (
    "These rules depend on knowing what is in the machine, and nothing has read "
    "it yet. A check that was skipped silently is indistinguishable from one "
    "that passed, so they are listed:"
)

VALIDATE_SCAN_HINT = (
    "Open the Hardware tab and press Scan this machine to decide them."
)

VALIDATE_CLEAN = (
    "Nothing to report. Every requirement in this build is satisfied, no two "
    "components conflict, and no rule in the set has anything to say about this "
    "combination."
)

# ── Export screen ─────────────────────────────────────────────────────────────

EXPORT_BANNER = (
    "Preview only — nothing is written to disk and nothing is installed. These "
    "are the files milestone 4 will generate for real."
)

EXPORT_FILES = (
    ("packages", "packages.txt", "Every package this build pulls in"),
    ("install", "install.sh", "The installation steps, in order"),
    ("manifest", "system.toml", "The build itself, as a reproducible file"),
)

# ── Footer / misc ─────────────────────────────────────────────────────────────

FOOTER_NOTE = "Milestone 3 — compatibility engine"
