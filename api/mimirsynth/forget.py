"""Right to be forgotten (#134): deleting an entity, a person for instance, with everything that names it, after a **report** that says
what each layer would lose and what stays to review.

- **What is looked for.** The entity itself (by its uuid) and its name, its aliases in the graph and the aliases the request adds (an
  email, a nickname). Text is matched as whole words, ignoring case and accents. The report and the deletion select the same things.
- **Layers and what deleting does there**, as agreed on the issue:
  - the graph: the entity, its facts and the duplicates merged into it (deleted); the episodes that mention it (deleted; when the
    rest is worth keeping the brain's LLM writes it again without the person, as a new proposal a curator decides); facts of other
    entities, summaries of other entities and entities named like it (to review: never deleted on their own);
  - the graph snapshots kept to undo an entity merge (cleaned inside: the same deletions, so the undo keeps working);
  - the episode index and the documents' chunks (the episodes' chunks go with them; a document that names it loses its chunks and is
    **blocked**: it is not indexed again until it changes at its source, or an administrator re-indexes it on purpose);
  - the database: proposals (their text purged), the recall sample, recall logs and their ratings, summary and type suggestions,
    finished jobs and notifications (deleted); replays of the sample, reference-query runs, curator runs, webhook events, the
    vocabulary history and the audit log (cleaned: what names it becomes «[olvidado]»); reference queries (to review); what hangs
    from its facts (confirmations, probes, recall dates, archive: deleted);
  - outside MimirSynth: backups, application logs and other systems, which this cannot reach.
- **Who.** The brain's owner or an instance administrator, from a session (not with an API token). Deleting asks for the entity's
  name typed again, runs as a job, and wipes the job's parameters when it ends. The audit log records the report and the deletion with
  the entity's id and the counts per layer, never names or text.
"""
import json
import logging
import re
import unicodedata
from collections.abc import Iterable
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import delete, select

from . import jobs
from .deps import BrainCtx, audit, owner_of_brain

log = logging.getLogger("mimirsynth.forget")
router = APIRouter(prefix="/api/brains/{slug}/forget")
KIND = "forget.run"
MAX_ITEMS = 200       # items listed per layer to review
MAX_ROWS = 200_000    # rows read per table or graph query
MAX_REWRITES = 50     # episodes the LLM writes again in one deletion; the rest are deleted without a rewrite
MIN_TERM = 3
GONE = "[olvidado]"


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

    def scrub(self, value):
        """The value with every string that names it replaced by GONE (inside lists and dicts too)."""
        if isinstance(value, str):
            return GONE if self(value) else value
        if isinstance(value, list):
            return [self.scrub(v) for v in value]
        if isinstance(value, dict):
            return {k: self.scrub(v) for k, v in value.items()}
        return value


# --- what is selected -------------------------------------------------------------------------

def _layer(key: str, where: str, action: str, count: int, **extra) -> dict:
    return {"key": key, "where": where, "action": action, "count": count, **extra}


def _graph_targets(g, uuid: str, m: Matcher) -> dict:
    """In one graph: the entity's facts, the duplicates merged into it, the episodes that mention or name it, and what of other
    entities names it."""
    from .db import rows
    own = rows(g.query("MATCH (n:Entity {uuid:$u})-[r:RELATES_TO]-() RETURN DISTINCT r.uuid AS uuid, "
                       "r.invalid_at IS NULL AND r.expired_at IS NULL AS current", {"u": uuid}))
    merged = {r["uuid"] for r in rows(g.query("MATCH (d:Merged) RETURN d.uuid AS uuid, d.name AS name, d.merged_into AS into LIMIT $n",
                                                {"n": MAX_ROWS})) if r["into"] == uuid or m(r["name"])}
    mentioned = {r["uuid"] for r in rows(g.query("MATCH (e:Episodic)-[:MENTIONS]->(n) WHERE n.uuid = $u OR n.uuid IN $d RETURN e.uuid AS uuid",
                                                 {"u": uuid, "d": sorted(merged)}))}
    texted = {r["uuid"] for r in rows(g.query("MATCH (e:Episodic) RETURN e.uuid AS uuid, e.name AS name, e.content AS content LIMIT $n",
                                                {"n": MAX_ROWS})) if m(r["name"]) or m(r["content"])}
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
    return {"facts": {r["uuid"] for r in own}, "current": sum(1 for r in own if r["current"]), "merged": merged,
            "mentioned": mentioned, "texted": texted - mentioned, "episodes": mentioned | texted,
            "other_facts": other_facts, "summaries": summaries, "entities": entities}


