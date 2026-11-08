#!/usr/bin/env python3
"""Copies the shared Python library into every plugin that carries it, and the server's secret detector into the library.

An agent installs a plugin's folder and nothing outside it, so a plugin cannot import `integrations/shared` from where it is: it carries
an exact copy. This script writes the copies; `--check` only says which are out of date (a test runs it, so a change to the library
that was not copied fails the CI).

  python integrations/shared/vendor.py            write the copies
  python integrations/shared/vendor.py --check    exit 1 and list the files that differ

A new Python plugin adds its folder to TARGETS.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LIB = ROOT / "integrations" / "shared" / "python" / "mimirsynth_agent"
DETECTOR = ROOT / "api" / "mimirsynth" / "secretscan.py"
TARGETS = [   # folders that get a copy of LIB
    ROOT / "integrations" / "claude-code" / "plugin" / "scripts" / "mimirsynth_agent",
    ROOT / "integrations" / "hermes-agent" / "plugin" / "mimirsynth_agent",
    ROOT / "integrations" / "codex" / "plugin" / "scripts" / "mimirsynth_agent",
]


def pairs() -> list:
    """(source, copy) for every file that must be identical."""
    out = [(DETECTOR, LIB / "secretscan.py")]
    files = sorted(p for p in LIB.glob("*.py"))
    for target in TARGETS:
        out += [(f, target / f.name) for f in files]
    return out


def stale() -> list:
    """Copies that differ from their source, and files in a copy that the library no longer has."""
    bad = [copy for src, copy in pairs() if not copy.exists() or copy.read_bytes() != src.read_bytes()]
    names = {p.name for p in LIB.glob("*.py")}
    for target in TARGETS:
        bad += [p for p in target.glob("*.py") if p.name not in names]
    return bad


def main(argv: list) -> int:
    if "--check" in argv:
        bad = stale()
        for p in bad:
            print(f"Out of date: {p.relative_to(ROOT)}")
        if bad:
            print("Fix: python integrations/shared/vendor.py")
        return 1 if bad else 0
    shutil.copyfile(DETECTOR, LIB / "secretscan.py")
    for target in TARGETS:
        target.mkdir(parents=True, exist_ok=True)
        names = {p.name for p in LIB.glob("*.py")}
        for p in target.glob("*.py"):
            if p.name not in names:
                p.unlink()
        for f in LIB.glob("*.py"):
            shutil.copyfile(f, target / f.name)
    print(f"Copied the library into {len(TARGETS)} plugin(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
