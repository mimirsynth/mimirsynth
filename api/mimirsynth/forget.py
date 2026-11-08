"""Right to be forgotten (#134), first part: the **report**. Before anything is deleted, the brain's owner (or an instance administrator)
asks what deleting an entity, a person for instance, would touch, layer by layer, and what would stay to review. Nothing is changed.

- **What is looked for.** The entity itself (by its uuid) and its name, its aliases in the graph and the aliases the request adds (an
  email, a nickname). Text is matched as whole words, ignoring case and accents.
- **Layers and what deleting would do there**, as agreed on the issue:
  - the graph: the entity and its facts (delete); the episodes that mention it (delete, and the brain's LLM offers a rewrite without
    the person as a new proposal); facts of other entities, summaries of other entities and entities named like it (to review: never
    deleted on their own);
  - the graph snapshots kept to undo an entity merge (cleaned inside, so the undo keeps working);
  - the episode index and the documents' chunks (the episodes' chunks go with them; a document that mentions it is blocked from
    re-indexing until it changes at its source);
  - the database: proposals (their text purged), the recall sample, recall logs and their ratings, summary suggestions, jobs,
    notifications, webhook events and the audit log (cleaned), reference queries (to review), and what hangs from its facts
    (confirmations, probes, recall dates, archive);
  - outside MimirSynth: backups, application logs and other systems, which this cannot reach.
- **Who.** The brain's owner or an instance administrator, from a session (not with an API token). The audit log records that a
  report was made and its counts per layer, never names or text.
"""
import json
import re
import unicodedata
from collections.abc import Iterable

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from .deps import BrainCtx, audit, owner_of_brain

router = APIRouter(prefix="/api/brains/{slug}/forget")
MAX_ITEMS = 200       # items listed per layer to review
MAX_ROWS = 200_000    # rows read per table or graph query
MIN_TERM = 3


def norm(s) -> str:
    """Lower case without accents, for matching."""
    return "".join(c for c in unicodedata.normalize("NFKD", str(s or "")) if not unicodedata.combining(c)).casefold()


class Matcher:
    """Whole-word, case- and accent-insensitive search for a set of terms."""

    def __init__(self, terms: Iterable[str]):
        self.terms = sorted({" ".join(norm(t).split()) for t in terms if len(" ".join(norm(t).split())) >= MIN_TERM}, key=len, reverse=True)
        self.rx = re.compile(r"(?<!\w)(" + "|".join(re.escape(t).replace(r"\ ", r"\s+") for t in self.terms) + r")(?!\w)") if self.terms else None

    def __call__(self, text) -> bool:
        if not self.rx or text is None:
            return False
        if not isinstance(text, str):
            text = json.dumps(text, ensure_ascii=False, default=str)
        return bool(self.rx.search(norm(text)))

    def like(self) -> list[str]:
        """SQL LIKE patterns that every match satisfies (letters that may carry an accent become `_`), to narrow the rows read."""
        return ["%" + re.sub(r"[aeiouyncs%\s]", "_", t) + "%" for t in self.terms]


# --- the layers -----------------------------------------------------------------------------

def _layer(key: str, where: str, action: str, count: int, **extra) -> dict:
    return {"key": key, "where": where, "action": action, "count": count, **extra}


def _graph_layers(g, uuid: str, m: Matcher) -> tuple[list[dict], set[str], set[str]]:
    """The entity, its facts, the episodes that mention it and what of other entities names it. Returns the layers, the episodes and
    the entity's facts (their uuids)."""
    from .db import rows
    own = rows(g.query("MATCH (n:Entity {uuid:$u})-[r:RELATES_TO]-(:Entity) RETURN DISTINCT r.uuid AS uuid, "
                       "r.invalid_at IS NULL AND r.expired_at IS NULL AS current", {"u": uuid}))
    facts = {r["uuid"] for r in own}
    mentioned = {r["uuid"] for r in rows(g.query("MATCH (e:Episodic)-[:MENTIONS]->(:Entity {uuid:$u}) RETURN e.uuid AS uuid", {"u": uuid}))}
    texted = {r["uuid"] for r in rows(g.query("MATCH (e:Episodic) RETURN e.uuid AS uuid, e.name AS name, e.content AS content LIMIT $n",
                                                {"n": MAX_ROWS})) if m(r["name"]) or m(r["content"])}
    episodes = mentioned | texted
    other_facts, entities, summaries = [], [], []
    for r in rows(g.query("MATCH (a:Entity)-[r:RELATES_TO]->(b:Entity) WHERE a.uuid <> $u AND b.uuid <> $u "
                          "RETURN r.uuid AS uuid, r.fact AS fact, a.name AS source, b.name AS target LIMIT $n", {"u": uuid, "n": MAX_ROWS})):
        if m(r["fact"]):
            other_facts.append(r)
    for r in rows(g.query("MATCH (n:Entity) WHERE n.uuid <> $u RETURN n.uuid AS uuid, n.name AS name, coalesce(n.aliases, []) AS aliases, "
                          "coalesce(n.summary, '') AS summary LIMIT $n", {"u": uuid, "n": MAX_ROWS})):
        if m(r["name"]) or any(m(a) for a in r["aliases"] or []):
            entities.append({"uuid": r["uuid"], "name": r["name"]})
        elif m(r["summary"]):
            summaries.append({"uuid": r["uuid"], "name": r["name"]})
    layers = [
        _layer("entity", "graph", "delete", 1, facts=len(facts), current=sum(1 for r in own if r["current"])),
        _layer("episodes", "graph", "delete", len(episodes), mentions=len(mentioned), text=len(texted - mentioned)),
        _layer("other_facts", "graph", "review", len(other_facts), items=other_facts[:MAX_ITEMS]),
        _layer("other_summaries", "graph", "review", len(summaries), items=summaries[:MAX_ITEMS]),
        _layer("similar_entities", "graph", "review", len(entities), items=entities[:MAX_ITEMS]),
    ]
    return layers, episodes, facts


