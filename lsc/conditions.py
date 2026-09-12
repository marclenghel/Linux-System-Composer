"""The vocabulary a compatibility rule is allowed to speak.

A rule in this project is data, not code: it says *when* it applies using the
small set of conditions below, and the engine evaluates them. That restriction
is the whole point. A rule written as a Python function could do anything, could
not be counted, and could not be explained to anyone; a rule written as
`AllOf(Has("hyprland"), HasAnyOf("nvidia", "nvidia-open"))` can be listed,
tested, and eventually loaded from a file instead of a module.

Nothing here knows about the terminal, and nothing here knows about any specific
component — the knowledge lives in data/rules.py, the machinery lives here.

One trap is worth pointing out. Conditions that ask about the machine only mean
something when a real machine has actually been read. If `GpuVendor("NVIDIA")`
simply returned False on a build with no detected hardware, then
`Not(GpuVendor("NVIDIA"))` would return *True*, and every rule phrased in the
negative would fire on a machine nobody had looked at. So conditions do not
silently degrade: each one reports whether it needs hardware, `Condition`
propagates that up the tree, and the engine skips any rule whose conditions need
a reading it does not have.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Mapping


# ── What a rule gets to look at ───────────────────────────────────────────────


@dataclass
class Context:
    """Everything a rule may ask about, in the form it wants to ask.

    Built once per evaluation by the engine. `effective` is the important one:
    it holds not only what the user picked but everything those picks drag in
    behind them, which is why this engine can see conflicts the naive check
    could not.
    """

    # category id -> component id, exactly as the user chose it
    selections: Mapping[str, str] = field(default_factory=dict)

    # component id -> the chain that brought it in; empty tuple means "chosen
    # directly", ("hardened",) means "pulled in because hardened requires it"
    effective: Mapping[str, tuple[str, ...]] = field(default_factory=dict)

    # Every tag carried by any effective component, flattened for cheap lookup.
    tags: frozenset[str] = frozenset()

    # The version of the kernel this build would run, as (major, minor).
    kernel_version: tuple[int, ...] | None = None

    # The machine, and whether it was actually read. The sample profile is not a
    # machine, and rules must not treat it as one.
    hardware: Mapping[str, Any] | None = None
    hardware_is_real: bool = False

    # ── derived hardware facts ────────────────────────────────────────────────
    #
    # Computed once here rather than re-derived inside every condition, so a
    # rule about the GPU vendor reads like a sentence instead of a dict walk.

    gpu_vendors: frozenset[str] = frozenset()
    gpu_names: tuple[str, ...] = ()
    modules: frozenset[str] = frozenset()
    ram_gb: float | None = None
    cpu_arch: str | None = None

    def __post_init__(self) -> None:
        profile = self.hardware or {}
        gpus = profile.get("gpus") or []
        self.gpu_vendors = frozenset(
            str(gpu.get("vendor", "")).upper() for gpu in gpus if gpu.get("vendor")
        )
        self.gpu_names = tuple(str(gpu.get("name", "")) for gpu in gpus if gpu.get("name"))
        self.modules = frozenset(
            str(driver.get("name", "")) for driver in profile.get("drivers") or []
        )
        ram = (profile.get("ram") or {}).get("total_gb")
        self.ram_gb = float(ram) if isinstance(ram, (int, float)) and ram else None
        self.cpu_arch = (profile.get("cpu") or {}).get("arch") or None


# ── The conditions themselves ─────────────────────────────────────────────────


class Condition:
    """Base class. Subclasses implement `holds`, and that is all they do."""

    #: True on conditions that read the detected machine.
    reads_hardware: bool = False

    #: Sub-conditions, for the combinators.
    children: tuple["Condition", ...] = ()

    def holds(self, ctx: Context) -> bool:  # pragma: no cover - abstract
        raise NotImplementedError

    @property
    def needs_hardware(self) -> bool:
        """Whether anything in this tree asks about the machine.

        The engine uses this to skip a rule outright rather than let it draw a
        conclusion from a reading that was never taken.
        """
        return self.reads_hardware or any(child.needs_hardware for child in self.children)


# -- combinators ---------------------------------------------------------------


@dataclass(frozen=True)
class AllOf(Condition):
    """True when every part is true."""

    parts: tuple[Condition, ...]

    def __init__(self, *parts: Condition) -> None:
        object.__setattr__(self, "parts", parts)

    @property
    def children(self) -> tuple[Condition, ...]:  # type: ignore[override]
        return self.parts

    def holds(self, ctx: Context) -> bool:
        return all(part.holds(ctx) for part in self.parts)


@dataclass(frozen=True)
class AnyOf(Condition):
    """True when at least one part is true."""

    parts: tuple[Condition, ...]

    def __init__(self, *parts: Condition) -> None:
        object.__setattr__(self, "parts", parts)

    @property
    def children(self) -> tuple[Condition, ...]:  # type: ignore[override]
        return self.parts

    def holds(self, ctx: Context) -> bool:
        return any(part.holds(ctx) for part in self.parts)


@dataclass(frozen=True)
class Not(Condition):
    """True when the inner condition is false."""

    inner: Condition

    @property
    def children(self) -> tuple[Condition, ...]:  # type: ignore[override]
        return (self.inner,)

    def holds(self, ctx: Context) -> bool:
        return not self.inner.holds(ctx)


# -- the build -----------------------------------------------------------------


@dataclass(frozen=True)
class Has(Condition):
    """True when every named component is in the build, directly or implied."""

    ids: tuple[str, ...]

    def __init__(self, *ids: str) -> None:
        object.__setattr__(self, "ids", ids)

    def holds(self, ctx: Context) -> bool:
        return all(component_id in ctx.effective for component_id in self.ids)


@dataclass(frozen=True)
class HasAnyOf(Condition):
    """True when at least one of the named components is in the build."""

    ids: tuple[str, ...]

    def __init__(self, *ids: str) -> None:
        object.__setattr__(self, "ids", ids)

    def holds(self, ctx: Context) -> bool:
        return any(component_id in ctx.effective for component_id in self.ids)


@dataclass(frozen=True)
class Chose(Condition):
    """True when this exact component is the answer to this exact category.

    Different from `Has`: this one ignores implied components, which matters
    when a rule is about a decision the user made rather than a consequence.
    """

    category_id: str
    component_id: str

    def holds(self, ctx: Context) -> bool:
        return ctx.selections.get(self.category_id) == self.component_id


@dataclass(frozen=True)
class CategoryFilled(Condition):
    """True when the user has answered this category at all."""

    category_id: str

    def holds(self, ctx: Context) -> bool:
        return bool(ctx.selections.get(self.category_id))


@dataclass(frozen=True)
class Tagged(Condition):
    """True when any component in the build carries this tag.

    Lets a rule talk about a kind of component rather than a list of ids, so
    adding a fifth tiling compositor to the catalogue does not mean editing
    every rule that already covers the other four.
    """

    tag: str

    def holds(self, ctx: Context) -> bool:
        return self.tag in ctx.tags


@dataclass(frozen=True)
class KernelBelow(Condition):
    """True when the build's kernel is older than the given version.

    Unknown counts as false: refusing to guess is better than inventing a
    version number and warning about it.
    """

    version: str

    def holds(self, ctx: Context) -> bool:
        if ctx.kernel_version is None:
            return False
        return ctx.kernel_version < parse_version(self.version)


# -- the machine ---------------------------------------------------------------


@dataclass(frozen=True)
class GpuVendor(Condition):
    """True when the machine has at least one GPU from any of these vendors."""

    reads_hardware = True
    vendors: tuple[str, ...]

    def __init__(self, *vendors: str) -> None:
        object.__setattr__(self, "vendors", tuple(v.upper() for v in vendors))

    def holds(self, ctx: Context) -> bool:
        return bool(ctx.gpu_vendors & set(self.vendors))


@dataclass(frozen=True)
class OnlyGpuVendors(Condition):
    """True when every GPU the machine reported is from one of these vendors.

    False when no GPU was reported at all — "all of nothing" is technically true
    and practically useless.
    """

    reads_hardware = True
    vendors: tuple[str, ...]

    def __init__(self, *vendors: str) -> None:
        object.__setattr__(self, "vendors", tuple(v.upper() for v in vendors))

    def holds(self, ctx: Context) -> bool:
        return bool(ctx.gpu_vendors) and ctx.gpu_vendors <= set(self.vendors)


@dataclass(frozen=True)
class NvidiaPreTuring(Condition):
    """True when the machine has an NVIDIA GPU older than the RTX 20 series.

    The cut matters because NVIDIA's open kernel modules simply do not support
    anything before Turing, so recommending them on a GTX 1060 is not a
    suggestion, it is a machine that will not start a graphical session.
    """

    reads_hardware = True

    def holds(self, ctx: Context) -> bool:
        return any(is_pre_turing_nvidia(name) for name in ctx.gpu_names)


@dataclass(frozen=True)
class ModuleLoaded(Condition):
    """True when this kernel module is loaded on the machine right now.

    The strongest evidence the detector can offer: not "this hardware could use
    btrfs" but "this machine is mounting btrfs as you read this".
    """

    reads_hardware = True
    name: str

    def holds(self, ctx: Context) -> bool:
        return self.name in ctx.modules


@dataclass(frozen=True)
class RamBelowGb(Condition):
    """True when the machine has less memory than this."""

    reads_hardware = True
    gb: float

    def holds(self, ctx: Context) -> bool:
        return ctx.ram_gb is not None and ctx.ram_gb < self.gb


@dataclass(frozen=True)
class CpuArch(Condition):
    """True when the machine's CPU architecture is one of these."""

    reads_hardware = True
    arches: tuple[str, ...]

    def __init__(self, *arches: str) -> None:
        object.__setattr__(self, "arches", arches)

    def holds(self, ctx: Context) -> bool:
        return ctx.cpu_arch in self.arches


