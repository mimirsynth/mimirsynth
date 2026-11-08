"""Distilling repeated episodes (#297): agents write the same lesson again and again in slightly different words, and the recall spends
its budget on the repetitions. The curator's `distil` pass (off by default) finds those groups, the brain's LLM writes one short, dated
note that states the lesson, and a person decides.

- **Groups.** Episodes that mention the same entity **and** whose text is close (cosine ≥ `distil_similarity`, 0.85 by default, over
  the mean of their chunks in the episode index), with every pair of a group that close. At least `distil_min` episodes (3). The most
  specific entity first: an entity mentioned by fewer episodes names the subject better. No LLM is needed to group, so the preview
  costs nothing.
- **Cost.** One call to the brain's LLM per group, at most `distil_calls` (5) per daily run; the rest waits for the next one.
- **The proposal** (`curator.distil`) carries the note and its originals as evidence. It is **never approved on its own**: no
  auto-approval tier, no decider, no bulk approval. A person reads what the LLM wrote, one at a time.
- **The originals.** Each one is ticked «delete if the note covers it» (all by default; a curator unticks what must stay before
  approving). Once the note is ingested, an original is **covered** when every fact that came only from it is current and matches a
  fact of the note (the same two entities, and the same relation or a close text). Covered and ticked originals are deleted; the
  others stay, and the proposal says what each one adds. Deleting cannot be undone, so it happens only then.
- **Deleting an episode** removes the episode, the facts that came only from it and the entities left with nothing; a fact that other
  episodes also support stays, without the reference. (graphiti-core's `remove_episode` would also delete the facts the episode
  created first even when later episodes confirmed them.)
"""
import json
import logging
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from .deps import BrainCtx, audit, brain_access
from .models import Brain, Proposal
from .store import _factory

log = logging.getLogger("mimirsynth.distil")
router = APIRouter(prefix="/api/brains/{slug}/curator/distil")
curator = brain_access("curator")
CATEGORY = "curator.distil"
DEFAULTS = {"distil_similarity": 0.85, "distil_min": 3, "distil_calls": 5}
MAX_PER_ENTITY = 300      # the most recent episodes of an entity that are compared
MAX_GROUPS = 200
TEXT_PER_EPISODE = 1500   # characters of each original the LLM reads
SNIPPET = 300
COVER_SIMILARITY = 0.85   # a fact of the original and one of the note say the same with a different relation name


def by_hand(p) -> bool:
    """A distilled note is approved by a person, one at a time: what the LLM wrote is always read (#297)."""
    return (getattr(p, "category", None) or "") == CATEGORY


def _when(s) -> str:
    return str(s or "")


# --- grouping ---------------------------------------------------------------------------------

def groups(items: list[dict], vectors: dict[str, list[float]], threshold: float, min_size: int) -> list[tuple[list[dict], float]]:
    """Groups of `items` (in their order) where every pair is at least `threshold` close; each with its lowest pair similarity."""
    import numpy as np
    have = [i for i in items if vectors.get(i["uuid"]) is not None]
    if len(have) < min_size:
        return []
    m = np.array([vectors[i["uuid"]] for i in have], dtype=float)
    norms = np.linalg.norm(m, axis=1)
    norms[norms == 0] = 1.0
    m = m / norms[:, None]
    sim = m @ m.T
    used: set[int] = set()
    out = []
    for i in range(len(have)):
        if i in used:
            continue
        members = [i]
        for j in range(i + 1, len(have)):
            if j not in used and all(sim[j, k] >= threshold for k in members):
                members.append(j)
        if len(members) >= min_size:
            used |= set(members)
            low = min(float(sim[a, b]) for a in members for b in members if a < b)
            out.append(([have[k] for k in members], round(low, 3)))
    return out