def _snapshot_names(graph_name: str) -> list[str]:
    from .db import client
    return sorted(x for x in client().list_graphs() if x.startswith(f"_snap_{graph_name}_"))


def _snapshots(graph_name: str, uuid: str, m: Matcher) -> list[dict]:
    """The graph copies an entity merge keeps to undo it that still hold the entity, a duplicate merged into it or an episode naming it."""
    from .db import client
    hit = []
    for name in _snapshot_names(graph_name):
        t = _graph_targets(client().select_graph(name), uuid, m)
        has = bool(t["facts"]) or _exists(client().select_graph(name), uuid)
        if has or t["episodes"] or t["merged"]:
            hit.append({"name": name, "entity": has, "episodes": len(t["episodes"])})
    return hit


def _exists(g, uuid: str) -> bool:
    from .db import rows
    return bool(rows(g.query("MATCH (n:Entity {uuid:$u}) RETURN n.uuid AS uuid", {"u": uuid})))


def _scan(db, model, brain_id: int, cols: list[str], m: Matcher, text_cols: list[str] | None = None) -> list:
    """Rows of a table of the brain whose columns name it. Text columns narrow the rows in SQL first; JSON ones are read whole."""
    from sqlalchemy import or_
    q = select(model).where(model.brain_id == brain_id)
    if text_cols and not set(cols) - set(text_cols):
        q = q.where(or_(*[getattr(model, c).ilike(p) for c in text_cols for p in m.like()]))
    return [row for row in db.scalars(q.limit(MAX_ROWS)) if any(m(getattr(row, c)) for c in cols)]


def _documents(db, brain_id: int, m: Matcher) -> dict[int, int]:
    """Documents of the brain whose chunks, title or file name name it, with how many chunks do (needs the document index)."""
    from sqlalchemy import or_
    from .docindex import DocChunk
    from .models import Document
    docs: dict[int, int] = {}
    q = select(DocChunk.document_id, DocChunk.text).where(DocChunk.brain_id == brain_id, or_(*[DocChunk.text.ilike(p) for p in m.like()]))
    for did, txt in db.execute(q.limit(MAX_ROWS)):
        if m(txt):
            docs[did] = docs.get(did, 0) + 1
    for d in db.scalars(select(Document).where(Document.brain_id == brain_id, Document.status != "deleted")):
        if d.id not in docs and (m(d.title) or m(d.filename)):
            docs[d.id] = 0
    return docs


def _db_targets(db, brain_id: int, facts: set[str], m: Matcher) -> dict:
    from .models import (Audit, CuratorRun, FactArchive, FactConfirmation, FactProbe, FactRecall, Job, Notification, Proposal, RecallLog,
                         RecallSample, RefQuery, RefRun, ReplayRun, RetypeSuggestion, SummarySuggestion, VocabOp, WebhookEvent)
    hanging = []
    if facts:
        for model in (FactConfirmation, FactProbe, FactRecall, FactArchive):
            hanging += list(db.scalars(select(model).where(model.brain_id == brain_id, model.fact_uuid.in_(sorted(facts)))))
    hanging += [p for p in _scan(db, FactProbe, brain_id, ["evidence", "value"], m) if p.fact_uuid not in facts]
    return {
        "proposals": _scan(db, Proposal, brain_id, ["name", "body", "review_note"], m, ["name", "body", "review_note"]),
        "recall_samples": _scan(db, RecallSample, brain_id, ["query"], m, ["query"]),
        "recall_logs": _scan(db, RecallLog, brain_id, ["query_text"], m, ["query_text"]),
        "replay_runs": _scan(db, ReplayRun, brain_id, ["results"], m),
        "ref_runs": _scan(db, RefRun, brain_id, ["results"], m),
        "curator_runs": _scan(db, CuratorRun, brain_id, ["findings", "error"], m),
        "summary_suggestions": _scan(db, SummarySuggestion, brain_id, ["name", "current", "proposed", "applied"], m,
                                     ["name", "current", "proposed", "applied"]),
        "retype_suggestions": _scan(db, RetypeSuggestion, brain_id, ["name"], m, ["name"]),
        "jobs": _scan(db, Job, brain_id, ["title", "params", "log", "error", "result"], m),
        "notifications": _scan(db, Notification, brain_id, ["title", "body"], m, ["title", "body"]),
        "webhook_events": _scan(db, WebhookEvent, brain_id, ["title"], m, ["title"]),
        "vocab_history": _scan(db, VocabOp, brain_id, ["summary", "detail"], m),
        "audit": [a for a in _scan(db, Audit, brain_id, ["detail"], m) if a.action not in ("forget.report", "forget.run")],
        "fact_records": hanging,
        "ref_queries": _scan(db, RefQuery, brain_id, ["query", "expect", "avoid", "note"], m),
    }


