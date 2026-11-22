"""Retirement trigger (#455): a new fact saying an entity was retired, removed, replaced, migrated or decommissioned queues a topic
review of that entity, with the fact as its anchor, so the facts that still describe it as live reach a curator.

- **Which facts.** The new facts of an ingested episode (after #458 merged the repeats and dropped the trivial ones) that are still
  current, whose relation is marked in the brain's ontology (`retires`: the end that is retired, `source` or `target`) or is one of the
  names below. With no extra AI call: the relation's name already says it.
- **Which end.** «X REPLACED_BY Y», «X MIGRATED_TO Y» retire their source; «Y REPLACES X», «Y SUPERSEDES X» their target.
- **The review** (`topic_review.queue_retirement`): one per entity; a second fact joins it while it is still queued. Nothing is
  invalidated without a person: the review only proposes. The proposal's ingestion report says what was queued and what was not, and why.
"""
import logging

from .ontology import canon, get_ontology

log = logging.getLogger("mimirsynth.retirement")

# The relation names an extraction writes for these events, by the end that is retired or replaced.
SOURCE = frozenset("""REPLACED_BY SUPERSEDED_BY MIGRATED_TO DEPRECATED_BY SUCCEEDED_BY RETIRED_ON RETIRED_IN DECOMMISSIONED_ON
DECOMMISSIONED_IN REMOVED_ON REMOVED_IN REEMPLAZADO_POR SUSTITUIDO_POR MIGRADO_A RETIRADO_EN DADO_DE_BAJA_EN""".split())
TARGET = frozenset("""REPLACES SUPERSEDES SUCCEEDS MIGRATED_FROM DECOMMISSIONED RETIRED DEPRECATED REMOVED REEMPLAZA REEMPLAZA_A
SUSTITUYE SUSTITUYE_A MIGRADO_DESDE RETIRA DA_DE_BAJA DIO_DE_BAJA""".split())
PREFIXES = ("HAS_BEEN_", "HAVE_BEEN_", "HA_SIDO_", "WAS_", "WERE_", "IS_", "FUE_", "ES_")
FACT_CHARS = 300
MAX_FACTS = 50   # retirement facts read per ingestion


def marks(onto: dict | None) -> dict[str, str]:
    """The relations the brain's ontology marks, by the graph's spelling of their name, and the end each one retires."""
    return {canon(t["name"]): t["retires"] for t in (onto or {}).get("edge_types", []) if t.get("retires") in ("source", "target")}


def end(name: str | None, marked: dict[str, str]) -> str | None:
    """The end a fact of this relation retires or replaces, or None when the relation does not say so."""
    c = canon(name or "")
    if c in marked:
        return marked[c]
    for p in PREFIXES:
        if c.startswith(p):
            c = c[len(p):]
            break
    return "source" if c in SOURCE else "target" if c in TARGET else None


READ = ("MATCH (a:Entity)-[r:RELATES_TO]->(b:Entity) WHERE r.uuid IN $u AND r.invalid_at IS NULL AND r.expired_at IS NULL "
        "RETURN r.uuid AS uuid, r.name AS name, r.fact AS fact, a.uuid AS s, a.name AS sname, b.uuid AS t, b.name AS tname")


def detect(db, brain, report: dict, proposal_id: int | None = None, graph=None) -> dict | None:
    """Queues a review of each entity the episode's new facts say was retired or replaced. Returns what it did, for the ingestion
    report, or None when no new fact says so. Never fails the ingestion: a failure (the graph down, say) is logged and said."""
    from . import topic_review
    from .db import graph as open_graph, rows
    new = set(report.get("_new_edges") or [])
    names = {u: n for u, n in report.get("_edges") or [] if u in new}
    if not names:
        return None
    out: dict = {"queued": [], "joined": [], "not_queued": []}
    try:
        marked = marks(get_ontology(db, brain.id))
        hits = [u for u, n in names.items() if end(n, marked)]
        if not hits:
            return None
        g = graph if graph is not None else open_graph(brain.graph_name)
        by_entity: dict[str, tuple[str, list[dict]]] = {}
        for f in rows(g.query(READ, {"u": hits[:MAX_FACTS]})):
            side = end(names.get(f["uuid"]) or f["name"], marked)
            if side is None:
                continue
            uuid, name = (f["s"], f["sname"]) if side == "source" else (f["t"], f["tname"])
            anchor = {"uuid": f["uuid"], "fact": " ".join(str(f["fact"] or "").split())[:FACT_CHARS], "relation": f["name"] or "",
                      "proposal": proposal_id}
            by_entity.setdefault(uuid, (name or "", []))[1].append(anchor)
        for uuid, (name, anchors) in by_entity.items():
            what, rid = topic_review.queue_retirement(db, brain, uuid, name, anchors)
            entry = {"entity": uuid, "name": name[:200], "facts": [a["uuid"] for a in anchors]}
            if rid is None:
                out["not_queued"].append({**entry, "why": what})
            else:
                out[what].append({**entry, "review": rid})
    except Exception as e:  # noqa: BLE001  (the episode is in; the review can still be asked for from the entity page)
        db.rollback()
        log.exception("no se pudo encolar la revisión de una retirada (brain %s)", brain.id)
        out["error"] = str(e)[:300]
    return out
