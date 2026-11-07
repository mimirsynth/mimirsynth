"""Ingestion self-test (#296): a fact can be ingested well and never be found, because newer, more detailed facts bury a basic one. After
a proposal is ingested, a job asks the recall one **control question** per new fact (up to MAX_FACTS) and checks that the fact comes
back among the first ones; if it does not, the proposal is flagged «ingested but not retrievable», with the question and what outranked it.

- **Questions** come from a template, without an LLM: the subject's name and the relation in words («Vaultwarden runs on»). They are
  internal: no agent sees them, they are not logged for the ratings and they are kept only on the proposal, for curators.
- **Bounded:** at most MAX_FACTS facts per proposal, and at most `ingest_selftest_per_hour` proposals per brain and hour (the rest
  are not checked, and say so). Off with `ingest_selftest = no`.
- **Where it shows:** in the proposal's detail (`selftest`), and in the memory health as the share of recently ingested proposals
  whose facts were all retrievable (`retrievable`, #292).
"""
import logging
import re
from datetime import datetime, timezone

from . import appsettings, jobs, ratelimit
from .db import graph, rows
from .models import Brain, Proposal
from .store import _factory

log = logging.getLogger("mimirsynth.selftest")
KIND = "proposal.selftest"
MAX_FACTS = 5
TOP = 8   # a fact counts as retrievable if it is among the first TOP current facts of the recall
_EDGES = ("MATCH (a:Entity)-[r:RELATES_TO]->(b:Entity) WHERE $ep IN coalesce(r.episodes, []) AND r.invalid_at IS NULL AND r.expired_at IS NULL "
          "RETURN r.uuid AS uuid, r.name AS name, r.fact AS fact, a.name AS source, b.name AS target ORDER BY r.uuid LIMIT $n")


def question(fact: dict) -> str:
    """The control question of a fact: its subject and its relation in words («HOSTED_ON» → «hosted on»)."""
    rel = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", fact.get("name") or "").replace("_", " ").lower().strip()
    return f"{fact.get('source') or ''} {rel}".strip()


def check(brain_id: int, graph_name: str, facts: list[dict], recall) -> list[dict]:
    """Asks each fact's question and says whether it came back, at which rank, and what came first when it did not."""
    out = []
    for f in facts:
        q = question(f)
        got = [x for x in (recall(q).get("facts") or []) if x.get("status") != "invalidated"][:TOP]
        uuids = [x.get("uuid") for x in got]
        rank = uuids.index(f["uuid"]) + 1 if f["uuid"] in uuids else None
        out.append({"fact_uuid": f["uuid"], "fact": f.get("fact"), "question": q, "found": rank is not None, "rank": rank,
                    "outranked_by": [] if rank else [x.get("fact") for x in got[:3]]})
    return out


def enabled() -> bool:
    return appsettings.get("ingest_selftest") == "yes"


def submit(pid: int, brain_id: int) -> int | None:
    """Queues the self-test of an ingested proposal, unless it is off or the brain used up its checks for this hour (then it says so)."""
    if not enabled():
        return None
    if not ratelimit.allow(f"selftest:{brain_id}", int(appsettings.get("ingest_selftest_per_hour")), 3600):
        with _factory()() as db:
            p = db.get(Proposal, pid)
            if p:
                p.selftest = {"skipped": "rate", "checked_at": datetime.now(timezone.utc).isoformat()}
                db.commit()
        return None
    return jobs.submit(KIND, brain_id, {"pid": pid}, f"Comprobar que se recupera la propuesta #{pid}", dedupe_key=f"{KIND}:{pid}")


@jobs.register(KIND, "Comprobar que se recupera lo ingerido", limit=1)
def _job(ctx: "jobs.JobCtx", p: dict) -> dict:
    from .recall import recall
    with _factory()() as db:
        pr = db.get(Proposal, p["pid"])
        if not pr or pr.status != "ingested" or not pr.episode_uuid:
            return {}
        b = db.get(Brain, pr.brain_id)
        bid, gname, ep = b.id, b.graph_name, pr.episode_uuid
    facts = rows(graph(gname).query(_EDGES, {"ep": ep, "n": MAX_FACTS}))
    lang = appsettings.get("default_language") or "es"
    try:
        results = check(bid, gname, facts, lambda q: recall(bid, gname, q, TOP, 0, 4000, n_docs=0, lang=lang))
        out = {"checked_at": datetime.now(timezone.utc).isoformat(), "results": results,
               "retrievable": all(r["found"] for r in results) if results else None}
    except Exception as e:  # noqa: BLE001  (an embedding engine down: the check says so, nothing else fails)
        log.warning("no se pudo comprobar la propuesta %s: %s", p["pid"], e)
        results, out = [], {"checked_at": datetime.now(timezone.utc).isoformat(), "error": str(e)[:300]}
    with _factory()() as db:
        pr = db.get(Proposal, p["pid"])
        pr.selftest = out
        db.commit()
    return {"facts": len(results), "found": sum(r["found"] for r in results)}


def retrievability(db, brain_id: int, days: int = 30) -> dict:
    """Share of the proposals ingested in the last `days` whose new facts all came back to their control questions (for the health)."""
    from datetime import timedelta
    from sqlalchemy import select
    since = datetime.now(timezone.utc) - timedelta(days=days)
    checked = [p.selftest for p in db.scalars(select(Proposal).where(Proposal.brain_id == brain_id, Proposal.status == "ingested",
                                                                      Proposal.ingested_at >= since, Proposal.selftest.is_not(None)))
               if p.selftest.get("retrievable") is not None]
    ok = sum(1 for s in checked if s["retrievable"])
    return {"retrievable": round(ok / len(checked), 4) if checked else None, "selftested": len(checked), "not_retrievable": len(checked) - ok}