def _vectors(brain_id: int, uuids: list[str]) -> dict[str, list[float]]:
    """The mean of each episode's chunk vectors in the episode index (none without PostgreSQL + pgvector)."""
    from . import index
    if not uuids or not index.enabled():
        return {}
    from sqlalchemy import text
    from .store import engine
    sums: dict[str, list] = {}
    with engine().connect() as c:
        for u, e in c.execute(text("SELECT episode_uuid, embedding::text FROM episode_chunks WHERE brain_id = :b AND episode_uuid = ANY(:u)"),
                              {"b": brain_id, "u": uuids}):
            v = json.loads(e)
            s = sums.setdefault(u, [[0.0] * len(v), 0])
            s[0] = [a + b for a, b in zip(s[0], v)]
            s[1] += 1
    return {u: [x / n for x in s] for u, (s, n) in sums.items()}


def _busy(db, brain_id: int) -> set[str]:
    """Episodes already in a pending distilled note, or in one a curator rejected: not proposed again."""
    out: set[str] = set()
    for d in db.scalars(select(Proposal.decision).where(Proposal.brain_id == brain_id, Proposal.category == CATEGORY,
                                                        Proposal.status.in_(("pending", "rejected")))):
        out |= {e["uuid"] for e in ((d or {}).get("curator") or {}).get("episodes", [])}
    return out


_MENTIONS = ("MATCH (e:Episodic)-[:MENTIONS]->(n:Entity) WITH n, e ORDER BY e.valid_at DESC "
             "WITH n, collect(e.uuid) AS eps WHERE size(eps) >= $min RETURN n.uuid AS uuid, n.name AS name, eps ORDER BY size(eps), n.uuid")
_EPISODES = "MATCH (e:Episodic) WHERE e.uuid IN $u RETURN e.uuid AS uuid, e.name AS name, e.content AS content, e.valid_at AS valid_at"


def find(brain_id: int, cfg: dict | None = None) -> list[dict]:
    """Findings of the distil pass: one per group, with its originals as evidence. Read-only, no LLM."""
    from . import curator as cur
    from .db import graph, rows
    with _factory()() as db:
        b = db.get(Brain, brain_id)
        cfg = cfg or cur.config(b)
        gname, busy = b.graph_name, _busy(db, brain_id)
    thr, low = float(cfg.get("distil_similarity") or DEFAULTS["distil_similarity"]), int(cfg.get("distil_min") or DEFAULTS["distil_min"])
    g = graph(gname)
    taken = set(busy)
    out = []
    for ent in rows(g.query(_MENTIONS, {"min": low})):
        eps = [u for u in ent["eps"] if u not in taken][:MAX_PER_ENTITY]
        if len(eps) < low:
            continue
        info = {r["uuid"]: r for r in rows(g.query(_EPISODES, {"u": eps}))}
        items = sorted((info[u] for u in eps if u in info), key=lambda e: (_when(e.get("valid_at")), e["uuid"]))
        for members, sim in groups(items, _vectors(brain_id, [i["uuid"] for i in items]), thr, low):
            taken |= {m["uuid"] for m in members}
            out.append({"pass": "distil", "subject": ent["name"], "relation": "", "keep": None, "replace": [], "similarity": sim,
                        "episodes": [{"uuid": m["uuid"], "name": m.get("name") or "", "valid_at": m.get("valid_at"),
                                      "text": (m.get("content") or "")[:SNIPPET]} for m in members],
                        "why": f"{len(members)} episodes about «{ent['name']}» say nearly the same (similarity ≥ {sim:g})"})
            if len(out) >= MAX_GROUPS:
                return out
    return out


# --- the note -----------------------------------------------------------------------------------

PROMPT = """You keep a team's long-term memory tidy. The notes below were saved at different times and repeat the same lesson about «{entity}».
Write ONE short note (at most five sentences) that states the lesson as it stands now, in the language of the notes.
- Keep every concrete detail that is still true: names, versions, numbers, dates, commands, paths.
- When the notes disagree, the most recent one wins; say briefly what changed and since when.
- Start with the date the lesson holds from (YYYY-MM-DD).
- Do not invent anything that is not in the notes.
Answer only with JSON: {{"title": "<at most eight words>", "note": "<the note>"}}"""


def _engine() -> dict | None:
    from .llm import resolve
    with _factory()() as db:
        return resolve(db)


def _ask(eng: dict, msgs: list[dict]) -> str:
    from .summary_review import ask
    return ask(eng, msgs)


