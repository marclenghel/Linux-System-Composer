"""Milestone 4: the files actually land on a disk.

Every test here uses a real temporary directory, because the thing being
tested is exactly the part that a fake would have to pretend about. They are
still fast — three small text files — and they clean up after themselves.

The invariant running through all of them: a write is never destructive and
never leaves the directory it was given.
"""

from __future__ import annotations

import os
import pathlib
import tempfile
import unittest

from lsc import generate
from lsc.data.hardware import sample_profile
from lsc.data.presets import PRESETS
from lsc.models import Build
from lsc.safety import journal
from lsc.safety.paths import OutsideRoot


def gaming_build() -> Build:
    """A preset that validates cleanly, so preflight is not the thing under test."""
    preset = next(p for p in PRESETS if p.id == "gaming")
    return Build(name="gaming", selections=dict(preset.selections))


def broken_build() -> Build:
    """Hardened pulls in linux-hardened, which refuses to sit beside nvidia.

    The conflict is transitive — nothing in the catalogue states it directly —
    so this doubles as a check that preflight is asking the real engine rather
    than doing its own shallow pass.
    """
    return Build(
        name="broken",
        selections={
            "base": "arch",
            "kernel": "linux-hardened",
            "gpu": "nvidia",
            "security": "hardened",
            "filesystem": "ext4",
            "bootloader": "grub",
            "display": "wayland",
            "desktop": "kde",
            "audio": "pipewire",
        },
    )


class WriteTestCase(unittest.TestCase):
    """Gives each test an empty directory whose parent exists."""

    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._temp.name)
        self.target = self.root / "out"
        self.build = gaming_build()
        self.hardware = sample_profile()

    def tearDown(self) -> None:
        self._temp.cleanup()

    def plan(self, build: Build | None = None) -> generate.WritePlan:
        return generate.plan(build or self.build, self.target, self.hardware)

    def write(self, build: Build | None = None) -> None:
        generate.apply(self.plan(build))


class TestPlanning(WriteTestCase):
    def test_a_fresh_directory_is_all_creates(self) -> None:
        plan = self.plan()
        self.assertEqual([a.action for a in plan.actions], ["create"] * 3)
        self.assertTrue(plan.may_write)

    def test_planning_writes_nothing(self) -> None:
        """The dry run is a dry run all the way down."""
        self.plan()
        self.assertFalse(self.target.exists())

    def test_a_second_plan_sees_its_own_output_as_unchanged(self) -> None:
        self.write()
        plan = self.plan()
        self.assertEqual([a.action for a in plan.actions], ["unchanged"] * 3)
        self.assertEqual(plan.changes, ())

    def test_an_edited_file_is_seen_as_a_replacement(self) -> None:
        self.write()
        (self.target / "packages.txt").write_text("edited\n", encoding="utf-8")
        actions = {a.name: a.action for a in self.plan().actions}
        self.assertEqual(actions["packages.txt"], "replace")
        self.assertEqual(actions["install.sh"], "unchanged")

    def test_the_summary_names_the_target_and_the_files(self) -> None:
        summary = self.plan().summary()
        self.assertIn(str(self.target), summary)
        for name in generate.filenames():
            self.assertIn(name, summary)


