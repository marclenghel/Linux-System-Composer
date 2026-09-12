#!/usr/bin/env bash
# Launch Linux System Composer on Linux or macOS.
#
#   ./run.sh            start the app
#   ./run.sh --test     run the test suite instead
#   ./run.sh --report   print the detected hardware as JSON instead
#
# Works from any directory, and creates the virtual environment on first run.

set -euo pipefail
cd "$(dirname "$0")"

VENV_PYTHON=".venv/bin/python"

if [ ! -x "$VENV_PYTHON" ]; then
    echo "First run - setting up the virtual environment..."

    python=""
    for candidate in python3.14 python3.13 python3.12 python3.11 python3; do
        if command -v "$candidate" >/dev/null 2>&1; then
            python="$candidate"
            break
        fi
    done

    if [ -z "$python" ]; then
        echo "No Python 3.11+ found. Install it with your package manager:" >&2
        echo "  Arch:    sudo pacman -S python" >&2
        echo "  Debian:  sudo apt install python3 python3-venv" >&2
        echo "  Fedora:  sudo dnf install python3" >&2
        exit 1
    fi

    "$python" -m venv .venv
    "$VENV_PYTHON" -m pip install --quiet --upgrade pip
    "$VENV_PYTHON" -m pip install --quiet -r requirements.txt
    echo "Ready."
fi

case "${1:-}" in
    --test)   exec "$VENV_PYTHON" -m unittest discover -s tests -v ;;
    --report) exec "$VENV_PYTHON" -m lsc --report ;;
    # --dry-run, --write, --rollback and --preset need no case of their own:
    # the catch-all below already hands every argument to the module.
    *)        exec "$VENV_PYTHON" -m lsc "$@" ;;
esac
