"""Quality at write time (#458): right after an episode is ingested, the facts it just created that repeat each other, or a current
fact already in the brain, word for word become one, and those with a placeholder or the memory itself at one end are dropped. Only
edges this same episode created are ever deleted; what was already in the brain is never touched beyond linking the episode to it.
Near-duplicates and the subtler noise stay curator proposals: without a person a wrong merge would lose information silently."""
import logging

from .curator import NOISE_RULES, sure_noise
from .db import graph, rows

log = logging.getLogger("mimirsynth.write_quality")

_FOUND = ("MATCH (a:Entity)-[r:RELATES_TO]->(b:Entity) WHERE r.uuid IN $u "
          "RETURN r.uuid AS uuid, r.fact AS fact, r.episodes AS episodes, r.invalid_at AS invalid_at, r.expired_at AS expired_at, "
          "a.uuid AS su, a.name AS source, b.uuid AS tu, b.name AS target")
_CURRENT = ("MATCH (a:Entity)-[r:RELATES_TO]->(b:Entity) WHERE a.uuid IN $ends AND b.uuid IN $ends AND NOT r.uuid IN $new "
            "AND r.invalid_at IS NULL AND r.expired_at IS NULL RETURN r.uuid AS uuid, r.fact AS fact, a.uuid AS su, b.uuid AS tu")
SAME_EPISODE = "says word for word what another fact of this episode says"
SAME_CURRENT = "says word for word what a current fact already in the brain says"


def same_text(text) -> str:
    """A fact's text as compared here: case, spacing and a closing full stop do not count."""
    return " ".join(str(text or "").lower().split()).rstrip(" .")


def _pair(f: dict) -> tuple[str, str]:
    return tuple(sorted((str(f["su"]), str(f["tu"]))))


def _old(f: dict) -> bool:
    return bool(f.get("invalid_at") or f.get("expired_at"))


def new_of(found: list[dict], episode: str) -> list[dict]:
    """The facts this episode created: their only episode is this one. The others in the ingest report were already in the brain."""
    return [f for f in found if list(f.get("episodes") or []) == [episode]]


def decide(found: list[dict], episode: str, current: list[dict]) -> dict:
    """What to do with the facts of an ingest report. `found`: the report's facts as read from the graph; `current`: the current facts
    already in the brain between the ends of the new ones. Returns the uuids to delete, the existing facts to link the episode to, and
    the entries of the report."""
    new = new_of(found, episode)
    ids = {f["uuid"] for f in new}
    # A fact this episode invalidated may have been replaced by a trivial-looking one: that one stays, for a person to judge.
    ends_hit = {str(f[k]) for f in found if f["uuid"] not in ids and _old(f) for k in ("su", "tu")}
    gone, link, collapsed, dropped = [], [], [], []
    kept: dict[tuple, str] = {}
    for f in new:
        rule = sure_noise(f)
        if rule and not ({str(f["su"]), str(f["tu"])} & ends_hit):
            gone.append(f["uuid"])
            dropped.append({"fact": f["fact"], "rule": rule, "why": NOISE_RULES[rule]})
            continue
        key = (*_pair(f), same_text(f["fact"]), _old(f))
        if key in kept:
            gone.append(f["uuid"])
            collapsed.append({"fact": f["fact"], "kept": kept[key], "why": SAME_EPISODE})
        else:
            kept[key] = f["uuid"]
    by_pair: dict[tuple, list[dict]] = {}
    for c in current:
        if c["uuid"] not in ids:
            by_pair.setdefault(_pair(c), []).append(c)
    for (a, b, text, old), uuid in kept.items():
        match = None if old else next((c for c in by_pair.get((a, b), []) if same_text(c["fact"]) == text), None)
        if match:
            gone.append(uuid)
            link.append(match["uuid"])
            fact = next(f["fact"] for f in new if f["uuid"] == uuid)
            collapsed.append({"fact": fact, "kept": match["uuid"], "why": SAME_CURRENT})
            for e in collapsed:
                if e["kept"] == uuid:
                    e["kept"] = match["uuid"]
    return {"gone": gone, "link": sorted(set(link)), "collapsed": collapsed, "dropped": dropped}


def apply(brain, rep: dict, episode: str) -> None:
    """Applies `decide` to the edges add_episode left in rep['_edges'], keeps there only the ones that stay, and adds what it did to the
    ingest report. A failure here never fails the ingestion: the episode is already in."""
    edges = rep.get("_edges") or []
    if not edges or not episode:
        return
    try:
        g = graph(brain.graph_name)
        found = rows(g.query(_FOUND, {"u": [u for u, _ in edges]}))
        new = [f for f in new_of(found, episode) if not _old(f)]
        ends = sorted({str(f[k]) for f in new for k in ("su", "tu")})
        current = rows(g.query(_CURRENT, {"ends": ends, "new": [f["uuid"] for f in new]})) if ends else []
        out = decide(found, episode, current)
        if out["gone"]:   # the guard repeats here what `decide` already checked: only an edge whose only episode is this one goes
            g.query("MATCH ()-[r:RELATES_TO]->() WHERE r.uuid IN $u AND size(r.episodes) = 1 AND $e IN r.episodes DELETE r",
                    {"u": out["gone"], "e": episode})
        for u in out["link"]:
            g.query("MATCH ()-[r:RELATES_TO {uuid:$u}]->() WHERE NOT $e IN coalesce(r.episodes, []) SET r.episodes = coalesce(r.episodes, []) + [$e]",
                    {"u": u, "e": episode})
        if out["gone"] or out["link"]:
            g.query("MATCH (e:Episodic {uuid:$e}) SET e.entity_edges = [x IN coalesce(e.entity_edges, []) WHERE NOT x IN $g] + "
                    "[x IN $l WHERE NOT x IN coalesce(e.entity_edges, [])]", {"e": episode, "g": out["gone"], "l": out["link"]})
        gone = set(out["gone"])
        rep["_edges"] = [(u, n) for u, n in edges if u not in gone]
        if gone and isinstance(rep.get("edges"), int):
            rep["edges"] = max(0, rep["edges"] - len(gone))
        if out["collapsed"]:
            rep["collapsed"] = out["collapsed"]
        if out["dropped"]:
            rep["dropped"] = out["dropped"]
    except Exception:  # noqa: BLE001 — the episode is in; this only tidies it
        log.exception("no se pudo revisar la calidad de los hechos tras ingerir")
        rep["quality_error"] = True
