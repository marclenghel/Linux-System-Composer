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
)

STATUS_NOT_DONE = (
    "Hardware detection. The screen shows sample data shaped exactly like the "
    "Rust prototype's JSON output, so porting the detector changes no screens.",
    "The compatibility engine. Validate runs a deliberately simple check over "
    "the requires/conflicts fields — enough to prove the screen works, nowhere "
    "near the rule engine described in the README.",
    "Writing anything to disk. Export shows you the files; it does not save "
    "them, and it certainly does not install anything.",
)

ROADMAP = (
    ("1", "Interface and catalogue", "done", "Screens, navigation, 40 components with their relationships."),
    ("2", "Hardware detection", "next", "Port the Rust detector to Python; drop it in behind load_profile()."),
    ("3", "Compatibility engine", "planned", "Real rule evaluation: resolution, explanation, suggested fixes."),
    ("4", "Config generation", "planned", "Write package manifests, install scripts, and bootloader entries."),
    ("5", "Safety layer", "planned", "Dry runs, snapshots, rollback, and a boot fallback that works."),
)

# ── Hardware screen ───────────────────────────────────────────────────────────

HARDWARE_SAMPLE_BANNER = (
    "Sample data — detection is not ported yet. These fields match the Rust "
    "prototype's JSON exactly, so the real detector drops straight in."
)

HARDWARE_INTRO = (
    "Detection feeds composition. Knowing the GPU vendor narrows the driver "
    "choice, the CPU feature level decides whether an optimised kernel is worth "
    "it, and the modules already loaded tell you what this machine is running "
    "today."
)

# ── Compose screen ────────────────────────────────────────────────────────────

COMPOSE_HELP = "↑ ↓ move   Enter select   Tab next pane   presets on the buttons above   r reset"

PRESETS_TITLE = "Start from a preset"

# ── Validate screen ───────────────────────────────────────────────────────────

VALIDATE_PLACEHOLDER_BANNER = (
    "Placeholder check. This reads the requires/conflicts fields in the "
    "catalogue and nothing more — no version constraints, no transitive "
    "resolution, no hardware awareness. Milestone 3 replaces it."
)

VALIDATE_CLEAN = (
    "Nothing to report. Every requirement in this build is satisfied and no two "
    "components declare a conflict with each other."
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

FOOTER_NOTE = "Milestone 1 — interface and catalogue"
