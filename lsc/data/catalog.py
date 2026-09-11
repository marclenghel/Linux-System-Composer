"""The component catalogue — the heart of the project's content.

Scope note: the README picks the Arch ecosystem as the single starting target,
so every component below is something you can actually install on an Arch-based
system. Supporting Debian and Fedora later means adding more catalogues, not
changing this file's shape.

The `requires` / `conflicts` / `recommends` fields are already filled in even
though no real engine reads them yet. Writing the knowledge down while it is
fresh is the cheap part; the engine that reasons over it is the expensive part.
"""

from __future__ import annotations

from lsc.models import Category, Component, Layer

# ── Stack layers ──────────────────────────────────────────────────────────────
#
# Listed top-down, which is the order the diagram draws them in: applications at
# the top, physical hardware at the bottom. A layer is linked to the category
# that fills it through Category.layer, so adding a category with a known layer
# makes it appear in the diagram automatically.

LAYERS: tuple[Layer, ...] = (
    Layer("apps", "Applications", "Browsers, editors, games — whatever the machine is for"),
    Layer("desktop", "Desktop / WM", "What you actually look at and click on"),
    Layer("audio", "Audio", "How sound gets from an application to the speakers"),
    Layer("display", "Display Server", "Draws windows and routes input"),
    Layer("init", "Init & Services", "PID 1 — starts everything else and keeps it running"),
    Layer("drivers", "GPU Driver", "Translates between the kernel and the graphics card"),
    Layer("storage", "Filesystem", "How bytes are laid out on the disk"),
    Layer("kernel", "Kernel", "Talks to the hardware; everything above depends on it"),
    Layer("boot", "Bootloader", "Firmware hands control here, this hands it to the kernel"),
    Layer("hardware", "Hardware", "The physical machine — detected, not chosen"),
)

# Layers that hold a fixed value in this milestone rather than a user choice.
FIXED_LAYERS: dict[str, str] = {
    "apps": "chosen per preset",
    "init": "systemd",
    "hardware": "detected",
}


# ── Base system ───────────────────────────────────────────────────────────────

BASE = Category(
    id="base",
    name="Base System",
    layer="base",
    question="Which Arch-based foundation?",
    description=(
        "The base decides which repositories you get, how fast packages move, and how "
        "much is set up for you before you start. Everything else in this composer "
        "assumes pacman and Arch package naming."
    ),
    default="arch",
    components=(
        Component(
            id="arch",
            name="Arch Linux",
            summary="Rolling release, nothing you did not install yourself",
            description=(
                "The reference point. A rolling release, pacman, the AUR, and an install "
                "that contains almost nothing until you add it. The best choice when the "
                "goal is to understand the system you are building, because nothing is "
                "hidden behind a vendor's defaults."
            ),
            tags=("rolling", "minimal", "pacman"),
            packages=("base", "base-devel", "linux-firmware"),
        ),
        Component(
            id="cachyos",
            name="CachyOS",
            summary="Arch plus performance-tuned kernels and optimised repos",
            description=(
                "Arch underneath, with its own repositories built for newer CPU feature "
                "levels (x86-64-v3 and v4) and a set of aggressively tuned kernels. Aimed "
                "at desktops and gaming. The tradeoff is one more party between you and "
                "upstream Arch."
            ),
            tags=("rolling", "performance", "gaming"),
            recommends=("linux-cachyos",),
            packages=("base", "base-devel", "cachyos-keyring"),
            maturity="modern",
        ),
        Component(
            id="endeavouros",
            name="EndeavourOS",
            summary="Near-vanilla Arch with a graphical installer",
            description=(
                "Arch with the installation sanded down and a small set of convenience "
                "packages. After install it stays close enough to vanilla that Arch Wiki "
                "instructions apply directly, which is exactly what you want while "
                "learning."
            ),
            tags=("rolling", "beginner-friendly"),
            packages=("base", "base-devel"),
        ),
        Component(
            id="manjaro",
            name="Manjaro",
            summary="Arch-derived, but packages are held back roughly two weeks",
            description=(
                "Manjaro delays Arch packages to test them. That sounds safer and often "
                "is, but the AUR always builds against current Arch, so an AUR package "
                "can expect libraries Manjaro has not shipped yet. Worth knowing about "
                "precisely because it is the kind of hidden interaction this project "
                "exists to surface."
            ),
            tags=("rolling", "delayed", "aur-risk"),
            packages=("base", "base-devel"),
        ),
    ),
)


