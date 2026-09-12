# Every file, and why it exists

A file-by-file reference for Linux System Composer. The README explains what
the project is and [docs/rules.md](rules.md) explains how to write a
compatibility rule; this document answers the narrower question an examiner,
a contributor, or a future version of the author actually asks first — *what
is in here, and why is it a separate file?*

Line counts are approximate and will drift. Everything else should be true or
it is a bug in this document.

---

## Table of contents

- [Reading order](#reading-order)
- [The shape of the project](#the-shape-of-the-project)
- [Top level](#top-level)
- [`lsc/` — the package](#lsc--the-package)
- [`lsc/compat/` — the compatibility engine](#lsccompat--the-compatibility-engine)
- [`lsc/generate/` — turning a build into files](#lscgenerate--turning-a-build-into-files)
- [`lsc/safety/` — the safety layer](#lscsafety--the-safety-layer)
- [`lsc/data/` — the knowledge](#lscdata--the-knowledge)
- [`lsc/detect/` — hardware detection](#lscdetect--hardware-detection)
- [`lsc/screens/` — the interface](#lscscreens--the-interface)
- [`lsc/widgets/` and `lsc/styles/`](#lscwidgets-and-lscstyles)
- [`tests/`](#tests)
- [`docs/` and `legacy/`](#docs-and-legacy)
- [The dependency direction](#the-dependency-direction)

---

## Reading order

If you are opening this repository for the first time, these six files in this
order will explain the project faster than anything else:

1. **`lsc/models.py`** — the five dataclasses everything else is made of.
2. **`lsc/data/catalog.py`** — the actual Linux knowledge, as data.
3. **`lsc/compat/conditions.py`** — how a rule is written down.
4. **`lsc/compat/engine.py`** — how a rule is evaluated.
5. **`lsc/generate/plan.py`** — how a build becomes a set of intended file writes.
6. **`tests/test_architecture.py`** — the boundaries the whole thing is built to respect.

---

## The shape of the project

```
lsc/
  app.py  __main__.py  models.py  content.py      the shell and the vocabulary
  compat/      the compatibility engine            milestone 3
  generate/    a build -> files on a disk          milestone 4
  safety/      the fence around writing            milestone 5
  data/        the knowledge: components, rules    milestones 1 and 3
  detect/      reading a real machine              milestone 2
  screens/     five screens, one module each       milestone 1
  widgets/     shared interface pieces
  styles/      every colour, in one stylesheet
```

The division that matters is not by milestone but by direction: everything
above `screens/` knows nothing about terminals, and that is enforced by a test
rather than by discipline.

---

## Top level

### `run.sh`, `run.ps1`, `run.cmd`

The launchers. They exist because "clone it and run it" has to be one command
on a machine that may have no virtual environment, no dependencies, and a
Python that is not obviously a Python.

`run.ps1` searches candidate interpreters and proves each one by executing it,
because Windows ships a zero-byte `python.exe` stub in WindowsApps that opens
the Microsoft Store instead of running anything. It also drops
`$ErrorActionPreference` back to `Continue` before handing off, because under
`Stop`, PowerShell treats everything a native program writes to stderr as a
terminating error — and unittest writes its entire report there, so a passing
test run would otherwise look like a crash.

Both accept `--dry-run`, `--write`, `--rollback` and `--preset` and pass them
through to the module. `run.cmd` exists so the project can be started by double-clicking: it hands
off to `run.ps1` with `-ExecutionPolicy Bypass`, and pauses on failure so the
window stays open long enough to read the error.

### `pyproject.toml`

Packaging metadata. Lists all eight subpackages explicitly, and lists
`styles/*.tcss` as package data — the stylesheet is not a `.py` file, so
without that line an installed copy would be missing it and the app would fail
to start.

### `requirements.txt`

One line: Textual. It brings Rich with it. The core is standard library only.

### `.gitattributes`

Pins line endings. `run.sh` with CRLF endings fails on a Linux checkout with an
error that blames the interpreter rather than the endings, which is a bad half
hour for whoever hits it.

### `README.md`

The project document: what it is, the reasoning behind the architecture, the
milestone table, and an explicit list of what does *not* work.

### `LICENSE`

---

## `lsc/` — the package

### `lsc/__init__.py` — 9 lines

The version string and the app name. `__version__` is read by the manifest
generator rather than copied into it, because a version string written into a
generated file is one that will eventually be wrong in a file somebody is
relying on to reproduce a system.

### `lsc/__main__.py` — 141 lines

The command line: `--report`, `--dry-run`, `--write`, `--rollback`, `--preset`,
`--scan`. With no arguments it starts the interface.

These exist so the interesting behaviour is reachable without launching a
full-screen application over the top of the output, and so the safety layer can
be demonstrated in a terminal recording. Every one of them goes through the
same plan/preflight/write path as the Export screen's buttons — a command line
that took a shortcut past the safety layer would be a hole in it.

Textual is imported inside the function rather than at module level, so
`--report` on a headless machine never loads the interface.

### `lsc/app.py` — 155 lines

The shell: the theme, the five tabs, the key bindings, and the single `Build`
that every screen reads from.

Deliberately thin. It owns the Build and wires the tabs together; all content
lives in screen modules. It also routes two messages: `BuildChanged` from
Compose, which tells Validate, Export and Hardware to catch up, and `Scanned`
from Hardware, which hands the machine reading to Validate and Export so the
rules that need one can stop answering *unknown*.

`animation_level` is set on the instance rather than as a class attribute,
because that is where Textual reads it from — a class attribute of the same
name is silently ignored.

### `lsc/models.py` — 171 lines

`Component`, `Category`, `Layer`, `Build`, `Suggestion`, `Issue`, `Preset`.
Plain frozen dataclasses with no behaviour, because the whole premise is that a
Linux system is *data* — a graph of components and relationships — before it is
ever a shell script.

Two fields are worth singling out. `Component.provides` carries `(key, value)`
pairs, which is how a component states something with a value in it; a version
constraint needs that, because `requires`/`conflicts` can only name other
components. And `Issue.key` is a stable identity for deduplication, so that
collapsing two reports of the same problem never depends on how a sentence
happens to be worded.

### `lsc/content.py` — 186 lines

Every piece of interface copy that is not component data, in one file. Having
it in one place is what makes it possible to check the tone of the whole
application by reading a single file — including `STATUS_DONE` and
`STATUS_NOT_DONE`, which are the app's own honest account of itself.

---

## `lsc/compat/` — the compatibility engine

Milestone 3, and the part the README calls the heart of the project. Four
modules in dependency order, plus a package façade.

### `lsc/compat/__init__.py` — 36 lines

Re-exports the façade. Screens import this package and nothing below it, which
is why the engine could be replaced wholesale — as it already was once — without
a screen changing its imports.

### `lsc/compat/conditions.py` — 469 lines

**The language.** Condition nodes as data: `Selected`, `AnySelected`,
`CategoryIs`, `CategoryEmpty`, `HasTag`, `Fact`, `VersionAtLeast`,
`VersionBelow`, `AllOf`, `AnyOf`, `Not`.

Two things make this file what it is. First, every node serialises to JSON and
back, because a lambda cannot be written to a TOML file and a rule set that only
exists as Python has to be rewritten the day it moves out of Python. Second, the
logic is three-valued: a condition returns true, false, or **unknown**. "Is this
card older than Turing?" has no answer until the machine has been scanned, and
answering *false* there would quietly pass a build that is about to fail.

### `lsc/compat/facts.py` — 284 lines

**The world.** Turns a `Build` plus a hardware reading into one flat namespace
of facts that conditions query — `build.*` always present, `hardware.*` absent
until a real scan. `GpuFact`, `HardwareFacts`, `World`, `build_world`.

### `lsc/compat/engine.py` — 507 lines

**The interpreter.** Graph closure, rule evaluation, and message templating.

The important function is `requirement_closure`: it walks the `requires` edges
transitively and keeps the path. That is what lets the engine report that
Hardened conflicts with the proprietary NVIDIA driver when nothing in the
catalogue says so — Hardened needs `linux-hardened`, and `linux-hardened`
refuses to sit beside `nvidia`. An engine that looked one hop would find
nothing wrong with that build.

It also produces the `Report`, which carries not just the issues but the checks
that could not be made, because a check that was skipped silently is
indistinguishable from one that passed.

### `lsc/compat/checks.py` — 62 lines

**The façade.** `check`, `summarise`, `build_is_installable`, `category_name`.

Small on purpose. Before milestone 3 this file *was* the engine — a forty-line
walk over the relationship tuples with no conditions, no versions, no
transitivity and no idea what machine it was on. Its name and function
signatures survived the replacement, which is why no screen had to be edited to
gain any of the engine behind it.

---

## `lsc/generate/` — turning a build into files

Milestone 4. The split between deciding and doing is the design.

### `lsc/generate/__init__.py` — 31 lines

Re-exports `render`, `plan`, `apply` and the types around them.

### `lsc/generate/render.py` — 248 lines

A build becomes the text of three files: `packages.txt` (every package, grouped
by the decision that added it, because a flat list of ninety names tells you
nothing about why any of them is there), `install.sh` (the steps in dependency
order, written to be readable rather than clever), and `system.toml` (the build
as something you could commit, share, or feed back in).

Pure — every function returns a string and nothing opens a file. It also embeds
the compatibility engine's warnings for that exact build into the generated
script as comments, above the commands they concern. A warning that only ever
appeared on a screen the user has since closed did not survive to the moment it
mattered, and that moment is when somebody runs the script.

### `lsc/generate/plan.py` — 183 lines

`FileAction`, `WritePlan`, `plan()`. Reads the target directory and works out,
per file, whether writing would **create**, **replace**, leave **unchanged**, or
find something **preexisting** — a file already there that happens to be
byte-identical to ours and therefore is not ours to delete later.

Building a plan opens nothing for writing. This is the dry run, and it is the
same object the real write consumes.

### `lsc/generate/writer.py` — 215 lines

**The only module in the project that creates files**, and deliberately the
smallest interesting file in the repository: everything requiring a judgement
was decided before `apply()` is called.

Three rules hold here and `tests/test_architecture.py` enforces all three —
every path goes through `ensure_within()` before it is opened, anything
replaced is copied into `.lsc-backups/` first, and a journal is saved
afterwards so the write can be reversed.

Files are written in binary with explicit `\n`, because this project is
developed on Windows and generates scripts for Linux, where CRLF endings fail
with an error that blames the interpreter.

---

## `lsc/safety/` — the safety layer

Milestone 5. Two different things called "rollback" meet in this package and
the code keeps them apart deliberately.

### `lsc/safety/__init__.py` — 43 lines

The façade, and the place the two meanings are spelled out.

### `lsc/safety/paths.py` — 129 lines

Where output may and may not go. Pure — it inspects paths and returns reasons.
Refuses system directories and the home directory itself, requires the parent
to already exist so a typo cannot quietly build a tree somewhere nobody will
look again, and provides `ensure_within()`, the single function every
filesystem mutation in the project passes through first. That is the entire
containment story, which is why it is one function.

The system directory table is written with forward slashes, which `pathlib`
reads identically on Windows and which cannot be mangled by whatever quoting a
file passes through on its way into a repository.

### `lsc/safety/preflight.py` — 173 lines

What has to be true before anything is written. Returns **blockers** (writing
does not proceed) and **notes** (it proceeds and you are told).

This is where milestone 3 earns its keep: a build the engine reports errors on
is refused outright. A warning nobody must act on is one people learn to scroll
past; a warning that stops the export gets read.

### `lsc/safety/journal.py` — 162 lines

The record of exactly what was written — every path, the SHA-256 of the bytes
put there, and where the previous contents went if anything was replaced. Kept
in the output directory as `.lsc-journal.json`, so moving the directory moves
its history and deleting it leaves no dangling record.

The hash is the important field; see below. `backup_stamp()` has microsecond
resolution because two writes in the same second would otherwise share a backup
directory, and the version guaranteed to be the user's own is the oldest — the
worst possible one to lose.

### `lsc/safety/rollback.py` — 114 lines

Undoing a write without destroying anything that was not ours. A file is only
removed or restored if it is **still byte-for-byte what we wrote**; anything
else is left alone and reported.

Generate a script, spend an hour editing it, press Roll back, and the correct
behaviour is to keep the hour of work and say so. That is most of the
difference between a rollback you can press without thinking and one you have
to reason about first. The journal is deleted only when the undo was complete,
so a partial rollback stays resumable.

### `lsc/safety/snapshots.py` — 130 lines

Whether the system *being designed* can roll back — not the machine you are
running on. Snapshotting a real machine needs root, and a tool whose promise is
that it never touches your system does not get an exception for the feature
called safety.

Whether you can undo a bad kernel update in six months is settled the moment
you pick a filesystem, several screens before anyone finds out. This module
says so while the decision is still reversible, and its output goes into the
generated script as comments.

---

## `lsc/data/` — the knowledge

Data, not machinery. Nothing in here runs.

### `lsc/data/catalog.py` — 818 lines

The component catalogue: 40 components across 9 categories, with their
dependencies, conflicts, recommended pairings and packages written down. The
largest file in the project, and appropriately so — this is the content the
whole thing exists to reason about.

Scoped to the Arch ecosystem, as the README commits to. Supporting Debian later
means adding catalogues, not changing this file's shape.

### `lsc/data/rules.py` — 579 lines

The 25 compatibility rules, as data. Plain "X requires Y" and "X conflicts with
Y" stay in the catalogue next to the component and the engine derives issues
from those edges itself; only knowledge with a *condition* in it — anything
with a version, anything about the machine, anything of the form "if this and
that" — is written here as a rule.

### `lsc/data/gpus.py` — 157 lines

Graphics model strings turned into something a rule can reason about. Detection
reports `"NVIDIA GeForce RTX 3060"`; a rule needs to know that is Ampere and
therefore new enough for the open kernel modules.

Deliberately a table rather than a chain of `if "RTX" in name` tests: a table
can be read by someone checking whether their card is covered, extended without
touching logic, and tested exhaustively. Ranks are spaced by ten so a
generation discovered to sit between two known ones does not force a
renumbering.

### `lsc/data/presets.py` — 102 lines

Gaming, Developer, Minimal, Security Hardened. Shaped identically to a saved
build on purpose — "share a system blueprint" and "load a preset" are the same
feature, differing only in where the file came from.

### `lsc/data/hardware.py` — 87 lines

The seam between the screens and the detector, plus the sample profile. The
interface never needs to know whether it is looking at a real machine or a
fixture — only at the `source` field, which says which.

The sample profile is kept for three reasons: the interface has something to
draw in the fraction of a second before a scan finishes, the tests do not need
a particular machine to run on, and a demo can be given from a laptop that is
not the one being described.

This module used to carry a `suggestions_for()` that matched vendor substrings
and returned advice. Milestone 3 deleted it: turning "the string said NVIDIA"
into "use the open modules" is a compatibility judgement, and those now live in
`rules.py` where they can state their condition, explain themselves, and be
tested.

---

## `lsc/detect/` — hardware detection

Milestone 2. The Python port of `legacy/rust-hardware-detect/`.

### `lsc/detect/__init__.py` — 148 lines

Dispatch by platform, and the shape of the result — exactly the dict the
Hardware screen already consumed as sample data, which is why wiring real
detection in changed no screen code.

Three rules, all learned from the prototype. **Never fail**: every field falls
back to `Unknown`, because a partial reading is useful and an exception is not.
**Never modify the system**: the prototype ran `sudo pacman -S pciutils` when
`lspci` was missing; reading `/sys/bus/pci/devices/` needs no external command
and no root. **Never block for long**: this runs from a UI thread, so every
subprocess has a timeout.

### `lsc/detect/_shell.py` — 121 lines

Every detection path goes through here, so the failure behaviour is identical
everywhere: a missing command, a permission error or a hung process produces
`None`, never an exception and never a hang.

### `lsc/detect/linux.py` — 308 lines

`/proc`, `/sys`, and the PCI bus. Reading `/sys/bus/pci/devices/` gives the
vendor of every display controller without `lspci` and without root, which is
how the prototype's package installation was designed out rather than ported.

### `lsc/detect/macos.py` — 178 lines

`sysctl`, `system_profiler`, `kextstat`.

### `lsc/detect/windows.py` — 226 lines

One CIM query returning JSON, parsed in Python. The prototype started
PowerShell five separate times — kernel, board, GPUs, drivers, network — and
each start costs the better part of a second. One script turns several seconds
into roughly one.

---

## `lsc/screens/` — the interface

One module per screen. None of them contain Linux knowledge; they read the
catalogue and ask the engine.

### `lsc/screens/overview.py` — 60 lines

The landing screen: what this is, how to drive it, and — from `content.py` — an
honest account of which parts are real. A demo that overstates completeness is
a liability, not an asset.

### `lsc/screens/hardware.py` — 269 lines

Draws the sample profile immediately, then scans the real machine on a
background thread and swaps the result in. Detection takes a few seconds on
Windows, and an interface that freezes for three seconds on startup reads as
broken even when it is working.

The banner always says which of the two you are looking at: at a glance you
should never be unsure whether the RTX 3060 on screen is in this machine or in
an example. The advice below it is the engine's advice, with the rule that
produced it named underneath.

### `lsc/screens/compose.py` — 296 lines

The screen the project is named after. Three panes — decisions, options,
consequences — with the stack diagram showing where the highlighted choice
lands. It mutates nothing except the Build and announces every change with a
`BuildChanged` message, so the other tabs catch up without this module knowing
they exist.

### `lsc/screens/validate.py` — 142 lines

What your choices imply. The part worth looking at is the **Not checked**
panel: rules that depend on the machine cannot reach an answer until it has
been read, and this screen lists them rather than passing over them.

### `lsc/screens/export.py` — 202 lines

The build as files, and the files onto a disk. The controls appear in the order
the safety argument runs in — target directory, Dry run, Write files, Roll back
— because the dry run is the honest default and is computed by the same code
that does the writing.

When preflight blocks a build, the Write button is **disabled** with the reason
on the banner rather than refusing on press: a button that is going to say no
should look like it is going to say no.

---

## `lsc/widgets/` and `lsc/styles/`

### `lsc/widgets/stack_diagram.py` — 112 lines

Ten layers drawn top-down, redrawn whenever a selection changes, so the
abstract claim "a Linux system is a stack of dependent layers" becomes
something you can watch happen. Base system and security profile are drawn
outside the stack on purpose: they are not layers, they cut across all of them.

### `lsc/widgets/panel.py` — 42 lines

Bordered boxes and hanging-indent bullets, shared because they are used often
enough to be worth one definition.

### `lsc/styles/app.tcss`

Every colour in the application, as theme variables. One file, so re-theming
never means hunting through screens.

---

## `tests/`

222 tests. Most guard *data* rather than behaviour, because the data is where
this project's value is and where a mistake is hardest to see by reading: a
relationship id pointing at nothing, a preset that does not install, a rule that
can never fire, a GPU pattern shadowing the one below it.

| File | Lines | What it defends |
|------|-------|-----------------|
| `test_architecture.py` | 301 | The boundaries: core imports no interface, only three modules may write, nothing elevates or installs |
| `test_write.py` | 354 | Milestone 4 — planning, writing, dry runs, overwriting, refusal, generated content |
| `test_safety.py` | 301 | Milestone 5 — path rules, preflight, the journal, rollback, snapshot advice |
| `test_rules.py` | 315 | The rule set as knowledge: every rule can fire, templates resolve, the worked example holds |
| `test_conditions.py` | 289 | The rule language: three-valued logic, versions, JSON round trip |
| `test_engine.py` | 263 | The evaluator: closure, transitivity, conflicts, unknown not swallowed, ordering |
| `test_detect.py` | 255 | The detector, including parsing fixtures from real machines |
| `test_catalog.py` | 226 | Catalogue integrity, diagram coverage, presets, export |
| `test_gpus.py` | 145 | The graphics table, including that no pattern shadows another |
| `fixtures.py` | 115 | Fixture machines and builds, shared by the engine and rule tests |

`test_write.py` and `test_safety.py` are the exceptions to the data rule: they
use real temporary directories, because the thing they test is exactly the part
a fake would have to pretend about.

**`test_architecture.py` deserves singling out.** It is where the project's
central promise lives. Until milestone 4 that promise was *nothing writes*,
which was easy to check and worthless the day the tool started writing. It is
now narrower rather than weaker: three named modules may touch a disk, every
other module may not, each of the three must import the guard that confines it,
and the allowlist fails if it grows past three without someone editing the
assertion that says so.

---

## `docs/` and `legacy/`

### `docs/rules.md`

How to write a compatibility rule: the shape of one, the condition vocabulary,
the fact namespace, message templates, where a rule belongs versus where a
plain catalogue edge belongs, and what the tests will demand of it.

### `docs/files.md`

This document.

### `legacy/rust-hardware-detect/`

The original Rust prototype, kept for reference rather than out of sentiment:
its platform-specific commands were the specification the Python detector was
ported against, and the three deliberate departures from it — no package
installation, one Windows query instead of five, and never failing — are easier
to argue for with the original still readable.

---

## The dependency direction

The rule that is enforced is about one boundary only:

```
screens/  widgets/  app.py          the interface
    |
    v
compat/  generate/  safety/  data/  detect/  models.py  content.py
```

Arrows across that line only point down. `tests/test_architecture.py` fails if
that stops being true, and the payoff was demonstrated in milestone 3: the
entire compatibility engine was swapped in underneath five screens without one
of them changing an import.

Below the line the picture is a layering, not a strict hierarchy:

```
generate/ ──> safety/ ──> compat/ ──> data/ ──> models.py
    │                        ^                     ^
    └────────────────────────┘─────────────────────┘
```

`generate/` asks `safety/` whether it may write and asks `compat/` directly for
the warnings it embeds in the script. `safety/preflight.py` asks `compat/`
whether the build is sound. `compat/` reads the catalogue and the rules from
`data/`. Everything is built from the dataclasses in `models.py`, which imports
nothing.

### The one cycle, and how it is broken

`data/` and `compat/` genuinely point at each other, and this is worth
understanding rather than tidying away:

- `data/rules.py` imports `compat.conditions` and `compat.engine.Rule`, because
  a rule is written in the condition vocabulary and has to name its own type.
- `compat/engine.py` imports `data.catalog`, because evaluating anything means
  knowing what the components are.

Left alone that is a circular import. It is broken at one line —
`compat/engine.py` imports `data.rules` *inside* `evaluate()` rather than at
module level:

```python
def evaluate(...):
    from lsc.data.rules import RULES
```

That is the honest resolution rather than a trick. The direction that has to
hold at import time is *rules depend on the language they are written in*; the
engine only needs the rule set at the moment it runs, not at the moment it is
defined. Moving the rule set out to TOML later — which the README describes as
a loader rather than a rewrite — removes this cycle entirely, because a TOML
file cannot import anything.

One other edge crosses areas for a small reason: `compat/facts.py` imports a
single constant from `detect/` (`SOURCE_DETECTED`) to tell a real reading from
the sample profile, and `data/hardware.py` imports `detect()` itself, because
that module is the seam the screens talk to.
