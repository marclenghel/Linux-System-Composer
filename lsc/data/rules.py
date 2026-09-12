"""The compatibility rules — the knowledge, separated from the machinery.

Everything here is data. Nothing in this file runs; lsc/compat/engine.py reads it.
That is the point: the README's data layer holds "compatibility rules", and a
rule set written as conditions rather than as code can be moved into a TOML
file by writing a loader, never by rewriting the evaluator.

What belongs here and what does not:

  * A plain "X requires Y" or "X conflicts with Y" belongs in the catalogue,
    next to the component, and the engine turns those edges into issues by
    itself. Duplicating them here would create two places to be wrong.
  * A rule with a *condition* belongs here — anything of the shape "if this
    and that, then", anything comparing a version, anything that depends on
    what is actually plugged into the machine.

Every rule states what to do about the problem, and most also carry a
Suggestion: the same advice in a form a program can act on. An issue with no
way forward is treated as a bug in the rule, because the promise in the README
is that this tool explains incompatibilities rather than refusing them.

Rules that need hardware evaluate to UNKNOWN until a real scan has finished,
and the Validate screen lists them as unchecked rather than pretending they
passed. See lsc/compat/facts.py for why the sample profile is not good enough.
"""

from __future__ import annotations

from lsc.compat.conditions import (
    AllOf,
    AnySelected,
    CategoryEmpty,
    Fact,
    Not,
    Selected,
    VersionBelow,
)
from lsc.data import gpus
from lsc.compat.engine import Rule
from lsc.models import Suggestion

ARCH_WIKI = "https://wiki.archlinux.org"

# Rules that need to know what is in the machine say so, so that an undecided
# rule can explain what would decide it.
NEEDS_SCAN = "a hardware scan"
NEEDS_GPU_MODEL = "a graphics card this project's model table recognises"
NEEDS_KERNEL = "a kernel selected in the build"
NEEDS_FILESYSTEM = "a filesystem selected in the build"


# ── NVIDIA and Wayland ────────────────────────────────────────────────────────
#
# This cluster is the README's worked example, and it is the reason the project
# exists: the interaction between a compositor, a driver, and a kernel is real,
# it is well documented, and it is spread across four different documents none
# of which mention the other three.

