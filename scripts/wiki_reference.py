#!/usr/bin/env python3
"""The reference tables of the wiki are written from the code (#184), in English and Spanish, between «generated» markers: the
notification events (`notify.EVENTS` and `notify.EVENT_DOCS`) on Notifications and the instance settings (`appsettings.REGISTRY`) on
Settings reference. The rest of each page (introduction, explanations, examples) stays outside the markers and is edited by hand.

The Spanish text is the one in the code and the English one comes from the translation catalogues, so a new event or setting needs its
translation once, not once per page. An entry without a description or a translation is reported and the check fails.

Run it with the API's interpreter, which can import `mimirsynth`:

  api/.venv/bin/python scripts/wiki_reference.py           writes the tables
  api/.venv/bin/python scripts/wiki_reference.py --check   CI: fails if a page is out of date, or if an entry cannot be written
"""
import argparse
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WIKI = ROOT / "docs" / "wiki"
I18N = ROOT / "web" / "src" / "i18n"
START = "<!-- generated:start (scripts/wiki_reference.py writes this part from the code: do not edit it by hand) -->"
END = "<!-- generated:end -->"
SEVERITY = {"critical": ("critical", "crítico"), "warning": ("warning", "aviso"), "info": ("info", "información")}
# The guide each group of settings links to (English page titles; the Spanish ones come from each page's language link).
GUIDES = {"general": "Administration overview", "security": "Security and two-factor", "mail": "SMTP email", "identity": "OIDC identity",
          "docs": "Folders and limits", "recall": "Recall and ingestion", "ingest": "Recall and ingestion", "notifications": "Notifications"}
WORDS = {"en": {"Event": "Event", "Severity": "Severity", "When": "When", "Setting": "Setting", "Key": "Key", "Default": "Default",
                "Range or values": "Range or values", "Description": "Description", "Guide": "Guide", "text": "text", "url": "URL"},
         "es": {"Event": "Evento", "Severity": "Severidad", "When": "Cuándo", "Setting": "Ajuste", "Key": "Clave", "Default": "Por defecto",
                "Range or values": "Rango o valores", "Description": "Descripción", "Guide": "Guía", "text": "texto", "url": "URL"}}