# ── version helpers ───────────────────────────────────────────────────────────


def parse_version(text: str | None) -> tuple[int, ...]:
    """Turn "6.12.8-arch1-1" into (6, 12, 8).

    Deliberately forgiving, because kernel version strings are a zoo: distro
    suffixes, release candidates, and vendor tags all have to fall off without
    taking the numbers with them. Returns () for anything unreadable, which
    every caller treats as "unknown" rather than as zero.
    """
    if not text:
        return ()
    match = re.match(r"\s*v?(\d+(?:\.\d+)*)", text)
    if not match:
        return ()
    return tuple(int(part) for part in match.group(1).split("."))


def is_pre_turing_nvidia(name: str) -> bool:
    """Whether an NVIDIA marketing name denotes a card older than Turing.

    Name matching, and it is worth being explicit about why that is acceptable
    here while it was not acceptable as a whole compatibility story: the answer
    only needs one bit, the naming is public and stable, and being wrong costs a
    missing note rather than a broken build.

    The catch is the GTX 16-series. A GTX 1650 is Turing, a GTX 1060 is Pascal,
    and the only thing separating them is the second digit — so the 16-series
    has to be matched before the "GTX 1x" families it otherwise looks like.
    """
    upper = name.upper()
    if "RTX" in upper:
        return False
    match = re.search(r"\b(?:GTX|GT)\s*(\d{3,4})\b", upper)
    if not match:
        return False
    number = match.group(1)
    # GTX 1630/1650/1660 are Turing; everything else in the 10-series is Pascal.
    if number.startswith("16") and len(number) == 4:
        return False
    return True


