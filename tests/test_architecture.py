"""The two rules this project does not bend, enforced instead of remembered.

Both of these have been written down in comments since milestone 1, and a
comment is a rule that holds until someone is in a hurry. They are cheap to
check by reading the source as a syntax tree, so they are checked.

  1. The core knows nothing about the terminal. models, conditions, facts,
     engine, checks, export, data/ and detect/ import nothing from the
     interface, so a different front end stays possible. Milestone 3 is the
     evidence that this pays: the whole compatibility engine was added without
     one screen changing its imports.

  2. Nothing installs, elevates, or writes to the system. The Rust prototype
     ran `sudo pacman -S pciutils` when a tool was missing. The Python port
     deliberately does not, and Export returns strings rather than writing
     files.
"""

from __future__ import annotations

import ast
import pathlib
import unittest

PACKAGE = pathlib.Path(__file__).resolve().parent.parent / "lsc"

# Everything that must stay free of interface code. The screens and widgets
# packages are the interface, and app.py is the shell that joins the two.
CORE = (
    "models.py",
    "conditions.py",
    "facts.py",
    "engine.py",
    "checks.py",
    "export.py",
    "content.py",
    "data",
    "detect",
)


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
    return names


def docstring_lines(path: pathlib.Path) -> set[int]:
    """Every line number covered by a docstring.

    The two scans below read the source as text rather than as syntax, so they
    also see the prose that explains what this project deliberately does *not*
    do. `detect/linux.py` promising it will never run `sudo pacman -S` must not
    read as running it.
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


class TestTheCoreKnowsNothingAboutTheTerminal(unittest.TestCase):
    def test_no_core_module_imports_textual(self) -> None:
        for path in core_modules():
            with self.subTest(module=path.name):
                offenders = {n for n in imported_names(path) if n.split(".")[0] == "textual"}
                self.assertEqual(offenders, set(), f"{path.name} imports {offenders}")

    def test_no_core_module_imports_a_screen_or_a_widget(self) -> None:
        for path in core_modules():
            with self.subTest(module=path.name):
                offenders = {
                    n
                    for n in imported_names(path)
                    if n.startswith(("lsc.screens", "lsc.widgets", "lsc.app"))
                }
                self.assertEqual(offenders, set(), f"{path.name} imports {offenders}")

    def test_the_core_files_being_guarded_all_exist(self) -> None:
        """A renamed file must not silently drop out of this check."""
        for path in core_modules():
            with self.subTest(module=str(path)):
                self.assertTrue(path.exists(), f"{path} is listed in CORE but missing")


class TestNothingTouchesTheSystem(unittest.TestCase):
    def test_nothing_opens_a_file_for_writing(self) -> None:
        """Export returns strings. Milestone 4 is where writing arrives."""
        for path in every_module():
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
                    continue
                if node.func.id != "open":
                    continue
                modes = [a.value for a in node.args[1:2] if isinstance(a, ast.Constant)]
                modes += [
                    k.value.value
                    for k in node.keywords
                    if k.arg == "mode" and isinstance(k.value, ast.Constant)
                ]
                for mode in modes:
                    with self.subTest(module=path.name, mode=mode):
                        self.assertNotIn("w", str(mode))
                        self.assertNotIn("a", str(mode))

    def test_no_module_calls_a_filesystem_mutation(self) -> None:
        forbidden = {
            "os.remove", "os.rmdir", "os.unlink", "os.mkdir", "os.makedirs",
            "os.rename", "shutil.rmtree", "shutil.copy", "shutil.move",
            "pathlib.Path.write_text", "Path.write_text", "Path.write_bytes",
        }
        for path in every_module():
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    name = ast.unparse(node.func)
                    with self.subTest(module=path.name, call=name):
                        self.assertNotIn(name, forbidden)

    def test_nothing_elevates(self) -> None:
        """The prototype ran `sudo pacman -S pciutils`. This does not.

        Checked as text rather than as syntax, because the point is that the
        word must not appear in a command anywhere - including inside a string
        that some future code path might hand to a shell.
        """
        for path in every_module():
            for forbidden in ("sudo ", "pkexec", "doas ", "runas"):
                with self.subTest(module=path.name, word=forbidden.strip()):
                    # The prose explaining what the prototype used to do is
                    # allowed to name it; a line of code is not.
                    offending = [l for l in command_lines(path) if forbidden in l]
                    self.assertEqual(offending, [], f"{path.name}: {offending}")

    # export.py renders the text of an install script for a person to read, so
    # `pacman -S` is its subject matter rather than something it runs. That it
    # cannot run anything is checked separately and more directly: it opens no
    # file for writing, and it may not import subprocess.
    GENERATES_SCRIPT_TEXT = {"export.py"}

    def test_no_package_manager_is_invoked(self) -> None:
        for path in every_module():
            if path.name in self.GENERATES_SCRIPT_TEXT:
                continue
            for forbidden in ("pacman -S", "apt install", "dnf install", "pip install"):
                with self.subTest(module=path.name, command=forbidden):
                    offending = [l for l in command_lines(path) if forbidden in l]
                    self.assertEqual(offending, [], f"{path.name}: {offending}")

    def test_the_exempted_file_still_exists(self) -> None:
        """A rename must not quietly widen the exemption to nothing."""
        for name in self.GENERATES_SCRIPT_TEXT:
            with self.subTest(module=name):
                self.assertIn(name, [p.name for p in every_module()])

    def test_only_the_detector_starts_a_subprocess(self) -> None:
        """Reading a machine needs to run commands; nothing else does."""
        for path in every_module():
            if "detect" in path.parts:
                continue
            with self.subTest(module=path.name):
                self.assertNotIn("subprocess", imported_names(path))


if __name__ == "__main__":
    unittest.main()
