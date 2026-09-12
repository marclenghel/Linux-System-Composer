"""A record of exactly what was written, so it can be taken back.

Rollback is only as honest as its record. A tool that deletes "the files it
probably created" will eventually delete something it did not, so this module
writes down every path it touched, the SHA-256 of the bytes it put there, and
where it put the previous contents if it replaced anything.

The hash is the important field. On the way back out, rollback compares it
against what is on disk now: if they differ, the file has been edited since it
was generated, and it is left exactly where it is. Undoing a write must never
throw away work somebody did afterwards.

The journal lives in the output directory as `.lsc-journal.json`. Keeping it
beside the files rather than in a home-directory database means moving the
directory moves its history with it, and deleting the directory does not leave
a dangling record behind.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from lsc.safety.paths import ensure_within

JOURNAL_NAME = ".lsc-journal.json"

# The backups of anything this tool overwrote. A directory rather than a
# `.bak` suffix beside each file, so that a second write does not overwrite
# the backup taken by the first one.
BACKUP_DIRECTORY = ".lsc-backups"


def digest(text: str) -> str:
    """The SHA-256 of the text as this project writes it.

    Encoded UTF-8 with the newlines left alone. The files are written in binary
    with explicit "\n" endings for exactly this reason: a hash that changed
    depending on the platform that computed it would make rollback refuse to
    run on the machine that did the writing.
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def digest_of_file(path: pathlib.Path) -> str | None:
    """The hash of a file on disk, or None when it is not there or unreadable."""
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


@dataclass(frozen=True)
class WrittenFile:
    """One file this tool put on a disk."""

    name: str                    # relative to the output directory
    sha256: str                  # of what was written
    action: str                  # created | overwritten
    backup: str | None = None    # relative path of the previous contents

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "sha256": self.sha256,
            "action": self.action,
            "backup": self.backup,
        }

    @staticmethod
    def from_json(raw: Any) -> "WrittenFile":
        return WrittenFile(
            name=str(raw["name"]),
            sha256=str(raw["sha256"]),
            action=str(raw.get("action", "created")),
            backup=raw.get("backup"),
        )


@dataclass(frozen=True)
class Journal:
    """Everything one write did, in the form rollback needs to undo it."""

    build_name: str
    composer_version: str
    written_at: str
    files: tuple[WrittenFile, ...] = ()
    selections: dict[str, str] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "build_name": self.build_name,
            "composer_version": self.composer_version,
            "written_at": self.written_at,
            "files": [f.to_json() for f in self.files],
            "selections": dict(self.selections),
        }

    @staticmethod
    def from_json(raw: Any) -> "Journal":
        return Journal(
            build_name=str(raw.get("build_name", "unknown")),
            composer_version=str(raw.get("composer_version", "unknown")),
            written_at=str(raw.get("written_at", "")),
            files=tuple(WrittenFile.from_json(f) for f in raw.get("files", [])),
            selections=dict(raw.get("selections", {})),
        )


def now() -> str:
    """A timestamp that sorts and does not depend on the local clock's offset."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def backup_stamp() -> str:
    """A directory name for one write's backups.

    Microseconds rather than seconds because two writes a moment apart is not
    a hypothetical — pressing Write twice, or a test doing it in a loop, lands
    both in the same second, and a stamp that collides would back up over the
    backup. The one version guaranteed to be the user's own is the oldest, so
    that is exactly the wrong one to lose.
    """
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%f")


def path_for(root: pathlib.Path) -> pathlib.Path:
    return root / JOURNAL_NAME


def read(root: str | pathlib.Path) -> Journal | None:
    """The journal in this directory, or None if there is not a readable one.

    A corrupt journal reads as no journal rather than as an exception. The
    caller's next move is the same either way — treat the directory as one this
    tool does not have a record of — and a crash on start-up because a JSON
    file got truncated would be a poor reward for keeping records.
    """
    candidate = pathlib.Path(root).expanduser().resolve() / JOURNAL_NAME
    try:
        raw = json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(raw, dict):
        return None
    try:
        return Journal.from_json(raw)
    except (KeyError, TypeError, ValueError):
        return None


def save(root: pathlib.Path, entry: Journal) -> pathlib.Path:
    """Write the journal into the output directory. One of three writing calls
    in the entire project, and like the other two it goes through the guard."""
    destination = ensure_within(root, path_for(root))
    text = json.dumps(entry.to_json(), indent=2) + "\n"
    destination.write_bytes(text.encode("utf-8"))
    return destination
