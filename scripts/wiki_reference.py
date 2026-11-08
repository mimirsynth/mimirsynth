#!/usr/bin/env python3
"""The reference tables of the wiki are written from the code (#184), in English and Spanish, between «generated» markers: the
notification events (`notify.EVENTS` and `notify.EVENT_DOCS`) on Notifications, the instance settings (`appsettings.REGISTRY`) on
Settings reference, and every route of the app by area and role (FastAPI) on REST API. The rest of each page (introduction,
explanations, notes on particular routes, examples) stays outside the markers and is edited by hand.

The Spanish text is the one in the code and the English one comes from the translation catalogues, so a new event or setting needs its
translation once, not once per page. An entry without a description or a translation is reported and the check fails.

Run it with the API's interpreter, which can import `mimirsynth`:

  api/.venv/bin/python scripts/wiki_reference.py           writes the tables
  api/.venv/bin/python scripts/wiki_reference.py --check   CI: fails if a page is out of date, or if an entry cannot be written
"""
import argparse
import importlib.util
import json
import re
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
                "Range or values": "Range or values", "Description": "Description", "Guide": "Guide", "text": "text", "url": "URL",
                "Area": "Area", "Routes": "Routes", "Role": "Role", "Access": "Access"},
         "es": {"Event": "Evento", "Severity": "Severidad", "When": "Cuándo", "Setting": "Ajuste", "Key": "Clave", "Default": "Por defecto",
                "Range or values": "Rango o valores", "Description": "Descripción", "Guide": "Guía", "text": "texto", "url": "URL",
                "Area": "Área", "Routes": "Rutas", "Role": "Rol", "Access": "Acceso"}}

# REST API: every route under /api, from FastAPI, by area and by the role its dependencies require (the minimum: some routes check
# more inside, and the hand-written notes of the page say so). An area is found by the longest path prefix that matches; a route
# with no area, or a brain route with no role, is reported, so a new one gets a deliberate place in the page.
BRAIN = "/api/brains/{slug}"
ROLES = {"public": ("public", "pública"), "reader": ("reader", "lector"), "contributor": ("contributor", "colaborador"),
         "curator": ("curator", "curador"), "admin": ("administrator", "administrador"), "owner": ("owner", "propietario"),
         "session": ("signed in", "con sesión"), "instance": ("instance administrator", "administrador de la instancia"),
         "hook": ("the webhook's secret", "el secreto del webhook")}
# Routes whose access is not a role (the incoming webhook answers to its own secret), and routes left out (the MCP endpoint only
# answers POST; GET and DELETE exist to say so with a 405).
SPECIAL = {("POST", BRAIN + "/hooks/{key}"): "hook"}
SKIP = {("GET", BRAIN + "/mcp"), ("DELETE", BRAIN + "/mcp")}
METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE"]
BRAIN_AREAS = [  # (English, Spanish, path prefixes after /api/brains/{slug}; "" is the brain itself)
    ("Recall", "Recall", ["/recall", "/answer", "/mcp", "/news", "/whoami"]), ("Text index", "Índice de texto", ["/index"]),
    ("Overview", "Resumen", ["/overview"]), ("Episodes", "Episodios", ["/episodes"]), ("Facts", "Hechos", ["/facts", "/timeline", "/entities"]),
    ("Graph and query", "Grafo y consulta", ["/graph", "/query"]), ("Proposals", "Propuestas", ["/proposals"]), ("Documents", "Documentos", ["/docs"]),
    ("Vocabulary", "Vocabulario", ["/vocabulary", "/vocab", "/ontology", "/retype", "/summaries"]), ("Needs your attention", "Necesita tu atención", ["/attention"]),
    ("What changed", "Lo que ha cambiado", ["/changes"]), ("Facts to review", "Hechos a revisar", ["/review"]),
    ("Contradictions", "Contradicciones", ["/conflicts"]), ("Reference queries", "Consultas de referencia", ["/refqueries"]),
    ("Memory health", "Salud de la memoria", ["/health"]),
    ("Replay sample", "Muestra para repetir", ["/replay"]),
    ("Curator", "Curador", ["/curator"]),
    ("Archived facts", "Hechos archivados", ["/archive"]),
    ("Right to be forgotten", "Derecho al olvido", ["/forget"]),
    ("Verifiable facts", "Hechos verificables", ["/verifiers", "/probes"]),
    ("Review by category", "Revisión por categorías", ["/review/categories"]),
    ("Federation", "Federación", ["/grants"]), ("Jobs", "Trabajos", ["/jobs"]), ("Members", "Miembros", ["/members"]), ("Tokens", "Tokens", ["/tokens"]),
    ("The brain itself", "El propio brain", ["", "/delete", "/secrets"]), ("AI consumption", "Consumo de IA", ["/ai-usage", "/ai-budget"]),
    ("Incoming webhooks", "Webhooks de entrada", ["/webhooks", "/hooks"]), ("Retention", "Retención", ["/retention"]), ("Export", "Exportar", ["/exports"]),
]
INSTANCE_AREAS = [  # path prefixes after /api
    ("Access", "Acceso", ["/auth"]), ("My account", "Mi cuenta", ["/me", "/users/{uid}/avatar", "/onboarding"]), ("Search all brains", "Buscar en todos los brains", ["/search"]),
    ("Notifications", "Notificaciones", ["/notifications"]), ("Brains", "Brains", ["/brains"]), ("AI consumption", "Consumo de IA", ["/ai-usage"]),
    ("Import a brain", "Importar un brain", ["/brain-imports"]),
    ("Administration", "Administración", ["/admin", "/users", "/audit", "/settings", "/oidc-providers", "/llm-engines", "/embedding-engines",
                                          "/decision-engines", "/doc-roots", "/ai-status"]),
    ("Embedding model change", "Cambio de modelo de embeddings", ["/embedding-engines/reindex", "/embedding-engines/{eid}/reindex"]),
    ("Public", "Públicas", ["/health", "/config"]),
]


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