def describe(condition: Condition) -> str:
    """A readable form of a condition, for tests and for explaining a rule.

    Not shown in the interface today. It exists because a rule engine whose
    rules cannot be printed is a rule engine nobody will trust.
    """
    if isinstance(condition, AllOf):
        return " and ".join(describe(part) for part in condition.parts)
    if isinstance(condition, AnyOf):
        return "(" + " or ".join(describe(part) for part in condition.parts) + ")"
    if isinstance(condition, Not):
        return f"not {describe(condition.inner)}"
    if isinstance(condition, Has):
        return " and ".join(condition.ids)
    if isinstance(condition, HasAnyOf):
        return "(" + " or ".join(condition.ids) + ")"
    if isinstance(condition, Chose):
        return f"{condition.category_id}={condition.component_id}"
    if isinstance(condition, CategoryFilled):
        return f"{condition.category_id} answered"
    if isinstance(condition, Tagged):
        return f"tagged {condition.tag}"
    if isinstance(condition, KernelBelow):
        return f"kernel < {condition.version}"
    if isinstance(condition, GpuVendor):
        return "GPU from " + "/".join(condition.vendors)
    if isinstance(condition, OnlyGpuVendors):
        return "only " + "/".join(condition.vendors) + " GPUs"
    if isinstance(condition, NvidiaPreTuring):
        return "pre-Turing NVIDIA GPU"
    if isinstance(condition, ModuleLoaded):
        return f"module {condition.name} loaded"
    if isinstance(condition, RamBelowGb):
        return f"RAM < {condition.gb:g} GB"
    if isinstance(condition, CpuArch):
        return "CPU is " + "/".join(condition.arches)
    return condition.__class__.__name__


__all__ = [
    "AllOf",
    "AnyOf",
    "CategoryFilled",
    "Chose",
    "Condition",
    "Context",
    "CpuArch",
    "GpuVendor",
    "Has",
    "HasAnyOf",
    "KernelBelow",
    "ModuleLoaded",
    "Not",
    "NvidiaPreTuring",
    "OnlyGpuVendors",
    "RamBelowGb",
    "Tagged",
    "describe",
    "is_pre_turing_nvidia",
    "parse_version",
]
