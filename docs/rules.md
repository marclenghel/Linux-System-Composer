# Writing a compatibility rule

This is the reference for the rule language added in milestone 3. It covers
what a rule is, what it can ask about the world, and the rules the rules
themselves have to follow.

The short version: **a rule is data, not code.** It is a tree of small frozen
records that the evaluator walks. Nothing in `lsc/data/rules.py` runs.

- [Why data and not functions](#why-data-and-not-functions)
- [The shape of a rule](#the-shape-of-a-rule)
- [Conditions](#conditions)
- [Three-valued logic](#three-valued-logic)
- [The fact namespace](#the-fact-namespace)
- [Message templates](#message-templates)
- [Where a rule belongs](#where-a-rule-belongs)
- [What the tests will demand](#what-the-tests-will-demand)
- [How the pieces fit](#how-the-pieces-fit)

---

## Why data and not functions

A lambda cannot be written to a TOML file, and a string of Python cannot be
evaluated without handing every rule file the power to run anything on the
machine. Neither is acceptable in a project whose README promises a data layer
holding compatibility rules and a safety layer around everything it touches.

A tree of records is neither. It serialises, it is inspectable, and it cannot
do anything the evaluator does not let it do.

The claim is checked, not assumed: `tests/test_rules.py` writes the entire rule
set to JSON, reads it back, and evaluates both copies against every fixture. If
they ever disagree, the test fails. Moving the rules into TOML later is
therefore a loader — perhaps forty lines — and not a rewrite of the evaluator.

## The shape of a rule

```python
Rule(
    id="nvidia-open-needs-turing",          # stable; shown in the interface
    severity="error",                       # error | warning | info
    when=AllOf(
        Selected("nvidia-open"),
        Fact("hardware.gpu.nvidia_rank", "lt", gpus.TURING),
    ),
    title="{gpu.name} is too old for the open NVIDIA kernel modules",
    detail="The open kernel modules only drive cards that have the GSP "
           "microcontroller, which arrived with Turing...",
    fix="Choose NVIDIA (proprietary) instead.",
    suggest=Suggestion("gpu", "nvidia"),    # the fix a program could apply
    reference="https://wiki.archlinux.org/title/NVIDIA#Installation",
    needs="a graphics card this project's model table recognises",
)
```

| Field | Meaning |
|---|---|
| `id` | Stable identifier. Shown under every issue so a user can trace a message back to the data that produced it. |
| `severity` | `error` blocks the build; `warning` and `info` do not. |
| `when` | The condition tree. |
| `title` / `detail` / `fix` | Templates, rendered against the world's bindings. |
| `suggest` | Optional. The same advice as `fix`, in a form a program can act on. |
| `reference` | Optional. Where to read more. Must be `https://`. |
| `needs` | What would have to be known for this rule to reach an answer. Only shown when the rule is undecided. |

`fix` is mandatory. An issue with no way forward is treated as a bug in the
rule, because the README's promise is that this tool *explains*
incompatibilities rather than refusing them.

## Conditions

| Node | True when |
|---|---|
| `Selected(id)` | that component is in the build |
| `AnySelected(id, id, ...)` | at least one of them is |
| `CategoryIs(category, id)` | that category's answer is exactly that component |
| `CategoryEmpty(category)` | that category has no answer |
| `HasTag(tag)` | any selected component carries the tag |
| `Fact(key, op, value)` | the fact compares as asked |
| `VersionAtLeast(key, "6.6")` | the version in that fact is that or newer |
| `VersionBelow(key, "6.6")` | the version in that fact is older |
| `AllOf(...)` / `AnyOf(...)` / `Not(...)` | the usual, with the twist below |

`Fact` operators: `eq`, `ne`, `lt`, `lte`, `gt`, `gte`, `in`, `contains`.
`in` asks whether the fact is one of the values given; `contains` asks whether
the fact (a list or a string) holds the value given. An unknown operator raises
when the rule is constructed, so a typo fails at import rather than making the
rule silently never fire.

Prefer `HasTag` over a long `AnySelected` when the catalogue already knows the
answer. "Any Wayland compositor" is a tag, and writing it as a tag means adding
a new compositor later does not mean editing every rule about compositors.

## Three-valued logic

Conditions answer **true**, **false**, or **unknown**, and unknown is the
reason this section exists.

"Is the graphics card older than Turing?" has no answer until the machine has
been scanned. Answering *false* there would quietly pass a build that is about
to fail; answering *true* would invent hardware. So the answer is unknown, it
propagates the way Kleene's logic says it should, and the Validate screen lists
the rule under **Not checked** with its `needs` line.

```
AllOf:  any false  -> false        (even with unknowns present)
        else any unknown -> unknown
        else true

AnyOf:  any true   -> true         (even with unknowns present)
        else any unknown -> unknown
        else false

Not:    unknown -> unknown
```

The `AllOf` short circuit matters: a rule about Hyprland must not report itself
as unchecked on a build containing no Hyprland, however little is known about
the graphics card.

**A missing fact is always unknown, never false.** This is why every
filesystem in the catalogue declares `fs.out_of_tree`, including the ones for
which the answer is boring — leaving it out would make the engine say it could
not tell whether ext4 is in the kernel tree, which it plainly can.

## The fact namespace

One flat namespace, two halves. A rule compares a floor the *build* promises
against a floor the *machine* provides with the same operator, and neither the
evaluator nor the rule cares which side a fact came from.

### `build.*` — always present

`build.<category_id>` is the selected component's id, or the string `"none"`
when nothing is selected. Never absent, so it is never unknown.

### Facts a component provides

A component contributes facts through `Component.provides`:

```python
Component(
    id="linux-lts",
    provides=(("kernel.version", "6.12"), ("kernel.channel", "lts")),
    ...
)
```

Currently provided: `kernel.version`, `kernel.channel`, `driver.branch`,
`driver.out_of_tree`, `fs.snapshots`, `fs.out_of_tree`.

Kernel versions are stated as **floors** — "choosing this gets you at least
this" — rather than as whatever Arch ships today. A floor only ever
understates, so a rule built on one can warn that a kernel is too old and can
never wrongly promise that one is new enough. `CATALOGUE_AS_OF` in
`lsc/data/catalog.py` records when they were last checked.

### `hardware.*` — absent until a real scan

| Fact | Type |
|---|---|
| `hardware.platform` | `linux` / `macos` / `windows` |
| `hardware.os`, `hardware.kernel`, `hardware.motherboard` | string |
| `hardware.cpu.brand`, `hardware.cpu.arch` | string |
| `hardware.cpu.cores` | int |
| `hardware.ram_gb` | float |
| `hardware.gpu.count` | int |
| `hardware.gpu.vendors` | tuple of strings |
| `hardware.gpu.has_nvidia` / `has_amd` / `has_intel` | bool |
| `hardware.gpu.nvidia_rank` | int — **absent if the model is unrecognised** |
| `hardware.modules` | tuple of loaded module names |
| `hardware.disk.types` | tuple of strings |
| `hardware.is_virtual` | bool |

Two deliberate decisions live in this table.

**The sample profile is refused.** `HardwareFacts.from_profile` returns `None`
for anything not marked as a real reading. The Hardware screen shows a fixture
until detection returns, and firing hardware rules against it would put "your
GeForce RTX 4070 Ti is Ada" on screen for someone sitting at a different
machine.

**`hardware.gpu.nvidia_rank` is absent for an unrecognised card.** The model
table in `lsc/data/gpus.py` maps a string like `GA106 [GeForce RTX 3060]` to
Ampere and a rank. A card released after the table was last edited gets no
rank, the fact is absent, and every rule about generations goes unknown.
Refusing someone a driver because a lookup table is out of date would be
exactly the kind of confident wrongness this project exists to avoid.

## Message templates

`title`, `detail` and `fix` are rendered against the world's bindings, so a
rule can name a specific card without running any Python.

| Binding | Example |
|---|---|
| `{gpu.name}` `{gpu.vendor}` `{gpu.architecture}` | the headline detected GPU |
| `{machine.kernel}` `{machine.os}` `{machine.cpu}` `{machine.ram_gb}` | the detected machine |
| `{choice.<category_id>}` | the *display name* of what is selected, e.g. `NVIDIA (proprietary)` |
| any provided fact key | `{kernel.version}` |

Dotted names are looked up as single flat keys, not as attribute access. A
missing binding renders as `?` rather than raising — and a test asserts that
every placeholder in every rule resolves in the situations where that rule
actually fires, so a `?` should never reach a user.

**Literal braces break templates.** Write `kernel_min 6.6`, not
`{"kernel_min": "6.6"}`.

## Where a rule belongs

| Knowledge | Where it goes |
|---|---|
| "X requires Y" | `requires=` on the component, in the catalogue |
| "X conflicts with Y" | `conflicts=` on the component |
| "X pairs well with Y" | `recommends=` on the component |
| "if X **and** Y, then..." | a rule in `lsc/data/rules.py` |
| anything with a version in it | a rule |
| anything about the actual machine | a rule |

The engine turns the catalogue's edges into issues by itself, including
transitively. Restating a plain requirement as a rule creates two places to be
wrong.

Transitivity is worth spelling out, because it is where the engine earns its
name. The catalogue nowhere says that the Hardened security profile conflicts
with the proprietary NVIDIA driver. It says Hardened needs `linux-hardened`,
and separately that `linux-hardened` refuses to sit beside `nvidia`. The engine
walks the `requires` edges, keeps the path it walked, and reports:

```
linux-hardened conflicts with NVIDIA (proprietary)

linux-hardened is not something you picked directly — it is pulled
in by Hardened:  Hardened → linux-hardened
```

## What the tests will demand

Adding a rule means `tests/test_rules.py` will insist on all of this:

- the `id` is unique
- every component the condition names exists in the catalogue
- `severity` is one of the three the interface can draw
- `title`, `detail` and `fix` are all non-empty
- a `suggest` names a component that really is in the category it names
- a `reference`, if present, is `https://`
- every placeholder resolves wherever the rule fires
- no rendered message leaks a `{` or `}`
- **the rule fires in at least one scenario**

That last one is the important one. A rule that can never fire looks exactly
like a rule that works. Adding a rule usually means adding the scenario in
`SCENARIOS` that proves it fires, which is the intended cost.

A rule that no build in the current catalogue can trigger — because the
constraint is real but every available choice already satisfies it — goes in
`SYNTHETIC_WORLDS` with the world that proves it works. That list is meant to
stay short, and a separate test fails if something in it can in fact be
triggered by a real build.

## How the pieces fit

```
lsc/conditions.py     the language    nodes, three-valued logic, JSON round trip
lsc/facts.py          the world       a Build + a hardware reading -> facts
lsc/engine.py         the interpreter graph closure, rule evaluation, templating
lsc/data/rules.py     the knowledge   the rules themselves
lsc/data/gpus.py      a lookup table  GPU model string -> architecture, capability
lsc/checks.py         the façade      what the screens call
```

None of these imports Textual, and none of them writes to the system.
