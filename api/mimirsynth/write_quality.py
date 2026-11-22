"""Quality at write time (#458): right after an episode is ingested, the facts it just created that repeat each other, or a current
fact already in the brain, word for word become one, and those with a placeholder or the memory itself at one end are dropped. Only
edges this same ingestion created are ever deleted; what was already in the brain is never touched beyond linking the episode to it.
Near-duplicates and the subtler noise stay curator proposals: without a person a wrong merge would lose information silently."""
import logging

from .curator import META, NOISE_RULES, PLACEHOLDERS, _name
from .db import graph, rows

log = logging.getLogger("mimirsynth.write_quality")

_FOUND = ("MATCH (a:Entity)-[r:RELATES_TO]->(b:Entity) WHERE r.uuid IN $u "
          "RETURN r.uuid AS uuid, r.fact AS fact, r.episodes AS episodes, r.invalid_at AS invalid_at, r.expired_at AS expired_at, "
          "a.uuid AS su, a.name AS source, b.uuid AS tu, b.name AS target")
_CURRENT = ("MATCH (a:Entity)-[r:RELATES_TO]->(b:Entity) WHERE a.uuid IN $ends AND b.uuid IN $ends AND NOT r.uuid IN $new "
            "AND r.invalid_at IS NULL AND r.expired_at IS NULL RETURN r.uuid AS uuid, r.fact AS fact, a.uuid AS su, b.uuid AS tu")
# The guard repeats what `decide` checked: only an edge whose only episode is this one goes. It returns what it really deleted.
_DELETE = ("MATCH ()-[r:RELATES_TO]->() WHERE r.uuid IN $u AND size(r.episodes) = 1 AND $e IN r.episodes "
           "WITH r, r.uuid AS gone DELETE r RETURN gone")
_LINK = ("MATCH ()-[r:RELATES_TO {uuid:$u}]->() WHERE NOT $e IN coalesce(r.episodes, []) "
         "SET r.episodes = coalesce(r.episodes, []) + [$e]")
_EPISODE = ("MATCH (e:Episodic {uuid:$e}) SET e.entity_edges = [x IN coalesce(e.entity_edges, []) WHERE NOT x IN $g] + "
            "[x IN $l WHERE NOT x IN coalesce(e.entity_edges, [])]")
SAME_EPISODE = "says word for word what another fact of this episode says"
SAME_CURRENT = "says word for word what a current fact already in the brain says"
# Words of the curator's placeholder list that can also be a real thing's name («User» in a software brain, «Ella» a first name,
# «LE» Let's Encrypt): at write time, with no person to look, they are left to the curator.
_NOT_AT_WRITE = frozenset("user the-user usuario el-usuario la le lo él ella".split())
# Only pronouns count when capitalised («It runs on…»); any other placeholder or memory word only in lower case: «Thing» (AWS IoT),
# «Episode», «Entity» or «The Graph» can be real things and stay with the curator. A name in capitals («IT») never counts.
_PRONOUNS = frozenset("it this that these those them they something someone esto eso ello ellos ellas algo alguien".split())


def same_text(text) -> str:
    """A fact's text as compared here: case, spacing and a closing full stop do not count."""
    t = " ".join(str(text or "").lower().split())
    return t[:-1].rstrip() if t.endswith(".") and not t.endswith("..") else t


def write_rule(f: dict) -> str | None:
    """The curator's sure noise rules as applied with no person (#458): an end that is a placeholder or the memory itself, written in
    lower case (a pronoun may also be capitalised), never in capitals nor one of the names that can be a real thing."""
    for end in (f.get("source"), f.get("target")):
        raw = " ".join(str(end or "").split())
        n = _name(raw)
        if n in _NOT_AT_WRITE or not (raw == raw.lower() or (n in _PRONOUNS and raw == raw.capitalize())):
            continue
        if n in PLACEHOLDERS:
            return "placeholder"
        if n in META:
            return "meta"
    return None


def _pair(f: dict) -> tuple[str, str]:
    return tuple(sorted((str(f["su"]), str(f["tu"]))))


def _old(f: dict) -> bool:
    return bool(f.get("invalid_at") or f.get("expired_at"))


def new_of(found: list[dict], episode: str, created: set[str]) -> list[dict]:
    """The facts this ingestion created: graphiti created them during it and their only episode is this one. A fact graphiti resolved
    to an existing edge also gets this episode, and may have had none before (an adopted graph): the creation time tells it apart."""
    return [f for f in found if f["uuid"] in created and list(f.get("episodes") or []) == [episode]]


