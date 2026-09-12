"""Milestone 5: the safety layer.

The tests that matter most in this file are the ones about *not* doing things.
It is easy to write a rollback that restores every file it finds; the point of
this one is that it refuses to touch a file somebody edited after it was
generated, and refuses to touch a directory it has no record of at all.

The two meanings of "rollback" are kept apart here as carefully as they are in
the code. TestRollingBackAWrite is about undoing what this tool did to a
directory. TestSnapshotAdvice is about whether the Linux system being designed
would be able to undo a bad update — advice only, on a machine this tool never
touches.
"""

from __future__ import annotations

import os
import pathlib
import tempfile
import unittest

from lsc import generate
from lsc.data.hardware import sample_profile
from lsc.models import Build
from lsc.safety import journal, paths, preflight, rollback, snapshots
from lsc.safety.paths import OutsideRoot
from tests.test_write import broken_build, gaming_build


class SafetyTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._temp.name)
        self.target = self.root / "out"
        self.build = gaming_build()
        self.hardware = sample_profile()

    def tearDown(self) -> None:
        self._temp.cleanup()

    def write(self) -> None:
        generate.apply(generate.plan(self.build, self.target, self.hardware))


# ── paths ────────────────────────────────────────────────────────────────────


class TestWhereOutputMayGo(unittest.TestCase):
    def test_a_system_directory_is_refused_by_name(self) -> None:
        candidates = ["/etc", "/usr", "/boot"] if os.name == "posix" else ["C:/Windows"]
        for candidate in candidates:
            with self.subTest(directory=candidate):
                reason = paths.refuse_reason(candidate)
                self.assertIsNotNone(reason)
                assert reason is not None
                self.assertIn("system directory", reason)

    def test_the_home_directory_itself_is_refused(self) -> None:
        reason = paths.refuse_reason(pathlib.Path.home())
        self.assertIsNotNone(reason)

    def test_a_subdirectory_of_home_is_fine(self) -> None:
        """Refusing ~ must not turn into refusing everything under it."""
        self.assertIsNone(paths.refuse_reason(pathlib.Path.home() / "systems"))

    def test_traversal_does_not_escape_the_root(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            root = pathlib.Path(name)
            self.assertTrue(paths.is_within(root, root / "a" / "b"))
            self.assertFalse(paths.is_within(root, root / ".." / "elsewhere"))
            with self.assertRaises(OutsideRoot):
                paths.ensure_within(root, root / ".." / "elsewhere")

    def test_a_path_is_its_own_root(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            self.assertTrue(paths.is_within(name, name))


# ── preflight ────────────────────────────────────────────────────────────────


class TestPreflight(SafetyTestCase):
    def test_a_clean_build_may_be_written(self) -> None:
        verdict = preflight.inspect(self.build, self.target, self.hardware)
        self.assertTrue(verdict.may_write)
        self.assertEqual(verdict.blockers, ())

    def test_a_build_with_errors_may_not(self) -> None:
        verdict = preflight.inspect(broken_build(), self.target, self.hardware)
        self.assertFalse(verdict.may_write)
        self.assertIn("build-has-errors", verdict.codes())

    def test_the_blocker_names_the_actual_error(self) -> None:
        """A refusal that does not say what is wrong is just an obstacle."""
        verdict = preflight.inspect(broken_build(), self.target, self.hardware)
        blocker = next(b for b in verdict.blockers if b.code == "build-has-errors")
        self.assertIn("linux-hardened", blocker.message)
        self.assertTrue(blocker.fix)

    def test_an_unrecognised_occupant_is_pointed_out(self) -> None:
        self.target.mkdir()
        (self.target / "install.sh").write_text("someone else's\n", encoding="utf-8")
        verdict = preflight.inspect(
            self.build, self.target, self.hardware, filenames=generate.filenames()
        )
        self.assertIn("unknown-occupant", verdict.codes())
        self.assertTrue(verdict.may_write, "a warning, not a refusal")

    def test_our_own_earlier_output_is_recognised(self) -> None:
        self.write()
        verdict = preflight.inspect(
            self.build, self.target, self.hardware, filenames=generate.filenames()
        )
        self.assertIn("overwriting-own-output", verdict.codes())
        self.assertNotIn("unknown-occupant", verdict.codes())

    def test_every_finding_carries_a_message(self) -> None:
        verdict = preflight.inspect(broken_build(), self.target, self.hardware)
        for finding in verdict.blockers + verdict.notes:
            with self.subTest(code=finding.code):
                self.assertTrue(finding.message.strip())


# ── the journal ──────────────────────────────────────────────────────────────


class TestTheJournal(SafetyTestCase):
    def test_it_survives_the_round_trip(self) -> None:
        entry = journal.Journal(
            build_name="demo",
            composer_version="9.9.9",
            written_at=journal.now(),
            files=(journal.WrittenFile("a.txt", journal.digest("hi"), "created"),),
            selections={"kernel": "linux"},
        )
        self.assertEqual(journal.Journal.from_json(entry.to_json()), entry)

    def test_a_missing_journal_reads_as_none(self) -> None:
        self.assertIsNone(journal.read(self.root))

    def test_a_corrupt_journal_reads_as_none_rather_than_raising(self) -> None:
        """Crashing on start-up because a JSON file got truncated would be a
        poor reward for keeping records."""
        self.target.mkdir()
        (self.target / journal.JOURNAL_NAME).write_text("{not json", encoding="utf-8")
        self.assertIsNone(journal.read(self.target))

    def test_a_journal_of_the_wrong_shape_reads_as_none(self) -> None:
        self.target.mkdir()
        (self.target / journal.JOURNAL_NAME).write_text("[1, 2, 3]", encoding="utf-8")
        self.assertIsNone(journal.read(self.target))


# ── rolling back a write ─────────────────────────────────────────────────────


class TestRollingBackAWrite(SafetyTestCase):
    def test_files_we_created_are_removed(self) -> None:
        self.write()
        result = rollback.roll_back(self.target)

        self.assertEqual(set(result.removed), set(generate.filenames()))
        self.assertEqual(result.kept, ())
        for name in generate.filenames():
            self.assertFalse((self.target / name).exists())

    def test_the_journal_goes_too_when_the_undo_was_complete(self) -> None:
        self.write()
        rollback.roll_back(self.target)
        self.assertIsNone(journal.read(self.target))

    def test_files_we_replaced_are_restored(self) -> None:
        self.target.mkdir()
        (self.target / "packages.txt").write_text("mine\n", encoding="utf-8")
        self.write()
        self.assertNotEqual(
            (self.target / "packages.txt").read_text(encoding="utf-8"), "mine\n"
        )

        result = rollback.roll_back(self.target)

        self.assertIn("packages.txt", result.restored)
        self.assertEqual(
            (self.target / "packages.txt").read_text(encoding="utf-8"), "mine\n"
        )

    def test_a_file_edited_since_it_was_generated_is_left_alone(self) -> None:
        """The single most important test in the safety layer.

        You generated a script, spent an hour editing it, and pressed Roll
        back. The correct behaviour is to keep your hour of work and say so.
        """
        self.write()
        edited = self.target / "install.sh"
        edited.write_text("# my own work\n", encoding="utf-8")

        result = rollback.roll_back(self.target)

        self.assertEqual(edited.read_text(encoding="utf-8"), "# my own work\n")
        self.assertIn("install.sh", [name for name, _why in result.kept])
        self.assertNotIn("install.sh", result.removed)

    def test_the_journal_stays_when_something_was_kept(self) -> None:
        """A partial rollback has to remain resumable."""
        self.write()
        (self.target / "install.sh").write_text("mine\n", encoding="utf-8")
        rollback.roll_back(self.target)
        self.assertIsNotNone(journal.read(self.target))

    def test_a_directory_with_no_journal_is_refused(self) -> None:
        self.target.mkdir()
        (self.target / "install.sh").write_text("not ours\n", encoding="utf-8")

        with self.assertRaises(rollback.NothingToRollBack):
            rollback.roll_back(self.target)

        self.assertTrue((self.target / "install.sh").exists())

    def test_a_dry_run_changes_nothing(self) -> None:
        self.write()
        before = {
            name: (self.target / name).read_bytes() for name in generate.filenames()
        }

        result = rollback.roll_back(self.target, dry_run=True)

        self.assertTrue(result.dry_run)
        self.assertEqual(set(result.removed), set(generate.filenames()))
        for name, contents in before.items():
            self.assertEqual((self.target / name).read_bytes(), contents)
        self.assertIsNotNone(journal.read(self.target))

    def test_an_already_deleted_file_is_not_an_error(self) -> None:
        self.write()
        (self.target / "packages.txt").unlink()

        result = rollback.roll_back(self.target)

        self.assertIn("packages.txt", [name for name, _why in result.kept])
        self.assertIn("install.sh", result.removed)

    def test_write_then_roll_back_leaves_the_directory_as_it_was(self) -> None:
        """The round trip, which is the whole promise in one assertion."""
        self.target.mkdir()
        (self.target / "notes.md") .write_text("keep me\n", encoding="utf-8")
        before = sorted(p.name for p in self.target.iterdir())

        self.write()
        rollback.roll_back(self.target)

        after = [
            p.name
            for p in self.target.iterdir()
            if p.name != journal.BACKUP_DIRECTORY
        ]
        self.assertEqual(sorted(after), before)
        self.assertEqual((self.target / "notes.md").read_text(encoding="utf-8"), "keep me\n")


# ── advice about the system being designed ───────────────────────────────────


class TestSnapshotAdvice(unittest.TestCase):
    def test_btrfs_can_roll_back(self) -> None:
        advice = snapshots.advise(Build(selections={"filesystem": "btrfs"}))
        self.assertTrue(advice.capable)
        self.assertIn("snapper", advice.packages)

    def test_zfs_can_roll_back(self) -> None:
        advice = snapshots.advise(Build(selections={"filesystem": "zfs"}))
        self.assertTrue(advice.capable)

    def test_ext4_cannot_and_says_why_it_matters(self) -> None:
        advice = snapshots.advise(Build(selections={"filesystem": "ext4"}))
        self.assertFalse(advice.capable)
        self.assertIn("live USB", advice.detail)

    def test_no_filesystem_chosen_is_not_an_answer(self) -> None:
        """Unknown stays unknown here too, exactly as it does in the engine."""
        advice = snapshots.advise(Build(selections={}))
        self.assertFalse(advice.capable)
        self.assertIsNone(advice.filesystem)

    def test_every_advice_line_fits_in_a_comment_block(self) -> None:
        for filesystem in ("btrfs", "zfs", "ext4", "xfs"):
            advice = snapshots.advise(Build(selections={"filesystem": filesystem}))
            comment = advice.as_script_comment()
            with self.subTest(filesystem=filesystem):
                self.assertTrue(all(line.startswith("#") for line in comment.splitlines()))
                self.assertLessEqual(max(len(l) for l in comment.splitlines()), 80)

    def test_the_capable_list_matches_the_advice(self) -> None:
        """The table and the function must not drift apart."""
        for filesystem in snapshots.SNAPSHOT_CAPABLE:
            advice = snapshots.advise(Build(selections={"filesystem": filesystem}))
            with self.subTest(filesystem=filesystem):
                self.assertTrue(advice.capable)


if __name__ == "__main__":
    unittest.main()