NVIDIA_WAYLAND_RULES: tuple[Rule, ...] = (
    Rule(
        id="hyprland-nvidia",
        severity="warning",
        when=AllOf(Selected("hyprland"), AnySelected("nvidia", "nvidia-open")),
        title="Hyprland on NVIDIA needs four things set up before it will behave",
        detail=(
            "This combination works, and it is the single most common way to end up "
            "with a black screen on first boot. Four separate pieces have to line up:\n\n"
            "1.  DRM kernel mode setting.  Add nvidia_drm.modeset=1 to the kernel "
            "command line. Without it the compositor has no DRM device to drive and "
            "will not start at all.\n\n"
            "2.  The modules in the initramfs.  Put nvidia, nvidia_modeset, nvidia_uvm "
            "and nvidia_drm in mkinitcpio's MODULES, and add the pacman hook that "
            "rebuilds the initramfs when the driver updates — otherwise the next "
            "driver upgrade silently leaves a stale image behind.\n\n"
            "3.  Explicit sync.  Driver 555 or newer and Hyprland 0.42 or newer speak "
            "the explicit synchronisation protocol. Older pairs of the two flicker and "
            "tear in XWayland windows, which is the artefact everyone reports and "
            "almost nobody diagnoses.\n\n"
            "4.  XWayland.  Programs that still speak X11 run through XWayland. They "
            "look blurry under fractional scaling unless Hyprland is told to let them "
            "scale themselves, and a few screen-capture and global-hotkey tools need "
            "Wayland-native replacements rather than configuration."
        ),
        fix=(
            "Set nvidia_drm.modeset=1, list the four NVIDIA modules in mkinitcpio, and "
            "check that the driver is at least 555. The generated install script "
            "already writes the kernel parameter for you — the Export tab shows it."
        ),
        reference=f"{ARCH_WIKI}/title/Hyprland#NVIDIA",
        needs=NEEDS_SCAN,
    ),
    Rule(
        id="nvidia-wayland-modeset",
        severity="warning",
        when=AllOf(
            AnySelected("nvidia", "nvidia-open"),
            Selected("wayland"),
            # Hyprland has its own rule above, which says all of this and more.
            Not(Selected("hyprland")),
        ),
        title="Wayland on NVIDIA needs DRM mode setting turned on explicitly",
        detail=(
            "The NVIDIA driver does not enable DRM kernel mode setting by itself on "
            "every version and configuration, and a Wayland compositor cannot start "
            "without it. The failure looks like a session that drops straight back to "
            "the login screen with nothing useful in the log."
        ),
        fix=(
            "Add nvidia_drm.modeset=1 to the kernel command line, and rebuild the "
            "initramfs with the NVIDIA modules included."
        ),
        reference=f"{ARCH_WIKI}/title/NVIDIA#DRM_kernel_mode_setting",
    ),
    Rule(
        id="nvidia-open-needs-turing",
        severity="error",
        when=AllOf(
            Selected("nvidia-open"),
            Fact("hardware.gpu.nvidia_rank", "lt", gpus.TURING),
        ),
        title="{gpu.name} is too old for the open NVIDIA kernel modules",
        detail=(
            "The open kernel modules only drive cards that have the GSP "
            "microcontroller, which arrived with Turing — the RTX 20 and GTX 16 "
            "series. This machine reports a {gpu.name}, which is {gpu.architecture}, "
            "so the open module will refuse to bind to it and the machine will boot "
            "without acceleration."
        ),
        fix="Choose NVIDIA (proprietary) instead — it is the supported driver for this card.",
        suggest=Suggestion("gpu", "nvidia"),
        reference=f"{ARCH_WIKI}/title/NVIDIA#Installation",
        needs=NEEDS_GPU_MODEL,
    ),
    Rule(
        id="nvidia-open-is-available",
        severity="info",
        when=AllOf(
            Selected("nvidia"),
            Fact("hardware.gpu.nvidia_rank", "gte", gpus.TURING),
        ),
        title="{gpu.name} could use the open NVIDIA modules instead",
        detail=(
            "{gpu.name} is {gpu.architecture}, which is new enough for NVIDIA's own "
            "open kernel modules. They are the vendor's recommended driver on this "
            "generation, and they behave noticeably better under Wayland. The "
            "user-space libraries are the same closed ones either way, so this is not "
            "a trade of performance for principle."
        ),
        fix="Switch the graphics stack to NVIDIA (open modules).",
        suggest=Suggestion("gpu", "nvidia-open"),
        needs=NEEDS_GPU_MODEL,
    ),
    Rule(
        id="nvidia-driver-without-nvidia-gpu",
        severity="warning",
        when=AllOf(
            AnySelected("nvidia", "nvidia-open"),
            Fact("hardware.gpu.has_nvidia", "eq", False),
        ),
        title="An NVIDIA driver is selected, but no NVIDIA card was detected",
        detail=(
            "Detection found {gpu.name} and no NVIDIA hardware at all. Installing the "
            "NVIDIA driver on a machine without an NVIDIA GPU costs a DKMS rebuild on "
            "every kernel update and gains nothing. This is only the right choice if "
            "you are composing this build for a different machine."
        ),
        fix="If this build is for the machine you are sitting at, use Mesa instead.",
        suggest=Suggestion("gpu", "mesa"),
    ),
    Rule(
        id="mesa-with-nvidia-only",
        severity="warning",
        when=AllOf(
            Selected("mesa"),
            Fact("hardware.gpu.has_nvidia", "eq", True),
            Fact("hardware.gpu.has_amd", "eq", False),
            Fact("hardware.gpu.has_intel", "eq", False),
        ),
        title="Mesa is selected, but the only graphics in this machine is NVIDIA",
        detail=(
            "The Mesa entry covers the AMD and Intel drivers that ship inside the "
            "kernel. On an NVIDIA-only machine it leaves you with Nouveau, which works "
            "but cannot raise the card's clocks on most models — so the machine runs, "
            "slowly, and it is not obvious why."
        ),
        fix=(
            "Pick an NVIDIA driver. The open modules are right for Turing and newer; "
            "older cards need the proprietary one."
        ),
        suggest=Suggestion("gpu", "nvidia-open"),
    ),
    Rule(
        id="nvidia-wayland-old-running-kernel",
        severity="warning",
        when=AllOf(
            AnySelected("nvidia", "nvidia-open"),
            Selected("wayland"),
            Fact("hardware.platform", "eq", "linux"),
            VersionBelow("hardware.kernel", "6.6"),
        ),
        title="This machine is running kernel {machine.kernel}, which is old for NVIDIA on Wayland",
        detail=(
            "The framebuffer console handoff that nvidia_drm.fbdev=1 performs wants a "
            "kernel with simpledrm, and the Wayland fixes in the NVIDIA driver assume "
            "a reasonably current one. On {machine.kernel} you can expect a blank or "
            "corrupted virtual console and a rougher time in general.\n\n"
            "This is a note about the machine you are sitting at, not about the build "
            "you are composing — the build's own kernel choice is checked separately."
        ),
        fix=(
            "Nothing needs changing in this build. If you are upgrading this machine "
            "in place rather than reinstalling, update the kernel first."
        ),
        needs=NEEDS_SCAN,
    ),
    Rule(
        id="nvidia-dkms-on-a-rolling-kernel",
        severity="info",
        when=AllOf(
            AnySelected("nvidia", "nvidia-open"),
            Fact("kernel.channel", "eq", "mainline"),
        ),
        title="The NVIDIA module has to be rebuilt on every kernel update",
        detail=(
            "{choice.gpu} is built outside the kernel tree, and {choice.kernel} moves "
            "with mainline. Every kernel update therefore triggers a DKMS rebuild, and "
            "when the driver has not caught up with a new kernel yet the rebuild fails "
            "and you reboot into a machine with no graphics.\n\n"
            "This is a normal, survivable part of running this combination. It is "
            "worth knowing before it happens rather than at midnight."
        ),
        fix=(
            "Keep a fallback kernel installed, or move to linux-lts, which changes "
            "series rarely enough that the driver is always ready first."
        ),
        suggest=Suggestion("kernel", "linux-lts"),
        needs=NEEDS_KERNEL,
    ),
)


