"""Structured claims in a proposal: the write gate (#295).

Free text is extracted into facts on its own, without looking at what the brain already knows, so a repeat with other words stays as
a second current fact and a change of value can leave the old one current too. Next to its text, a proposal may now carry **claims**:
`{subject, relation, value, valid_from?, supersedes?}`. When it is sent, each claim is compared with the subject's current facts in
the same relation (names and merged names of the entity; the relation through its aliases) and gets a verdict:

- **confirms:** a current fact already says it (same value, or one of its merged names). Approving it records a **confirmation** of
  that fact (renews its shelf life, with who and when) instead of a new fact; if every claim of the proposal confirms, nothing is
  ingested. A repeat of a fact already no longer true is not a confirmation: it never revives it.
- **replaces:** the claim names the fact it replaces (`supersedes`, its uuid), or the relation is functional (one value at a time) and
  the subject has other current values. Approving it invalidates those facts with the claim's `valid_from` (else the proposal's date,
  else now), as a manual contradiction resolution does: in the vocabulary history, undoable.
- **may_replace:** the subject has other current values in a relation that is not functional: a warning for the proposer and the
  curator («this looks like it replaces …»), nothing is invalidated unless the claim says `supersedes`.
- **new:** nothing current in that relation.

The actions are applied by the ingestion job, after the grace period that lets a person undo an approval and after the text is in the
graph, so a failed ingestion never leaves an old fact invalidated without its replacement. Each one is applied once (a retry skips
what is done) and only to facts still current at that moment. A proposal that replaces facts is decided by a person: the decider
leaves it to a curator and a batch approval skips it, as for corrections.

Clients that send only text keep working; the comparison of their text with what the brain knows stays in the review queue
(`related_verdict`).
"""
from datetime import datetime, timezone
from types import SimpleNamespace

from pydantic import BaseModel, Field

from .db import rows
from .vocab import resolve

MAX = 20
VERDICTS = ("new", "confirms", "replaces", "may_replace")
SHOWN = 10   # facts kept per claim as evidence

_CURRENT = ("MATCH (a:Entity)-[r:RELATES_TO]->(b:Entity) WHERE (toLower(a.name) = $k OR any(x IN coalesce(a.aliases, []) WHERE toLower(x) = $k)) "
            "AND r.invalid_at IS NULL AND r.expired_at IS NULL RETURN r.uuid AS uuid, r.name AS name, r.fact AS fact, r.valid_at AS valid_at, "
            "a.name AS source, b.name AS target, coalesce(b.aliases, []) AS target_aliases")
_ONE = ("MATCH (a:Entity)-[r:RELATES_TO {uuid:$u}]->(b:Entity) RETURN r.uuid AS uuid, r.name AS name, r.fact AS fact, r.valid_at AS valid_at, "
        "r.invalid_at AS invalid_at, r.expired_at AS expired_at, a.name AS source, b.name AS target")


class ClaimIn(BaseModel):
    subject: str = Field(min_length=1, max_length=255, description="The entity the claim is about, by its name or a merged name.")
    relation: str = Field(min_length=1, max_length=128, description="The relation, as the brain's ontology names it (HostedOn, RUNS_ON…).")
    value: str = Field(min_length=1, max_length=500, description="The other end: an entity's name or a value.")
    valid_from: datetime | None = Field(None, description="Since when it is true; the date the replaced facts stop being true.")
    supersedes: str | None = Field(None, min_length=1, max_length=64, description="uuid of the current fact this claim replaces.")


class ClaimError(ValueError):
    """A claim that cannot be accepted (its `supersedes` is not a current fact of the brain). `code`: what the message says."""

    def __init__(self, code: str, uuid: str):
        super().__init__(code)
        self.code, self.uuid = code, uuid


def _norm(s) -> str:
    return " ".join(str(s or "").lower().split())


def _short(f: dict) -> dict:
    return {k: f.get(k) for k in ("uuid", "fact", "source", "target", "valid_at")}