# ── Kernel ────────────────────────────────────────────────────────────────────

KERNEL = Category(
    id="kernel",
    name="Kernel",
    layer="kernel",
    question="Which kernel?",
    description=(
        "The kernel sets the floor for everything above it: which GPU drivers build, "
        "which filesystems exist, which compositor features work. Newer is usually "
        "better for new hardware and worse for modules built outside the kernel tree."
    ),
    default="linux",
    components=(
        Component(
            id="linux",
            name="linux",
            summary="The current mainline stable kernel",
            description=(
                "Vanilla upstream, packaged by Arch. The default answer. New hardware "
                "support arrives quickly, and every wiki page assumes you are running it."
            ),
            tags=("mainline", "default"),
            packages=("linux", "linux-headers"),
        ),
        Component(
            id="linux-lts",
            name="linux-lts",
            summary="Long-term support — older, slower moving, more predictable",
            description=(
                "Tracks an upstream long-term series. Fewer surprises across updates, "
                "which matters when you depend on modules built outside the kernel tree "
                "— the proprietary NVIDIA driver, ZFS, VirtualBox. The cost is late "
                "support for hardware released after the branch was cut."
            ),
            tags=("lts", "conservative"),
            packages=("linux-lts", "linux-lts-headers"),
        ),
        Component(
            id="linux-zen",
            name="linux-zen",
            summary="Mainline patched for desktop responsiveness",
            description=(
                "A collection of patches aimed at interactive workloads — scheduling and "
                "latency tweaks rather than raw throughput. A safe first step away from "
                "vanilla: still mainline, still current, just tuned for a desktop."
            ),
            tags=("desktop", "low-latency"),
            packages=("linux-zen", "linux-zen-headers"),
        ),
        Component(
            id="linux-cachyos",
            name="linux-cachyos",
            summary="Heavily tuned scheduler and build flags",
            description=(
                "Alternative CPU schedulers (BORE and sched-ext among them), link-time "
                "optimisation, and builds targeting newer instruction set levels. Real "
                "gains on interactive and gaming workloads. Needs the CachyOS "
                "repositories, so it drags the base choice along with it."
            ),
            tags=("performance", "gaming", "scheduler"),
            requires=("cachyos",),
            packages=("linux-cachyos", "linux-cachyos-headers"),
            maturity="modern",
        ),
        Component(
            id="linux-hardened",
            name="linux-hardened",
            summary="Security patches first, compatibility second",
            description=(
                "Upstream hardening patches plus stricter defaults. Genuinely raises the "
                "bar against exploitation, and genuinely breaks things: some out-of-tree "
                "modules, some virtualisation, most anti-cheat. Pick it when the "
                "machine's job is to be hard to attack."
            ),
            tags=("security", "hardened"),
            conflicts=("nvidia",),
            packages=("linux-hardened", "linux-hardened-headers"),
        ),
    ),
)


# ── Bootloader ────────────────────────────────────────────────────────────────