class TestWriting(WriteTestCase):
    def test_the_files_appear_with_the_planned_contents(self) -> None:
        plan = self.plan()
        result = generate.apply(plan)

        self.assertEqual(set(result.created), set(generate.filenames()))
        for action in plan.actions:
            written = (self.target / action.name).read_text(encoding="utf-8")
            self.assertEqual(written, action.contents)

    def test_a_journal_is_left_behind(self) -> None:
        self.write()
        entry = journal.read(self.target)
        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertEqual(entry.build_name, "gaming")
        self.assertEqual({f.name for f in entry.files}, set(generate.filenames()))
        self.assertEqual(entry.selections, self.build.selections)

    def test_the_journal_hashes_match_what_is_on_disk(self) -> None:
        """The hash is what rollback trusts, so it had better be of the bytes
        that were actually written rather than of the string we meant to write."""
        self.write()
        entry = journal.read(self.target)
        assert entry is not None
        for written in entry.files:
            on_disk = journal.digest_of_file(self.target / written.name)
            self.assertEqual(on_disk, written.sha256, written.name)

    def test_generated_files_use_unix_line_endings(self) -> None:
        """This project is developed on Windows and generates scripts for Linux.

        A shell script with CRLF endings fails on the machine it was written
        for, with an error that blames the interpreter rather than the endings.
        Writing bytes rather than text is what prevents it, so this is the test
        that stops someone 'tidying' that up.
        """
        self.write()
        for name in generate.filenames():
            raw = (self.target / name).read_bytes()
            self.assertNotIn(b"\r\n", raw, f"{name} has CRLF line endings")

    def test_the_directory_is_created_but_its_parent_is_not(self) -> None:
        deep = self.root / "missing" / "out"
        plan = generate.plan(self.build, deep, self.hardware)
        self.assertFalse(plan.may_write)
        self.assertIn("bad-target", plan.preflight.codes())

    def test_nothing_outside_the_target_is_touched(self) -> None:
        witness = self.root / "untouched.txt"
        witness.write_text("original\n", encoding="utf-8")
        self.write()
        self.assertEqual(witness.read_text(encoding="utf-8"), "original\n")
        self.assertEqual(
            sorted(p.name for p in self.root.iterdir()), ["out", "untouched.txt"]
        )

    @unittest.skipUnless(os.name == "posix", "no execute bit on Windows")
    def test_the_install_script_is_executable(self) -> None:
        self.write()
        self.assertTrue(os.access(self.target / "install.sh", os.X_OK))


class TestDryRun(WriteTestCase):
    def test_a_dry_run_creates_nothing(self) -> None:
        result = generate.apply(self.plan(), dry_run=True)
        self.assertTrue(result.dry_run)
        self.assertFalse(self.target.exists())

    def test_a_dry_run_reports_what_the_real_one_would_do(self) -> None:
        """Both modes come out of the same plan, so they must agree exactly.

        This is the test that makes the dry run trustworthy: if the two ever
        diverge, the preview stops being evidence about the real thing.
        """
        plan = self.plan()
        dry = generate.apply(plan, dry_run=True)
        wet = generate.apply(plan)
        self.assertEqual(dry.created, wet.created)
        self.assertEqual(dry.replaced, wet.replaced)
        self.assertEqual(dry.unchanged, wet.unchanged)


class TestOverwriting(WriteTestCase):
    def test_replaced_files_are_backed_up_first(self) -> None:
        self.write()
        (self.target / "packages.txt").write_text("mine\n", encoding="utf-8")

        result = generate.apply(self.plan())

        self.assertEqual(result.replaced, ("packages.txt",))
        self.assertEqual(len(result.backups), 1)
        backup = self.target / result.backups[0]
        self.assertEqual(backup.read_text(encoding="utf-8"), "mine\n")

    def test_a_second_write_does_not_clobber_the_first_backup(self) -> None:
        """Backups go in a directory named for the moment they were taken.

        Without that, writing twice would back up over the backup, and the
        oldest version — the one that was actually the user's — would be the
        one lost.
        """
        self.write()
        (self.target / "packages.txt").write_text("first\n", encoding="utf-8")
        generate.apply(self.plan())
        (self.target / "packages.txt").write_text("second\n", encoding="utf-8")
        generate.apply(self.plan())

        backups = sorted(
            (self.target / journal.BACKUP_DIRECTORY).rglob("packages.txt")
        )
        self.assertEqual(len(backups), 2)
        self.assertEqual(
            {b.read_text(encoding="utf-8") for b in backups}, {"first\n", "second\n"}
        )

    def test_a_file_that_was_already_there_is_never_claimed(self) -> None:
        """Identical contents do not make a file ours.

        Narrow, but it is the exact shape of the mistake this layer exists to
        prevent. packages.txt carries no timestamp, so a user who generated one
        by other means can legitimately have a byte-identical copy sitting in
        the target directory. Recording it in the journal because it matches
        would mean Roll back deletes a file this tool never wrote.
        """
        self.target.mkdir()
        generated = generate.render("packages", self.build, self.hardware)
        (self.target / "packages.txt").write_bytes(generated.encode("utf-8"))

        result = generate.apply(self.plan())

        self.assertEqual(result.preexisting, ("packages.txt",))
        self.assertNotIn("packages.txt", result.created)

        entry = journal.read(self.target)
        assert entry is not None
        self.assertNotIn("packages.txt", {f.name for f in entry.files})

    def test_an_unclaimed_file_survives_a_rollback(self) -> None:
        self.target.mkdir()
        generated = generate.render("packages", self.build, self.hardware)
        (self.target / "packages.txt").write_bytes(generated.encode("utf-8"))
        self.write()

        from lsc.safety import rollback

        rollback.roll_back(self.target)

        self.assertTrue((self.target / "packages.txt").exists())
        self.assertFalse((self.target / "install.sh").exists())

    def test_the_plan_says_so_before_anything_happens(self) -> None:
        self.target.mkdir()
        generated = generate.render("packages", self.build, self.hardware)
        (self.target / "packages.txt").write_bytes(generated.encode("utf-8"))

        plan = self.plan()

        actions = {a.name: a.action for a in plan.actions}
        self.assertEqual(actions["packages.txt"], "preexisting")
        self.assertFalse(next(a for a in plan.actions if a.name == "packages.txt").is_ours)
        self.assertIn("not written by this tool", plan.summary())

    def test_our_own_output_is_still_recognised_on_a_second_write(self) -> None:
        """The flip side: once we have written it, it is ours and stays ours."""
        self.write()
        result = generate.apply(self.plan())
        self.assertEqual(set(result.unchanged), set(generate.filenames()))
        self.assertEqual(result.preexisting, ())

    def test_an_unchanged_file_is_still_recorded_as_ours(self) -> None:
        """Otherwise rollback would leave behind whichever file happened to
        already be byte-identical to what we were about to write."""
        self.write()
        generate.apply(self.plan())
        entry = journal.read(self.target)
        assert entry is not None
        self.assertEqual({f.name for f in entry.files}, set(generate.filenames()))


