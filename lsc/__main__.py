"""Entry point: `python -m lsc`.

    python -m lsc              start the composer
    python -m lsc --report     print the hardware reading as JSON and exit

--report exists for two reasons: it is how you debug detection without
launching a full-screen application over the top of the output, and it is the
closest equivalent to what the Rust prototype did. Note that it *prints* the
JSON rather than writing hardware_report.json — this milestone does not write
files, and a shell redirect does the same job with the user deciding where.
"""

from __future__ import annotations

import json
import sys


def main() -> None:
    # The Windows console still defaults to a legacy code page, which would
    # turn the box-drawing characters in the stack diagram into question marks.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    if "--report" in sys.argv[1:]:
        from lsc.detect import detect

        print(json.dumps(detect(), indent=2))
        return

    from lsc.app import run

    run()


if __name__ == "__main__":
    main()
