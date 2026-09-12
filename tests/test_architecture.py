"""The rules this project does not bend, enforced instead of remembered.

These have been written down in comments since milestone 1, and a comment is a
rule that holds until someone is in a hurry. They are cheap to check by reading
the source as a syntax tree, so they are checked.

  1. The core knows nothing about the terminal. models, compat/, generate/,
     safety/, data/ and detect/ import nothing from the interface, so a
     different front end stays possible. Milestone 3 was the evidence that this
     pays: the whole compatibility engine was added without one screen changing
     its imports.

  2. Nothing installs anything, and nothing elevates. The Rust prototype ran
     `sudo pacman -S pciutils` when a tool was missing. The Python port
     deliberately does not.

  3. Writing is confined. Until milestone 4 this said "nothing writes", which
     was easy to check and easy to keep. Now that the whole point of the tool
     is to produce files, the rule has to be narrower instead of weaker: three
     named modules may touch a disk, every other module may not, and all three
     confine themselves to a directory the user named.

Rule 3 is the one worth reading twice. A project whose safety story is "we
never write" has no safety story the day it starts writing; what makes the
promise survive milestone 4 is that the list of modules allowed to write is
short enough to audit, and is audited here.
"""

from __future__ import annotations

import ast
import pathlib
import unittest

PACKAGE = pathlib.Path(__file__).resolve().parent.parent / "lsc"

# Everything that must stay free of interface code. screens/ and widgets/ are
# the interface, and app.py is the shell that joins the two.
CORE = (
    "models.py",
    "content.py",
    "compat",
    "generate",
    "safety",
    "data",
    "detect",
)

# The only modules permitted to change anything on a disk. Every entry is a
# path relative to lsc/, not a bare filename, so that adding a file called
# writer.py somewhere else does not quietly inherit the permission.
#
#   generate/writer.py   creates the generated files, and backs up what it
#                        replaces
#   safety/journal.py    records what was written, so it can be undone
#   safety/rollback.py   undoes it: restores backups, removes what we created
MAY_WRITE = (
    "generate/writer.py",
    "safety/journal.py",
    "safety/rollback.py",
)

# Calls that change something on a disk.
MUTATIONS = frozenset(
    {
        "os.remove", "os.rmdir", "os.unlink", "os.mkdir", "os.makedirs", "os.rename",
        "shutil.rmtree", "shutil.copy", "shutil.copy2", "shutil.move",
        "path.write_text", "path.write_bytes", "path.unlink", "path.mkdir",
        "path.chmod", "path.rmdir", "path.touch", "path.rename",
    }
)

# These two render the text of a shell script for a person to read, so
# `pacman -S` is their subject matter rather than something they run. That
# neither can run anything is checked separately and more directly: neither is
# in MAY_WRITE, and neither may import subprocess.
GENERATES_SCRIPT_TEXT = (
    "generate/render.py",
    "safety/snapshots.py",
)


def relative(path: pathlib.Path) -> str:
    """A module's path relative to lsc/, with forward slashes on every OS."""
    return path.relative_to(PACKAGE).as_posix()


def core_modules() -> list[pathlib.Path]:
    found: list[pathlib.Path] = []
    for entry in CORE:
        target = PACKAGE / entry
        if target.is_dir():
            found.extend(sorted(target.rglob("*.py")))
        else:
            found.append(target)
    return found


def every_module() -> list[pathlib.Path]:
    return sorted(PACKAGE.rglob("*.py"))


