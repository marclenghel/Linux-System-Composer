"""What has to be true before anything is written.

This is where milestone 3 earns its keep. The compatibility engine spent a
whole milestone learning to tell a build that cannot work from one that can,
and the single most useful thing to do with that answer is to refuse to
generate an installation script from a build the engine says is broken. A
warning nobody has to act on is a warning people learn to scroll past; a
warning that stops the export is one they read.

Two kinds of finding, and the difference matters:

  blockers   writing does not proceed. A compatibility error, or a target
             directory that must not be written to.
  notes      writing proceeds and the user is told. Files about to be
             replaced, a directory this tool has no record of, output landing
             inside the composer's own source tree.

Nothing here writes anything. It reads the build, asks the engine, looks at
the target directory, and returns sentences.
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass
from typing import Any, Mapping

from lsc import compat
from lsc.models import Build
from lsc.safety import journal, paths


@dataclass(frozen=True)
class Finding:
    """One reason to stop, or one thing worth saying before carrying on."""

    code: str            # stable identity, so tests name a finding not a sentence
    message: str         # what is true
    fix: str = ""        # what to do about it


@dataclass(frozen=True)
class Preflight:
    """The verdict on writing this build into this directory."""

    target: pathlib.Path
    blockers: tuple[Finding, ...] = ()
    notes: tuple[Finding, ...] = ()

    @property
    def may_write(self) -> bool:
        return not self.blockers

    def codes(self) -> tuple[str, ...]:
        """Every finding's code, blockers first. Convenient for tests and for
        deciding which banner the Export screen shows."""
        return tuple(f.code for f in self.blockers + self.notes)


def inspect(
    build: Build,
    target: str | pathlib.Path,
    hardware_profile: Mapping[str, Any] | None = None,
    *,
    filenames: tuple[str, ...] = (),
) -> Preflight:
    """Decide whether this build may be written into this directory."""
    resolved = paths.resolve(target)
    blockers: list[Finding] = []
    notes: list[Finding] = []

    # ── 1. Is the build itself sound? ─────────────────────────────────────────
    issues = compat.check(build, hardware_profile)
    errors = [i for i in issues if i.severity == "error"]
    if errors:
        blockers.append(
            Finding(
                code="build-has-errors",
                message=(
                    f"This build has {len(errors)} unresolved "
                    f"{'error' if len(errors) == 1 else 'errors'}: "
                    + "; ".join(i.title for i in errors[:3])
                    + ("; ..." if len(errors) > 3 else "")
                ),
                fix=(
                    "Open Validate and resolve them. Generating an install "
                    "script from a build the engine says cannot work would be "
                    "handing someone a script that breaks their machine."
                ),
            )
        )

    warnings = [i for i in issues if i.severity == "warning"]
    if warnings:
        notes.append(
            Finding(
                code="build-has-warnings",
                message=(
                    f"{len(warnings)} warning{'s' if len(warnings) != 1 else ''} "
                    f"will be written into the files as comments, not silently "
                    f"dropped."
                ),
                fix="Read them on the Validate tab if you have not already.",
            )
        )

    # ── 2. Is the target somewhere output belongs? ────────────────────────────
    refusal = paths.refuse_reason(resolved)
    if refusal:
        blockers.append(
            Finding(
                code="bad-target",
                message=refusal,
                fix="Choose a directory you own, or create its parent first.",
            )
        )
        # No point inspecting the contents of a directory that is off limits.
        return Preflight(target=resolved, blockers=tuple(blockers), notes=tuple(notes))

    if paths.inside_the_composer(resolved):
        notes.append(
            Finding(
                code="inside-the-composer",
                message=(
                    f"{resolved} is inside the composer's own source tree. That "
                    f"works, but generated output usually belongs somewhere it "
                    f"will not be confused with the program."
                ),
                fix="Give an absolute path if that was not deliberate.",
            )
        )

    # ── 3. What is already in there? ──────────────────────────────────────────
    existing = [name for name in filenames if (resolved / name).is_file()]
    record = journal.read(resolved)

    if existing and record is None:
        notes.append(
            Finding(
                code="unknown-occupant",
                message=(
                    f"{resolved} already contains "
                    + ", ".join(existing)
                    + ", and there is no record of this tool having written it."
                ),
                fix=(
                    "The previous contents are copied into "
                    f"{journal.BACKUP_DIRECTORY}/ before anything is replaced, "
                    "and Roll back will put them back."
                ),
            )
        )
    elif existing and record is not None:
        notes.append(
            Finding(
                code="overwriting-own-output",
                message=(
                    f"{resolved} holds output written by this tool on "
                    f"{record.written_at} for build '{record.build_name}'."
                ),
                fix="Writing again replaces it. The previous version is backed up.",
            )
        )

    if not resolved.exists():
        notes.append(
            Finding(
                code="creating-directory",
                message=f"{resolved} does not exist yet and will be created.",
            )
        )

    return Preflight(target=resolved, blockers=tuple(blockers), notes=tuple(notes))
