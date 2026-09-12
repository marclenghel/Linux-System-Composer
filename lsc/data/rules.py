"""The curated rules — the knowledge that does not fit in a tuple.

The catalogue's `requires` / `conflicts` / `recommends` fields cover the
relationships that are simply true: Hyprland needs Wayland, PipeWire replaces
PulseAudio. The engine derives issues from those automatically, so none of them
need to be repeated here.

What cannot be written as a tuple is everything with a *condition* attached.
"NVIDIA and Wayland" is not a conflict — it works, and it is what most people
run — but it needs a kernel parameter that nothing tells you about until the
screen stays black. "PulseAudio" is not broken on Wayland either; it just
silently costs you screen sharing. Those are the facts this file exists for, and
they are the facts the README promised when it said the tool should *explain*
incompatibilities rather than refuse them.

Every rule carries a fix, because an explanation with no way forward is not
advice. Rules whose conditions mention the machine only run when a machine has
actually been read — see the note at the top of lsc/conditions.py.

Sources are the Arch Wiki, the NVIDIA and OpenZFS documentation, and the
upstream project wikis. Where a fact has a version number attached it lives in
the catalogue as data, not in the sentence, so it can be corrected without
rewriting the explanation.
"""

from __future__ import annotations

from dataclasses import dataclass

from lsc.conditions import (
    AllOf,
    CategoryFilled,
    Chose,
    Condition,
    CpuArch,
    GpuVendor,
    Has,
    HasAnyOf,
    ModuleLoaded,
    Not,
    NvidiaPreTuring,
    OnlyGpuVendors,
    RamBelowGb,
    Tagged,
)


@dataclass(frozen=True)
class Rule:
    """One piece of conditional knowledge.

    `id` is stable and is the thing tests refer to, so a rule can be renamed for
    readability without breaking anything. `components` lists what the rule is
    about, which lets the interface point at the relevant part of the build
    instead of making the user work out which of their nine choices is meant.
    """

    id: str
    severity: str                        # error | warning | info
    when: Condition
    title: str
    detail: str
    fix: str
    components: tuple[str, ...] = ()


# ── Graphics: the layer that produces the most broken systems ─────────────────