def decide(found: list[dict], episode: str, current: list[dict], created: set[str]) -> dict:
    """What to do with the facts of an ingest report. `found`: the report's facts as read from the graph; `current`: the current facts
    already in the brain between the ends of the new ones; `created`: the uuids graphiti created in this ingestion. Returns the uuids
    to delete, the existing facts to link the episode to, and the entries of the report (each with the uuid it removes)."""
    new = new_of(found, episode, created)
    ids = {f["uuid"] for f in new}
    # Graphiti looks for what a new fact invalidates in the whole brain, not only between its entities: when this episode invalidated
    # anything, a trivial-looking fact may be the replacement, so none is dropped and a person judges them.
    replaced = any(f["uuid"] not in ids and _old(f) for f in found)
    gone, link, collapsed, dropped = [], [], [], []
    kept: dict[tuple, str] = {}
    for f in new:
        rule = None if replaced else write_rule(f)
        if rule:
            gone.append(f["uuid"])
            dropped.append({"uuid": f["uuid"], "fact": f["fact"], "rule": rule, "why": NOISE_RULES[rule]})
            continue
        key = (*_pair(f), same_text(f["fact"]), _old(f))
        if key in kept:
            gone.append(f["uuid"])
            collapsed.append({"uuid": f["uuid"], "fact": f["fact"], "kept": kept[key], "with": "episode", "why": SAME_EPISODE})
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
            collapsed.append({"uuid": uuid, "fact": fact, "kept": match["uuid"], "with": "current", "why": SAME_CURRENT})
            for e in collapsed:
                if e["kept"] == uuid:   # its repeats end in the brain's fact too
                    e["kept"], e["with"], e["why"] = match["uuid"], "current", SAME_CURRENT
    return {"gone": gone, "link": sorted(set(link)), "collapsed": collapsed, "dropped": dropped}


def without_text(rep: dict) -> dict:
    """The ingest report with the text of the joined and dropped facts removed (forgetting an entity, #458): counts and uuids stay."""
    if not (rep.get("collapsed") or rep.get("dropped")):
        return rep
    return {**rep, **{k: [{x: y for x, y in e.items() if x != "fact"} for e in rep[k]] for k in ("collapsed", "dropped") if rep.get(k)}}


def apply(brain, rep: dict, episode: str) -> None:
    """Applies `decide` to the edges add_episode left in rep['_edges'] (and the ones it created, rep['_new_edges']), keeps in
    rep['_edges'] only the ones that stay, and adds what it did to the ingest report. A failure here never fails the ingestion."""
    created = set(rep.pop("_new_edges", None) or [])
    edges = rep.get("_edges") or []
    if not edges or not episode or not created:
        return
    try:
        g = graph(brain.graph_name)
        found = rows(g.query(_FOUND, {"u": [u for u, _ in edges]}))
        new = [f for f in new_of(found, episode, created) if not _old(f)]
        ends = sorted({str(f[k]) for f in new for k in ("su", "tu")})
        current = rows(g.query(_CURRENT, {"ends": ends, "new": [f["uuid"] for f in new]})) if ends else []
        out = decide(found, episode, current, created)
        if not out["gone"]:
            return
        for u in out["link"]:   # first the link: a failure after it leaves a copy, never a fact without its episode
            g.query(_LINK, {"u": u, "e": episode})
        gone = {r["gone"] for r in rows(g.query(_DELETE, {"u": out["gone"], "e": episode}))}
        rep["_edges"] = [(u, n) for u, n in edges if u not in gone]
        names = {n for _, n in rep["_edges"]}
        if rep.get("off_ontology"):
            rep["off_ontology"] = [n for n in rep["off_ontology"] if n in names]
        if isinstance(rep.get("edges"), int):
            rep["edges"] = max(0, rep["edges"] - len(gone))
        collapsed = [e for e in out["collapsed"] if e["uuid"] in gone]
        dropped = [e for e in out["dropped"] if e["uuid"] in gone]
        if collapsed:
            rep["collapsed"] = collapsed
        if dropped:
            rep["dropped"] = dropped
        g.query(_EPISODE, {"e": episode, "g": sorted(gone), "l": out["link"]})
    except Exception:  # noqa: BLE001 — the episode is in; this only tidies it
        log.exception("no se pudo revisar la calidad de los hechos tras ingerir")
        rep["quality_error"] = True