# ── things that cross layers ──────────────────────────────────────────────────
#
# The rules this project exists for: a choice in one part of the stack quietly
# breaking something in a part that looks unrelated.

CROSS_LAYER_RULES: tuple[Rule, ...] = (
    Rule(
        id="wayland-screen-sharing-needs-pipewire",
        severity="warning",
        when=AllOf(
            Selected("wayland"),
            Not(Selected("headless")),
            AnySelected("pulseaudio", "alsa"),
        ),
        title="Screen sharing will not work: Wayland routes video through PipeWire",
        detail=(
            "This one surprises people because it looks like an audio decision.\n\n"
            "Under Wayland an application cannot read the screen directly — the "
            "compositor will not let it. Capture goes through xdg-desktop-portal, "
            "which hands the frames over as a PipeWire stream. With {choice.audio} "
            "there is no PipeWire session for it to hand them to, so screen sharing in "
            "a browser, in a call, or in OBS produces a black rectangle."
        ),
        fix=(
            "Select PipeWire as the audio stack. It also replaces PulseAudio and JACK, "
            "so nothing is lost by the change."
        ),
        suggest=Suggestion("audio", "pipewire"),
    ),
    Rule(
        id="zfs-on-a-rolling-kernel",
        severity="warning",
        when=AllOf(Selected("zfs"), Fact("kernel.channel", "eq", "mainline")),
        title="ZFS and a rolling kernel will eventually stop each other booting",
        detail=(
            "OpenZFS cannot ship inside the kernel for licensing reasons, so it is "
            "always chasing mainline and only declares support up to a kernel it has "
            "been tested against. {choice.kernel} follows mainline, so sooner or later "
            "an update arrives that ZFS has not caught up with, the module fails to "
            "build, and the machine reboots unable to mount its own root filesystem."
        ),
        fix=(
            "Pair ZFS with linux-lts, which stays on one series long enough for ZFS to "
            "keep up. If you keep the rolling kernel, never reboot after an update "
            "without checking that the ZFS module rebuilt."
        ),
        suggest=Suggestion("kernel", "linux-lts"),
        needs=NEEDS_KERNEL,
    ),
    Rule(
        id="btrfs-snapshots-need-grub-to-be-bootable",
        severity="info",
        when=AllOf(Selected("btrfs"), Not(Selected("grub"))),
        title="Btrfs snapshots exist, but {choice.bootloader} cannot boot one",
        detail=(
            "Snapshots are only half of a rollback. Restoring one from a running "
            "system is easy; the case you actually need it for is the one where the "
            "system no longer starts, and then you have to be able to choose a "
            "snapshot from the boot menu.\n\n"
            "GRUB does this with grub-btrfs, which writes a menu entry per snapshot. "
            "{choice.bootloader} has no equivalent, so recovery means booting "
            "installation media first."
        ),
        fix=(
            "Either switch to GRUB and install grub-btrfs, or accept that rolling back "
            "a broken boot means reaching for a USB stick."
        ),
        suggest=Suggestion("bootloader", "grub"),
    ),
    Rule(
        id="btrfs-with-grub-should-add-grub-btrfs",
        severity="info",
        when=AllOf(Selected("btrfs"), Selected("grub")),
        title="This pair can boot straight into a snapshot",
        detail=(
            "Btrfs and GRUB together are the combination that makes the rollback story "
            "work: grub-btrfs regenerates the boot menu with an entry for every "
            "snapshot, so a system broken by an update can be recovered from the boot "
            "menu without any external media.\n\n"
            "Nothing is wrong with this build. It is worth saying because the pairing "
            "is the reason to choose either of them."
        ),
        fix="Install grub-btrfs and snapper, and take a snapshot before system updates.",
        reference=f"{ARCH_WIKI}/title/Snapper",
    ),
    Rule(
        id="apparmor-needs-a-kernel-parameter",
        severity="info",
        when=AnySelected("apparmor", "hardened"),
        title="AppArmor does nothing until it is enabled on the kernel command line",
        detail=(
            "Arch builds AppArmor into its kernels but does not activate it. Install "
            "the package, reboot, and the profiles sit there doing nothing — with no "
            "error anywhere to suggest that the confinement you think you have is not "
            "running."
        ),
        fix=(
            "Add lsm=landlock,lockdown,yama,integrity,apparmor,bpf to the kernel "
            "command line. The generated install script lists it for you; see Export."
        ),
        reference=f"{ARCH_WIKI}/title/AppArmor",
    ),
    # Written against the facts two different components provide rather than
    # against their ids, so it covers any future pairing of an out-of-tree
    # driver with an out-of-tree filesystem without being edited.
    Rule(
        id="two-out-of-tree-modules",
        severity="warning",
        when=AllOf(
            Fact("driver.out_of_tree", "eq", "yes"),
            Fact("fs.out_of_tree", "eq", "yes"),
        ),
        title="Both the graphics driver and the filesystem live outside the kernel",
        detail=(
            "{choice.gpu} and {choice.filesystem} are each built against the kernel "
            "rather than shipped inside it, and each lags mainline by its own amount. "
            "That gives every single kernel update two independent chances to fail: "
            "one that leaves the machine without graphics, and one that leaves it "
            "unable to mount its own root filesystem.\n\n"
            "Neither choice is wrong. Both at once is a combination worth making on "
            "purpose rather than by accident."
        ),
        fix=(
            "Keep a known-good kernel installed as a fallback boot entry, and check "
            "that both modules rebuilt before rebooting after an update. An LTS kernel "
            "makes this happen far less often."
        ),
        suggest=Suggestion("kernel", "linux-lts"),
        needs=NEEDS_FILESYSTEM,
    ),
    Rule(
        id="manjaro-and-the-aur",
        severity="info",
        when=Selected("manjaro"),
        title="Manjaro holds packages back, and the AUR does not know that",
        detail=(
            "AUR build files are written against current Arch. Manjaro delays Arch "
            "packages by roughly two weeks to test them, so an AUR package can expect a "
            "library version Manjaro has not shipped yet, and the build fails for a "
            "reason that has nothing to do with the package.\n\n"
            "It is a good illustration of the kind of hidden interaction this whole "
            "project is about: neither side is broken, and the combination still is."
        ),
        fix=(
            "Use the AUR sparingly on Manjaro, or choose a base that tracks Arch "
            "directly if you rely on it."
        ),
        suggest=Suggestion("base", "arch"),
    ),
    Rule(
        id="headless-needs-no-display-server",
        severity="info",
        when=AllOf(Selected("headless"), Not(CategoryEmpty("display"))),
        title="A headless build does not need {choice.display}",
        detail=(
            "With no desktop selected nothing will ever connect to a display server, "
            "so {choice.display} would be installed and never started. The stack "
            "diagram draws the gap honestly if you leave the layer empty."
        ),
        fix="Clear the display server choice under Compose — an empty answer is valid here.",
    ),
    Rule(
        id="hyprland-kernel-floor",
        severity="warning",
        when=AllOf(Selected("hyprland"), VersionBelow("kernel.version", "6.6")),
        title="Hyprland expects a newer kernel than {choice.kernel} guarantees",
        # A message is a template, so a literal brace would be read as the start
        # of a placeholder. The README's example is quoted without its braces
        # rather than escaped, because escaped braces in a sentence someone has
        # to read are worse than the sentence not containing any.
        detail=(
            "This is the README's own worked example — kernel_min 6.6 — written as "
            "something the engine can actually check. Hyprland leans on recent DRM "
            "work, and on a kernel below 6.6 you are outside what anyone upstream is "
            "testing.\n\n"
            "No kernel in the current catalogue trips this, which is the correct "
            "result rather than a broken rule: the constraint is real and every "
            "available choice already satisfies it."
        ),
        fix="Choose a kernel of 6.6 or newer. Every kernel in this catalogue qualifies.",
        suggest=Suggestion("kernel", "linux"),
        needs=NEEDS_KERNEL,
    ),
    Rule(
        id="xorg-is-in-maintenance-mode",
        severity="info",
        when=Selected("xorg"),
        title="Xorg still works, and nobody is developing it any more",
        detail=(
            "Choosing X11 is defensible — some hardware, some accessibility tools and "
            "most screen-sharing software still work better on it. It is worth knowing "
            "that upstream development has stopped, that mixed-DPI multi-monitor setups "
            "will not improve, and that the applications you depend on will gradually "
            "move their attention to Wayland."
        ),
        fix=(
            "No action needed. Revisit the choice when the specific thing keeping you "
            "on X11 gains a Wayland answer."
        ),
    ),
    Rule(
        id="experimental-compositor",
        severity="info",
        when=Selected("niri"),
        title="niri is young, and the catalogue says so",
        detail=(
            "Scrollable tiling is a genuinely different idea and niri is unusually well "
            "built for its age, but it is marked experimental here for a reason: fewer "
            "users have hit the edges, and configuration formats in young compositors "
            "move. Worth demonstrating, worth thinking about before it is the only "
            "desktop on a machine you rely on."
        ),
        fix="Keep a second session installed — Sway or KDE — so a bad update is not a dead machine.",
    ),
)