GRAPHICS_RULES: tuple[Rule, ...] = (
    Rule(
        id="nvidia-wayland-modeset",
        severity="warning",
        when=AllOf(Has("wayland"), HasAnyOf("nvidia", "nvidia-open")),
        title="NVIDIA on Wayland needs DRM mode setting turned on",
        detail=(
            "NVIDIA's kernel module does not enable DRM kernel mode setting by "
            "itself, and no Wayland compositor will start without it. The failure "
            "looks like a black screen or a session that drops straight back to "
            "the login manager, with nothing in the log that points at the cause. "
            "This is the single most common way an otherwise correct NVIDIA "
            "Wayland build fails."
        ),
        fix=(
            "Boot with nvidia_drm.modeset=1 as a kernel parameter. The generated "
            "install script already adds it, so this is a note about what that "
            "line is for rather than something left for you to remember."
        ),
        components=("wayland", "nvidia", "nvidia-open"),
    ),
    Rule(
        id="hyprland-nvidia",
        severity="warning",
        when=AllOf(Has("hyprland"), HasAnyOf("nvidia", "nvidia-open")),
        title="Hyprland on NVIDIA is the combination that needs the most care",
        detail=(
            "It works, and plenty of people run it, but it asks for more than any "
            "other pairing in this catalogue: DRM mode setting at boot, a driver "
            "new enough to support explicit sync — without it you get flickering "
            "and stuttering that look like broken hardware — and XWayland patches "
            "for the X11 applications that are still scaled wrongly without them. "
            "Hyprland also moves fast enough that a configuration file can stop "
            "parsing after an update, which is harder to debug when the graphics "
            "stack is also suspect."
        ),
        fix=(
            "Prefer the open kernel modules on an RTX 20-series card or newer, "
            "keep the driver current rather than pinned, and if you want the "
            "quiet life, KDE Plasma on the same hardware needs none of this."
        ),
        components=("hyprland", "nvidia", "nvidia-open"),
    ),
    Rule(
        id="nvidia-open-pre-turing",
        severity="error",
        when=AllOf(Has("nvidia-open"), NvidiaPreTuring()),
        title="The open NVIDIA modules do not support this machine's GPU",
        detail=(
            "NVIDIA's open kernel modules start at Turing — the RTX 20 series and "
            "the GTX 16 series. The card detected in this machine is older than "
            "that, and the open module will not bind to it, so the build would "
            "install and then come up with no acceleration at all."
        ),
        fix=(
            "Choose NVIDIA (proprietary), which supports this card, or Nouveau if "
            "you would rather stay entirely open and can live with the "
            "performance."
        ),
        components=("nvidia-open",),
    ),
    Rule(
        id="nvidia-driver-without-nvidia-gpu",
        severity="warning",
        when=AllOf(HasAnyOf("nvidia", "nvidia-open", "nouveau"), Not(GpuVendor("NVIDIA"))),
        title="An NVIDIA driver is selected, but no NVIDIA GPU was detected",
        detail=(
            "The scan of this machine found no NVIDIA card. Installing the driver "
            "anyway is not fatal — it builds, it loads nothing — but it adds a "
            "module that has to be rebuilt on every kernel update in exchange for "
            "nothing at all."
        ),
        fix=(
            "If you are composing this build for a different machine, ignore "
            "this. Otherwise Mesa is the stack that matches the hardware in front "
            "of you."
        ),
        components=("nvidia", "nvidia-open", "nouveau"),
    ),
    Rule(
        id="mesa-without-amd-or-intel",
        severity="warning",
        when=AllOf(Has("mesa"), OnlyGpuVendors("NVIDIA")),
        title="Mesa is selected, but the only GPU detected is NVIDIA",
        detail=(
            "Mesa covers AMD and Intel graphics. On an NVIDIA-only machine it "
            "leaves you with Nouveau's kernel driver by default, which means a "
            "working desktop at a fraction of the card's performance — enough to "
            "look like the build succeeded, slow enough to be the first thing you "
            "notice."
        ),
        fix=(
            "Pick an NVIDIA driver: the open modules on an RTX 20-series card or "
            "newer, the proprietary one otherwise."
        ),
        components=("mesa",),
    ),
    Rule(
        id="nouveau-on-capable-card",
        severity="info",
        when=AllOf(Has("nouveau"), GpuVendor("NVIDIA"), Not(NvidiaPreTuring())),
        title="Nouveau will not use most of this card",
        detail=(
            "Nouveau cannot raise clock speeds on recent NVIDIA hardware without "
            "signed firmware the vendor does not publish, so a card like the one "
            "in this machine runs at close to idle frequencies. Everything works; "
            "almost nothing is fast."
        ),
        fix=(
            "Fine if this is a terminal-and-browser machine. For anything that "
            "renders, the open NVIDIA modules give you the card you paid for."
        ),
        components=("nouveau",),
    ),
    Rule(
        id="vm-guest-on-real-hardware",
        severity="warning",
        when=AllOf(Has("vm-guest"), GpuVendor("NVIDIA", "AMD", "INTEL")),
        title="Virtual machine graphics are selected, but this looks like real hardware",
        detail=(
            "The guest drivers talk to a virtual display device. On a physical "
            "machine there is no such device, so the graphical session has "
            "nothing to start on."
        ),
        fix=(
            "Choose the stack that matches the detected GPU — Mesa for AMD and "
            "Intel, an NVIDIA driver for NVIDIA. Keep this selection only if the "
            "build is destined for a VM."
        ),
        components=("vm-guest",),
    ),
)


# ── Audio: the layer where things go quiet instead of failing ─────────────────

