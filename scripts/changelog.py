#!/usr/bin/env python3
"""The changelog is written at release time from the pull requests, so that pull requests never touch CHANGELOG.md (#168).

Every pull request describes its change in a `## Changelog` section of its description, one entry per line:

    ## Changelog
    Added: **Incoming webhooks** (#122). Alerts and deployments from other tools ...
    Fixed: The recall no longer ...

The type is one of Added, Changed, Deprecated, Removed, Fixed or Security (Keep a Changelog); a line that does not start with a type
continues the entry above it. HTML comments are ignored. A pull request with the label `no-changelog` (CI, docs, dependency bumps)
needs no section.

  python scripts/changelog.py --check-pr EVENT.json   CI: fails if the pull request in this GitHub event has no entry
  python scripts/changelog.py --preview               what [Unreleased] would contain now (pull requests merged since the last tag)
  python scripts/changelog.py                         writes those entries under [Unreleased] in CHANGELOG.md
  python scripts/changelog.py --release 0.11.0        the same, then moves [Unreleased] under «## [0.11.0] - today»

It reads the merged pull requests through the GitHub API, with GITHUB_TOKEN, GH_TOKEN or `gh auth token`. Standard library only.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

TYPES = ("Added", "Changed", "Deprecated", "Removed", "Fixed", "Security")
EXEMPT_LABEL = "no-changelog"
EXEMPT_AUTHORS = ("dependabot[bot]",)
ROOT = Path(__file__).resolve().parent.parent
CHANGELOG = ROOT / "CHANGELOG.md"
_ENTRY = re.compile(rf"^\s*[-*]?\s*({'|'.join(TYPES)})\s*:\s*(.*)$", re.I)


def section(body: str) -> str:
    """The text of the `## Changelog` section of a pull request description, without HTML comments."""
    body = re.sub(r"<!--.*?-->", "", (body or "").replace("\r\n", "\n"), flags=re.S)
    m = re.search(r"^##\s+Changelog\s*$(.*?)(?=^##\s|\Z)", body, flags=re.M | re.S | re.I)
    return m.group(1).strip() if m else ""


def entries(body: str) -> list[tuple[str, str]]:
    """The (type, text) entries of a pull request description, in order."""
    out: list[list[str]] = []
    for line in section(body).split("\n"):
        m = _ENTRY.match(line)
        if m:
            out.append([next(t for t in TYPES if t.lower() == m.group(1).lower()), m.group(2).strip()])
        elif line.strip() and out:
            out[-1][1] = f"{out[-1][1]} {line.strip()}".strip()
    return [(t, text) for t, text in out if text]


def check(pr: dict) -> str:
    """Empty if the pull request is fine; otherwise why it is not."""
    labels = {(lb.get("name") or "").lower() for lb in pr.get("labels") or []}
    if EXEMPT_LABEL in labels or (pr.get("user") or {}).get("login") in EXEMPT_AUTHORS:
        return ""
    if not re.search(r"^##\s+Changelog\s*$", (pr.get("body") or "").replace("\r\n", "\n"), flags=re.M | re.I):
        return f"The description has no «## Changelog» section. Add one (see the template) or the label «{EXEMPT_LABEL}»."
    if not entries(pr.get("body") or ""):
        return f"The «## Changelog» section has no entry. Each one starts with {', '.join(TYPES[:-1])} or {TYPES[-1]}, then a colon."
    return ""


def line(pr_number: int, text: str) -> str:
    return f"- {text}" if f"#{pr_number}" in text else f"- {text} (#{pr_number})"


def unreleased(changelog: str) -> str:
    """The [Unreleased] section of a changelog, heading included."""
    start = changelog.index("## [Unreleased]")
    nxt = re.search(r"^## \[", changelog[start + 3:], flags=re.M)
    return changelog[start:start + 3 + nxt.start()] if nxt else changelog[start:]


def merge(changelog: str, new: dict[str, list[str]], release: str | None = None, today: date | None = None) -> str:
    """CHANGELOG.md with the new lines added to [Unreleased] (in Keep a Changelog order, skipping lines already there), and with
    [Unreleased] moved under the release heading if one is given."""
    text = changelog.replace("\r\n", "\n")
    head = re.search(r"^## \[Unreleased\][^\n]*\n", text, flags=re.M)
    if not head:
        raise SystemExit("CHANGELOG.md has no «## [Unreleased]» heading")
    start = head.end()
    nxt = re.search(r"^## \[", text[start:], flags=re.M)
    end = start + nxt.start() if nxt else len(text)
    current: dict[str, list[str]] = {}
    kind = None
    for ln in text[start:end].split("\n"):
        m = re.match(r"^### (\w+)", ln)
        if m:
            kind = m.group(1)
            current.setdefault(kind, [])
        elif ln.strip() and kind:
            current[kind].append(ln)
    for kind, lines in new.items():
        have = current.setdefault(kind, [])
        have.extend(x for x in lines if x not in have)
    order = list(TYPES) + [k for k in current if k not in TYPES]
    block = "".join(f"### {k}\n" + "\n".join(current[k]) + "\n\n" for k in order if current.get(k))
    if release:
        body = f"## [Unreleased]\n\n## [{release}] - {(today or date.today()).isoformat()}\n{block}"
    else:
        body = f"## [Unreleased]\n{block}"
    return text[:head.start()] + body + text[end:].lstrip("\n")


# --- GitHub ----------------------------------------------------------------------------------------

def _token() -> str:
    tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if tok:
        return tok
    try:
        return subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def _repo() -> str:
    url = subprocess.run(["git", "remote", "get-url", "origin"], capture_output=True, text=True, cwd=ROOT).stdout.strip()
    m = re.search(r"github\.com[:/](.+?)(?:\.git)?$", url)
    if not m:
        raise SystemExit("cannot tell the GitHub repository from the origin remote; pass --repo owner/name")
    return m.group(1)


def _since(tag: str | None) -> tuple[str, str]:
    """The last tag (or the given one) and the date of its commit."""
    tag = tag or subprocess.run(["git", "describe", "--tags", "--abbrev=0"], capture_output=True, text=True, cwd=ROOT).stdout.strip()
    if not tag:
        raise SystemExit("no tag to start from; pass --since vX.Y.Z")
    when = subprocess.run(["git", "log", "-1", "--format=%cI", tag], capture_output=True, text=True, cwd=ROOT, check=True).stdout.strip()
    return tag, when


def merged_since(repo: str, when: str, token: str, base: str = "main") -> list[dict]:
    """The pull requests merged into `base` after `when`, oldest first (one merged into another branch is not a release note: it
    reaches `base` through the pull request that merges that branch)."""
    out, page = [], 1
    while True:
        q = urllib.parse.quote(f"repo:{repo} is:pr is:merged base:{base} merged:>{when}")
        req = urllib.request.Request(f"https://api.github.com/search/issues?q={q}&per_page=100&page={page}&sort=updated&order=asc",
                                     headers={"Accept": "application/vnd.github+json", **({"Authorization": f"Bearer {token}"} if token else {})})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.load(r)
        out += data.get("items") or []
        if len(out) >= data.get("total_count", 0) or not data.get("items"):
            break
        page += 1
    return sorted(out, key=lambda p: (p.get("pull_request") or {}).get("merged_at") or "")


def collect(prs: list[dict]) -> tuple[dict[str, list[str]], list[str]]:
    """The changelog lines by type, and the pull requests that should have had an entry and have none."""
    new: dict[str, list[str]] = {}
    missing = []
    for pr in prs:
        if check(pr):
            missing.append(f"#{pr['number']} {pr['title']}")
            continue
        for kind, text in entries(pr.get("body") or ""):
            new.setdefault(kind, []).append(line(pr["number"], text))
    return new, missing


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check-pr", metavar="EVENT", help="the GitHub event file of a pull request (CI)")
    ap.add_argument("--preview", action="store_true", help="print the [Unreleased] section instead of writing it")
    ap.add_argument("--release", metavar="X.Y.Z", help="also move [Unreleased] under this version, dated today")
    ap.add_argument("--since", metavar="TAG", help="start after this tag (default: the last one)")
    ap.add_argument("--repo", metavar="OWNER/NAME", help="default: from the origin remote")
    ap.add_argument("--base", default="main", help="the branch releases are cut from (default: main)")
    a = ap.parse_args(argv)
    if a.check_pr:
        pr = json.loads(Path(a.check_pr).read_text(encoding="utf-8"))["pull_request"]
        why = check(pr)
        if why:
            print(f"::error title=Changelog::{why}")
            return 1
        print("changelog: " + ("exempt" if not section(pr.get("body") or "") else f"{len(entries(pr['body']))} entries"))
        return 0
    tag, when = _since(a.since)
    new, missing = collect(merged_since(a.repo or _repo(), when, _token(), a.base))
    for m in missing:
        print(f"warning: merged without a changelog entry: {m}", file=sys.stderr)
    raw = CHANGELOG.read_bytes().decode("utf-8")
    if a.preview:
        print(f"Merged since {tag} ({when}):\n")
        print(unreleased(merge(raw, new)).rstrip())
        return 0
    result = merge(raw, new, a.release)
    CHANGELOG.write_bytes(result.replace("\n", "\r\n" if "\r\n" in raw else "\n").encode("utf-8"))
    print(f"CHANGELOG.md: {sum(len(v) for v in new.values())} entries from the pull requests merged since {tag}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
