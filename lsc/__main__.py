"""Entry point: `python -m lsc`.

The stdout reconfiguration matters on Windows, where the console still defaults
to a legacy code page and the box-drawing characters in the stack diagram would
otherwise come out as question marks.
"""

from __future__ import annotations

import sys


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    from lsc.app import run

    run()


if __name__ == "__main__":
    main()