def _parse(raw: str, entity: str) -> tuple[str, str]:
    m = re.search(r"\{.*\}", raw or "", re.S)
    if m:
        try:
            d = json.loads(m.group(0))
            return str(d.get("title") or entity).strip(), str(d.get("note") or "").strip()
        except (ValueError, AttributeError):
            pass
    return entity, (raw or "").strip()


def _latest(eps: list[dict]) -> datetime | None:
    best = None
    for e in eps:
        try:
            d = datetime.fromisoformat(str(e.get("valid_at")).replace("Z", "+00:00"))
        except ValueError:
            continue
        d = d if d.tzinfo else d.replace(tzinfo=timezone.utc)
        best = d if best is None or d > best else best
    return best


def propose(db, brain: Brain, author, f: dict) -> int | None:
    """One call to the brain's LLM for one group, and its note as a pending proposal. None when nothing came back or it was blocked."""
    from . import secretguard, usage
    from .db import graph, rows
    if usage.paused(brain.id):
        return None
    eng = _engine()
    if not eng:
        raise RuntimeError("no hay motor LLM configurado para destilar")
    full = {r["uuid"]: r for r in rows(graph(brain.graph_name).query(_EPISODES, {"u": [e["uuid"] for e in f["episodes"]]}))}
    if len(full) < len(f["episodes"]):   # an original went away since the pass read it
        return None
    notes = "\n\n".join(f"[{_when(full[e['uuid']].get('valid_at'))[:10]}] {full[e['uuid']].get('name') or ''}\n"
                        f"{(full[e['uuid']].get('content') or '')[:TEXT_PER_EPISODE]}" for e in f["episodes"])
    with usage.scope(brain.id, "curator"):
        raw = _ask(eng, [{"role": "system", "content": PROMPT.format(entity=f["subject"])}, {"role": "user", "content": notes}])
    title, note = _parse(raw, f["subject"])
    if not note:
        return None
    try:
        note, found = secretguard.guard(brain, note)
    except secretguard.Blocked:
        log.warning("la nota destilada del brain %s lleva secretos que el brain bloquea: no se propone", brain.id)
        return None
    p = Proposal(brain_id=brain.id, author_id=author.id, name=f"Curador: destila «{title[:200]}»"[:255], body=note, source="text",
                 status="pending", kind="memory", source_description="curator: distil", category=CATEGORY, related_verdict="new",
                 reference_time=_latest(f["episodes"]), secret_findings=found or None,
                 decision={"curator": {"pass": "distil", "why": f["why"], "keep": None, "entity": f["subject"], "similarity": f.get("similarity"),
                                       "episodes": f["episodes"], "delete": [e["uuid"] for e in f["episodes"]]}})
    db.add(p)
    db.commit()
    audit(db, None, "proposal.submit", brain, id=p.id, status="pending", by="curator", category=CATEGORY)
    return p.id


# --- after the note is ingested ---------------------------------------------------------------

_EDGES = ("MATCH (a:Entity)-[r:RELATES_TO]->(b:Entity) WHERE {where} RETURN r.uuid AS uuid, r.name AS name, r.fact AS fact, "
          "a.uuid AS s, b.uuid AS t, r.fact_embedding AS e, r.invalid_at AS invalid_at, r.expired_at AS expired_at")


def covered(f: dict, note: list[dict]) -> bool:
    """A fact of an original says nothing the note does not: it is current and a fact of the note links the same two entities with
    the same relation or a close text."""
    from .health import _cosine
    from .vocab import canon_rel
    if f.get("invalid_at") or f.get("expired_at"):
        return False   # history the note does not keep
    for n in note:
        if {n["s"], n["t"]} != {f["s"], f["t"]}:
            continue
        if canon_rel(n["name"]) == canon_rel(f["name"]):
            return True
        if n.get("e") is not None and f.get("e") is not None and _cosine(n["e"], f["e"]) >= COVER_SIMILARITY:
            return True
    return False


