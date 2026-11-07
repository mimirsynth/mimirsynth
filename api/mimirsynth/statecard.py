"""Current-state card per entity (#294): for a question about the present, the recall answers first from the entity's current state, the
current value of each relation, before any fact, fragment or passage that competes with it; the history stays available below.

- **The card** of an entity: its current facts grouped by relation (through the relation aliases), each with the date it became valid,
  its trust tier and, when it has a probe, its verification. As the reviewer decided on #294, every current fact of a relation is
  listed and the ranking decides; only a relation a curator marked **functional** (one value at a time) shows a single value, the
  newest, and says how many others are current (a possible contradiction, #113).
- **Derived, never stored:** it is read from the graph when asked, so it is always the current state and rebuilding it loses nothing.
  A fact replaced by a newer one leaves the card at once and stays in the recall's «no longer true» section.
- **In the recall**, with `recall_state_card` on (off by default; reference queries can simulate it): the entities of the first
  current facts (up to MAX_ENTITIES) get their card at the top of the context and in the JSON (`state`). A question about the past
  («before», «history», «what was») gets no card. `GET /api/brains/{slug}/entities/{uuid}/state` gives one entity's card.
"""
import re

from fastapi import Depends, HTTPException

from . import appsettings
from .db import rows
from .deps import BrainCtx
from .entity_page import router, reader
from .i18n import tr
from .vocab import alias_map, resolve

MAX_ENTITIES = 2
MAX_FACTS = 12   # per card
_PAST = re.compile(r"\b(antes|anterior(es|mente)?|historia|hist[oó]ric[oa]s?|cambi[oó]|sol[ií]a|era|estaba|before|previous(ly)?|history|historical|"
                   r"used to|was|were|changed)\b", re.I)
_CARD = ("MATCH (a:Entity {uuid:$u})-[r:RELATES_TO]->(b:Entity) WHERE r.invalid_at IS NULL AND r.expired_at IS NULL "
         "RETURN r.uuid AS uuid, r.name AS name, r.fact AS fact, r.valid_at AS valid_at, r.created_at AS created_at, r.episodes AS episodes, "
         "a.name AS source, a.uuid AS source_uuid, b.name AS target, b.uuid AS target_uuid "
         "ORDER BY coalesce(r.valid_at, r.created_at) DESC, r.uuid LIMIT 200")


def about_the_past(query: str) -> bool:
    return bool(_PAST.search(query or ""))


def card(brain_id: int, graph, uuid: str, amap: dict | None, functional: set[str]) -> dict | None:
    """The current state of one entity, or None if it has no current fact."""
    from . import trust, verify
    facts = rows(graph.query(_CARD, {"u": uuid}))
    if not facts:
        return None
    for f in facts:
        f["status"] = "current"
    facts = trust.mark(brain_id, verify.mark(brain_id, facts), trust=False)   # tier and verification, without reordering
    by: dict[str, list[dict]] = {}
    for f in facts:
        by.setdefault(resolve(f["name"], amap), []).append(f)
    relations, shown = [], 0
    for rel in sorted(by):
        fs = by[rel]   # newest first
        one = rel in functional
        values = fs[:1] if one else fs
        values = values[:max(0, MAX_FACTS - shown)]
        if not values:
            break
        shown += len(values)
        relations.append({"relation": rel, "functional": one, "also_current": len(fs) - 1 if one else 0,
                          "values": [{k: v.get(k) for k in ("uuid", "fact", "target", "target_uuid", "valid_at", "trust", "verification")} for v in values]})
    return {"uuid": uuid, "name": facts[0]["source"], "relations": relations}


def for_recall(brain_id: int, graph, query: str, facts: list[dict], amap: dict | None, on: bool | None = None) -> list[dict]:
    """The cards of the entities the recall's first current facts are about, unless it is off or the question is about the past."""
    from .conflicts import _brain_functional
    from .store import _factory
    if not (bool(on) if on is not None else appsettings.get("recall_state_card") == "yes") or about_the_past(query):
        return []
    seen: list[str] = []
    for f in facts:
        if f.get("status") == "current" and not f.get("origin") and f.get("source_uuid") and f["source_uuid"] not in seen:
            seen.append(f["source_uuid"])
        if len(seen) >= MAX_ENTITIES:
            break
    if not seen:
        return []
    with _factory()() as db:
        functional = _brain_functional(db, brain_id)
    return [c for u in seen if (c := card(brain_id, graph, u, amap, functional))]


def context_lines(cards: list[dict], lang: str) -> list[str]:
    """The cards as the agent reads them, before everything else."""
    from .recall import _fmt_date
    out = []
    for c in cards:
        out.append(tr("## Estado actual de «{{entity}}»", lang, entity=c["name"]))
        for r in c["relations"]:
            vals = "; ".join(f"{v['target']} ({tr('desde {{date}}', lang, date=_fmt_date(v['valid_at']))})" for v in r["values"])
            extra = " " + tr("[y {{n}} valores más vigentes: posible contradicción]", lang, n=r["also_current"]) if r["also_current"] else ""
            out.append(f"- {r['relation']}: {vals}{extra}")
    return out


@router.get("/{uuid}/state")
def entity_state(uuid: str, ctx: BrainCtx = Depends(reader)):
    """The current-state card of one entity of this brain."""
    from .conflicts import _brain_functional
    c = card(ctx.brain.id, ctx.graph, uuid, alias_map(ctx.db, ctx.brain.id), _brain_functional(ctx.db, ctx.brain.id))
    if c is None:
        raise HTTPException(404, "la entidad no tiene hechos vigentes")
    return c
