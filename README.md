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
      - [Rules are data](#rules-are-data)
      - [Three answers, not two](#three-answers-not-two)
      - [Following the graph](#following-the-graph)
      - [The worked example](#the-worked-example)
      - [Where the knowledge lives](#where-the-knowledge-lives)
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

Today the catalogue, the rules and the presets are Python data structures —
frozen dataclasses, no logic in them — held in `lsc/data/`.

They are written that way rather than as TOML on purpose, and the choice is
reversible by design: every condition and every rule serialises to JSON and
back, and a test evaluates both copies against every fixture to prove the two
agree. Moving the rule set into a file is therefore a loader, not a rewrite.

Python first buys type checking, autocompletion, and a typo that fails a test
instead of crashing at start-up. TOML later buys rules that can be edited and
shared without touching the program. The intended order is to get the knowledge
right, then move it.

---

# Core Systems


## Compatibility Engine

The heart of the platform, and as of milestone 3 it is real. Full reference in
[docs/rules.md](docs/rules.md).

Responsible for:

- dependency resolution, following the graph rather than one hop
- conflict detection, including conflicts nothing in the data states directly
- version constraints
- reasoning about the hardware actually present
- explaining every issue, and suggesting a way forward

### Rules are data

A rule is not a Python function. It is a tree of small frozen records the
evaluator walks:

```python
Rule(
    id="nvidia-open-needs-turing",
    severity="error",
    when=AllOf(
        Selected("nvidia-open"),
        Fact("hardware.gpu.nvidia_rank", "lt", gpus.TURING),
    ),
    title="{gpu.name} is too old for the open NVIDIA kernel modules",
    detail="The open kernel modules only drive cards with the GSP "
           "microcontroller, which arrived with Turing. This machine "
           "reports a {gpu.name}, which is {gpu.architecture}...",
    fix="Choose NVIDIA (proprietary) instead.",
    suggest=Suggestion("gpu", "nvidia"),
)
```

Why records and not lambdas: a lambda cannot be written to a TOML file. The
data layer below is supposed to hold compatibility rules, and a rule set that
only exists as Python has to be rewritten the day it moves out of Python. A
tree of records survives the round trip to JSON and back — and the test suite
serialises the whole rule set, reads it back, and checks both copies produce
identical results, so that is a checked property rather than an intention.

### Three answers, not two

A condition returns true, false, or **unknown**. "Is the graphics card older
than Turing?" has no answer until the machine has been scanned, and answering
*false* there would quietly pass a build that is about to fail.

So unknown propagates, and the Validate screen lists what it could not check
alongside what it found. A check that was skipped silently is indistinguishable
from one that passed.

The same principle covers a graphics card the model table does not recognise:
it gets no generation, every rule about generations goes unknown, and the
engine says so. Refusing someone a driver because a lookup table is out of date
would be exactly the kind of confident wrongness this project exists to avoid.

### Following the graph

Nothing in the catalogue says the Hardened security profile conflicts with the
proprietary NVIDIA driver. It says Hardened needs `linux-hardened`, and
separately that `linux-hardened` refuses to sit beside `nvidia`. An engine that
looks one hop finds nothing wrong with that build. This one walks the requires
edges, keeps the path, and reports:

```
✕  linux-hardened conflicts with NVIDIA (proprietary)

   linux-hardened and NVIDIA (proprietary) cannot be installed on the
   same system.

   linux-hardened is not something you picked directly — it is pulled
   in by Hardened:  Hardened → linux-hardened

   Fix  Drop one of them — replace linux-hardened under Kernel, or
        NVIDIA (proprietary) under GPU Driver.
```

### The worked example

Selecting Hyprland alongside an NVIDIA driver produces the specific warning
this README has promised since the first commit — DRM mode setting, the
initramfs modules, explicit sync and the driver version it needs, and XWayland
— rather than a generic "these conflict". There is a test for each of those
four points, because a promise in a README is worth what its test is worth.

### Where the knowledge lives

```
lsc/conditions.py     the language      nodes, three-valued logic, JSON round trip
lsc/facts.py          the world         a Build + a hardware reading -> facts
lsc/engine.py         the interpreter   graph closure, evaluation, templating
lsc/data/rules.py     the knowledge     the rules themselves
lsc/data/gpus.py      a lookup table    GPU model -> architecture, capability
lsc/checks.py         the façade        what the screens call
```

Plain "X requires Y" and "X conflicts with Y" stay in the catalogue next to the
component, and the engine turns those edges into issues itself. Only knowledge
with a *condition* in it — "if this and that", anything with a version,
anything about the machine — is written as a rule.


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
- **the compatibility engine** — conditional rules, version constraints,
  transitive resolution through the dependency graph, and rules that reason
  about the card actually in the machine. Every rule is data, and every issue
  carries an explanation and a way forward. See
  [Compatibility Engine](#compatibility-engine) below and
  [docs/rules.md](docs/rules.md).
- **detection feeding composition** — the advice on the Hardware screen is now
  the engine's advice, with the rule that produced it named underneath

What does not work yet, and is not pretended to:

- **writing files** — Export shows you what would be generated. It writes
  nothing and installs nothing.
- **package-level resolution** — the engine reasons about components, not about
  individual packages and their versions. That is pacman's job, and this tool
  stops where pacman starts.
- **a complete rule set** — the rules cover the interactions worth knowing
  about, not the whole of Linux. Validate lists the checks it could not make
  rather than passing over them in silence.

## Milestones

| # | Milestone | State |
|---|-----------|-------|
| 1 | Interface and catalogue | done |
| 2 | Hardware detection — the Rust detector ported to Python | done |
| 3 | Compatibility engine — real rule evaluation | done |
| 4 | Config generation — actually write the files | next |
| 5 | Safety layer — dry runs, snapshots, rollback | planned |

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

161 tests. Most of them guard data rather than behaviour, because the data is
where this project's value is and where a mistake is hardest to see by
reading: relationship ids that point at nothing, presets that do not install,
a rule that can never fire, a GPU pattern that shadows the one below it.

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
  conditions.py     the rule language: condition nodes, three-valued logic
  facts.py          a Build plus a hardware reading, as one namespace of facts
  engine.py         the evaluator: graph closure, rule evaluation, templating
  checks.py         the façade the screens call
  export.py         a build rendered as packages.txt / install.sh / system.toml
  detect/           hardware detection, ported from the Rust prototype
    linux.py          /proc, /sys, and the PCI bus
    macos.py          sysctl, system_profiler, kextstat
    windows.py        one CIM query, parsed from JSON
  data/
    catalog.py      the 40 components and their relationships
    rules.py        the compatibility rules, as data
    gpus.py         GPU model strings -> architecture and capability
    presets.py      Gaming, Developer, Minimal, Security Hardened
    hardware.py     the sample profile, and the seam detection plugs into
  screens/          one module per screen
  widgets/          the stack diagram and small shared pieces
  styles/app.tcss   all colours, as theme variables
docs/
  rules.md          how to write a compatibility rule
tests/
  fixtures.py       fixture machines and builds, shared by the rule tests
legacy/
  rust-hardware-detect/   the original Rust prototype, kept for reference
run.sh / run.ps1 / run.cmd   launchers that also do first-run setup
```

Nothing under `models.py`, `conditions.py`, `facts.py`, `engine.py`,
`checks.py`, `export.py`, `data/` or `detect/` imports anything from the
interface. The entire compatibility engine was added in milestone 3 without a
single screen changing its imports, which is what that separation was for.

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
