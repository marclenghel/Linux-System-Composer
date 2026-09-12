"""The only module in this project that creates files.

Milestone 4 is this file, and it is deliberately the smallest interesting file
in the repository. Everything that required a judgement — what the files should
contain, whether the build is fit to write, whether the directory is a
reasonable place to put anything — was decided before apply() is called. What
is left is carrying out a plan that has already been checked, and writing down
what was done so it can be undone.

Three rules hold here, and tests/test_architecture.py enforces all three:

  * every path goes through paths.ensure_within() before it is opened, so a
    write cannot escape the directory the user named;
  * anything replaced is copied into .lsc-backups/ first, so a write is never
    destructive;
  * a journal is saved afterwards, so the write can be reversed.
"""

from __future__ import annotations

import os
import pathlib
import shutil
from dataclasses import dataclass

from lsc import __version__
from lsc.generate.plan import WritePlan
from lsc.safety import journal
from lsc.safety.paths import ensure_within


class Refused(Exception):
    """apply() was called on a plan that preflight had already blocked.

    The Export screen never gets here because it does not offer the button,
    but the function is public and the command line calls it too, so refusing
    loudly beats trusting every caller to have checked.
    """


@dataclass(frozen=True)
class WriteResult:
    """What actually happened."""

    target: pathlib.Path
    created: tuple[str, ...] = ()
    replaced: tuple[str, ...] = ()
    unchanged: tuple[str, ...] = ()
    preexisting: tuple[str, ...] = ()
    backups: tuple[str, ...] = ()
    journal_path: pathlib.Path | None = None
    dry_run: bool = False

    @property
    def touched(self) -> tuple[str, ...]:
        return self.created + self.replaced

    def summary(self) -> str:
        if self.dry_run:
            return f"Dry run — nothing written to {self.target}"
        parts = []
        if self.created:
            parts.append(f"{len(self.created)} created")
        if self.replaced:
            parts.append(f"{len(self.replaced)} replaced")
        if self.unchanged:
            parts.append(f"{len(self.unchanged)} already current")
        if self.preexisting:
            parts.append(f"{len(self.preexisting)} left alone (not ours)")
        if self.backups:
            parts.append(f"{len(self.backups)} backed up")
        return f"{self.target}: " + (", ".join(parts) if parts else "nothing to do")


def apply(plan: WritePlan, *, dry_run: bool = False) -> WriteResult:
    """Carry out a plan. With dry_run, report what it would have done instead.

    The dry run returns here rather than in the caller so that both modes
    produce the same WriteResult from the same code path. A dry run that goes
    down a different branch than the real thing is a dry run that can be wrong
    about the real thing.
    """
    if not plan.may_write:
        reasons = "; ".join(b.message for b in plan.preflight.blockers)
        raise Refused(f"preflight blocked this write: {reasons}")

    root = plan.target
    created: list[str] = []
    replaced: list[str] = []
    unchanged: list[str] = []
    preexisting: list[str] = []
    backups: list[str] = []

    buckets = {
        "create": created,
        "replace": replaced,
        "unchanged": unchanged,
        "preexisting": preexisting,
    }

    if dry_run:
        for action in plan.actions:
            buckets[action.action].append(action.name)
        return WriteResult(
            target=root,
            created=tuple(created),
            replaced=tuple(replaced),
            unchanged=tuple(unchanged),
            preexisting=tuple(preexisting),
            dry_run=True,
        )

    root.mkdir(parents=False, exist_ok=True)

    backup_root = _free_backup_directory(root)

    recorded: list[journal.WrittenFile] = []

    for action in plan.actions:
        destination = ensure_within(root, root / action.name)
        backup_name: str | None = None

        if action.action == "preexisting":
            # Identical to what we would write, but it was here first. Touching
            # nothing and recording nothing is the only honest option: the file
            # is not ours, so rollback must not remove it.
            preexisting.append(action.name)
            continue

        if action.action == "unchanged":
            unchanged.append(action.name)
            # Still recorded, because a previous write of ours did put it here.
            # Without this, rollback would leave behind the one file that
            # happened to already match what we were about to write.
            recorded.append(
                journal.WrittenFile(action.name, action.sha256, "created", None)
            )
            continue

        if action.action == "replace":
            backup_root.mkdir(parents=True, exist_ok=True)
            backup_path = ensure_within(root, backup_root / action.name)
            shutil.copy2(destination, backup_path)
            backup_name = str(backup_path.relative_to(root)).replace(os.sep, "/")
            backups.append(backup_name)
            replaced.append(action.name)
        else:
            created.append(action.name)

        # Binary mode with explicit "\n": a generated shell script with CRLF
        # endings fails on the machine it was written for, and this tool runs
        # on Windows while writing files meant for Linux.
        destination.write_bytes(action.contents.encode("utf-8"))

        if action.executable:
            _make_executable(destination)

        recorded.append(
            journal.WrittenFile(
                name=action.name,
                sha256=action.sha256,
                action="overwritten" if action.action == "replace" else "created",
                backup=backup_name,
            )
        )

    entry = journal.Journal(
        build_name=plan.build_name,
        composer_version=__version__,
        written_at=journal.now(),
        files=tuple(recorded),
        selections=dict(plan.selections),
    )
    journal_path = journal.save(root, entry)

    return WriteResult(
        target=root,
        created=tuple(created),
        replaced=tuple(replaced),
        unchanged=tuple(unchanged),
        preexisting=tuple(preexisting),
        backups=tuple(backups),
        journal_path=journal_path,
    )


def _free_backup_directory(root: pathlib.Path) -> pathlib.Path:
    """A backup directory for this write that does not already exist.

    The timestamp alone would almost always do, and "almost always" is not the
    standard the safety layer is held to: the whole reason backups go in a
    directory per write is so that one write cannot destroy another's, and a
    name collision would quietly undo that.
    """
    base = root / journal.BACKUP_DIRECTORY
    stamp = journal.backup_stamp()
    candidate = base / stamp
    attempt = 2
    while candidate.exists():
        candidate = base / f"{stamp}-{attempt}"
        attempt += 1
    return ensure_within(root, candidate)


def _make_executable(path: pathlib.Path) -> None:
    """Set the execute bit, where there is one.

    Windows has no execute bit and chmod there is a no-op that still succeeds,
    so this is guarded rather than wrapped in a try: a silent no-op is correct
    on Windows and a failure worth knowing about on Linux.
    """
    if os.name != "posix":
        return
    mode = path.stat().st_mode
    path.chmod(mode | 0o111)
