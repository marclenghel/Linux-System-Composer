# Linux-System-Composer
A compatibility-aware platform for visually designing, validating, generating, and deploying custom Linux systems.

---

# Table of contents

- [Overview](#overview)
- [Vision](#vision)
- [The core ideas](#the-core-idea)
- [Main goals](#main-goals)
   - [1. Visual Linux System Composition](#1-visual-linux-system-composition)
   - [2. Compatibility Intelligence](#2-compatibility-intelligence)
   - [3. Reproducibility](#3-reproducibility)
   - [4. Safety](#4-safety)
- [Project Philosophy](#project-philosophy)
- [Inspiration](#inspiration)
- [Long-Term Vision](#long-term-vision)
- [Current Development Direction](#current-development-direction)
- [Architecture](#architecture)
   - [Interface](#interface)
   - [Core](#core)
   - [Data Layer](#data-layer)
- [Core Systems](#core-systems)
   - [Compatibility Engine](#compatibility-engine)
   - [Hardware Detection Layer](#hardware-detection-layer)
   - [Configuration Generator](#configuration-generator)
   - [Safety Layer](#safety-layer)
- [Initial Scope](#initial-scope)
- [MVP Features](#mvp-features)
   - [Planned MVP](#planned-mvp)
      - [Stack Selection](#stack-selection)
      - [Compatibility Validation](#compatibility-validation)
      - [Presets](#presets)
      - [Config Generation](#config-generation)
- [Challenges](#challenges)
- [Why This Project Exists](#why-this-project-exists)
- [Status](#status)
   - [Milestones](#milestones)
   - [On the compatibility engine](#on-the-compatibility-engine)
   - [On the detector](#on-the-detector)
- [Running it](#running-it)
   - [Tests](#tests)
   - [Hardware, without the interface](#hardware-without-the-interface)
   - [Layout](#layout)
- [Contributing](#contributing)
- [Future Possibilities](#future-possibilities)
- [Final Goal](#final-goal)

---

# Overview

Linux System Composer is an attempt to rethink how Linux systems are built.

Instead of manually:

- reading fragmented wiki pages
- debugging incompatible packages
- rebuilding environments repeatedly
- memorizing hidden system interactions
- copying random shell commands from forums

this project aims to provide:

- a visual Linux stack builder
- a compatibility intelligence engine
- a configuration generator
- a reproducible system composer
- a safe experimentation environment

The goal is not to replace Linux expertise.

The goal is to make Linux architecture understandable, composable, and reproducible.

---

# Vision

Modern Linux customization is powerful but fragmented.

Every layer of the system exists in isolation:

- kernels
- bootloaders
- init systems
- desktop environments
- compositors
- filesystems
- audio systems
- GPU drivers
- package managers
- performance tweaks
- security frameworks

Users are expected to understand:

- dependencies
- conflicts
- undocumented assumptions
- distro-specific behavior
- hardware compatibility

Linux System Composer aims to unify this into a single interactive system composition workflow.

---

# The Core Idea

Treat Linux systems as composable architecture graphs instead of disconnected configuration files.

Example:

```
Hardware
   ↓
Kernel
   ↓
Drivers
   ↓
Init System
   ↓
Display Server
   ↓
Desktop Environment / WM
   ↓
Applications
```

Every component:

- depends on other components
- conflicts with some configurations
- has performance implications
- has security tradeoffs
- has compatibility constraints

The platform models these relationships directly.

---

# Main Goals

## 1. Visual Linux System Composition

Users should be able to:

- choose kernels
- choose desktop environments
- choose filesystems
- choose audio systems
- choose GPU stacks
- choose security profiles
- choose optimization presets

through an interactive interface.


## 2. Compatibility Intelligence

The platform should:

- detect conflicts
- explain incompatibilities
- suggest fixes
- recommend optimal stacks
- prevent invalid combinations

Example:

```
Selected:
✓ Hyprland
✓ NVIDIA

Warning:
Hyprland + NVIDIA requires:
- DRM modeset
- explicit sync
- recent kernel
- compatible XWayland patches
```


## 3. Reproducibility

Generated systems should be reproducible.

Possible outputs:

- installation scripts
- package manifests
- declarative configs
- system templates
- dotfiles
- boot profiles


## 4. Safety

The platform should prioritize:

- rollback support
- dry-run validation
- snapshot integration
- safe experimentation
- recoverability

---

# Project Philosophy

This project is NOT:

- another Linux distro
- another installer
- another package manager
- another desktop environment

The project is:

> a Linux orchestration and compatibility platform.
> 

The primary innovation is:

> modeling Linux as a dependency and compatibility graph.
> 

---

# Inspiration

This project draws inspiration from:

- NixOS
- Arch Linux
- CachyOS
- Docker
- Ansible
- YaST
- modern game-engine-style tooling
- infrastructure-as-code systems

---

# Long-Term Vision

The long-term goal is to create a platform where users can:

- visually design Linux systems
- generate reproducible environments
- deploy systems safely
- share system blueprints
- build custom operating systems without deep Linux expertise

Potential future capabilities:

- ISO generation
- immutable systems
- cloud deployment
- remote fleet orchestration
- community build marketplace
- live compatibility scoring
- AI-assisted configuration generation

---

# Current Development Direction

The project will begin as a:

> Linux Stack Composer
> 

NOT a full operating system builder.

The first versions will focus on:

- compatibility modeling
- stack visualization
- config generation
- validation

before attempting:

- installers
- ISO generation
- custom kernels
- distro creation

---

# Architecture

The project was prototyped in Rust and is now being rebuilt in Python. The old
prototype is kept under `legacy/rust-hardware-detect/` — its platform-specific
detection commands are still the reference for the port.

## Interface

- Python 3.11+
- [Textual](https://textual.textualize.io/) — a terminal user interface framework

Reasons:

- one language for the whole project instead of two
- no system dependencies, no build step, no packaging toolchain
- runs anywhere Linux runs, including over SSH on a machine with no desktop
- a terminal tool for building Linux systems is in the right register

## Core

- Python, standard library only

The interface is deliberately thin. Everything that matters — the component
catalogue, the compatibility rules, the configuration generator — is plain data
and plain functions with no knowledge of the terminal, so the same core could
later be driven by a web or desktop front end without being rewritten.

## Data Layer

Possible formats:

- JSON
- TOML
- YAML
- SQLite

Used for:

- compatibility rules
- dependency graphs
- system presets
- hardware profiles

---

# Core Systems


## Compatibility Engine

The heart of the platform, and as of milestone 3 the part that exists rather
than the part that is planned. It lives in `lsc/engine.py`, the vocabulary its
rules are written in lives in `lsc/conditions.py`, and the rules themselves are
data in `lsc/data/rules.py`. [How it works](#on-the-compatibility-engine) is
below, under Status.

Responsible for:

- dependency resolution
- conflict detection
- recommendation generation
- stack validation

The relationships that are simply true are fields on a component, and the engine
derives issues from them:

```python
Component(
    id="hyprland",
    requires=("wayland",),
    recommends=("pipewire",),
    kernel_min="6.6",
)
```

The facts with a *condition* attached cannot be written that way — "NVIDIA and
Wayland" is not a conflict, it is a pairing that needs a kernel parameter nobody
tells you about — so those are rules:

```python
Rule(
    id="nvidia-wayland-modeset",
    severity="warning",
    when=AllOf(Has("wayland"), HasAnyOf("nvidia", "nvidia-open")),
    title="NVIDIA on Wayland needs DRM mode setting turned on",
    detail="...no Wayland compositor will start without it...",
    fix="Boot with nvidia_drm.modeset=1...",
)
```


## Hardware Detection Layer

Detects:

- GPU
- CPU
- storage
- network devices
- peripherals

Used for:

- compatibility filtering
- optimization suggestions
- driver recommendations


## Configuration Generator

Generates:

- install scripts
- package manifests
- system configs
- bootloader configs
- dotfiles
- deployment recipes


## Safety Layer

Handles:

- backups
- rollback
- snapshots
- validation
- dry-run mode
- boot fallback logic

---

# Initial Scope

The project should begin with ONE ecosystem only.

Chosen:

- Arch-based Linux

Reasons:

- modular
- composable
- massive package ecosystem
- strong documentation
- ideal for experimentation

Supporting every distro immediately would massively increase complexity.

---

# MVP Features

## Planned MVP

### Stack Selection

- distro base
- desktop environment
- window manager
- audio stack
- filesystem
- GPU stack


### Compatibility Validation

- dependency checks
- conflict warnings
- recommendation engine


### Presets

Examples:

- Gaming
- Developer
- Minimal
- Security Hardened


### Config Generation

Generate:

- installation scripts
- package lists
- config manifests


# Challenges

This project is difficult because Linux itself is highly fragmented.

Major challenges:

- cross-distro compatibility
- undocumented interactions
- rapidly changing ecosystems
- hardware edge cases
- trust and safety
- rollback reliability

The hardest problem is not installation.

The hardest problem is:

> encoding Linux compatibility knowledge into a maintainable system.

---

# Why This Project Exists

Linux is powerful but inaccessible.

The ecosystem still relies heavily on:

- tribal knowledge
- scattered documentation
- manual troubleshooting
- trial and error

This project exists to make Linux:

- more understandable
- more reproducible
- more visual
- more composable
- safer to experiment with

without removing the power and flexibility that make Linux valuable.

---

# Status

**Milestone 3 of 5 — the compatibility engine.**

What works today:

- the full interface: five screens, keyboard navigation, live stack diagram
- the component catalogue: 40 components across 9 categories, with their
  dependencies, conflicts, and recommended pairings written down
- four preset builds, and an export preview that turns a build into file
  contents
- **real hardware detection** on Linux, macOS and Windows, running in a
  background thread so the interface never freezes while it reads
- **the compatibility engine** — resolution before judgement, conditional rules
  with explanations and fixes, and hardware-aware rules that stay silent until a
  machine has actually been read. Described in full below.

What does not work yet, and is not pretended to:

- **package-level dependency solving** — the graph is components, not packages.
  The engine knows Hyprland needs Wayland; it does not know that your mirror is
  missing a library version.
- **kernel versions that keep themselves current** — the numbers the engine
  compares against are written by hand in the catalogue and go stale until
  somebody refreshes them.
- **writing files** — Export shows you what would be generated. It writes
  nothing and installs nothing.

## Milestones

| # | Milestone | State |
|---|-----------|-------|
| 1 | Interface and catalogue | done |
| 2 | Hardware detection — the Rust detector ported to Python | done |
| 3 | Compatibility engine — real rule evaluation | done |
| 4 | Config generation — actually write the files | next |
| 5 | Safety layer — dry runs, snapshots, rollback | planned |

## On the compatibility engine

The placeholder it replaced was a forty-line walk over three tuple fields. Five
things make the difference between that and an engine.

**It resolves before it judges.** Selecting the Hardened security profile pulls
in the hardened kernel, because the profile declares it as a requirement. The
hardened kernel refuses the proprietary NVIDIA driver. The old check never saw
that conflict, because `linux-hardened` was not in the list of things the user
had literally selected. The engine first computes the *effective set* — every
selection plus everything those selections drag in behind them, transitively —
and only then looks for problems:

```
✕  NVIDIA (proprietary) conflicts with linux-hardened

   NVIDIA (proprietary) is selected. linux-hardened is not selected
   directly — it is required by Hardened. They cannot be installed
   together.

   Fix  Change one of the two decisions behind this:
        NVIDIA (proprietary) or Hardened.
```

The chain is the point. An error about a component the user never chose is
useless without it, and the suggested fix names a decision they can actually
revisit rather than the implied component they have no control over.

**It can tell a gap from a contradiction.** "Hyprland requires Wayland and you
have not chosen a display server" is a gap — the answer is to choose one, and the
build will imply it anyway. "Hyprland requires Wayland and you chose Xorg" is a
contradiction: two decisions that cannot both stand, and which one to abandon is
the user's call, not the tool's. The placeholder printed the same sentence for
both.

**It reasons about versions.** Components may declare the oldest kernel they will
run on, and kernel components carry the version of their series, so a floor can
be compared against something real. This one is honestly quiet: with the current
catalogue every floor is met, so it says nothing. It is covered directly by tests
rather than left to rot, and it earns its place the first time a component needs
something newer than the LTS series.

**It knows about the machine, when there is one.** Rules may ask what GPU is in
this computer, how much memory it has, or which modules are loaded right now — so
"the open NVIDIA modules do not support this machine's GPU" is an error on a GTX
1060 and silence on an RTX 4070.

The trap underneath that feature is worth spelling out, because getting it wrong
would make the tool actively misleading. One rule reads *"an NVIDIA driver is
selected, but no NVIDIA GPU was detected"*. Phrased as a negative, evaluated
against a machine nobody has read, it is true of every computer in the world. So
conditions do not silently degrade to false: each one declares whether it reads
hardware, the condition tree propagates that upward, and the engine skips any
rule that needs a reading it does not have. The Validate screen then says how
much of the rule set actually ran:

```
⚠  Build-only check. The rules that ask about the GPU, the memory, or the
   loaded modules are skipped until a scan has run — open Hardware to take one.
   11 of 19 rules ran; 8 need a hardware reading.
```

A tool that gives advice should be able to state how much it looked at. "No
problems found" means something different when a third of the rules were skipped.

**The knowledge is separable from the evaluation.** `lsc/engine.py` contains no
Linux knowledge at all — every sentence a user reads comes from the catalogue or
from a rule. Rules are data, written in a fixed vocabulary of conditions rather
than as Python functions, which is what lets them be counted, printed, tested
for reachability, and eventually loaded from a file instead of a module.

The tests are the part to read if you want to know what the engine really
promises: `tests/test_engine.py` covers resolution, transitive conflicts, the
gap/contradiction distinction, version floors, every hardware rule, and — the one
that matters most — that no hardware rule can fire without a hardware reading.
One test sweeps pairs of choices across the whole catalogue to prove every rule
is reachable, which is the only way a typo in a component id inside a rule ever
becomes visible.

## On the detector

Ported from `legacy/rust-hardware-detect/`, with three deliberate changes.

**It does not install anything.** The prototype ran `sudo pacman -S pciutils`
when `lspci` was missing. Reading `/sys/bus/pci/devices/` gives the vendor of
every display controller with no external command and no root, so the
dependency was never needed. A tool asked to *look at* a machine must not
install packages as a side effect — least of all a project whose README
promises a safety layer.

**Windows takes one query instead of five.** The prototype started PowerShell
separately for the kernel, the board, the GPUs, the drivers and the network,
and each start costs the better part of a second. One script returning JSON
turns several seconds into roughly one.

**It cannot fail.** Every field falls back to `Unknown` rather than raising, so
a machine with no `ip`, no `lspci`, or a restricted `/proc` still reports its
CPU and memory. A partial reading is useful; an exception is not.

---

# Running it

Requires Python 3.11 or newer. The launcher creates the virtual environment
and installs dependencies the first time you run it, and works from any
directory.

**Linux / macOS**

```bash
./run.sh
```

**Windows** — from PowerShell, or by double-clicking `run.cmd`:

```powershell
.\run.ps1
```

Best in a terminal at least 120 columns wide. Press `1`–`5` to move between
screens, `t` to switch to a light theme for a projector, and `q` to quit.

## Tests

```bash
./run.sh --test          # Windows: .\run.ps1 -Test
```

## Hardware, without the interface

Prints the detected machine as JSON — the same reading the Hardware screen
shows, and the closest equivalent to what the Rust prototype produced:

```bash
./run.sh --report        # Windows: .\run.ps1 -Report
```

## Layout

```
lsc/
  app.py            the shell: theme, tabs, key bindings, the single Build
  models.py         Component, Category, Build, Issue — plain dataclasses
  content.py        every piece of interface copy, in one file
  engine.py         the compatibility engine: resolve, then judge
  conditions.py     the vocabulary a rule may speak, and the Context it reads
  export.py         a build rendered as packages.txt / install.sh / system.toml
  detect/           hardware detection, ported from the Rust prototype
    linux.py          /proc, /sys, and the PCI bus
    macos.py          sysctl, system_profiler, kextstat
    windows.py        one CIM query, parsed from JSON
  data/
    catalog.py      the 40 components and their relationships
    rules.py        the curated rules — knowledge that needs a condition
    presets.py      Gaming, Developer, Minimal, Security Hardened
    hardware.py     the sample profile, and the seam detection plugs into
  screens/          one module per screen
  widgets/          the stack diagram and small shared pieces
  styles/app.tcss   all colours, as theme variables
legacy/
  rust-hardware-detect/   the original Rust prototype, kept for reference
run.sh / run.ps1 / run.cmd   launchers that also do first-run setup
```

---

# Contributing

Contributions are welcome in areas such as:

- Linux internals
- kernel knowledge
- packaging systems
- desktop environments
- Wayland/X11
- security
- hardware compatibility
- UI/UX design
- Python development
- documentation

---

# Future Possibilities

Potential future features:

- visual kernel configuration
- rollback-aware live system editing
- immutable system generation
- AI-assisted compatibility resolution
- boot profile management
- performance tuning presets
- cloud image deployment
- distributed system orchestration

---

# Final Goal

The final goal is not simply to create another Linux tool.

The goal is to create:

> a modern platform for designing, understanding, and composing Linux systems intelligently.
>