def _snapshots(graph_name: str, uuid: str, m: Matcher) -> dict:
    """The graph copies an entity merge keeps to undo it: which still hold the entity or an episode that names it."""
    from .db import client, rows
    hit = []
    for name in sorted(x for x in client().list_graphs() if x.startswith(f"_snap_{graph_name}_")):
        s = client().select_graph(name)
        has = bool(rows(s.query("MATCH (n:Entity {uuid:$u}) RETURN n.uuid AS uuid", {"u": uuid})))
        eps = sum(1 for r in rows(s.query("MATCH (e:Episodic) RETURN e.name AS name, e.content AS content LIMIT $n", {"n": MAX_ROWS}))
                  if m(r["name"]) or m(r["content"]))
        if has or eps:
            hit.append({"name": name, "entity": has, "episodes": eps})
    return _layer("snapshots", "snapshots", "clean", len(hit), items=hit)


def _scan(db, model, brain_id: int, cols: list[str], m: Matcher, text_cols: list[str] | None = None) -> list:
    """Rows of a table of the brain whose columns name it. Text columns narrow the rows in SQL first; JSON ones are read whole."""
    from sqlalchemy import or_
    q = select(model).where(model.brain_id == brain_id)
    if text_cols and not set(cols) - set(text_cols):
        q = q.where(or_(*[getattr(model, c).ilike(p) for c in text_cols for p in m.like()]))
    out = []
    for row in db.scalars(q.limit(MAX_ROWS)):
        if any(m(getattr(row, c)) for c in cols):
            out.append(row)
    return out


def _index_layers(db, brain_id: int, episodes: set[str], m: Matcher) -> list[dict]:
    from . import index
    if not index.enabled():
        return [_layer("episode_chunks", "index", "delete", 0, unavailable=True), _layer("documents", "index", "block", 0, unavailable=True)]
    from sqlalchemy import or_, text
    from .docindex import DocChunk
    from .models import Document
    from .store import engine
    with engine().connect() as c:
        chunks = c.execute(text("SELECT count(*) FROM episode_chunks WHERE brain_id = :b AND episode_uuid = ANY(:u)"),
                           {"b": brain_id, "u": sorted(episodes)}).scalar() if episodes else 0
    docs: dict[int, int] = {}
    q = select(DocChunk.document_id, DocChunk.text).where(DocChunk.brain_id == brain_id, or_(*[DocChunk.text.ilike(p) for p in m.like()]))
    for did, txt in db.execute(q.limit(MAX_ROWS)):
        if m(txt):
            docs[did] = docs.get(did, 0) + 1
    for d in db.scalars(select(Document).where(Document.brain_id == brain_id)):
        if d.id not in docs and (m(d.title) or m(d.filename)):
            docs[d.id] = 0
    titles = {d.id: d.title or d.filename for d in db.scalars(select(Document).where(Document.id.in_(list(docs))))} if docs else {}
    return [_layer("episode_chunks", "index", "delete", int(chunks or 0)),
            _layer("documents", "index", "block", len(docs), chunks=sum(docs.values()),
                   items=[{"id": i, "title": titles.get(i, ""), "chunks": n} for i, n in list(docs.items())[:MAX_ITEMS]])]