DB_ACTIONS = {"proposals": "purge", "recall_samples": "delete", "recall_logs": "delete", "replay_runs": "clean", "ref_runs": "clean",
              "curator_runs": "clean", "summary_suggestions": "delete", "retype_suggestions": "delete", "jobs": "delete",
              "notifications": "delete", "webhook_events": "clean", "vocab_history": "clean", "audit": "clean", "fact_records": "delete",
              "ref_queries": "review"}
OUTSIDE = [_layer("backups", "outside", "outside", 0), _layer("logs", "outside", "outside", 0), _layer("other_systems", "outside", "outside", 0)]


def select_all(db, brain, uuid: str, aliases: list[str]) -> tuple[dict, Matcher, dict, dict, dict[int, int]]:
    """The entity, the matcher and what each place holds: (entity, matcher, graph targets, database targets, documents)."""
    from . import index
    from .db import graph, rows
    g = graph(brain.graph_name)
    found = rows(g.query("MATCH (n:Entity {uuid:$u}) RETURN n.name AS name, coalesce(n.aliases, []) AS aliases", {"u": uuid}))
    if not found:
        raise HTTPException(404, "la entidad no existe en este brain")
    e = found[0]
    m = Matcher([e["name"], *(e["aliases"] or []), *aliases])
    if not m.terms:
        raise HTTPException(422, "hace falta al menos un nombre o alias de 3 caracteres o más")
    gt = _graph_targets(g, uuid, m)
    docs = _documents(db, brain.id, m) if index.enabled() else {}
    return {"uuid": uuid, "name": e["name"], "aliases": e["aliases"] or []}, m, gt, _db_targets(db, brain.id, gt["facts"], m), docs


def report(db, brain, uuid: str, aliases: list[str]) -> dict:
    from . import index
    from .models import Document, RecallRating
    from sqlalchemy import func
    entity, m, gt, dt, docs = select_all(db, brain, uuid, aliases)
    layers = [
        _layer("entity", "graph", "delete", 1, facts=len(gt["facts"]), current=gt["current"], merged=len(gt["merged"])),
        _layer("episodes", "graph", "delete", len(gt["episodes"]), mentions=len(gt["mentioned"]), text=len(gt["texted"])),
        _layer("other_facts", "graph", "review", len(gt["other_facts"]), items=gt["other_facts"][:MAX_ITEMS]),
        _layer("other_summaries", "graph", "review", len(gt["summaries"]), items=gt["summaries"][:MAX_ITEMS]),
        _layer("similar_entities", "graph", "review", len(gt["entities"]), items=gt["entities"][:MAX_ITEMS]),
    ]
    snaps = _snapshots(brain.graph_name, uuid, m)
    layers.append(_layer("snapshots", "snapshots", "clean", len(snaps), items=snaps))
    if index.enabled():
        from sqlalchemy import text
        from .store import engine
        with engine().connect() as c:
            chunks = c.execute(text("SELECT count(*) FROM episode_chunks WHERE brain_id = :b AND episode_uuid = ANY(:u)"),
                               {"b": brain.id, "u": sorted(gt["episodes"])}).scalar() if gt["episodes"] else 0
        titles = {d.id: d.title or d.filename for d in db.scalars(select(Document).where(Document.id.in_(list(docs))))} if docs else {}
        layers += [_layer("episode_chunks", "index", "delete", int(chunks or 0)),
                   _layer("documents", "index", "block", len(docs), chunks=sum(docs.values()),
                          items=[{"id": i, "title": titles.get(i, ""), "chunks": n} for i, n in list(docs.items())[:MAX_ITEMS]])]
    else:
        layers += [_layer("episode_chunks", "index", "delete", 0, unavailable=True), _layer("documents", "index", "block", 0, unavailable=True)]
    ratings = db.scalar(select(func.count()).select_from(RecallRating).where(RecallRating.log_id.in_([x.id for x in dt["recall_logs"]]))) \
        if dt["recall_logs"] else 0
    for key, rows_ in dt.items():
        extra = {"ratings": int(ratings or 0)} if key == "recall_logs" else {}
        if key == "ref_queries":
            extra = {"items": [{"id": r.id, "query": r.query} for r in rows_[:MAX_ITEMS]]}
        layers.append(_layer(key, "database", DB_ACTIONS[key], len(rows_), **extra))
    return {"entity": entity, "terms": m.terms, "layers": [*layers, *OUTSIDE]}