BOOTLOADER = Category(
    id="bootloader",
    name="Bootloader",
    layer="boot",
    question="What hands control to the kernel?",
    description=(
        "The first thing you configure and the first thing that can leave you with an "
        "unbootable machine. This is the layer the project's planned safety features — "
        "fallback entries, booting from a snapshot — will live in."
    ),
    default="systemd-boot",
    components=(
        Component(
            id="systemd-boot",
            name="systemd-boot",
            summary="Minimal UEFI loader, already on the system",
            description=(
                "Ships with systemd, is configured with a handful of plain text files, "
                "and does almost nothing beyond listing kernels and starting one. UEFI "
                "only, and the EFI partition has to be mounted where the kernels live. "
                "The simplicity is the feature."
            ),
            tags=("uefi", "simple"),
        ),
        Component(
            id="grub",
            name="GRUB",
            summary="Does everything, and is complicated in proportion",
            description=(
                "Boots BIOS and UEFI, reads encrypted volumes, and with grub-btrfs can "
                "list Btrfs snapshots as boot entries — which is how you roll back a "
                "broken update from the boot menu. Its configuration is generated rather "
                "than written, which makes it powerful and opaque at the same time."
            ),
            tags=("bios", "uefi", "snapshots"),
            recommends=("btrfs",),
            packages=("grub", "efibootmgr"),
        ),
        Component(
            id="refind",
            name="rEFInd",
            summary="Graphical UEFI boot menu that finds kernels on its own",
            description=(
                "Scans your partitions and presents what it finds, with icons and a "
                "theme. Pleasant on multi-boot machines where you are choosing between "
                "whole operating systems rather than kernel versions."
            ),
            tags=("uefi", "graphical", "multi-boot"),
            packages=("refind",),
        ),
        Component(
            id="limine",
            name="Limine",
            summary="Modern, fast, small, BIOS and UEFI",
            description=(
                "A newer loader with a readable configuration file and support for both "
                "firmware types. Less battle-tested than GRUB, with a smaller pool of "
                "people who can help when it breaks."
            ),
            tags=("bios", "uefi", "modern"),
            packages=("limine",),
            maturity="modern",
        ),
    ),
)


# ── Filesystem ────────────────────────────────────────────────────────────────

FILESYSTEM = Category(
    id="filesystem",
    name="Filesystem",
    layer="storage",
    question="How should the root filesystem be laid out?",
    description=(
        "The hardest choice to change later — it is decided at install time and "
        "reversing it means reinstalling. It also decides whether the safety features "
        "in this project's roadmap are possible on your machine at all."
    ),
    default="ext4",
    components=(
        Component(
            id="ext4",
            name="ext4",
            summary="The boring, correct default",
            description=(
                "Twenty years of production use. Fast, predictable, recoverable, and "
                "understood by every recovery tool that exists. What it does not give "
                "you is snapshots, checksums, or transparent compression."
            ),
            tags=("default", "reliable"),
            packages=("e2fsprogs",),
        ),
        Component(
            id="btrfs",
            name="Btrfs",
            summary="Copy-on-write: snapshots, subvolumes, compression",
            description=(
                "Lets you snapshot the system before an update and roll back in seconds "
                "if it goes wrong — the single most useful safety net on a rolling "
                "release. Also gives checksummed data and transparent compression. "
                "Databases and virtual machine images want copy-on-write switched off on "
                "their directories, or they fragment badly."
            ),
            tags=("cow", "snapshots", "compression"),
            recommends=("grub",),
            packages=("btrfs-progs", "snapper"),
        ),
        Component(
            id="xfs",
            name="XFS",
            summary="Built for large files and parallel throughput",
            description=(
                "Excellent with big sequential files and many concurrent writers. The "
                "catch that surprises people: an XFS filesystem can grow but can never "
                "shrink."
            ),
            tags=("throughput", "large-files"),
            packages=("xfsprogs",),
        ),
        Component(
            id="zfs",
            name="ZFS",
            summary="The strongest integrity guarantees, the most friction",
            description=(
                "Checksums everything, self-heals from redundancy, and can send snapshots "
                "over the network. It also lives outside the kernel tree for licensing "
                "reasons, so every kernel update becomes a question of whether ZFS has "
                "caught up. Pair it with an LTS kernel, or accept that you will "
                "occasionally have to wait before rebooting."
            ),
            tags=("integrity", "raid", "out-of-tree"),
            recommends=("linux-lts",),
            conflicts=("linux-hardened",),
            packages=("zfs-dkms", "zfs-utils"),
        ),
        Component(
            id="f2fs",
            name="F2FS",
            summary="Designed around how flash storage actually works",
            description=(
                "Log-structured and built for NAND. Meaningful on cheap eMMC and SD "
                "cards; on a decent NVMe drive the difference against ext4 is mostly "
                "theoretical."
            ),
            tags=("flash", "mobile"),
            packages=("f2fs-tools",),
        ),
    ),
)


