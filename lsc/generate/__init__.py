"""Turning a build into files, and putting them on a disk — milestones 3 and 4.

    render.py   a build -> the text of packages.txt, install.sh, system.toml
    plan.py     a build + a directory -> what writing it would do (the dry run)
    writer.py   carrying out a plan; the only module here that creates a file

The split between plan and writer is the point. Deciding and doing are
separate steps, so the interface can show the exact consequences of a button
before it is pressed, and the tests can assert on those consequences without
touching a filesystem at all.
"""

from __future__ import annotations

from lsc.generate.plan import FileAction, WritePlan, filenames, plan
from lsc.generate.render import install_script, manifest, package_list, render
from lsc.generate.writer import Refused, WriteResult, apply

__all__ = [
    "FileAction",
    "Refused",
    "WritePlan",
    "WriteResult",
    "apply",
    "filenames",
    "install_script",
    "manifest",
    "package_list",
    "plan",
    "render",
]