def delete_episode(graph, brain_id: int, uuid: str) -> None:
    """The episode, the facts only it supports and the entities left with nothing; shared facts lose only the reference."""
    from .db import rows
    mentioned = [r["uuid"] for r in rows(graph.query("MATCH (:Episodic {uuid:$o})-[:MENTIONS]->(n:Entity) RETURN n.uuid AS uuid", {"o": uuid}))]
    graph.query("MATCH ()-[r:RELATES_TO]->() WHERE size(r.episodes) = 1 AND $o IN r.episodes DELETE r", {"o": uuid})
    graph.query("MATCH ()-[r:RELATES_TO]->() WHERE $o IN r.episodes SET r.episodes = [x IN r.episodes WHERE x <> $o]", {"o": uuid})
    graph.query("MATCH (e:Episodic {uuid:$o}) DETACH DELETE e", {"o": uuid})
    if mentioned:
        graph.query("MATCH (n:Entity) WHERE n.uuid IN $m OPTIONAL MATCH (n)-[x]-() WITH n, count(x) AS c WHERE c = 0 DELETE n", {"m": mentioned})
    from . import index
    if index.enabled():
        from sqlalchemy import text
        from .store import engine
        with engine().begin() as c:
            c.execute(text("DELETE FROM episode_chunks WHERE brain_id = :b AND episode_uuid = :u"), {"b": brain_id, "u": uuid})


def finish(db, brain: Brain, p: Proposal) -> dict:
    """Once the note is in the graph: which originals it covers, and the covered ones a curator left ticked, deleted."""
    from .db import graph, rows
    g = graph(brain.graph_name)
    cur = (p.decision or {}).get("curator") or {}
    note = rows(g.query(_EDGES.format(where="$n IN r.episodes"), {"n": p.episode_uuid}))
    ticked, out = set(cur.get("delete") or []), {"deleted": [], "kept": []}
    for ep in cur.get("episodes") or []:
        u = ep["uuid"]
        if not rows(g.query("MATCH (e:Episodic {uuid:$o}) RETURN e.uuid AS uuid", {"o": u})):
            out["kept"].append({"uuid": u, "name": ep.get("name"), "why": "gone"})
            continue
        own = rows(g.query(_EDGES.format(where="size(r.episodes) = 1 AND $o IN r.episodes"), {"o": u}))
        more = [f["fact"] for f in own if not covered(f, note)]
        if more:
            out["kept"].append({"uuid": u, "name": ep.get("name"), "why": "says_more", "facts": more[:10]})
        elif u not in ticked:
            out["kept"].append({"uuid": u, "name": ep.get("name"), "why": "unticked"})
        else:
            delete_episode(g, brain.id, u)
            out["deleted"].append({"uuid": u, "name": ep.get("name"), "facts": len(own)})
            audit(db, None, "episode.deleted", brain, uuid=u, by="curator.distil", proposal=p.id, facts=len(own))
    return out


# --- API --------------------------------------------------------------------------------------

class DistilIn(BaseModel):
    delete: list[str] = Field(default_factory=list, max_length=500, description="the originals to delete once the note is ingested, if it covers them")


@router.put("/{pid}")
def set_delete(pid: int, body: DistilIn, ctx: BrainCtx = Depends(curator)):
    """Which originals of a pending distilled note may be deleted once it is ingested (only those the note covers will be)."""
    p = ctx.db.get(Proposal, pid)
    if not p or p.brain_id != ctx.brain.id or not by_hand(p):
        raise HTTPException(404, "no es una nota destilada de este brain")
    if p.status != "pending":
        raise HTTPException(409, "la propuesta ya está decidida")
    cur = dict((p.decision or {}).get("curator") or {})
    known = [e["uuid"] for e in cur.get("episodes") or []]
    if not set(body.delete) <= set(known):
        raise HTTPException(422, "solo se pueden marcar sus episodios originales")
    cur["delete"] = [u for u in known if u in set(body.delete)]
    p.decision = {**(p.decision or {}), "curator": cur}
    ctx.db.commit()
    audit(ctx.db, ctx.user, "proposal.distil", ctx.brain, id=p.id, delete=len(cur["delete"]), keep=len(known) - len(cur["delete"]))
    return {"delete": cur["delete"]}
