"""The safety layer — milestone 5.

The project's promise is that it never touches your system by accident, and
this package is where that promise is kept rather than merely stated.

    paths.py        where output may and may not go
    preflight.py    what has to be true before anything is written
    journal.py      the record of exactly what was written
    rollback.py     undoing a write, without destroying later edits
    snapshots.py    whether the system being *designed* can roll back

Worth being precise about the two meanings of "rollback" that meet here.
rollback.py undoes what this tool did to a directory: no privileges, no
filesystem features, just a journal and some hashes. snapshots.py is about the
Linux system described by the build — whether a bad kernel update on it will
be recoverable — and it only ever gives advice, because snapshotting a real
machine needs root and this tool does not take root for anything.
"""

from __future__ import annotations

from lsc.safety.journal import Journal, digest
from lsc.safety.paths import OutsideRoot, ensure_within, is_within, refuse_reason
from lsc.safety.preflight import Finding, Preflight, inspect
from lsc.safety.rollback import NothingToRollBack, RollbackResult, roll_back
from lsc.safety.snapshots import Advice, advise

__all__ = [
    "Advice",
    "Finding",
    "Journal",
    "NothingToRollBack",
    "OutsideRoot",
    "Preflight",
    "RollbackResult",
    "advise",
    "digest",
    "ensure_within",
    "inspect",
    "is_within",
    "refuse_reason",
    "roll_back",
]