def compare(graph, claim: dict, amap: dict | None, functional: set[str]) -> dict:
    """The claim with its canonical relation, its verdict and the current facts it was compared with."""
    rel = resolve(claim["relation"], amap)
    out = {**claim, "relation": rel}
    if claim.get("supersedes"):
        hit = rows(graph.query(_ONE, {"u": claim["supersedes"]}))
        if not hit:
            raise ClaimError("unknown", claim["supersedes"])
        if hit[0]["invalid_at"] or hit[0]["expired_at"]:
            raise ClaimError("not_current", claim["supersedes"])
        return {**out, "verdict": "replaces", "facts": [_short(hit[0])]}
    facts = [f for f in rows(graph.query(_CURRENT, {"k": _norm(claim["subject"])})) if resolve(f["name"], amap) == rel]
    value = _norm(claim["value"])
    same = [f for f in facts if _norm(f["target"]) == value or value in {_norm(a) for a in f.get("target_aliases") or []}]
    other = [f for f in facts if f not in same]
    if same:
        return {**out, "verdict": "confirms", "facts": [_short(f) for f in same[:SHOWN]]}
    if other:
        return {**out, "verdict": "replaces" if rel in functional else "may_replace", "facts": [_short(f) for f in other[:SHOWN]]}
    return {**out, "verdict": "new", "facts": []}


def check(graph, claims: list[dict], amap: dict | None, functional: set[str]) -> list[dict]:
    return [compare(graph, c, amap, functional) for c in claims]


def replaces(p) -> bool:
    """Whether approving the proposal invalidates facts: then a person decides it."""
    return any(c.get("verdict") == "replaces" for c in p.claims or [])


def actions_only(p) -> bool:
    """Approving it only applies its claims, with nothing to extract: every claim confirms, or it has no text (the curator's, #300).
    It needs no LLM."""
    return bool(p.claims) and (only_confirms(p) or not (p.body or "").strip())


def only_confirms(p) -> bool:
    """Every claim repeats a current fact: approving it confirms them and ingests nothing."""
    return bool(p.claims) and all(c.get("verdict") == "confirms" for c in p.claims)


def _current(graph, uuid: str) -> dict | None:
    hit = rows(graph.query(_ONE, {"u": uuid}))
    return hit[0] if hit and not hit[0]["invalid_at"] and not hit[0]["expired_at"] else None


def apply(db, graph, brain, p, user) -> dict:
    """Applies the claims of an approved proposal: confirmations and replacements, each once and only on facts still current. Returns
    what was done, for the ingestion report."""
    from .entity_types import _record
    from .models import FactConfirmation
    from sqlalchemy import select
    now = datetime.now(timezone.utc)
    ctx = SimpleNamespace(db=db, brain=brain, user=user)
    claims, done = [dict(c) for c in p.claims or []], {"confirmed": [], "superseded": []}
    for c in claims:
        if c.get("applied"):
            continue
        if c.get("verdict") == "confirms":
            uuids = [f["uuid"] for f in c.get("facts") or [] if _current(graph, f["uuid"])]
            for u in uuids:
                fc = db.scalar(select(FactConfirmation).where(FactConfirmation.brain_id == brain.id, FactConfirmation.fact_uuid == u))
                if not fc:
                    fc = FactConfirmation(brain_id=brain.id, fact_uuid=u)
                    db.add(fc)
                fc.confirmed_at, fc.user_id = now, user.id if user else None
            c["applied"] = {"action": "confirm", "facts": uuids, "at": now.isoformat()}
            done["confirmed"] += uuids
        elif c.get("verdict") == "replaces":
            when = c.get("valid_from") or (p.reference_time.isoformat() if p.reference_time else now.isoformat())
            gone = []
            for f in c.get("facts") or []:
                n = graph.query("MATCH ()-[r:RELATES_TO {uuid:$u}]->() WHERE r.invalid_at IS NULL AND r.expired_at IS NULL "
                                "SET r.invalid_at = $i, r.expired_at = $n RETURN count(r)", {"u": f["uuid"], "i": when, "n": now.isoformat()}).result_set[0][0]
                if n:
                    op = _record(ctx, "fact.invalidate", f"Sustituido por la propuesta #{p.id}: «{(f.get('fact') or '')[:60]}»",
                                 uuid=f["uuid"], before={"invalid_at": None, "expired_at": None})
                    gone.append({"uuid": f["uuid"], "op": op.id})
            c["applied"] = {"action": "supersede", "facts": gone, "invalid_at": when, "at": now.isoformat()}
            done["superseded"] += [g["uuid"] for g in gone]
        elif c.get("verdict") == "archives":   # out of the recall, reversible, the graph untouched (#297)
            from . import archive
            ok = _current(graph, c["archive"]) is not None and archive.put(db, brain.id, c["archive"], user.id if user else None, p.id,
                                                                            (p.decision or {}).get("curator", {}).get("why", ""))
            c["applied"] = {"action": "archive", "facts": [c["archive"]] if ok else [], "at": now.isoformat()}
            done.setdefault("archived", []).extend([c["archive"]] if ok else [])
        else:
            c["applied"] = {"action": "none", "at": now.isoformat()}
    p.claims = claims
    db.commit()
    return done