# --- deleting ---------------------------------------------------------------------------------

def delete_episode(graph, uuid: str) -> None:
    """The episode, the facts only it supports and the entities left with nothing; a fact other episodes support loses the reference.
    (graphiti-core's `remove_episode` would also delete the facts it created first even when later episodes support them.)"""
    from .db import rows
    mentioned = [r["uuid"] for r in rows(graph.query("MATCH (:Episodic {uuid:$o})-[:MENTIONS]->(n:Entity) RETURN n.uuid AS uuid", {"o": uuid}))]
    graph.query("MATCH ()-[r:RELATES_TO]->() WHERE size(r.episodes) = 1 AND $o IN r.episodes DELETE r", {"o": uuid})
    graph.query("MATCH ()-[r:RELATES_TO]->() WHERE $o IN r.episodes SET r.episodes = [x IN r.episodes WHERE x <> $o]", {"o": uuid})
    graph.query("MATCH (e:Episodic {uuid:$o}) DETACH DELETE e", {"o": uuid})
    if mentioned:
        graph.query("MATCH (n:Entity) WHERE n.uuid IN $m OPTIONAL MATCH (n)-[x]-() WITH n, count(x) AS c WHERE c = 0 DELETE n", {"m": mentioned})


def _forget_in(g, uuid: str, t: dict) -> None:
    """In one graph (the brain's or a snapshot): the episodes, the entity and the duplicates merged into it."""
    for ep in sorted(t["episodes"]):
        delete_episode(g, ep)
    g.query("MATCH (n) WHERE n.uuid = $u OR n.uuid IN $d DETACH DELETE n", {"u": uuid, "d": sorted(t["merged"])})


REWRITE = """Below is a note from a team's memory. Write it again without any information about the person or thing called: {names}.
Remove every mention of them, including what only makes sense about them; keep everything else as it is, in the same language.
If nothing useful is left, answer exactly EMPTY."""


def _rewrite(eng: dict | None, m: Matcher, name: str, content: str) -> str | None:
    """The episode written again without the entity, or None (nothing left, no engine, or it still names it)."""
    if not eng or not (content or "").strip():
        return None
    from .summary_review import ask
    text = (ask(eng, [{"role": "system", "content": REWRITE.format(names=", ".join(f"«{x}»" for x in m.terms))},
                      {"role": "user", "content": content[:6000]}]) or "").strip()
    if not text or text.upper().startswith("EMPTY") or m(text):
        return None
    return text