AUDIO_RULES: tuple[Rule, ...] = (
    Rule(
        id="pulseaudio-wayland-screen-sharing",
        severity="warning",
        when=AllOf(Has("wayland"), Has("pulseaudio")),
        title="Screen sharing will not work on Wayland with PulseAudio",
        detail=(
            "On Wayland an application cannot simply read the screen; it has to "
            "ask through xdg-desktop-portal, and the portal hands the capture "
            "over a PipeWire stream. With PulseAudio in place there is no such "
            "stream, so screen sharing in browsers, Discord, Zoom and OBS finds "
            "no sources. Audio itself is fine, which is what makes this hard to "
            "diagnose — nothing is broken, a feature is simply absent."
        ),
        fix=(
            "Select PipeWire. It speaks PulseAudio's protocol, so applications "
            "will not notice the change, and it is what a Wayland desktop expects "
            "to find."
        ),
        components=("pulseaudio", "wayland"),
    ),
    Rule(
        id="alsa-on-a-desktop",
        severity="warning",
        when=AllOf(Has("alsa"), CategoryFilled("desktop"), Not(Has("headless"))),
        title="ALSA alone is painful on a desktop",
        detail=(
            "With no sound server, the sound card is claimed by one application "
            "at a time. In practice a browser tab holding the device means your "
            "music player reports that audio is unavailable, and per-application "
            "volume, Bluetooth audio and hot-plugging headsets do not exist."
        ),
        fix=(
            "PipeWire on a desktop. Keep ALSA only for an embedded or "
            "single-purpose machine where exactly one program makes sound."
        ),
        components=("alsa",),
    ),
    Rule(
        id="sound-server-on-headless",
        severity="info",
        when=AllOf(Has("headless"), HasAnyOf("pipewire", "pulseaudio")),
        title="A headless build rarely needs a sound server",
        detail=(
            "Nothing in a console-only system plays audio, so the sound server "
            "and its session dependencies are packages that will never be used. "
            "Harmless, but this is the layer where a minimal build stops being "
            "minimal."
        ),
        fix=(
            "ALSA only, or leave the audio choice as it is if this machine will "
            "grow a desktop later."
        ),
        components=("headless", "pipewire", "pulseaudio"),
    ),
)


# ── Storage and the kernel: where updates break things weeks later ───────────

STORAGE_RULES: tuple[Rule, ...] = (
    Rule(
        id="zfs-on-a-rolling-kernel",
        severity="warning",
        when=AllOf(Has("zfs"), Not(Tagged("lts"))),
        title="ZFS on a rolling kernel can leave you unable to boot",
        detail=(
            "ZFS lives outside the kernel tree and each release states which "
            "kernel versions it supports. A rolling kernel regularly moves ahead "
            "of that list, and the module then fails to build. If ZFS holds your "
            "root filesystem, the machine that comes up after that update cannot "
            "mount it — the failure arrives on an ordinary Tuesday upgrade, not "
            "at install time, which is what makes it worth warning about now."
        ),
        fix=(
            "Pair ZFS with the LTS kernel, which stays inside the supported "
            "window. If you want a current kernel, keep root on something "
            "in-tree and give ZFS the data disks."
        ),
        components=("zfs",),
    ),
    Rule(
        id="btrfs-detected-but-not-selected",
        severity="info",
        when=AllOf(ModuleLoaded("btrfs"), Not(Has("btrfs"))),
        title="This machine is running Btrfs today",
        detail=(
            "The btrfs module is loaded right now, so the system you are "
            "composing from is already using it. Worth knowing before you choose "
            "something else: any subvolume layout and snapshot history on this "
            "disk belongs to Btrfs and does not survive a reformat."
        ),
        fix=(
            "Keep Btrfs to stay compatible with what is already here, or make "
            "sure you have the data elsewhere before switching filesystem."
        ),
        components=("btrfs",),
    ),
    Rule(
        id="snapshots-without-a-snapshotting-filesystem",
        severity="info",
        when=AllOf(Has("grub"), HasAnyOf("ext4", "xfs", "f2fs")),
        title="GRUB's snapshot booting needs a filesystem that has snapshots",
        detail=(
            "The strongest argument for GRUB on Arch is that it can boot directly "
            "into a Btrfs snapshot when an update goes wrong. On ext4, XFS or "
            "F2FS there are no snapshots to boot into, so that advantage is not "
            "part of this build."
        ),
        fix=(
            "Choose Btrfs if rollback matters to you. Otherwise systemd-boot is "
            "simpler and has less to go wrong."
        ),
        components=("grub",),
    ),
)


# ── Base, security, and choices that only bite later ─────────────────────────

