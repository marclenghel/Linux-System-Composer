"""Entry point: `python -m lsc`.

    python -m lsc                      start the composer
    python -m lsc --report             print the hardware reading as JSON
    python -m lsc --dry-run DIR        say what writing a build there would do
    python -m lsc --write DIR          write it
    python -m lsc --rollback DIR       undo the last write in that directory
    python -m lsc --preset NAME        which build the three above act on

The four file operations exist for the same reason --report does: to make the
interesting behaviour reachable without launching a full-screen application
over the top of the output. They also make the safety layer demonstrable in a
terminal recording, which a TUI is awkward to do.

Every one of them goes through exactly the same plan / preflight / write path
as the buttons on the Export screen. A command line that took a shortcut past
the safety layer would be a hole in it.
"""

from __future__ import annotations

import argparse
import json
import sys

EXIT_REFUSED = 2


def main(argv: list[str] | None = None) -> int:
    # The Windows console still defaults to a legacy code page, which would
    # turn the box-drawing characters in the stack diagram into question marks.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    parser = build_parser()
    args = parser.parse_args(argv)

    if args.report:
        from lsc.detect import detect

        print(json.dumps(detect(), indent=2))
        return 0

    if args.rollback:
        return run_rollback(args.rollback, dry_run=args.dry_run is not None)

    if args.write or args.dry_run:
        return run_write(
            target=args.write or args.dry_run,
            preset=args.preset,
            dry_run=args.write is None,
            scan=args.scan,
        )

    from lsc.app import run

    run()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lsc",
        description="Design a Linux system as a graph of components.",
    )
    parser.add_argument("--report", action="store_true", help="print hardware as JSON")
    parser.add_argument("--dry-run", metavar="DIR", help="say what a write would do")
    parser.add_argument("--write", metavar="DIR", help="write the build into DIR")
    parser.add_argument("--rollback", metavar="DIR", help="undo the last write in DIR")
    parser.add_argument(
        "--preset",
        default="gaming",
        help="which preset to act on (default: gaming)",
    )
    parser.add_argument(
        "--scan",
        action="store_true",
        help="read this machine first, so hardware rules can be decided",
    )
    return parser


def chosen_build(preset_id: str):
    """The build the file operations act on.

    A preset rather than an interactive session, because the command line is
    for demonstrating and scripting the write path, and the interesting
    composition happens on the Compose screen.
    """
    from lsc.data.presets import PRESETS
    from lsc.models import Build

    for preset in PRESETS:
        if preset.id == preset_id:
            return Build(name=preset.id, selections=dict(preset.selections))

    names = ", ".join(p.id for p in PRESETS)
    raise SystemExit(f"No preset called '{preset_id}'. Available: {names}")


def run_write(target: str, preset: str, dry_run: bool, scan: bool) -> int:
    from lsc import generate

    build = chosen_build(preset)
    hardware = None
    if scan:
        from lsc.detect import detect

        hardware = detect()

    plan = generate.plan(build, target, hardware)
    print(plan.summary())

    if not plan.may_write:
        return EXIT_REFUSED

    if dry_run:
        print("\nDry run — nothing was written.")
        return 0

    result = generate.apply(plan)
    print("\n" + result.summary())
    return 0


def run_rollback(target: str, dry_run: bool) -> int:
    from lsc.safety import rollback

    try:
        result = rollback.roll_back(target, dry_run=dry_run)
    except rollback.NothingToRollBack as error:
        print(error, file=sys.stderr)
        return EXIT_REFUSED

    print(result.summary())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