# ── what the machine can actually run ─────────────────────────────────────────
#
# These replace lsc/data/hardware.py's old suggestions_for, which matched vendor
# substrings. Every one of them says under what condition it applies and why,
# and none of them fires until the machine has actually been read.

HARDWARE_RULES: tuple[Rule, ...] = (
    Rule(
        id="running-in-a-virtual-machine",
        severity="warning",
        when=AllOf(
            Fact("hardware.is_virtual", "eq", True),
            Not(Selected("vm-guest")),
            Not(Selected("headless")),
        ),
        title="This looks like a virtual machine, but a bare-metal driver is selected",
        detail=(
            "Detection reports paravirtualised graphics or a hypervisor guest module. "
            "Inside a virtual machine there is no real GPU to drive: {choice.gpu} will "
            "either fail to bind or fall back to software rendering, and installing it "
            "costs a module rebuild for nothing."
        ),
        fix="Select the virtual machine guest drivers under GPU Driver.",
        suggest=Suggestion("gpu", "vm-guest"),
    ),
    Rule(
        id="guest-driver-on-real-hardware",
        severity="warning",
        when=AllOf(Selected("vm-guest"), Fact("hardware.is_virtual", "eq", False)),
        title="Guest drivers are selected, but this is real hardware",
        detail=(
            "Detection found {gpu.name} and no sign of a hypervisor. The guest drivers "
            "target a virtual display adapter, so on this machine they would leave the "
            "real card unaccelerated."
        ),
        fix="Select the driver that matches the card actually in the machine.",
        suggest=Suggestion("gpu", "mesa"),
    ),
    Rule(
        id="not-enough-memory-for-a-full-desktop",
        severity="warning",
        when=AllOf(
            AnySelected("kde", "gnome"),
            Fact("hardware.ram_gb", "lt", 8),
        ),
        title="{machine.ram_gb} GB of memory is tight for {choice.desktop}",
        detail=(
            "A full desktop environment brings a compositor, a settings daemon, a "
            "search indexer and a portal service, and they are resident the whole time "
            "the machine is on. On {machine.ram_gb} GB that is a large share of the "
            "memory gone before you open anything of your own."
        ),
        fix=(
            "Xfce is a conventional desktop that leaves considerably more memory free. "
            "A tiling window manager leaves more still."
        ),
        suggest=Suggestion("desktop", "xfce"),
    ),
    Rule(
        id="btrfs-is-already-in-use-here",
        severity="info",
        when=AllOf(
            Fact("hardware.modules", "contains", "btrfs"),
            Not(Selected("btrfs")),
        ),
        title="This machine already has the Btrfs module loaded",
        detail=(
            "The btrfs kernel module is live right now, which almost always means this "
            "machine is running Btrfs today. If you are composing a build to replace "
            "what is installed here, choosing {choice.filesystem} instead means "
            "reformatting rather than reinstalling over the top."
        ),
        fix="Consider Btrfs, or make sure you have backups before changing filesystem.",
        suggest=Suggestion("filesystem", "btrfs"),
    ),
    Rule(
        id="arm-machine-needs-the-mainline-kernel",
        severity="warning",
        when=AllOf(
            Fact("hardware.cpu.arch", "eq", "aarch64"),
            Not(Selected("linux")),
        ),
        title="This is an ARM machine, and {choice.kernel} is an x86 package",
        detail=(
            "Detection reports an aarch64 processor. The tuned kernels in this "
            "catalogue — zen, CachyOS, hardened — are built and distributed for x86_64, "
            "and their whole reason for existing is x86 scheduling and instruction set "
            "tuning. On ARM the mainline kernel is not a compromise, it is the choice "
            "that exists."
        ),
        fix="Select the mainline linux kernel.",
        suggest=Suggestion("kernel", "linux"),
    ),
    Rule(
        id="nouveau-on-a-modern-card",
        severity="info",
        when=AllOf(
            Selected("nouveau"),
            Fact("hardware.gpu.nvidia_rank", "gte", gpus.TURING),
        ),
        title="Nouveau will leave most of {gpu.name} unused",
        detail=(
            "Nouveau cannot raise clock speeds on most cards without signed firmware, "
            "so a {gpu.architecture} card will run at a small fraction of what it can "
            "do. That is fine for a terminal and a browser and painful for anything "
            "else."
        ),
        fix="Use the open NVIDIA kernel modules — this card is new enough for them.",
        suggest=Suggestion("gpu", "nvidia-open"),
        needs=NEEDS_GPU_MODEL,
    ),
)


# ── the rule set ──────────────────────────────────────────────────────────────

RULES: tuple[Rule, ...] = (
    NVIDIA_WAYLAND_RULES + CROSS_LAYER_RULES + HARDWARE_RULES
)

RULES_BY_ID: dict[str, Rule] = {rule.id: rule for rule in RULES}
