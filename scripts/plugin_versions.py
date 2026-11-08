#!/usr/bin/env python3
"""A pull request that changes an agent plugin bumps its version (#369, docs/AGENT_CLIENT.md «Releasing a plugin change»).

An agent only updates an installed plugin when the version in its manifest changes: with the same version, existing installs keep the
old scripts without anyone noticing. So any change under a plugin's folder (the vendored copy of the shared library included) must
raise the manifest's version above the base branch's.

  python scripts/plugin_versions.py --base origin/main    CI: fails if a plugin changed since the base and its version did not go up

A new plugin adds its folder and its manifest to PLUGINS. Standard library only.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# the plugin's folder → its manifest, whose "version" an agent compares to decide whether there is an update
PLUGINS = {
    "integrations/claude-code/plugin": "integrations/claude-code/plugin/.claude-plugin/plugin.json",
    "integrations/hermes-agent/plugin": "integrations/hermes-agent/plugin/plugin.yaml",
}
_SEMVER = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?$")


def parse(version: str) -> tuple:
    """A semantic version as something that sorts: a pre-release (1.0.0-rc.1) goes before its release. ValueError if it is not one."""
    m = _SEMVER.match(str(version or "").strip())
    if not m:
        raise ValueError(f"not a semantic version: {version!r}")
    pre = tuple((0, int(p), "") if p.isdigit() else (1, 0, p) for p in m[4].split(".")) if m[4] else None
    return (int(m[1]), int(m[2]), int(m[3]), (1,) if pre is None else (0, *pre))


_YAML_VERSION = re.compile(r"""^version:[ \t]*["']?([^"'#\s]*)""", re.M)


def version_of(manifest_text: str | None) -> str | None:
    """The manifest's "version": a JSON object, or a YAML one (plugin.yaml), whose top level `version:` line is read without a parser."""
    if manifest_text is None:
        return None
    if manifest_text.lstrip().startswith("{"):
        return str(json.loads(manifest_text).get("version") or "")
    m = _YAML_VERSION.search(manifest_text)
    return m[1] if m else ""


def check(changed: list[str], old: dict, new: dict) -> list[str]:
    """Why the change is not fine, one line per plugin: `changed` are the paths that differ from the base, `old` and `new` each plugin's
    version on the base and here (None when the plugin is not there)."""
    problems = []
    for folder in PLUGINS:
        if not any(p == folder or p.startswith(folder + "/") for p in changed):
            continue
        before, after = old.get(folder), new.get(folder)
        if after is None:
            continue   # the plugin was removed
        try:
            now = parse(after)
        except ValueError as e:
            problems.append(f"{PLUGINS[folder]}: {e}")
            continue
        if before is None:
            continue   # a new plugin: any version will do
        try:
            was = parse(before)
        except ValueError:
            continue   # the base's version was broken: any valid one fixes it
        if now <= was:
            problems.append(f"{folder} changed but its version is {after} (was {before} on the base): raise it in {PLUGINS[folder]}, "
                            "or installed copies will not update")
    return problems


def _git(*args: str) -> str | None:
    r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=False)
    return r.stdout if r.returncode == 0 else None


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--base", required=True, help="the branch or commit the pull request merges into, e.g. origin/main")
    a = ap.parse_args(argv)
    diff = _git("diff", "--name-only", f"{a.base}...HEAD")
    if diff is None:
        print(f"Cannot compare with {a.base}: is it fetched? (actions/checkout with fetch-depth: 0)")
        return 2
    changed = [p.strip() for p in diff.splitlines() if p.strip()]
    old = {f: version_of(_git("show", f"{a.base}:{m}")) for f, m in PLUGINS.items()}
    new = {f: version_of((ROOT / m).read_text(encoding="utf-8")) if (ROOT / m).exists() else None for f, m in PLUGINS.items()}
    problems = check(changed, old, new)
    for p in problems:
        print(p)
    if not problems:
        bumped = [f"{f} {old[f]} -> {new[f]}" for f in PLUGINS if any(p.startswith(f + "/") for p in changed)]
        print("Plugin versions are fine" + (": " + ", ".join(bumped) if bumped else ": no plugin changed"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
