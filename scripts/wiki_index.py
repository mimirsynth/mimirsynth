#!/usr/bin/env python3
"""The wiki's navigation is generated from docs/wiki/_index.yml (#168): `_Sidebar.md` entirely, and the page lists of `Home.md` and
`Inicio.md` between their «index» markers. Those parts are never edited by hand, so two pull requests that add pages do not write the
same lines: each adds one line to `_index.yml`.

Pages are named by their English title (the file name with spaces). The Spanish title comes from the link at the top of each English
page («**English** · [Español](Página)»), so the pairs live in one place only.

  python scripts/wiki_index.py           writes the generated files
  python scripts/wiki_index.py --check   CI: fails if they are not up to date, or if a page is missing from _index.yml
"""
import argparse
import re
import sys
import urllib.parse
from pathlib import Path

import yaml

WIKI = Path(__file__).resolve().parent.parent / "docs" / "wiki"
NOTICE = "<!-- generated from _index.yml by scripts/wiki_index.py: edit _index.yml, not this list -->"
START, END = "<!-- index:start -->", "<!-- index:end -->"
SPECIAL = {"_Sidebar", "_Footer", "Home", "Inicio"}


def _file(title: str) -> Path:
    return WIKI / f"{title.replace(' ', '-')}.md"


def spanish(title: str) -> str:
    """The Spanish title of an English page, from the language link at its top."""
    p = _file(title)
    if not p.exists():
        raise SystemExit(f"_index.yml names «{title}», but there is no {p.name}")
    first = p.read_text(encoding="utf-8").lstrip("﻿").split("\n", 1)[0]
    m = re.search(r"\[Español\]\(([^)]+)\)", first)
    if not m:
        raise SystemExit(f"{p.name} does not start with a link to its Spanish page («**English** · [Español](…)»)")
    return urllib.parse.unquote(m.group(1)).replace("-", " ")


def _links(pages: list[str], lang: str) -> list[str]:
    return [f"[[{p if lang == 'en' else spanish(p)}]]" for p in pages]


def sidebar(index: dict) -> str:
    out = ["**[MimirSynth](Home)** · [Español](Inicio)", ""]
    for s in index["sidebar"]:
        out += [f"**{s['title']['en']}**", *[f"- {x}" for x in _links(s["pages"], "en")], ""]
    out += ["---", "<details>", "<summary><b>Español</b></summary>", ""]
    out += "\n\n".join(f"**{s['title']['es']}:** " + " · ".join(_links(s["pages"], "es")) for s in index["sidebar"]).split("\n")
    out += ["</details>", ""]
    return "\n".join([NOTICE, *out])


def home_lists(index: dict, lang: str) -> str:
    out = [START, NOTICE]
    for g in index["home"]:
        out += [f"## {g['title'][lang]}"]
        for i, ln in enumerate(g["lines"]):
            if i:
                out.append("")
            label = f"{ln['label'][lang]} " if ln.get("label") else ""
            out.append(label + " · ".join(_links(ln["pages"], lang)))
        out.append("")
    out.append(END)
    return "\n".join(out)


def _with_lists(text: str, lists: str, name: str) -> str:
    if START not in text or END not in text:
        raise SystemExit(f"{name} has no «{START}» … «{END}» markers around its page lists")
    return text[:text.index(START)] + lists + text[text.index(END) + len(END):]


def expected(index: dict) -> dict[str, str]:
    """The generated files, with LF line ends."""
    out = {"_Sidebar.md": sidebar(index)}
    for name, lang in (("Home.md", "en"), ("Inicio.md", "es")):
        out[name] = _with_lists((WIKI / name).read_bytes().decode("utf-8").replace("\r\n", "\n"), home_lists(index, lang), name)
    return out


def unlisted(index: dict) -> list[str]:
    """Pages that are neither in the navigation nor declared as unlisted."""
    named = {p for s in index["sidebar"] for p in s["pages"]} | {p for g in index["home"] for ln in g["lines"] for p in ln["pages"]}
    named |= set(index.get("unlisted") or [])
    stems = {_file(n).stem for n in named | {spanish(p) for p in named}}
    return sorted(p.stem for p in WIKI.glob("*.md") if p.stem not in SPECIAL and p.stem not in stems)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true", help="fail if the generated files are not up to date")
    a = ap.parse_args(argv)
    index = yaml.safe_load((WIKI / "_index.yml").read_text(encoding="utf-8"))
    missing = unlisted(index)
    if missing:
        print("These wiki pages are not in docs/wiki/_index.yml (add them to a section, or to «unlisted»):\n  - " + "\n  - ".join(missing))
        return 1
    stale = []
    for name, text in expected(index).items():
        p = WIKI / name
        raw = p.read_bytes().decode("utf-8") if p.exists() else ""
        want = text.replace("\n", "\r\n") if "\r\n" in raw else text
        if raw != want:
            stale.append(name)
            if not a.check:
                p.write_bytes(want.encode("utf-8"))
    if a.check and stale:
        print(f"Out of date: {', '.join(stale)}. Run «python scripts/wiki_index.py» and commit the result.")
        return 1
    print(f"wiki index: {'up to date' if not stale or a.check else 'wrote ' + ', '.join(stale)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