# ── GPU driver ────────────────────────────────────────────────────────────────

GPU = Category(
    id="gpu",
    name="GPU Driver",
    layer="drivers",
    question="Which graphics stack?",
    description=(
        "The layer that produces the most broken systems, because it sits between a "
        "kernel that updates weekly and a compositor that assumes features the driver "
        "may not have. This is the single best argument for the whole project."
    ),
    default="mesa",
    components=(
        Component(
            id="mesa",
            name="Mesa (AMD / Intel)",
            summary="Open drivers, in the kernel, nothing to install",
            description=(
                "AMD and Intel graphics are supported by code that ships in the kernel "
                "and in Mesa. There is no driver installation step, no module rebuild, no "
                "version pinning. Wayland compositors were developed against this stack, "
                "so it is the path with the fewest surprises."
            ),
            tags=("open-source", "amd", "intel"),
            recommends=("wayland",),
            packages=("mesa", "vulkan-radeon", "vulkan-intel", "libva-mesa-driver"),
        ),
        Component(
            id="nvidia",
            name="NVIDIA (proprietary)",
            summary="Best performance on NVIDIA cards, most moving parts",
            description=(
                "The closed driver. Fastest option on NVIDIA hardware and the only one "
                "with full CUDA. It is a module built outside the kernel tree, so it has "
                "to be rebuilt for every kernel, and Wayland needs DRM kernel mode "
                "setting turned on explicitly before the compositor will start."
            ),
            tags=("proprietary", "nvidia", "cuda"),
            conflicts=("nouveau", "linux-hardened"),
            packages=("nvidia-dkms", "nvidia-utils", "lib32-nvidia-utils"),
        ),
        Component(
            id="nvidia-open",
            name="NVIDIA (open modules)",
            summary="NVIDIA's own open kernel modules — Turing and newer only",
            description=(
                "NVIDIA's open-source kernel module with the same closed user-space "
                "libraries on top. Now the vendor's recommended path on recent cards and "
                "noticeably better behaved on Wayland. Requires an RTX 20-series GPU or "
                "newer; older cards must use the closed module."
            ),
            tags=("nvidia", "open-kernel-module", "turing+"),
            conflicts=("nouveau",),
            recommends=("wayland",),
            packages=("nvidia-open-dkms", "nvidia-utils"),
            maturity="modern",
        ),
        Component(
            id="nouveau",
            name="Nouveau",
            summary="Reverse-engineered NVIDIA driver",
            description=(
                "Fully open and already in the kernel, so it simply works — at a fraction "
                "of the card's performance on most models, because clock speeds cannot be "
                "raised without signed firmware. Fine for a terminal and a browser, not "
                "for anything demanding."
            ),
            tags=("open-source", "nvidia", "limited-performance"),
            conflicts=("nvidia", "nvidia-open"),
            packages=("mesa", "xf86-video-nouveau"),
        ),
        Component(
            id="vm-guest",
            name="Virtual machine guest",
            summary="Paravirtualised graphics for a VM",
            description=(
                "For systems that will run inside QEMU/KVM, VirtualBox, or VMware. Uses "
                "the host's GPU through a virtual device instead of talking to real "
                "hardware. The right answer when you are testing a build before putting "
                "it on metal."
            ),
            tags=("virtual", "testing"),
            packages=("mesa", "xf86-video-vmware", "spice-vdagent"),
        ),
    ),
)


