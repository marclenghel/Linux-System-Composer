"""Graphics model strings, turned into something a rule can reason about.

Detection reports what the machine calls its graphics card: "NVIDIA GeForce
RTX 3060", "GA106 [GeForce RTX 3060]", "AMD Radeon RX 7900 XTX". That string
is useless to a compatibility rule. What a rule needs to know is that the
first two are Ampere, and therefore new enough for NVIDIA's open kernel
modules, while a GTX 1060 is Pascal and is not.

This module is the table that bridges the two, and it is deliberately a table
rather than a chain of `if "RTX" in name` tests. A table can be read by
someone checking whether their card is covered, extended without touching any
logic, and tested exhaustively against real strings.

Ranks are spaced by ten. Architectures are released in a fixed order and rules
want to ask "is this at least Turing?", so the ordering has to be a number;
the gaps leave room for a generation that turns out to sit between two we
already know about, without renumbering the ones on either side.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# ── NVIDIA generations, oldest first ──────────────────────────────────────────

TESLA = 10
FERMI = 20
KEPLER = 30
MAXWELL = 40
PASCAL = 50
VOLTA = 55
TURING = 60
AMPERE = 70
ADA = 80
HOPPER = 85
BLACKWELL = 90

# The one threshold any rule actually cares about. NVIDIA's open kernel module
# only supports GPUs with a GSP microcontroller, which arrived with Turing;
# everything older has to use the closed module no matter what the user picks.
NVIDIA_OPEN_MIN_RANK = TURING

UNKNOWN_RANK = 0


@dataclass(frozen=True)
class GpuFamily:
    """What a model string turned out to be."""

    vendor: str
    architecture: str
    rank: int = UNKNOWN_RANK


# ── The table ─────────────────────────────────────────────────────────────────
#
# First match wins, so the order is load-bearing: "GTX 1660" is Turing and
# "GTX 1060" is Pascal, and a pattern of GTX 1\d\d\d written first would
# swallow both. Every entry that overlaps a later one has a test.

_PATTERNS: tuple[tuple[str, GpuFamily], ...] = (
    # NVIDIA — workstation names come first, because they reuse the consumer
    # numbering roughly a generation behind it: a "Quadro RTX 4000" is Turing
    # while an "RTX 4090" is Ada, and the consumer pattern written first claims
    # both. This is the exact bug the ordering comment above is about.
    (r"\brtx\s*\d{4}\s*ada\b", GpuFamily("NVIDIA", "Ada Lovelace", ADA)),
    (r"\bquadro\s*rtx\b", GpuFamily("NVIDIA", "Turing", TURING)),
    (r"\brtx\s*a[2-6]\d{3}\b", GpuFamily("NVIDIA", "Ampere", AMPERE)),
    # NVIDIA — consumer, newest first
    (r"\brtx\s*50\d\d\b", GpuFamily("NVIDIA", "Blackwell", BLACKWELL)),
    (r"\brtx\s*40\d\d\b", GpuFamily("NVIDIA", "Ada Lovelace", ADA)),
    (r"\brtx\s*30\d\d\b", GpuFamily("NVIDIA", "Ampere", AMPERE)),
    (r"\brtx\s*20\d\d\b|\bgtx\s*16\d\d\b|\btitan\s*rtx\b", GpuFamily("NVIDIA", "Turing", TURING)),
    (r"\bgtx\s*10\d\d\b|\btitan\s*x[pv]\b|\bmx\s*[123][35]0\b", GpuFamily("NVIDIA", "Pascal", PASCAL)),
    (r"\btitan\s*v\b", GpuFamily("NVIDIA", "Volta", VOLTA)),
    (r"\bgtx\s*(9\d\d|75\d)\b|\btitan\s*x\b", GpuFamily("NVIDIA", "Maxwell", MAXWELL)),
    (r"\b(gtx|gt)\s*(6\d\d|7[0-46-9]\d)\b", GpuFamily("NVIDIA", "Kepler", KEPLER)),
    (r"\b(gtx|gts|gt)\s*[45]\d\d\b", GpuFamily("NVIDIA", "Fermi", FERMI)),
    (r"\b(gtx|gts|gt)\s*[123]\d\d\b|\bgeforce\s*[89]\d{3}\b", GpuFamily("NVIDIA", "Tesla", TESLA)),
    # NVIDIA — workstation and datacentre, which share the consumer silicon
    (r"\bb[12]00\b|\bgb\d{3}\b", GpuFamily("NVIDIA", "Blackwell", BLACKWELL)),
    (r"\bh[12]00\b|\bgh\d{3}\b", GpuFamily("NVIDIA", "Hopper", HOPPER)),
    (r"\bl4\d?s?\b", GpuFamily("NVIDIA", "Ada Lovelace", ADA)),
    (r"\ba(100|40|30|16|10|2)\b", GpuFamily("NVIDIA", "Ampere", AMPERE)),
    (r"\bt4\b", GpuFamily("NVIDIA", "Turing", TURING)),
    (r"\bv100\b", GpuFamily("NVIDIA", "Volta", VOLTA)),
    (r"\bp\d{3}\b|\bquadro\s*p\d+\b", GpuFamily("NVIDIA", "Pascal", PASCAL)),
    # A GeForce we cannot place is still definitely an NVIDIA card. Saying so
    # with an unknown rank is what lets a rule answer "I don't know" instead of
    # guessing, which is the whole reason ranks can be unknown.
    (r"\b(nvidia|geforce|quadro|tesla)\b", GpuFamily("NVIDIA", "unrecognised")),

    # AMD
    (r"\brx\s*9\d{3}\b", GpuFamily("AMD", "RDNA 4", 40)),
    (r"\brx\s*7\d{3}\b|\bradeon\s*8\d{2}m\b", GpuFamily("AMD", "RDNA 3", 30)),
    (r"\brx\s*6\d{3}\b|\bradeon\s*(6|7)\d{2}m\b", GpuFamily("AMD", "RDNA 2", 20)),
    (r"\brx\s*5\d{3}\b", GpuFamily("AMD", "RDNA", 10)),
    (r"\bvega\b|\brx\s*[45]\d\d\b|\bfury\b|\br9\s*\d{3}\b", GpuFamily("AMD", "GCN", 5)),
    # Integrated graphics are named after the APU, never after the architecture.
    (r"\b(raphael|phoenix|hawk\s*point|strix|granite\s*ridge)\b", GpuFamily("AMD", "RDNA 2/3 integrated", 20)),
    (r"\b(rembrandt|cezanne|renoir|picasso|barcelo)\b", GpuFamily("AMD", "Vega integrated", 5)),
    (r"\b(amd|radeon|ati)\b", GpuFamily("AMD", "unrecognised")),

    # Intel
    (r"\barc\s*b\d{3}\b", GpuFamily("Intel", "Xe2 (Battlemage)", 30)),
    (r"\barc\s*a\d{3}\b", GpuFamily("Intel", "Xe-HPG (Alchemist)", 20)),
    (r"\biris\s*xe\b|\bxe\s*graphics\b|\barc\s*graphics\b", GpuFamily("Intel", "Xe", 15)),
    (r"\b(uhd|hd)\s*graphics\b|\biris\s*(plus|pro)\b", GpuFamily("Intel", "Gen", 10)),
    (r"\bintel\b", GpuFamily("Intel", "unrecognised")),

    # Not a real card at all. Worth identifying, because "you are inside a
    # virtual machine" changes which driver is the right answer entirely.
    (r"\b(virtio|qxl|vmware|virtualbox|hyper-?v|parallels|bochs|cirrus)\b",
     GpuFamily("Virtual", "paravirtualised", 1)),
    (r"\bmicrosoft\s*basic\s*display\b", GpuFamily("Virtual", "no driver loaded", 1)),

    # Apple silicon, which turns up when the detector runs on a Mac.
    (r"\bapple\s*m\d\b", GpuFamily("Apple", "Apple silicon", 10)),
)

_COMPILED: tuple[tuple[re.Pattern[str], GpuFamily], ...] = tuple(
    (re.compile(pattern, re.IGNORECASE), family) for pattern, family in _PATTERNS
)


def identify(model: str) -> GpuFamily | None:
    """Work out what a reported graphics device actually is.

    Returns None when nothing matches, which a caller must treat as "unknown"
    rather than "no GPU" — an unrecognised card is the normal case for
    anything released after this table was last edited.
    """
    if not model:
        return None
    # Model strings arrive punctuated in every imaginable way: "GeForce RTX
    # 3060", "RTX3060", "GA106 [GeForce RTX 3060]". Flattening the separators
    # means one pattern covers all of them.
    haystack = re.sub(r"[\[\]()/_.,-]", " ", model)
    haystack = re.sub(r"\s+", " ", haystack)
    for pattern, family in _COMPILED:
        if pattern.search(haystack):
            return family
    return None


def supports_open_modules(rank: int) -> bool | None:
    """Can this NVIDIA GPU run the open kernel modules?

    None means "the table did not recognise the card", and the caller must not
    turn that into a No. Refusing a driver because a lookup table is out of
    date would be exactly the kind of confident wrongness this project exists
    to avoid.
    """
    if rank == UNKNOWN_RANK:
        return None
    return rank >= NVIDIA_OPEN_MIN_RANK