def run(brain_id: int, uuid: str, aliases: list[str], user_id: int | None, ctx=None) -> dict:
    """Deletes the entity and everything that names it, layer by layer. Returns the counts per layer (never names or text)."""
    from . import index, secretguard, usage
    from .db import client, graph, rows
    from .models import Brain, Document, NotifyDelivery, Proposal, RecallRating, User
    from .store import _factory
    out: dict[str, dict] = {}
    with _factory()() as db:
        brain = db.get(Brain, brain_id)
        entity, m, gt, dt, docs = select_all(db, brain, uuid, aliases)
        g = graph(brain.graph_name)
        # 1. the episodes the LLM can write again without the entity, as new proposals (before they go)
        eng = None
        if not usage.paused(brain.id):
            from .llm import resolve
            eng = resolve(db)
        author = db.get(User, user_id) if user_id else None
        rewritten = failed = 0
        eps = rows(g.query("MATCH (e:Episodic) WHERE e.uuid IN $u RETURN e.uuid AS uuid, e.name AS name, e.content AS content, "
                           "e.valid_at AS valid_at", {"u": sorted(gt["episodes"])})) if gt["episodes"] else []
        for i, e in enumerate(eps):
            if ctx:
                ctx.check()
                ctx.progress(i, len(eps), "episodios")
            if i >= MAX_REWRITES or not author:
                continue
            try:
                with usage.scope(brain.id, "forget"):
                    text = _rewrite(eng, m, e["name"], e["content"])
            except Exception:  # noqa: BLE001  (the episode is deleted anyway; it simply has no rewrite)
                log.warning("no se pudo reescribir un episodio del brain %s", brain.id, exc_info=True)
                failed += 1
                continue
            if not text:
                continue
            try:
                text, found = secretguard.guard(brain, text)
            except secretguard.Blocked:
                failed += 1
                continue
            name = "Reescrito sin datos personales" if m(e["name"]) else f"Reescrito sin datos personales: {e['name']}"[:255]
            when = None
            try:
                when = datetime.fromisoformat(str(e.get("valid_at")).replace("Z", "+00:00")) if e.get("valid_at") else None
            except ValueError:
                pass
            db.add(Proposal(brain_id=brain.id, author_id=author.id, name=name, body=text, source="text", status="pending", kind="memory",
                            source_description="right to be forgotten", category="forget.rewrite", reference_time=when,
                            secret_findings=found or None))
            rewritten += 1
        db.commit()
        # 2. the graph and its snapshots
        _forget_in(g, uuid, gt)
        out["entity"] = {"done": 1, "facts": len(gt["facts"]), "merged": len(gt["merged"])}
        out["episodes"] = {"done": len(gt["episodes"]), "rewritten": rewritten, "rewrite_failed": failed,
                           "without_rewrite": max(0, len(eps) - MAX_REWRITES)}
        snaps = 0
        for name in _snapshot_names(brain.graph_name):
            s = client().select_graph(name)
            t = _graph_targets(s, uuid, m)
            if t["episodes"] or t["merged"] or t["facts"] or _exists(s, uuid):
                _forget_in(s, uuid, t)
                snaps += 1
        out["snapshots"] = {"done": snaps}
        # 3. the indexes
        if index.enabled():
            from sqlalchemy import text as sql
            from .docindex import delete_document
            from .store import engine
            with engine().begin() as c:
                n = c.execute(sql("DELETE FROM episode_chunks WHERE brain_id = :b AND episode_uuid = ANY(:u)"),
                              {"b": brain.id, "u": sorted(gt["episodes"])}).rowcount if gt["episodes"] else 0
            out["episode_chunks"] = {"done": int(n or 0)}
            now = datetime.now(timezone.utc).isoformat()
            for d in db.scalars(select(Document).where(Document.id.in_(list(docs)))) if docs else []:
                delete_document(d.id)
                d.status, d.chunks, d.meta = "blocked", 0, {**(d.meta or {}), "forget_blocked_at": now}
            db.commit()
            out["documents"] = {"done": len(docs), "pending": len(docs)}   # each one is to be corrected at its source
        # 4. the database
        logs = [x.id for x in dt["recall_logs"]]
        if logs:
            db.execute(delete(RecallRating).where(RecallRating.log_id.in_(logs)))
        notes = [x.id for x in dt["notifications"]]
        if notes:
            db.execute(delete(NotifyDelivery).where(NotifyDelivery.notification_id.in_(notes)))
        for p in dt["proposals"]:
            p.name, p.body, p.source_description, p.review_note = "", "", "", ""
            p.decision, p.secret_findings, p.correction, p.claims = None, None, None, None
            p.purged_at = datetime.now(timezone.utc)
            if p.status == "pending":
                p.status, p.reviewed_at, p.review_kind = "rejected", datetime.now(timezone.utc), "direct"
        busy = []
        for key in ("recall_samples", "recall_logs", "summary_suggestions", "retype_suggestions", "notifications", "fact_records"):
            for r in dt[key]:
                db.delete(r)
        for j in dt["jobs"]:
            if j.status in ("queued", "running"):
                busy.append(j.id)
            else:
                db.delete(j)
        for r in dt["replay_runs"] + dt["ref_runs"]:
            r.results = [x for x in (r.results or []) if not m(x)]
        for r in dt["curator_runs"]:
            r.findings, r.error = m.scrub(r.findings), m.scrub(r.error)
        for w in dt["webhook_events"]:
            w.title = GONE
        for v in dt["vocab_history"]:
            v.summary, v.detail = m.scrub(v.summary), m.scrub(v.detail)
        for a in dt["audit"]:
            a.detail = m.scrub(a.detail)
        db.commit()
        for key in DB_ACTIONS:
            if key != "ref_queries":
                out[key] = {"done": len(dt[key]) - (len(busy) if key == "jobs" else 0)}
        out["jobs"]["pending"] = len(busy)
        out["review"] = {"other_facts": len(gt["other_facts"]), "other_summaries": len(gt["summaries"]),
                         "similar_entities": len(gt["entities"]), "ref_queries": len(dt["ref_queries"])}
        audit(db, db.get(User, user_id) if user_id else None, "forget.run", brain, entity=uuid, counts=out)
    return out


