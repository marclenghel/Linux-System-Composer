"""What a write would do, worked out before anything is written.

A plan is the dry run. Building one reads the target directory and the build,
renders every file in full, and decides for each whether it would be created,
replaced, or left alone because it is already exactly right — but it opens
nothing for writing. The Export screen can therefore show the user the precise
consequences of a button before they press it, and the test suite can assert
on those consequences without a temporary directory.

Writing is then a separate, dumber step: writer.apply() takes a plan and
carries it out. Splitting it this way is what makes "dry run" a real mode
rather than a flag that some code paths remember to check.
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass, field
from typing import Any, Mapping

from lsc import content
from lsc.generate import render
from lsc.models import Build
from lsc.safety import journal, paths
from lsc.safety.preflight import Preflight, inspect

# The file that has to be runnable. Everything else this project generates is
# something you read, so it is the only one.
EXECUTABLE = "install.sh"


@dataclass(frozen=True)
class FileAction:
    """One file, and what would happen to it."""

    name: str                # filename, relative to the target directory
    kind: str                # the render kind that produced it
    contents: str
    action: str              # create | replace | unchanged | preexisting
    sha256: str
    executable: bool = False

    @property
    def changes_anything(self) -> bool:
        return self.action in ("create", "replace")

    @property
    def is_ours(self) -> bool:
        """Whether this file may go in the journal, and so be rolled back.

        "preexisting" is the one case where it may not: the file was already
        there before this tool ever wrote to the directory, and it happens to
        be byte-identical to what we would have written. Recording it would
        make rollback delete a file we never created.
        """
        return self.action != "preexisting"

    def line(self) -> str:
        """One row of the dry-run listing."""
        verb = {
            "create": "create ",
            "replace": "replace",
            "unchanged": "same as",
            "preexisting": "not ours",
        }[self.action]
        size = len(self.contents.encode("utf-8"))
        return f"  {verb}  {self.name:<16} {size:>6} bytes"


@dataclass(frozen=True)
class WritePlan:
    """Everything writer.apply() needs, and everything a person needs to judge it."""

    target: pathlib.Path
    build_name: str
    preflight: Preflight
    actions: tuple[FileAction, ...] = ()
    selections: dict[str, str] = field(default_factory=dict)

    @property
    def may_write(self) -> bool:
        return self.preflight.may_write

    @property
    def changes(self) -> tuple[FileAction, ...]:
        return tuple(a for a in self.actions if a.changes_anything)

    def summary(self) -> str:
        """The dry run as text, which is also what `--dry-run` prints."""
        lines = [f"Target  {self.target}", ""]

        if self.preflight.blockers:
            lines.append("REFUSED — nothing would be written:")
            for blocker in self.preflight.blockers:
                lines.append(f"  x  {blocker.message}")
                if blocker.fix:
                    lines.append(f"     {blocker.fix}")
            return "\n".join(lines)

        lines.append(f"{len(self.changes)} of {len(self.actions)} files would change:")
        lines.extend(action.line() for action in self.actions)

        untouched = [a for a in self.actions if a.action == "preexisting"]
        if untouched:
            lines += [
                "",
                "Already present and identical, but not written by this tool, so "
                "left out of the journal and not removed by Roll back:",
            ]
            lines.extend(f"  -  {a.name}" for a in untouched)

        replaced = [a for a in self.actions if a.action == "replace"]
        if replaced:
            lines += [
                "",
                f"{len(replaced)} existing "
                f"{'file' if len(replaced) == 1 else 'files'} would be copied into "
                f"{journal.BACKUP_DIRECTORY}/ first.",
            ]

        if self.preflight.notes:
            lines += ["", "Worth knowing:"]
            for note in self.preflight.notes:
                lines.append(f"  -  {note.message}")

        return "\n".join(lines)


def filenames() -> tuple[str, ...]:
    """The files a write produces. Taken from the interface copy rather than
    repeated here, so the screen and the writer can never disagree about what
    a build generates."""
    return tuple(filename for _kind, filename, _description in content.EXPORT_FILES)


def plan(
    build: Build,
    target: str | pathlib.Path,
    hardware_profile: Mapping[str, Any] | None = None,
) -> WritePlan:
    """Work out what writing this build into this directory would do."""
    resolved = paths.resolve(target)
    preflight = inspect(build, resolved, hardware_profile, filenames=filenames())

    # What this directory already knows about itself. A file that matches what
    # we are about to write is only "unchanged" if a previous write of ours put
    # it there; otherwise it was already someone else's, and the fact that it
    # happens to be identical does not make it ours to delete later.
    record = journal.read(resolved)
    ours = {written.name for written in record.files} if record else set()

    actions: list[FileAction] = []
    for kind, filename, _description in content.EXPORT_FILES:
        text = render.render(kind, build, hardware_profile)
        destination = resolved / filename

        if not destination.is_file():
            action = "create"
        elif journal.digest_of_file(destination) != journal.digest(text):
            action = "replace"
        elif filename in ours:
            action = "unchanged"
        else:
            action = "preexisting"

        actions.append(
            FileAction(
                name=filename,
                kind=kind,
                contents=text,
                action=action,
                sha256=journal.digest(text),
                executable=filename == EXECUTABLE,
            )
        )

    return WritePlan(
        target=resolved,
        build_name=build.name,
        preflight=preflight,
        actions=tuple(actions),
        selections=dict(build.selections),
    )