def _script(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def catalog() -> dict[str, str]:
    """Spanish → English, from both catalogues and the fragments in the folder of the same name, if any."""
    out: dict[str, str] = {}
    for name in ("en.json", "en.server.json"):
        out.update(json.loads((I18N / name).read_text(encoding="utf-8")))
        parts = I18N / name.removesuffix(".json")
        for f in sorted(parts.glob("*.json")) if parts.is_dir() else []:
            out.update(json.loads(f.read_text(encoding="utf-8")))
    return {k: v for k, v in out.items() if v}


class Writer:
    """Translates and links while collecting what is missing, so one run reports every problem at once."""

    def __init__(self, cat: dict[str, str], spanish_page):
        self.cat, self.spanish_page, self.problems = cat, spanish_page, []

    def tr(self, text: str, lang: str, what: str) -> str:
        if lang == "es" or not text:
            return text
        if text not in self.cat:
            self.problems.append(f"no English translation for {what}: «{text}» (add it to the catalogue)")
            return text
        return self.cat[text]

    def link(self, page: str, lang: str) -> str:
        return f"[[{page if lang == 'en' else self.spanish_page(page)}]]"


def _num(v, lang: str) -> str:
    s = str(int(v)) if isinstance(v, float) and v.is_integer() else str(v)
    return s.replace(".", ",") if lang == "es" else s


def notifications(events: dict, docs: dict, lang: str, w: Writer) -> str:
    w_ = WORDS[lang]
    rows = [f"| {w_['Event']} | {w_['Severity']} | {w_['When']} |", "|---|---|---|"]
    order = list(SEVERITY)
    for key, (sev, _label) in sorted(events.items(), key=lambda kv: order.index(kv[1][0]) if kv[1][0] in order else len(order)):
        doc = docs.get(key)
        if not doc or not doc[0]:
            w.problems.append(f"the event {key} has no description for the wiki (notify.EVENT_DOCS)")
            continue
        when, page = w.tr(doc[0], lang, f"the event {key}"), doc[1]
        severity = w.tr(doc[2], lang, f"the severity of {key}") if len(doc) > 2 else SEVERITY.get(sev, (sev, sev))[lang == "es"]
        rows.append(f"| `{key}` | {severity} | {when}{f' ({w.link(page, lang)})' if page else ''} |")
    for key in docs:
        if key not in events:
            w.problems.append(f"notify.EVENT_DOCS describes {key}, which is not an event (notify.EVENTS)")
    return "\n".join(rows)


def settings(registry: list, groups: dict, defaults: dict, lang: str, w: Writer) -> str:
    w_, out = WORDS[lang], []
    for g, title in groups.items():
        defs = [d for d in registry if d.group == g]
        if not defs:
            continue
        out += [f"## {w.tr(title, lang, f'the group {g}')}", ""]
        if g in GUIDES:
            out += [f"{w_['Guide']}: {w.link(GUIDES[g], lang)}", ""]
        out += [f"| {w_['Setting']} | {w_['Key']} | {w_['Default']} | {w_['Range or values']} | {w_['Description']} |", "|---|---|---|---|---|"]
        for d in defs:
            if not d.help:
                w.problems.append(f"the setting {d.key} has no description (appsettings.REGISTRY)")
            unit = f" {w.tr(d.unit, lang, f'the unit of {d.key}')}" if d.unit else ""
            dv = defaults.get(d.key)
            default = "—" if dv in (None, "") else f"`{_num(dv, lang) if isinstance(dv, (int, float)) else dv}`{unit}"
            if d.type == "choice":
                rng = " / ".join(f"`{v}` ({w.tr(lbl, lang, f'a value of {d.key}')})" for v, lbl in d.choices)
            elif d.type in ("int", "float") and d.min is not None and d.max is not None:
                rng = f"{_num(d.min, lang)}–{_num(d.max, lang)}{unit}"
            else:
                rng = w_["url" if d.type == "url" else "text"]
            out.append(f"| {w.tr(d.label, lang, f'the setting {d.key}')} | `{d.key}` | {default} | {rng} | {w.tr(d.help, lang, f'the help of {d.key}')} |")
        out.append("")
    return "\n".join(out).rstrip("\n")


def replace_block(text: str, block: str, name: str) -> str:
    """The page with its generated part replaced; the part goes between the markers, which must be there once."""
    if text.count(START) != 1 or text.count(END) != 1:
        raise SystemExit(f"{name} needs exactly one pair of generated markers:\n{START}\n…\n{END}")
    head, rest = text.split(START)
    _old, tail = rest.split(END)
    return f"{head}{START}\n{block}\n{END}{tail}"


def expected(w: Writer) -> dict[str, str]:
    sys.path.insert(0, str(ROOT / "api"))
    from mimirsynth import appsettings, notify
    from mimirsynth.config import Settings
    defaults = {k: f.default for k, f in Settings.model_fields.items()}
    pages = {"Notifications.md": ("en", lambda lang: notifications(notify.EVENTS, notify.EVENT_DOCS, lang, w)),
             "Notificaciones.md": ("es", lambda lang: notifications(notify.EVENTS, notify.EVENT_DOCS, lang, w)),
             "Settings-reference.md": ("en", lambda lang: settings(appsettings.REGISTRY, appsettings.GROUPS, defaults, lang, w)),
             "Referencia-de-ajustes.md": ("es", lambda lang: settings(appsettings.REGISTRY, appsettings.GROUPS, defaults, lang, w))}
    out = {}
    for name, (lang, render) in pages.items():
        text = (WIKI / name).read_bytes().decode("utf-8").replace("\r\n", "\n")
        out[name] = replace_block(text, render(lang), name)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true", help="fail if a generated table is not up to date")
    a = ap.parse_args(argv)
    w = Writer(catalog(), _script("wiki_index").spanish)
    pages = expected(w)
    if w.problems:
        print("The wiki reference cannot be written:\n  - " + "\n  - ".join(dict.fromkeys(w.problems)))
        return 1
    stale = []
    for name, text in pages.items():
        p = WIKI / name
        raw = p.read_bytes().decode("utf-8")
        want = text.replace("\n", "\r\n") if "\r\n" in raw else text
        if raw != want:
            stale.append(name)
            if not a.check:
                p.write_bytes(want.encode("utf-8"))
    if a.check and stale:
        print(f"Out of date: {', '.join(stale)}. Run «python scripts/wiki_reference.py» with the API's interpreter and commit the result.")
        return 1
    print(f"wiki reference: {'up to date' if not stale or a.check else 'wrote ' + ', '.join(stale)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
