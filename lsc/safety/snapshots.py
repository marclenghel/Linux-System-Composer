"""Snapshots and rollback for the system being designed.

Read the name of this module carefully, because there are two different things
it could mean and only one of them is here.

It does **not** snapshot the machine you are running the composer on. Taking a
filesystem snapshot means root, and a tool whose stated promise is that it
never touches your system does not get to make an exception for the feature
called "safety". Rolling back what *this tool* did is a different job, done
without privileges, and it lives in rollback.py.

What this module does is work out whether the system being *designed* can roll
back at all, and say so while the decision is still reversible. Whether you can
undo a bad kernel update in six months is settled the moment you pick a
filesystem, which is exactly the kind of consequence-at-a-distance this whole
project exists to surface. Its output is advice and generated script comments.
"""

from __future__ import annotations

import textwrap
from dataclasses import dataclass

from lsc.models import Build

# Filesystems that can snapshot, and the tool people actually use with each.
SNAPSHOT_CAPABLE: dict[str, str] = {
    "btrfs": "snapper",
    "zfs": "zfs-auto-snapshot",
}


@dataclass(frozen=True)
class Advice:
    """What rollback will look like on the system this build describes."""

    filesystem: str | None
    capable: bool
    headline: str
    detail: str
    steps: tuple[str, ...] = ()
    packages: tuple[str, ...] = ()

    def as_script_comment(self) -> str:
        """The same advice, as commented lines for the generated installer.

        Comments rather than commands on purpose: a snapshot configuration is
        a decision about someone's disk layout, and this tool has not seen
        their disk. It writes down what to run, and a person runs it.
        """
        lines = [f"# {self.headline}", "#"]
        for sentence in textwrap.wrap(self.detail.rstrip(".") + ".", 68):
            lines.append(f"#   {sentence}")
        if self.steps:
            lines.append("#")
            for step in self.steps:
                lines.append(f"#   {step}")
        return "\n".join(lines)


def advise(build: Build) -> Advice:
    """What this build's filesystem choice means for recovering from a bad day."""
    filesystem = build.selected_id("filesystem")

    if filesystem == "btrfs":
        return Advice(
            filesystem=filesystem,
            capable=True,
            headline="Btrfs: this system can roll back a bad update",
            detail=(
                "Snapper takes a snapshot before every pacman transaction. "
                "A kernel or driver update that breaks the boot is undone by "
                "booting the previous snapshot rather than by rescuing the "
                "system from a live USB"
            ),
            steps=(
                "snapper -c root create-config /",
                "systemctl enable --now snapper-timeline.timer snapper-cleanup.timer",
                "# grub-btrfs puts the snapshots in the boot menu:",
                "systemctl enable --now grub-btrfsd",
            ),
            packages=("snapper", "snap-pac", "grub-btrfs"),
        )

    if filesystem == "zfs":
        return Advice(
            filesystem=filesystem,
            capable=True,
            headline="ZFS: this system can roll back a bad update",
            detail=(
                "Snapshots are free and instantaneous on ZFS. Take one before "
                "every system update and a broken upgrade costs you a reboot "
                "rather than an evening"
            ),
            steps=(
                "zfs snapshot zroot/ROOT/default@before-update",
                "zfs rollback zroot/ROOT/default@before-update   # if it goes wrong",
            ),
            packages=("zfs-auto-snapshot",),
        )

    if filesystem is None:
        return Advice(
            filesystem=None,
            capable=False,
            headline="No filesystem chosen, so nothing can be said about rollback",
            detail=(
                "Whether this system will be able to undo a bad update is "
                "decided by the filesystem, and that decision has not been "
                "made yet"
            ),
        )

    return Advice(
        filesystem=filesystem,
        capable=False,
        headline=f"{filesystem} cannot snapshot, so this system cannot roll back",
        detail=(
            "A kernel or driver update that fails to boot has to be repaired "
            "from a live USB. That is a normal way to run Linux and plenty of "
            "people do it, but it is worth choosing on purpose rather than "
            "discovering at midnight. Btrfs is the usual alternative, and this "
            "is the reason the Gaming preset selects it"
        ),
        steps=(
            "# Without snapshots, keep a fallback kernel installed:",
            "pacman -S --needed linux-lts",
            "# and keep the last few kernels in the boot menu.",
        ),
    )