# ── Display server ────────────────────────────────────────────────────────────

DISPLAY = Category(
    id="display",
    name="Display Server",
    layer="display",
    question="Wayland or X11?",
    description=(
        "The protocol between applications and whatever draws them. This choice "
        "constrains the desktop list above it and is constrained by the GPU driver "
        "below it — a three-way relationship the composer exists to make visible."
    ),
    default="wayland",
    # A headless build legitimately has no display server at all, so an empty
    # selection here is a valid answer rather than an unanswered question.
    optional=True,
    components=(
        Component(
            id="wayland",
            name="Wayland",
            summary="The modern protocol — where all active development is",
            description=(
                "Applications draw their own windows and the compositor arranges them. "
                "Better isolation between applications, per-monitor scaling and refresh "
                "rates that actually work, and no tearing by design. Programs written for "
                "X11 run through the XWayland compatibility layer, which is good but not "
                "invisible: some screen recording and global-hotkey tools still need "
                "Wayland-native replacements."
            ),
            tags=("modern", "isolated", "hidpi"),
            packages=("wayland", "xorg-xwayland"),
        ),
        Component(
            id="xorg",
            name="Xorg (X11)",
            summary="Mature, universal, effectively frozen",
            description=(
                "Thirty-odd years of software targets it, and every screen-sharing, "
                "remote-desktop, automation, and accessibility tool works. It is also in "
                "maintenance mode, has no real isolation between applications, and "
                "handles mixed-DPI multi-monitor setups poorly. Still the pragmatic "
                "choice for some hardware and some workflows."
            ),
            tags=("legacy", "compatible", "frozen"),
            packages=("xorg-server", "xorg-xinit"),
            maturity="legacy",
        ),
    ),
)


# ── Desktop / window manager ──────────────────────────────────────────────────