def _db_layers(db, brain_id: int, facts: set[str], m: Matcher) -> list[dict]:
    from sqlalchemy import func
    from .models import (Audit, FactArchive, FactConfirmation, FactProbe, FactRecall, Job, Notification, Proposal, RecallLog, RecallRating,
                         RecallSample, RefQuery, ReplayRun, SummarySuggestion, WebhookEvent)
    logs = _scan(db, RecallLog, brain_id, ["query_text"], m, ["query_text"])
    ratings = db.scalar(select(func.count()).select_from(RecallRating).where(RecallRating.log_id.in_([x.id for x in logs]))) if logs else 0
    hanging = 0
    if facts:
        for model in (FactConfirmation, FactProbe, FactRecall, FactArchive):
            hanging += db.scalar(select(func.count()).select_from(model).where(model.brain_id == brain_id, model.fact_uuid.in_(sorted(facts)))) or 0
    probes = [p for p in _scan(db, FactProbe, brain_id, ["evidence", "value"], m) if p.fact_uuid not in facts]
    refs = _scan(db, RefQuery, brain_id, ["query", "expect", "avoid", "note"], m)
    return [
        _layer("proposals", "database", "purge", len(_scan(db, Proposal, brain_id, ["name", "body", "review_note"], m, ["name", "body", "review_note"]))),
        _layer("recall_samples", "database", "delete", len(_scan(db, RecallSample, brain_id, ["query"], m, ["query"]))),
        _layer("recall_logs", "database", "delete", len(logs), ratings=int(ratings or 0)),
        _layer("replay_runs", "database", "clean", len(_scan(db, ReplayRun, brain_id, ["results"], m))),
        _layer("summary_suggestions", "database", "delete",
               len(_scan(db, SummarySuggestion, brain_id, ["name", "current", "proposed", "applied"], m, ["name", "current", "proposed", "applied"]))),
        _layer("jobs", "database", "delete", len(_scan(db, Job, brain_id, ["title", "params", "log", "error", "result"], m))),
        _layer("notifications", "database", "delete", len(_scan(db, Notification, brain_id, ["title", "body"], m, ["title", "body"]))),
        _layer("webhook_events", "database", "clean", len(_scan(db, WebhookEvent, brain_id, ["title"], m, ["title"]))),
        _layer("audit", "database", "clean", len(_scan(db, Audit, brain_id, ["detail"], m))),
        _layer("fact_records", "database", "delete", hanging + len(probes)),
        _layer("ref_queries", "database", "review", len(refs), items=[{"id": r.id, "query": r.query} for r in refs[:MAX_ITEMS]]),
    ]


OUTSIDE = [_layer("backups", "outside", "outside", 0), _layer("logs", "outside", "outside", 0), _layer("other_systems", "outside", "outside", 0)]


def report(db, brain, uuid: str, aliases: list[str]) -> dict:
    from .db import graph, rows
    g = graph(brain.graph_name)
    found = rows(g.query("MATCH (n:Entity {uuid:$u}) RETURN n.name AS name, coalesce(n.aliases, []) AS aliases", {"u": uuid}))
    if not found:
        raise HTTPException(404, "la entidad no existe en este brain")
    e = found[0]
    m = Matcher([e["name"], *(e["aliases"] or []), *aliases])
    if not m.terms:
        raise HTTPException(422, "hace falta al menos un nombre o alias de 3 caracteres o más")
    graph_layers, episodes, facts = _graph_layers(g, uuid, m)
    layers = [*graph_layers, _snapshots(brain.graph_name, uuid, m), *_index_layers(db, brain.id, episodes, m), *_db_layers(db, brain.id, facts, m), *OUTSIDE]
    return {"entity": {"uuid": uuid, "name": e["name"], "aliases": e["aliases"] or []}, "terms": m.terms, "layers": layers}


# --- API --------------------------------------------------------------------------------------

class ReportIn(BaseModel):
    entity: str = Field(min_length=1, max_length=64)
    aliases: list[str] = Field(default_factory=list, max_length=20, description="other names the person goes by: an email, a nickname")


@router.post("/report")
def make_report(body: ReportIn, request: Request, ctx: BrainCtx = Depends(owner_of_brain)):
    """What deleting an entity would touch, layer by layer, and what would stay to review. Read-only."""
    if getattr(request.state, "token", None) is not None:
        raise HTTPException(403, "el derecho al olvido se pide desde una sesión, no con un token")
    out = report(ctx.db, ctx.brain, body.entity, [a for a in body.aliases if a.strip()])
    audit(ctx.db, ctx.user, "forget.report", ctx.brain, entity=body.entity, counts={x["key"]: x["count"] for x in out["layers"]})
    return out
