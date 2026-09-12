"""Undo a write, without ever destroying something that was not ours.

The rule this module is built around: a file is only removed or restored if it
is still byte-for-byte what we wrote. Everything else is left alone and
reported. If you generated an install script last week, spent an hour editing
it, and then pressed Roll back, the correct behaviour is to keep your hour of
work and say so — not to restore the pristine generated version over the top
of it, and certainly not to delete it.

That is what the hashes in the journal are for, and it is the difference
between a rollback you can press without thinking and one you have to reason
about first.

This module writes to the disk — restoring a backup and deleting a generated
file are both mutations — so like writer.py it goes through paths.ensure_within
for every path it touches, and it will not act on a directory it has no
journal for.
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass

from lsc.safety import journal
from lsc.safety.paths import ensure_within, resolve


class NothingToRollBack(Exception):
    """There is no journal in this directory, so nothing here is known to be ours."""


@dataclass(frozen=True)
class RollbackResult:
    """What undoing the write did, or would have done."""

    target: pathlib.Path
    removed: tuple[str, ...] = ()        # files we created and have now deleted
    restored: tuple[str, ...] = ()       # files we replaced, put back as they were
    kept: tuple[tuple[str, str], ...] = ()   # (filename, why it was left alone)
    dry_run: bool = False

    def summary(self) -> str:
        verb = "would be" if self.dry_run else "were"
        parts = []
        if self.removed:
            parts.append(f"{len(self.removed)} {verb} removed")
        if self.restored:
            parts.append(f"{len(self.restored)} {verb} restored")
        if self.kept:
            parts.append(f"{len(self.kept)} left alone")
        head = f"{self.target}: " + (", ".join(parts) if parts else "nothing to undo")
        if not self.kept:
            return head
        lines = [head, ""]
        for name, why in self.kept:
            lines.append(f"  kept  {name} — {why}")
        return "\n".join(lines)


def roll_back(target: str | pathlib.Path, *, dry_run: bool = False) -> RollbackResult:
    """Put the directory back the way it was before the last write."""
    root = resolve(target)
    entry = journal.read(root)
    if entry is None:
        raise NothingToRollBack(
            f"{root} has no {journal.JOURNAL_NAME}, so nothing in it is known "
            f"to have been written by this tool. Nothing was touched."
        )

    removed: list[str] = []
    restored: list[str] = []
    kept: list[tuple[str, str]] = []

    for written in entry.files:
        path = ensure_within(root, root / written.name)

        if not path.exists():
            kept.append((written.name, "already gone"))
            continue

        current = journal.digest_of_file(path)
        if current != written.sha256:
            kept.append((written.name, "edited since it was generated"))
            continue

        if written.backup:
            backup = ensure_within(root, root / written.backup)
            if not backup.is_file():
                kept.append((written.name, "its backup is missing"))
                continue
            if not dry_run:
                path.write_bytes(backup.read_bytes())
            restored.append(written.name)
        else:
            if not dry_run:
                path.unlink()
            removed.append(written.name)

    # The journal describes a write that no longer stands, so it goes too —
    # but only when the undo was complete. A journal left behind after a
    # partial rollback is what lets a second attempt finish the job.
    if not dry_run and not kept:
        journal_path = ensure_within(root, journal.path_for(root))
        if journal_path.is_file():
            journal_path.unlink()

    return RollbackResult(
        target=root,
        removed=tuple(removed),
        restored=tuple(restored),
        kept=tuple(kept),
        dry_run=dry_run,
    )
