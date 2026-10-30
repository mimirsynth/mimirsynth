"""Política de secretos de cada brain (#116): qué se hace con lo que encuentra el detector (`secretscan`) antes de guardar una propuesta
o de indexar un documento.

- **mask** (por defecto): los secretos seguros se sustituyen por `[secreto eliminado: tipo]`; los posibles se marcan para el curador.
- **block**: un secreto seguro rechaza la propuesta o deja el documento sin indexar; los posibles se marcan.
- **warn**: no se cambia nada; todo se marca para el curador.

Lo marcado («flagged») no lo aprueba el decisor: la propuesta espera a una persona. Ni la auditoría, ni los logs, ni la API guardan el
valor detectado: solo la regla y su posición en el texto guardado.
"""
from . import appsettings
from .i18n import tr
from .models import Brain
from .secretscan import BY_ID, RULES, Finding, redact, scan

MODES = ("mask", "block", "warn")


class Blocked(Exception):
    """El brain bloquea y el texto lleva secretos seguros. `rules`: las reglas que saltaron; `labels`: sus tipos, ya traducidos."""
    def __init__(self, rules: list[str], labels: list[str]):
        super().__init__(", ".join(labels))
        self.rules, self.labels = rules, labels


def labels(lang: str) -> dict[str, str]:
    return {r.id: tr(r.label, lang) for r in RULES}


def instance_lang() -> str:
    return appsettings.get("default_language") or "es"


def guard(brain: Brain, text: str, lang: str | None = None) -> tuple[str, list[dict]]:
    """El texto que se guarda y los hallazgos `{rule, start, end, action}` (posiciones en ese texto; action: masked | flagged).
    El marcador se escribe en el idioma de la instancia, porque queda en la memoria y la leen todos. Lanza Blocked si toca."""
    found = scan(text, brain.secret_allow or "")
    if not found:
        return text, []
    lang = lang or instance_lang()
    names = labels(lang)
    if brain.secret_mode == "block" and any(f.certain for f in found):
        rules = sorted({f.rule for f in found if f.certain})
        raise Blocked(rules, [names[r] for r in rules])
    spans: list = []
    if brain.secret_mode == "warn":
        found = [Finding(f.rule, f.label, f.start, f.end, False) for f in found]  # nada se enmascara: todo pasa a «posible»
    out = redact(text, found, marker=tr("[secreto eliminado: {{label}}]", lang, label="{label}"), labels=names, spans=spans)
    return out, [{"rule": f.rule, "start": a, "end": b, "action": "masked" if masked else "flagged"} for f, a, b, masked in spans]


def audit_existing(db, brain: Brain, max_items: int = 500, max_bytes: int = 200 * 1024 * 1024) -> dict:
    """Pasa el detector, en solo lectura, por las propuestas y los documentos indexados del brain. Sirve para medir aciertos y falsos
    positivos antes de confiar en él. De cada hallazgo devuelve la regla y el texto que lo precede (con cualquier secreto ya tapado),
    nunca el valor. No cambia nada."""
    from sqlalchemy import select

    from . import docstore
    from .models import Document, Proposal

    by_rule: dict[str, dict] = {}
    items: list[dict] = []
    counts = {"proposals": 0, "documents": 0, "bytes": 0, "truncated": False}

    def look(kind: str, oid: int, title: str, text: str) -> None:
        found = scan(text, brain.secret_allow or "")
        if not found:
            return
        spans: list = []
        hidden = redact(text, found, marker="[{rule}]", everything=True, spans=spans)
        for f, a, _, _ in spans:
            r = by_rule.setdefault(f.rule, {"rule": f.rule, "label": f.label, "certain": f.certain, "count": 0, "items": 0})
            r["count"] += 1
        for rule in {f.rule for f in found}:
            by_rule[rule]["items"] += 1
        if len(items) < max_items:
            items.append({"kind": kind, "id": oid, "title": title[:200],
                          "findings": [{"rule": f.rule, "label": f.label, "certain": f.certain, "context": hidden[max(0, a - 60):a].replace("\n", " ")}
                                       for f, a, _, _ in spans[:20]]})

    for p in db.scalars(select(Proposal).where(Proposal.brain_id == brain.id).order_by(Proposal.id.desc())):
        counts["proposals"] += 1
        look("proposal", p.id, p.name, f"{p.name}\n{p.body}")
    for d in db.scalars(select(Document).where(Document.brain_id == brain.id, Document.status == "active", Document.text_ref != "")):
        try:
            path = docstore.resolve(d.text_ref)
            size = path.stat().st_size
        except (OSError, ValueError):
            continue
        if counts["bytes"] + size > max_bytes:
            counts["truncated"] = True
            break
        counts["documents"] += 1
        counts["bytes"] += size
        look("document", d.id, d.title or d.filename, path.read_text(encoding="utf-8", errors="replace"))
    return {**counts, "mode": brain.secret_mode, "rules": sorted(by_rule.values(), key=lambda r: (not r["certain"], -r["count"])),
            "items": items, "items_truncated": len(items) >= max_items}


def flagged(findings: list[dict] | None) -> bool:
    return any(f.get("action") == "flagged" for f in findings or [])


def summary(findings: list[dict]) -> list[dict]:
    """Recuento por regla y acción, para los metadatos de un documento."""
    out: dict[tuple[str, str], int] = {}
    for f in findings:
        out[(f["rule"], f["action"])] = out.get((f["rule"], f["action"]), 0) + 1
    return [{"rule": r, "action": a, "count": n} for (r, a), n in sorted(out.items())]


def describe(findings: list[dict] | None) -> list[dict]:
    """Los hallazgos con su etiqueta, para la API (en español, como el resto de textos del servidor que la interfaz traduce)."""
    return [{**f, "label": BY_ID[f["rule"]].label if f["rule"] in BY_ID else f["rule"]} for f in findings or []]