class TestRefusal(WriteTestCase):
    def test_a_build_with_errors_is_refused(self) -> None:
        plan = self.plan(broken_build())
        self.assertFalse(plan.may_write)
        self.assertIn("build-has-errors", plan.preflight.codes())
        self.assertIn("REFUSED", plan.summary())

    def test_applying_a_refused_plan_raises(self) -> None:
        plan = self.plan(broken_build())
        with self.assertRaises(generate.Refused):
            generate.apply(plan)
        self.assertFalse(self.target.exists())

    def test_a_system_directory_is_refused(self) -> None:
        plan = generate.plan(self.build, "/etc" if os.name == "posix" else "C:/Windows")
        self.assertFalse(plan.may_write)
        self.assertIn("bad-target", plan.preflight.codes())

    def test_a_write_cannot_escape_its_target(self) -> None:
        """The guard, exercised rather than merely imported.

        A plan is built normally and then its filename is bent into a traversal
        — which is the shape the bug would take if a build name or a filename
        ever reached a path unchecked.
        """
        import dataclasses

        plan = self.plan()
        escaped = dataclasses.replace(plan.actions[0], name="../escaped.txt")
        tampered = dataclasses.replace(plan, actions=(escaped,) + plan.actions[1:])

        with self.assertRaises(OutsideRoot):
            generate.apply(tampered)
        self.assertFalse((self.root / "escaped.txt").exists())


class TestGeneratedContent(WriteTestCase):
    def test_the_install_script_carries_the_engine_warnings(self) -> None:
        """Milestone 3's findings have to survive into milestone 4's output.

        The Gaming preset selects an NVIDIA driver with a Wayland compositor,
        which the rule set has something specific to say about. A warning that
        only ever appeared on a screen the user closed is a warning that did
        not make it to the moment it mattered.
        """
        script = generate.install_script(self.build, self.hardware)
        self.assertIn("What the compatibility engine wants you to know", script)
        self.assertIn("nvidia_drm.modeset=1", script)

    def test_the_install_script_explains_how_to_recover(self) -> None:
        script = generate.install_script(self.build, self.hardware)
        self.assertIn("Recovering from a bad update", script)
        self.assertIn("snapper", script)

    def test_a_filesystem_without_snapshots_says_so(self) -> None:
        build = Build(name="plain", selections={"filesystem": "ext4"})
        script = generate.install_script(build)
        self.assertIn("cannot roll back", script)

    def test_no_generated_line_is_unreadably_long(self) -> None:
        for name_ in ("packages", "install", "manifest"):
            text = generate.render(name_, self.build, self.hardware)
            longest = max(len(line) for line in text.splitlines())
            with self.subTest(file=name_):
                self.assertLessEqual(longest, 100)


if __name__ == "__main__":
    unittest.main()