SYSTEM_RULES: tuple[Rule, ...] = (
    Rule(
        id="manjaro-aur-mismatch",
        severity="info",
        when=Chose("base", "manjaro"),
        title="Manjaro holds packages back, and the AUR does not",
        detail=(
            "Manjaro delays Arch packages by roughly two weeks to test them, but "
            "AUR build recipes always target current Arch. So an AUR package can "
            "expect a library version Manjaro has not shipped yet, and the build "
            "fails for a reason that has nothing to do with the package itself. "
            "This is exactly the sort of hidden interaction this tool exists to "
            "surface, which is why Manjaro is in the catalogue at all."
        ),
        fix=(
            "Expect to wait, or build from the AUR sparingly. EndeavourOS stays "
            "close enough to vanilla Arch that the problem does not arise."
        ),
        components=("manjaro",),
    ),
    Rule(
        id="apparmor-needs-a-kernel-parameter",
        severity="info",
        when=Has("apparmor"),
        title="AppArmor does nothing until the kernel is told to load it",
        detail=(
            "Installing the packages and enabling the service is not enough: the "
            "security module has to be switched on at boot with a kernel "
            "parameter. Without it everything appears to be installed correctly "
            "and no profile is ever enforced, which is the worst of both worlds — "
            "the friction of having set it up and none of the protection."
        ),
        fix=(
            "Boot with lsm=landlock,lockdown,yama,integrity,apparmor,bpf. The "
            "generated install script writes it for you; this note explains what "
            "that line is."
        ),
        components=("apparmor",),
    ),
    Rule(
        id="hardened-desktop-friction",
        severity="info",
        when=AllOf(Has("hardened"), CategoryFilled("desktop"), Not(Has("headless"))),
        title="Expect to spend time on permission denials",
        detail=(
            "The hardened kernel disables features that ordinary desktop software "
            "uses, and sandboxing confines applications to paths you have to "
            "declare. The result is a machine that is genuinely harder to attack "
            "and that will, at some point, refuse to open a file you can plainly "
            "see. That is the profile working, not failing."
        ),
        fix=(
            "Keep this if the machine is a target worth hardening. For a desktop "
            "you use daily, AppArmor alone is most of the benefit for a fraction "
            "of the friction."
        ),
        components=("hardened",),
    ),
    Rule(
        id="tuned-kernel-on-non-x86",
        severity="error",
        # Stated positively on purpose. "Not x86_64" would also be true of a
        # machine whose architecture could not be read, and inventing an error
        # out of a missing reading is worse than staying quiet.
        when=AllOf(
            HasAnyOf("linux-zen", "linux-cachyos"),
            CpuArch("aarch64", "arm64", "armv7l", "riscv64"),
        ),
        title="The tuned kernels are built for x86 only",
        detail=(
            "linux-zen and the CachyOS kernels are compiled for x86-64 feature "
            "levels that do not exist on other architectures, and this machine "
            "reports a different one. There is no package to install."
        ),
        fix="Use the mainline kernel, which is built for this architecture.",
        components=("linux-zen", "linux-cachyos"),
    ),
    Rule(
        id="full-desktop-on-little-ram",
        severity="warning",
        when=AllOf(HasAnyOf("kde", "gnome"), RamBelowGb(8)),
        title="A full desktop on this much memory will feel it",
        detail=(
            "KDE Plasma and GNOME expect to be able to spend memory on a "
            "compositor, a search index, and a settings daemon. Below about 8 GB "
            "that competes with whatever you are actually trying to run, and the "
            "machine spends its time swapping."
        ),
        fix=(
            "Xfce on this hardware leaves considerably more memory for your work, "
            "and a tiling compositor like Sway less still."
        ),
        components=("kde", "gnome"),
    ),
    Rule(
        id="headless-with-a-display-server",
        severity="warning",
        when=AllOf(Has("headless"), HasAnyOf("wayland", "xorg")),
        title="A headless build does not need a display server",
        detail=(
            "Nothing in this build draws a window, so the display server is "
            "installed and never started. It is not harmful, but it pulls in a "
            "graphics stack that then has to be kept updated for no reason — and "
            "on a server, every package is another thing with a CVE."
        ),
        fix=(
            "Clear the display server selection. It is one of the two categories "
            "where an empty answer is the correct answer."
        ),
        components=("headless",),
    ),
)


# ── The rule set ──────────────────────────────────────────────────────────────

RULES: tuple[Rule, ...] = (
    *GRAPHICS_RULES,
    *AUDIO_RULES,
    *STORAGE_RULES,
    *SYSTEM_RULES,
)

RULES_BY_ID: dict[str, Rule] = {rule.id: rule for rule in RULES}


def rules_needing_hardware() -> tuple[Rule, ...]:
    """The rules that only run once a real machine has been read.

    Exposed so the interface can say how much of the rule set is being skipped
    on a build with no detection behind it, rather than quietly evaluating less
    than it claims.
    """
    return tuple(rule for rule in RULES if rule.when.needs_hardware)