DESKTOP = Category(
    id="desktop",
    name="Desktop / WM",
    layer="desktop",
    question="What do you want to look at?",
    description=(
        "A full desktop environment brings its own settings app, file manager, "
        "portals, and lock screen. A bare window manager brings a window manager, and "
        "you assemble the rest yourself."
    ),
    default="kde",
    components=(
        Component(
            id="hyprland",
            name="Hyprland",
            summary="Wayland tiling compositor with animations",
            description=(
                "Dynamic tiling, smooth animations, and a configuration file you are "
                "expected to write yourself. Extremely popular in customised-desktop "
                "circles. Wayland only, moves fast enough that configuration syntax "
                "occasionally breaks between releases, and historically the hardest "
                "compositor to run on NVIDIA."
            ),
            tags=("wayland", "tiling", "customisable"),
            requires=("wayland",),
            recommends=("pipewire",),
            packages=("hyprland", "waybar", "wofi", "xdg-desktop-portal-hyprland"),
            maturity="modern",
        ),
        Component(
            id="kde",
            name="KDE Plasma",
            summary="Full desktop, configurable down to the pixel",
            description=(
                "A complete environment with a settings panel for everything, and a "
                "Wayland session that is now the default and in good shape. The most "
                "familiar landing spot for someone arriving from Windows."
            ),
            tags=("wayland", "x11", "full-desktop"),
            recommends=("pipewire",),
            packages=("plasma-meta", "konsole", "dolphin"),
        ),
        Component(
            id="gnome",
            name="GNOME",
            summary="Full desktop, opinionated, very stable",
            description=(
                "Does things one way and does them well. The Wayland session is mature, "
                "and it is what most distributions ship and test by default. "
                "Customisation means extensions, and extensions break at major releases."
            ),
            tags=("wayland", "full-desktop", "opinionated"),
            recommends=("pipewire",),
            packages=("gnome", "gnome-tweaks"),
        ),
        Component(
            id="sway",
            name="Sway",
            summary="i3's layout and config file, on Wayland",
            description=(
                "A deliberate drop-in replacement for i3: the same manual tiling model "
                "and a nearly identical configuration file, running natively on Wayland. "
                "Stable and unexciting, which for a window manager is a compliment."
            ),
            tags=("wayland", "tiling", "i3-compatible"),
            requires=("wayland",),
            packages=("sway", "swaybg", "waybar", "foot"),
        ),
        Component(
            id="niri",
            name="niri",
            summary="Scrollable tiling — windows in an infinite row",
            description=(
                "Instead of subdividing the screen, windows sit in an endless horizontal "
                "strip that you scroll through, so opening a new window never resizes the "
                "ones you were already using. Young, but unusually well built, and a "
                "genuinely different idea worth demonstrating."
            ),
            tags=("wayland", "scrollable-tiling", "novel"),
            requires=("wayland",),
            packages=("niri", "waybar", "fuzzel"),
            maturity="experimental",
        ),
        Component(
            id="i3",
            name="i3",
            summary="The classic X11 tiling window manager",
            description=(
                "Manual tiling, a tiny resource footprint, and documentation that has "
                "been stable for a decade. X11 only — on Wayland, Sway is the direct "
                "equivalent."
            ),
            tags=("x11", "tiling", "lightweight"),
            requires=("xorg",),
            packages=("i3-wm", "i3status", "dmenu", "alacritty"),
        ),
        Component(
            id="xfce",
            name="Xfce",
            summary="Lightweight traditional desktop",
            description=(
                "A conventional desktop that runs comfortably on hardware other "
                "environments struggle with. Still X11 in practice; the Wayland port is "
                "in progress."
            ),
            tags=("x11", "lightweight", "traditional"),
            requires=("xorg",),
            packages=("xfce4", "xfce4-goodies"),
        ),
        Component(
            id="headless",
            name="No desktop (headless)",
            summary="Server or container — no graphical session at all",
            description=(
                "Stops the stack at the console. Correct for servers, build machines, and "
                "anything you will only ever reach over SSH, and it makes every layer "
                "above the kernel considerably simpler. With this selected the display "
                "server choice stops mattering — leave it unset."
            ),
            tags=("server", "console"),
            packages=("openssh",),
        ),
    ),
)


# ── Audio ─────────────────────────────────────────────────────────────────────

AUDIO = Category(
    id="audio",
    name="Audio Stack",
    layer="audio",
    question="How is sound handled?",
    description=(
        "Linux audio is three layers pretending to be one: kernel drivers, a sound "
        "server, and a compatibility interface for applications. The choice here is "
        "really about which sound server sits in the middle."
    ),
    default="pipewire",
    components=(
        Component(
            id="pipewire",
            name="PipeWire",
            summary="The current answer — replaces PulseAudio and JACK at once",
            description=(
                "Handles both ordinary desktop audio and low-latency professional audio "
                "through one server, while pretending to be PulseAudio, JACK, and ALSA so "
                "existing applications keep working. It also carries screen sharing on "
                "Wayland, which makes it effectively mandatory for a Wayland desktop."
            ),
            tags=("modern", "low-latency", "default"),
            conflicts=("pulseaudio",),
            packages=("pipewire", "pipewire-pulse", "pipewire-alsa", "wireplumber"),
        ),
        Component(
            id="pulseaudio",
            name="PulseAudio",
            summary="The previous standard, still perfectly functional",
            description=(
                "What everything used before PipeWire. Well understood and stable, but no "
                "longer where the work is happening, and it does not provide the screen "
                "sharing pieces a Wayland desktop expects."
            ),
            tags=("legacy", "stable"),
            conflicts=("pipewire",),
            packages=("pulseaudio", "pulseaudio-alsa", "pavucontrol"),
            maturity="legacy",
        ),
        Component(
            id="alsa",
            name="ALSA only",
            summary="Kernel drivers, no sound server",
            description=(
                "Straight to the hardware with nothing in between. The lowest possible "
                "overhead, and generally one application gets the sound card at a time. "
                "Appropriate for embedded systems and single-purpose machines, painful on "
                "a desktop."
            ),
            tags=("minimal", "embedded"),
            conflicts=("pipewire", "pulseaudio"),
            packages=("alsa-utils",),
        ),
    ),
)