def api_routes(app) -> list[tuple[str, str, str]]:
    """(method, path, access) of every documented route of the app, in the order they are declared."""
    from fastapi.routing import APIRoute
    flat = []
    for r in app.routes:
        sub = getattr(r, "original_router", None)  # a router included in the app
        flat += [x for x in sub.routes if isinstance(x, APIRoute)] if sub is not None else ([r] if isinstance(r, APIRoute) else [])

    def access(route) -> str:
        found = []

        def walk(dep):
            for d in dep.dependencies:
                name = getattr(d.call, "__qualname__", "")
                if name == "brain_access.<locals>.dep":
                    found.append(d.call.__closure__[0].cell_contents)  # brain_access(minimum)
                elif name == "require_admin":
                    found.append("instance")
                elif name == "current_user":
                    found.append("session")
                walk(d)
        walk(route.dependant)
        for level in ("owner", "admin", "curator", "contributor", "reader", "instance", "session"):
            if level in found:
                return level
        return "public"

    out = []
    for r in flat:
        if not r.include_in_schema or not r.path.startswith("/api"):
            continue
        path = re.sub(r"\{(\w+):\w+\}", r"{\1}", r.path)  # {doc_id:int} → {doc_id}
        for m in sorted(r.methods - {"HEAD", "OPTIONS"}):
            if (m, path) not in SKIP:
                out.append((m, path, SPECIAL.get((m, path), access(r))))
    return out


def _area(rel: str, areas: list) -> int | None:
    best, size = None, -1
    for i, (_en, _es, prefixes) in enumerate(areas):
        for p in prefixes:
            if (rel == p or (p and rel.startswith(p + "/"))) and len(p) > size:
                best, size = i, len(p)
    return best


def routes_table(routes: list[tuple[str, str, str]], brain: bool, lang: str, w: Writer) -> str:
    """One row per area and access level, with the routes as `GET/POST /path` in declaration order."""
    areas = BRAIN_AREAS if brain else INSTANCE_AREAS
    order = list(ROLES)
    rows: dict[tuple[int, str], dict[str, list[str]]] = {}
    for method, path, level in routes:
        if path.startswith(BRAIN) != brain:
            continue
        rel = path[len(BRAIN):] if brain else path[len("/api"):]
        i = _area(rel, areas)
        if i is None:
            w.problems.append(f"the route {method} {path} has no area in the wiki reference (BRAIN_AREAS / INSTANCE_AREAS in scripts/wiki_reference.py)")
            continue
        if brain and level in ("public", "session", "instance"):
            w.problems.append(f"the brain route {method} {path} needs no brain role: say who may call it in SPECIAL (scripts/wiki_reference.py)")
            continue
        rows.setdefault((i, level), {}).setdefault(rel or path, []).append(method)
    w_ = WORDS[lang]
    out = [f"| {w_['Area']} | {w_['Routes']} | {w_['Role' if brain else 'Access']} |", "|---|---|---|"]
    last = None
    for (i, level), paths in sorted(rows.items(), key=lambda kv: (kv[0][0], order.index(kv[0][1]))):
        name = f"**{areas[i][lang == 'es']}**" if i != last else ""
        last = i
        cell = " · ".join(f"`{'/'.join(sorted(set(ms), key=METHODS.index))} {p}`" for p, ms in paths.items())
        out.append(f"| {name} | {cell} | {ROLES[level][lang == 'es']} |".replace("|  |", "| |"))
    return "\n".join(out)


def rest(routes: list[tuple[str, str, str]], lang: str, w: Writer) -> str:
    if lang == "es":
        return ("## Rutas por brain\nTodas cuelgan de `/api/brains/{slug}/…`. El rol es el **mínimo** que piden sus dependencias; unas pocas rutas "
                "comprueban algo más, ver las notas de abajo.\n\n" + routes_table(routes, True, lang, w)
                + "\n\n## Rutas de cuenta y de instancia\nCuelgan de `/api/…`.\n\n" + routes_table(routes, False, lang, w))
    return ("## Per-brain routes\nAll hang off `/api/brains/{slug}/…`. The role is the **minimum** their dependencies require; a few routes "
            "check more, see the notes below.\n\n" + routes_table(routes, True, lang, w)
            + "\n\n## Account and instance routes\nUnder `/api/…`.\n\n" + routes_table(routes, False, lang, w))


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
    from mimirsynth.main import app
    defaults = {k: f.default for k, f in Settings.model_fields.items()}
    routes = api_routes(app)
    pages = {"REST-API.md": ("en", lambda lang: rest(routes, lang, w)), "API-REST.md": ("es", lambda lang: rest(routes, lang, w)),"Notifications.md": ("en", lambda lang: notifications(notify.EVENTS, notify.EVENT_DOCS, lang, w)),
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
