"""The world a rule is evaluated against.

A rule never touches a Build, a hardware report, or the catalogue directly. It
asks the World, and the World answers in one flat namespace of facts. That
indirection is what lets a rule compare a floor the *build* promises against a
floor the *machine* provides with the same operator, without knowing or caring
which side a fact came from.

Two namespaces of facts exist:

    build.*       what the user chose, and what those choices provide
    hardware.*    what the detector found on this machine

and the difference between them is deliberate. Every build.* fact is always
present, because the composer always knows what is and is not selected — an
empty category reads as the string "none", never as a missing fact. Every
hardware.* fact is absent until a real scan has finished, so a rule that
depends on the machine evaluates to UNKNOWN rather than guessing.

That last point is a decision, not an accident. The Hardware screen shows a
sample profile until detection returns, and firing hardware rules against a
fixture would put sentences like "your GeForce RTX 4070 Ti is Ada" on screen
for someone sitting at a ThinkPad. HardwareFacts.from_profile refuses anything
that is not a real reading, and the Validate screen says plainly that those
rules were not checked.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from lsc.data import gpus
from lsc.data.catalog import CATEGORIES, COMPONENTS_BY_ID
from lsc.detect import SOURCE_DETECTED
from lsc.models import Build

# What an unanswered category reads as in the fact namespace. A string rather
# than None, because None means "cannot tell" to every condition and an
# unanswered question is something the composer can tell you about precisely.
NOT_SET = "none"


# ── the machine ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class GpuFact:
    """One detected graphics device, with the model string resolved."""

    vendor: str
    name: str
    architecture: str = "unknown"
    rank: int = gpus.UNKNOWN_RANK

    @property
    def recognised(self) -> bool:
        return self.rank != gpus.UNKNOWN_RANK


@dataclass(frozen=True)
class HardwareFacts:
    """A detected machine, normalised into the shapes rules ask about."""

    platform: str = "unknown"          # which detector read this: linux | macos | windows
    os: str = "Unknown"
    kernel: str = "Unknown"
    cpu_brand: str = "Unknown"
    cpu_cores: int = 0
    cpu_arch: str = "unknown"
    ram_gb: float = 0.0
    motherboard: str = "Unknown"
    gpus: tuple[GpuFact, ...] = ()
    modules: frozenset[str] = frozenset()
    disk_types: tuple[str, ...] = ()

    @classmethod
    def from_profile(cls, profile: Mapping[str, Any] | None) -> HardwareFacts | None:
        """Normalise a detector report, or return None if it is not a real one.

        None is returned for the sample profile, for a missing profile, and for
        a scan that failed outright. Every caller treats None as "hardware is
        unknown", which is the only honest reading of any of those three.
        """
        if not profile or profile.get("source") != SOURCE_DETECTED:
            return None

        detected_gpus = []
        for entry in profile.get("gpus", []) or []:
            name = str(entry.get("name", "")).strip()
            vendor = str(entry.get("vendor", "Unknown")).strip()
            family = gpus.identify(f"{vendor} {name}")
            detected_gpus.append(
                GpuFact(
                    # The detector's vendor string is the authority on the
                    # vendor; the table is only consulted for the generation,
                    # which the detector has no opinion about.
                    vendor=vendor or (family.vendor if family else "Unknown"),
                    name=name or "Unknown",
                    architecture=family.architecture if family else "unknown",
                    rank=family.rank if family else gpus.UNKNOWN_RANK,
                )
            )

        cpu = profile.get("cpu", {}) or {}
        return cls(
            platform=str(profile.get("platform", "unknown")),
            os=str(profile.get("os", "Unknown")),
            kernel=str(profile.get("kernel", "Unknown")),
            cpu_brand=str(cpu.get("brand", "Unknown")),
            cpu_cores=int(cpu.get("cores", 0) or 0),
            cpu_arch=str(cpu.get("arch", "unknown")),
            ram_gb=float((profile.get("ram", {}) or {}).get("total_gb", 0.0) or 0.0),
            motherboard=str(profile.get("motherboard", "Unknown")),
            gpus=tuple(detected_gpus),
            modules=frozenset(
                str(driver.get("name", "")) for driver in profile.get("drivers", []) or []
            ),
            disk_types=tuple(
                str(disk.get("disk_type", "")) for disk in profile.get("disks", []) or []
            ),
        )

    # ── derived properties ────────────────────────────────────────────────────

    def vendors(self) -> frozenset[str]:
        return frozenset(gpu.vendor.upper() for gpu in self.gpus)

    def nvidia_gpus(self) -> tuple[GpuFact, ...]:
        return tuple(gpu for gpu in self.gpus if gpu.vendor.upper() == "NVIDIA")

    def best_nvidia_rank(self) -> int | None:
        """The newest NVIDIA generation present, or None if it cannot be told.

        Newest rather than oldest because the driver has to support the card
        you actually intend to render on, and a machine with an old card
        alongside a new one is choosing the new one.
        """
        ranks = [gpu.rank for gpu in self.nvidia_gpus() if gpu.recognised]
        return max(ranks) if ranks else None

    def is_virtual(self) -> bool:
        """Whether this looks like a virtual machine.

        Two independent signals, because either alone is wrong often enough to
        matter: a paravirtualised display adapter, or a hypervisor guest module
        loaded in the kernel.
        """
        if "VIRTUAL" in self.vendors():
            return True
        return bool(self.modules & {"virtio_pci", "vboxguest", "vmwgfx", "hv_vmbus", "virtio_gpu"})

    def headline_gpu(self) -> GpuFact | None:
        """The card a message should name when it mentions "your GPU".

        NVIDIA first, because every rule that cares about a specific model is
        an NVIDIA rule; otherwise whatever was reported first.
        """
        nvidia = self.nvidia_gpus()
        if nvidia:
            return max(nvidia, key=lambda gpu: gpu.rank)
        return self.gpus[0] if self.gpus else None


# ── the world ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class World:
    """Everything a condition is allowed to look at."""

    build: Build
    selected: frozenset[str] = frozenset()
    selections: Mapping[str, str | None] = field(default_factory=dict)
    tags: frozenset[str] = frozenset()
    facts: Mapping[str, Any] = field(default_factory=dict)
    bindings: Mapping[str, Any] = field(default_factory=dict)
    hardware: HardwareFacts | None = None

    @property
    def hardware_known(self) -> bool:
        return self.hardware is not None


def build_world(
    build: Build, hardware_profile: Mapping[str, Any] | None = None
) -> World:
    """Assemble the world for one build and, if it is real, one machine."""
    hardware = HardwareFacts.from_profile(hardware_profile)

    selections: dict[str, str | None] = {
        category.id: build.selected_id(category.id) for category in CATEGORIES
    }
    selected = build.selected_ids()

    tags: set[str] = set()
    facts: dict[str, Any] = {}
    bindings: dict[str, Any] = {}

    for category_id, component_id in selections.items():
        facts[f"build.{category_id}"] = component_id or NOT_SET
        component = COMPONENTS_BY_ID.get(component_id or "")
        bindings[f"choice.{category_id}"] = component.name if component else "nothing"
        if component is None:
            continue
        tags.update(component.tags)
        # A component contributes facts of its own — a kernel series, a driver
        # branch. This is what makes "the build promises at least 6.12" a thing
        # a rule can compare against, rather than knowledge locked in prose.
        for key, value in component.provides:
            facts[key] = value
            bindings[key] = value

    if hardware is not None:
        facts.update(_hardware_facts(hardware))
        bindings.update(_hardware_bindings(hardware))

    return World(
        build=build,
        selected=frozenset(selected),
        selections=selections,
        tags=frozenset(tags),
        facts=facts,
        bindings=bindings,
        hardware=hardware,
    )


def _hardware_facts(hardware: HardwareFacts) -> dict[str, Any]:
    """The hardware half of the namespace.

    Keys are only added when there is a real answer. A missing key reads as
    UNKNOWN, so leaving out `hardware.gpu.nvidia_rank` for a card the table
    does not recognise is what stops the engine claiming a brand-new GPU is too
    old for a driver just because it was released after this table was edited.
    """
    vendors = hardware.vendors()
    facts: dict[str, Any] = {
        "hardware.platform": hardware.platform,
        "hardware.os": hardware.os,
        "hardware.kernel": hardware.kernel,
        "hardware.cpu.brand": hardware.cpu_brand,
        "hardware.cpu.cores": hardware.cpu_cores,
        "hardware.cpu.arch": hardware.cpu_arch,
        "hardware.ram_gb": hardware.ram_gb,
        "hardware.motherboard": hardware.motherboard,
        "hardware.gpu.count": len(hardware.gpus),
        "hardware.gpu.vendors": tuple(sorted(vendors)),
        "hardware.gpu.has_nvidia": "NVIDIA" in vendors,
        "hardware.gpu.has_amd": "AMD" in vendors,
        "hardware.gpu.has_intel": "INTEL" in vendors,
        "hardware.modules": tuple(sorted(hardware.modules)),
        "hardware.disk.types": tuple(sorted(set(hardware.disk_types))),
        "hardware.is_virtual": hardware.is_virtual(),
    }

    nvidia_rank = hardware.best_nvidia_rank()
    if nvidia_rank is not None:
        facts["hardware.gpu.nvidia_rank"] = nvidia_rank

    return facts


def _hardware_bindings(hardware: HardwareFacts) -> dict[str, Any]:
    """The values a rule's message can name.

    Separate from facts because a message wants "GeForce RTX 3060" while a
    condition wants the number 70 — the same knowledge in the two shapes the
    two jobs need.
    """
    bindings: dict[str, Any] = {
        "machine.os": hardware.os,
        "machine.kernel": hardware.kernel,
        "machine.cpu": hardware.cpu_brand,
        "machine.ram_gb": f"{hardware.ram_gb:.0f}",
        "machine.motherboard": hardware.motherboard,
    }

    gpu = hardware.headline_gpu()
    if gpu is not None:
        bindings["gpu.name"] = gpu.name
        bindings["gpu.vendor"] = gpu.vendor
        bindings["gpu.architecture"] = gpu.architecture
    return bindings