@jobs.register(KIND, "Derecho al olvido", limit=1, resume=False)
def _job(ctx: "jobs.JobCtx", p: dict) -> dict:
    """The deletion, as a job. Its parameters (the aliases name the person) are wiped when it ends, whatever happens."""
    from .models import Job
    from .store import _factory
    try:
        return run(ctx.brain_id, p["entity"], p.get("aliases") or [], p.get("user_id"), ctx)
    finally:
        with _factory()() as db:
            j = db.get(Job, ctx.id)
            if j:
                j.params = {}
                db.commit()


# --- API --------------------------------------------------------------------------------------

def _session_only(request: Request) -> None:
    if getattr(request.state, "token", None) is not None:
        raise HTTPException(403, "el derecho al olvido se pide desde una sesión, no con un token")


class ReportIn(BaseModel):
    entity: str = Field(min_length=1, max_length=64)
    aliases: list[str] = Field(default_factory=list, max_length=20, description="other names the person goes by: an email, a nickname")


class RunIn(ReportIn):
    confirm: str = Field(min_length=1, max_length=500, description="the entity's name, typed again")


@router.post("/report")
def make_report(body: ReportIn, request: Request, ctx: BrainCtx = Depends(owner_of_brain)):
    """What deleting an entity would touch, layer by layer, and what would stay to review. Read-only."""
    _session_only(request)
    out = report(ctx.db, ctx.brain, body.entity, [a for a in body.aliases if a.strip()])
    audit(ctx.db, ctx.user, "forget.report", ctx.brain, entity=body.entity, counts={x["key"]: x["count"] for x in out["layers"]})
    return out


@router.post("/run", status_code=202)
def start_run(body: RunIn, request: Request, ctx: BrainCtx = Depends(owner_of_brain)):
    """Deletes the entity and everything that names it, as a job. `confirm` must be the entity's name, typed again."""
    from .db import rows
    _session_only(request)
    found = rows(ctx.graph.query("MATCH (n:Entity {uuid:$u}) RETURN n.name AS name", {"u": body.entity}))
    if not found:
        raise HTTPException(404, "la entidad no existe en este brain")
    if " ".join(body.confirm.split()) != " ".join((found[0]["name"] or "").split()):
        raise HTTPException(422, "escribe el nombre de la entidad tal cual para confirmar")
    jid = jobs.submit(KIND, ctx.brain.id, {"entity": body.entity, "aliases": [a for a in body.aliases if a.strip()], "user_id": ctx.user.id},
                      "Derecho al olvido", ctx.user.id, dedupe_key=f"{KIND}:{ctx.brain.id}")
    audit(ctx.db, ctx.user, "forget.start", ctx.brain, entity=body.entity, job=jid)
    return {"job": jid}