# ── Security profile ──────────────────────────────────────────────────────────

SECURITY = Category(
    id="security",
    name="Security Profile",
    layer="security",
    question="How locked down should this be?",
    description=(
        "Mandatory access control confines a program to what it is supposed to touch, "
        "so a compromised browser cannot read your SSH keys. It costs setup effort and "
        "the occasional mysterious permission denial."
    ),
    default="baseline",
    components=(
        Component(
            id="baseline",
            name="Baseline",
            summary="Standard permissions, firewall on, nothing exotic",
            description=(
                "Ordinary Unix permissions, sudo, regular updates, and a firewall that "
                "denies incoming connections. Not hardened, but not negligent either — "
                "the sane default for a personal machine."
            ),
            tags=("default",),
            packages=("ufw",),
        ),
        Component(
            id="apparmor",
            name="AppArmor",
            summary="Path-based confinement, well supported on Arch",
            description=(
                "Profiles describe which files and capabilities a program may use, keyed "
                "on executable paths. Easier to read and write than the alternative, and "
                "Arch supports it directly. It needs a kernel parameter to enable the "
                "security module at boot — exactly the kind of step a generated config "
                "should write for you."
            ),
            tags=("mac", "confinement"),
            packages=("apparmor", "audit"),
        ),
        Component(
            id="selinux",
            name="SELinux",
            summary="Label-based confinement — not supported on stock Arch",
            description=(
                "The stricter and more thorough model, and the default on Fedora and "
                "RHEL. On Arch it requires replacing core packages with SELinux-patched "
                "rebuilds from the AUR, which puts you outside the supported "
                "configuration for everything else. A textbook example of a choice that "
                "is fine on one distribution and a trap on another."
            ),
            tags=("mac", "labels", "unsupported-on-arch"),
            conflicts=("arch", "cachyos", "endeavouros", "manjaro", "apparmor"),
            packages=("selinux-refpolicy-arch",),
        ),
        Component(
            id="hardened",
            name="Hardened",
            summary="Hardened kernel, sandboxing, strict firewall",
            description=(
                "Stacks the hardened kernel with per-application sandboxing and a "
                "default-deny firewall. Meaningfully harder to attack and meaningfully "
                "more annoying to use — expect to spend time working out why a program "
                "cannot open a file it obviously should be able to."
            ),
            tags=("hardened", "sandboxing"),
            requires=("linux-hardened",),
            packages=("firejail", "nftables", "apparmor", "audit"),
        ),
    ),
)


# ── The catalogue ─────────────────────────────────────────────────────────────
#
# Order matters: this is the order the categories appear in the composer, and
# roughly the order you would actually make the decisions in.

CATEGORIES: tuple[Category, ...] = (
    BASE,
    KERNEL,
    BOOTLOADER,
    FILESYSTEM,
    GPU,
    DISPLAY,
    DESKTOP,
    AUDIO,
    SECURITY,
)

# Lookups, built once at import time.
CATEGORIES_BY_ID: dict[str, Category] = {c.id: c for c in CATEGORIES}
CATEGORY_BY_LAYER: dict[str, Category] = {c.layer: c for c in CATEGORIES}
COMPONENTS_BY_ID: dict[str, Component] = {
    component.id: component for category in CATEGORIES for component in category.components
}


def component_name(component_id: str) -> str:
    """Human-readable name for an id, falling back to the id itself.

    Used wherever a `requires` / `conflicts` id has to be shown to a person.
    """
    component = COMPONENTS_BY_ID.get(component_id)
    return component.name if component else component_id


def default_selections() -> dict[str, str]:
    """The build a new user starts from — every category's declared default."""
    return {c.id: c.default for c in CATEGORIES if c.default is not None}