def imported_names(path: pathlib.Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            names.update(f"{node.module}.{a.name}" for a in node.names)
    return names


def docstring_lines(path: pathlib.Path) -> set[int]:
    """Every line number covered by a docstring.

    Two of the scans below read the source as text rather than as syntax, so
    they also see the prose that explains what this project deliberately does
    *not* do. detect/linux.py promising it will never run `sudo pacman -S` must
    not read as running it.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    covered: set[int] = set()
    holders = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    for node in ast.walk(tree):
        if not isinstance(node, holders) or not node.body:
            continue
        first = node.body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            covered.update(range(first.lineno, (first.end_lineno or first.lineno) + 1))
    return covered


def command_lines(path: pathlib.Path) -> list[str]:
    """The lines that could become a command: no comments, no docstrings.

    Ordinary string literals stay in, because the thing worth catching is a
    command hiding in a string that some future code path hands to a shell.
    """
    prose = docstring_lines(path)
    source = path.read_text(encoding="utf-8").splitlines()
    return [
        line
        for number, line in enumerate(source, start=1)
        if number not in prose and not line.lstrip().startswith("#")
    ]


def mutation_calls(path: pathlib.Path) -> list[str]:
    """Every call in this module that would change something on a disk.

    Matched on the attribute rather than the whole expression, because the
    receiver is spelled a dozen ways — `destination.write_bytes`,
    `path.write_bytes`, `(root / name).write_bytes` — and the method name is
    the part that does the damage.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        function = node.func
        if isinstance(function, ast.Attribute):
            for mutation in MUTATIONS:
                if function.attr == mutation.split(".")[-1]:
                    found.append(f"{ast.unparse(function)} (line {node.lineno})")
                    break
        elif isinstance(function, ast.Name) and function.id == "open":
            modes = [a.value for a in node.args[1:2] if isinstance(a, ast.Constant)]
            modes += [
                k.value.value
                for k in node.keywords
                if k.arg == "mode" and isinstance(k.value, ast.Constant)
            ]
            if any(c in str(mode) for mode in modes for c in "wax+"):
                found.append(f"open(..., {modes}) (line {node.lineno})")
    return found


class TestTheCoreKnowsNothingAboutTheTerminal(unittest.TestCase):
    def test_no_core_module_imports_textual(self) -> None:
        for path in core_modules():
            with self.subTest(module=relative(path)):
                offenders = {n for n in imported_names(path) if n.split(".")[0] == "textual"}
                self.assertEqual(offenders, set(), f"{relative(path)} imports {offenders}")

    def test_no_core_module_imports_a_screen_or_a_widget(self) -> None:
        for path in core_modules():
            with self.subTest(module=relative(path)):
                offenders = {
                    n
                    for n in imported_names(path)
                    if n.startswith(("lsc.screens", "lsc.widgets", "lsc.app"))
                }
                self.assertEqual(offenders, set(), f"{relative(path)} imports {offenders}")

    def test_the_core_files_being_guarded_all_exist(self) -> None:
        """A renamed file must not silently drop out of this check."""
        for entry in CORE:
            with self.subTest(entry=entry):
                self.assertTrue(
                    (PACKAGE / entry).exists(), f"{entry} is listed in CORE but missing"
                )


class TestWritingIsConfined(unittest.TestCase):
    """Milestone 4 gave this project the ability to create files. This is the
    fence around it."""

    def test_only_the_writing_modules_change_anything(self) -> None:
        for path in every_module():
            if relative(path) in MAY_WRITE:
                continue
            with self.subTest(module=relative(path)):
                self.assertEqual(
                    mutation_calls(path),
                    [],
                    f"{relative(path)} is not in MAY_WRITE but mutates a disk",
                )

    def test_the_writing_modules_all_exist(self) -> None:
        """The allowlist must never grant permission to a file that is gone."""
        for entry in MAY_WRITE:
            with self.subTest(module=entry):
                self.assertTrue(
                    (PACKAGE / entry).is_file(), f"{entry} is in MAY_WRITE but missing"
                )

    def test_every_writing_module_confines_itself(self) -> None:
        """A module allowed to write must import the guard that bounds it.

        The guard doing its job is checked for real in test_write.py, by
        pointing a write outside its root and requiring it to raise. This is
        the cheaper companion check: that no writing module was ever added
        without the import at all.
        """
        for entry in MAY_WRITE:
            with self.subTest(module=entry):
                names = imported_names(PACKAGE / entry)
                self.assertIn(
                    "lsc.safety.paths.ensure_within",
                    names,
                    f"{entry} may write but does not import ensure_within",
                )

    def test_the_writing_modules_are_few(self) -> None:
        """An allowlist that grows without anyone noticing is not an allowlist.

        Three is not a magic number; it is the number that can be read in one
        sitting by whoever is deciding whether to trust this tool with a
        directory. If a fourth is genuinely needed, changing this line is the
        moment to argue for it.
        """
        self.assertLessEqual(len(MAY_WRITE), 3)


class TestNothingInstallsOrElevates(unittest.TestCase):
    def test_nothing_elevates(self) -> None:
        """The prototype ran `sudo pacman -S pciutils`. This does not.

        Checked as text rather than as syntax, because the point is that the
        word must not appear in a command anywhere — including inside a string
        that some future code path might hand to a shell.
        """
        for path in every_module():
            for forbidden in ("sudo ", "pkexec", "doas ", "runas"):
                with self.subTest(module=relative(path), word=forbidden.strip()):
                    offending = [l for l in command_lines(path) if forbidden in l]
                    self.assertEqual(offending, [], f"{relative(path)}: {offending}")

    def test_no_package_manager_is_invoked(self) -> None:
        for path in every_module():
            if relative(path) in GENERATES_SCRIPT_TEXT:
                continue
            for forbidden in ("pacman -S", "apt install", "dnf install", "pip install"):
                with self.subTest(module=relative(path), command=forbidden):
                    offending = [l for l in command_lines(path) if forbidden in l]
                    self.assertEqual(offending, [], f"{relative(path)}: {offending}")

    def test_the_exempted_file_still_exists(self) -> None:
        """A rename must not quietly widen the exemption to nothing."""
        for entry in GENERATES_SCRIPT_TEXT:
            with self.subTest(module=entry):
                self.assertTrue((PACKAGE / entry).is_file())

    def test_only_the_detector_starts_a_subprocess(self) -> None:
        """Reading a machine needs to run commands; nothing else does."""
        for path in every_module():
            if "detect" in path.parts:
                continue
            with self.subTest(module=relative(path)):
                self.assertNotIn("subprocess", imported_names(path))


if __name__ == "__main__":
    unittest.main()
