"""Where output may and may not go.

This module decides nothing about Linux and everything about not ruining
someone's afternoon. It is pure: it inspects paths and returns reasons. The
two modules that actually touch a disk both ask it first.

The rule it enforces is narrow on purpose. Linux System Composer writes a
handful of generated files into one directory the user names, and it must
never write anywhere else — not into /etc because the generated install script
mentions /etc, not into the repository it is running from because the default
target was left relative, and not over the top of a home directory because
someone typed `~` and pressed enter.
"""

from __future__ import annotations

import os
import pathlib


class OutsideRoot(Exception):
    """A write was attempted outside the directory it was confined to.

    Raised rather than returned because there is no sensible way to carry on:
    if the path arithmetic has gone wrong, the next thing to do is stop.
    """


# Directories that are part of an operating system rather than part of anyone's
# project. Writing generated files here is never what was meant, and the one
# time it is, a person can make the directory themselves and point at it.
#
# Listed for both platforms regardless of which one is running: a path is
# checked as text against its resolved form, and a Linux path on Windows simply
# never matches. Keeping both lists live means the guard behaves the same way
# in the test suite on either machine.
SYSTEM_DIRECTORIES: tuple[str, ...] = (
    "/", "/bin", "/boot", "/dev", "/etc", "/lib", "/lib64", "/opt", "/proc",
    "/root", "/run", "/sbin", "/srv", "/sys", "/usr", "/var",
    # Written with forward slashes, which pathlib reads the same way on
    # Windows and which cannot be mangled by whatever quotes this file passes
    # through on its way into a repository.
    "C:/", "C:/Windows", "C:/Program Files", "C:/Program Files (x86)",
    "C:/ProgramData",
)


def resolve(path: str | os.PathLike[str]) -> pathlib.Path:
    """A path in the one form the rest of this module reasons about.

    `expanduser` first, because `~/systems` from a text box is a string that
    means a directory, and `resolve` alone would treat the tilde as a folder
    name. `strict=False` because the target usually does not exist yet — that
    is the normal case, not an error.
    """
    return pathlib.Path(path).expanduser().resolve()


def is_within(root: str | os.PathLike[str], path: str | os.PathLike[str]) -> bool:
    """True when `path` is `root` or sits underneath it.

    Compared as resolved paths rather than as strings, so `out/../../etc` is
    seen for what it is and a symlink pointing out of the tree cannot smuggle
    a write past the check.
    """
    root_resolved = resolve(root)
    try:
        resolve(path).relative_to(root_resolved)
    except ValueError:
        return False
    return True


def ensure_within(root: str | os.PathLike[str], path: str | os.PathLike[str]) -> pathlib.Path:
    """Return `path` resolved, or raise if it escapes `root`.

    Every filesystem mutation in this project goes through a call to this
    function first. That is the whole containment story, so it is one function
    and there is a test that each writing module calls it.
    """
    if not is_within(root, path):
        raise OutsideRoot(f"{resolve(path)} is outside {resolve(root)}")
    return resolve(path)


def refuse_reason(target: str | os.PathLike[str]) -> str | None:
    """Why this directory must not be used as an output target, or None.

    A sentence rather than a code, because it is shown to a person who now has
    to choose somewhere else, and "target is a system directory" tells them
    less than naming the directory does.
    """
    path = resolve(target)

    system = {resolve(d) for d in SYSTEM_DIRECTORIES if pathlib.Path(d).exists()}
    if path in system:
        return (
            f"{path} is a system directory. Generated files go in a directory "
            f"you own — try a subdirectory instead."
        )

    if path == resolve(pathlib.Path.home()):
        return (
            f"{path} is your home directory itself. Writing loose files "
            f"straight into it would scatter them among everything else — "
            f"name a subdirectory, for example {path / 'systems'}."
        )

    if path.exists() and not path.is_dir():
        return f"{path} exists and is a file, not a directory."

    # The parent has to exist. Creating one missing directory is reasonable;
    # creating six is a sign the path was mistyped, and silently building a
    # tree from a typo is how files end up somewhere nobody looks again.
    if not path.exists() and not path.parent.is_dir():
        return f"{path.parent} does not exist, so {path.name} cannot be created inside it."

    return None


def inside_the_composer(target: str | os.PathLike[str]) -> bool:
    """True when the target is inside this project's own source tree.

    Not fatal — someone experimenting may genuinely want output beside the
    code — but worth saying out loud, because the usual cause is a relative
    path entered while the working directory happened to be the repository.
    """
    package_root = pathlib.Path(__file__).resolve().parent.parent
    return is_within(package_root.parent, target)
