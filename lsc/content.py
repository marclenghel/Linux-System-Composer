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
    "The compatibility engine. It resolves what your choices pull in before it "
    "judges them, so it catches conflicts through components you never selected; "
    "it separates a gap from a contradiction; and it runs a curated rule set "
    "whose hardware-aware rules only fire once a machine has been read.",
)

STATUS_NOT_DONE = (
    "Package-level dependency solving. The graph is components, not packages — "
    "the engine knows Hyprland needs Wayland, not that a particular library "
    "version is missing from your mirror.",
    "The kernel versions the engine compares against are written down by hand in "
    "the catalogue, so they go stale until somebody refreshes them.",
    "Writing anything to disk. Export shows you the files; it does not save "
    "them, and it certainly does not install anything.",
)

ROADMAP = (
    ("1", "Interface and catalogue", "done", "Screens, navigation, 40 components with their relationships."),
    ("2", "Hardware detection", "done", "Linux via /proc and /sys, macOS via system_profiler, Windows via one CIM query."),
    ("3", "Compatibility engine", "done", "Resolution before judgement, conditional rules, explanations with fixes."),
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
    "Detection feeds composition. Knowing the GPU vendor narrows the driver "
    "choice, the CPU feature level decides whether an optimised kernel is worth "
    "it, and the modules already loaded tell you what this machine is running "
    "today."
)

# ── Compose screen ────────────────────────────────────────────────────────────

COMPOSE_HELP = "↑ ↓ move   Enter select   Tab next pane   presets on the buttons above   r reset"

PRESETS_TITLE = "Start from a preset"

# ── Validate screen ───────────────────────────────────────────────────────────

# The screen used to carry a banner admitting the check behind it was a
# placeholder. Milestone 3 made the engine real, so the admission is gone — but
# the honesty it existed for is not: the coverage lines below say how much of the
# rule set actually ran, because "no problems found" means less when a third of
# the rules were skipped for want of a hardware reading.
VALIDATE_COVERAGE_FULL = (
    "Full check: the build, its implied components, and the rules that need to "
    "know what this machine is."
)

VALIDATE_COVERAGE_PARTIAL = (
    "Build-only check. The rules that ask about the GPU, the memory, or the "
    "loaded modules are skipped until a scan has run — open Hardware to take one."
)

VALIDATE_IMPLIED = "Pulled in by your choices:"

VALIDATE_CLEAN = (
    "Nothing to report. Every requirement in this build is satisfied, nothing it "
    "pulls in conflicts with anything else, and no rule in the set had anything "
    "to say about this combination."
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
