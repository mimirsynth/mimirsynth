"""Fact corrections from agents (#109): a proposal that points to one fact by its uuid and asks to invalidate it.

It goes through the same quarantine as `remember`: a contributor proposes it (also with the MCP tool `correct`) and a curator
approves it; the decider never approves it on its own, because invalidating is more delicate than adding. Over MCP it always stays
pending, even with a curator token: only the REST endpoint applies it at once when a curator sends it. On approval the fact is
invalidated as of the correction date (the given one or the proposal's) and, if it carries a replacement text, that text is ingested
as a normal episode with that same date. The invalidation goes to the vocabulary history like any other (the same operation that
Facts and Contradictions use, #113), and the proposal keeps the previous state for «Reactivate the fact».
The proposal stores in `correction` {fact_uuid, fact (the fact as it was), reason, invalid_at, op, applied_at, reverted_at};
`body` is the replacement text (empty if there is none)."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from . import ingest, secretguard
from .db import rows
from .deps import BrainCtx, audit, brain_access
from .entity_types import _record
from .i18n import language, tr
from .models import Proposal
from .proposals import _get, _out
from .roles import allows

router = APIRouter(prefix="/api/brains/{slug}/proposals")
contributor = brain_access("contributor")
curator = brain_access("curator")

FACT = ("MATCH (a:Entity)-[r:RELATES_TO {uuid:$u}]->(b:Entity) RETURN r.uuid AS uuid, r.name AS name, r.fact AS fact, r.valid_at AS valid_at, "
        "r.invalid_at AS invalid_at, r.expired_at AS expired_at, a.name AS source, b.name AS target")


class CorrectionIn(BaseModel):
    fact_uuid: str = Field(min_length=1, max_length=64)
    reason: str = Field(min_length=3, max_length=2000)
    replacement: str = Field("", max_length=50000)
    invalid_at: datetime | None = None
    source_description: str = Field("", max_length=255)
    confidence: float | None = Field(None, ge=0, le=1)


def _fact(ctx: BrainCtx, uuid: str) -> dict | None:
    r = rows(ctx.graph.query(FACT, {"u": uuid}))
    return r[0] if r else None


def _check(ctx: BrainCtx, uuid: str, lang: str) -> dict:
    """The fact must belong to this brain and be current. A fact lent by another brain is read-only."""
    f = _fact(ctx, uuid)
    if f is None:
        from .db import graph
        from .federation import sources_for
        for src in sources_for(ctx.db, ctx.brain):
            if src.scope in ("graph", "both") and rows(graph(src.graph_name).query("MATCH ()-[r:RELATES_TO {uuid:$u}]->() RETURN r.uuid AS u", {"u": uuid})):
                raise HTTPException(409, tr("El hecho es de «{{origin}}», que lo presta a este brain: es de solo lectura. Corrígelo en ese brain.", lang, origin=src.slug))
        raise HTTPException(404, tr("No hay ningún hecho con el uuid {{uuid}} en este brain.", lang, uuid=uuid))
    if f["invalid_at"]:
        raise HTTPException(409, tr("El hecho ya está invalidado desde {{date}}: no hay nada que corregir.", lang, date=str(f["invalid_at"])[:10]))
    return f


def _iso(d: datetime) -> str:
    return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).astimezone(timezone.utc).isoformat()


def create(ctx: BrainCtx, request: Request, body: CorrectionIn, direct: bool = True) -> Proposal:
    """Creates a correction (also used by the MCP tool `correct`). With `direct`, a curator applies it when sending it, as with `remember`."""
    lang = language(request)
    f = _check(ctx, body.fact_uuid.strip(), lang)
    try:
        reason, in_reason = secretguard.guard(ctx.brain, body.reason)
        text, in_body = secretguard.guard(ctx.brain, body.replacement)
    except secretguard.Blocked:
        audit(ctx.db, ctx.user, "proposal.blocked", ctx.brain, reason="secrets", kind="correction")
        raise HTTPException(422, tr("La corrección contiene secretos. Quítalos y guarda solo dónde están (por ejemplo, en qué gestor de contraseñas).", lang))
    found = [{**x, "field": "reason"} for x in in_reason] + [{**x, "field": "body"} for x in in_body]
    tok = getattr(request.state, "token", None)  # the title stays in memory (it names the replacement's episode): in the instance language
    when = body.invalid_at or datetime.now(timezone.utc)
    p = Proposal(brain_id=ctx.brain.id, author_id=ctx.user.id, token_id=tok.id if tok else None, kind="correction",
                 name=tr("Corrección: {{fact}}", secretguard.instance_lang(), fact=(f["fact"] or "")[:200])[:255], body=text, source="text",
                 source_description=body.source_description, reference_time=when, confidence=body.confidence, status="pending",
                 secret_findings=found or None,
                 correction={"fact_uuid": f["uuid"], "fact": f, "reason": reason, "invalid_at": _iso(when)})
    ctx.db.add(p); ctx.db.commit()
    audit(ctx.db, ctx.user, "proposal.submit", ctx.brain, id=p.id, status=p.status, kind="correction", fact=f["uuid"])
    if direct and allows(ctx.role, "curator") and not secretguard.flagged(found):
        try:
            apply(ctx, p, lang, kind="direct")
        except HTTPException:  # the fact changed in between: it stays pending for a person to look at
            ctx.db.refresh(p)
    return p


def apply(ctx: BrainCtx, p: Proposal, lang: str = "es", note: str = "", kind: str = "human") -> None:
    """Approves and applies a pending correction: invalidates the fact and, if there is a replacement, sends it to be ingested. The graph
    is only written if the fact is still current at that moment, and the proposal becomes approved in the same commit as the history
    operation: if the fact stopped being current between the check and the write, 409 and the proposal stays pending, never half done."""
    c = dict(p.correction or {})
    f = _check(ctx, c["fact_uuid"], lang)
    now = datetime.now(timezone.utc)
    done = ctx.graph.query("MATCH ()-[r:RELATES_TO {uuid:$u}]->() WHERE r.invalid_at IS NULL SET r.invalid_at = $i, r.expired_at = $n RETURN count(r)",
                           {"u": f["uuid"], "i": c["invalid_at"], "n": now.isoformat()}).result_set[0][0]
    if not done:
        raise HTTPException(409, tr("El hecho dejó de estar vigente mientras se revisaba la corrección: recházala.", lang))
    c["applied_at"] = now.isoformat()
    p.correction = c
    p.status, p.reviewer_id, p.reviewed_at, p.review_kind, p.review_note = "approved", ctx.user.id, now, kind, note
    if not p.body.strip():  # without a replacement there is nothing to ingest: it is already applied
        p.status, p.ingested_at = "ingested", now
    op = _record(ctx, "fact.invalidate", f"Invalidado por la corrección #{p.id}: «{(f['fact'] or '')[:60]}»",   # commits proposal and operation together
                 uuid=f["uuid"], before={"invalid_at": f["invalid_at"], "expired_at": f["expired_at"]})
    p.correction = {**c, "op": op.id}
    ctx.db.commit()
    if kind == "human":
        audit(ctx.db, ctx.user, "proposal.approved", ctx.brain, id=p.id, note=note)
    audit(ctx.db, ctx.user, "proposal.correction", ctx.brain, id=p.id, fact=f["uuid"], op=op.id)
    if p.status == "approved" and ingest.enabled():
        ingest.submit_ingest(p.id, ctx.brain.id, secretguard.safe_name(p), ctx.user.id)


@router.post("/corrections", status_code=201)
def submit(body: CorrectionIn, request: Request, ctx: BrainCtx = Depends(contributor)):
    """Contributor: it stays in quarantine. Curator or above: it is applied when sent."""
    return _out(create(ctx, request, body))


@router.post("/{pid}/reactivate")
def reactivate(pid: int, request: Request, ctx: BrainCtx = Depends(curator)):
    """Undoes an applied correction: the fact becomes current again with its previous state. An ingested replacement is left alone."""
    lang = language(request)
    p = _get(ctx, pid)
    c = dict(p.correction or {})
    if p.kind != "correction" or not c.get("applied_at"):
        raise HTTPException(409, tr("La propuesta no es una corrección aplicada.", lang))
    if c.get("reverted_at"):
        raise HTTPException(409, tr("El hecho ya se reactivó.", lang))
    f = _fact(ctx, c["fact_uuid"])
    if f is None:
        raise HTTPException(404, tr("El hecho ya no existe: se borró después de la corrección.", lang))
    if not f["invalid_at"]:
        raise HTTPException(409, tr("El hecho ya está vigente.", lang))
    before = c["fact"]
    ctx.graph.query("MATCH ()-[r:RELATES_TO {uuid:$u}]->() SET r.invalid_at = $i, r.expired_at = $e",
                    {"u": f["uuid"], "i": before.get("invalid_at"), "e": before.get("expired_at")})
    op = _record(ctx, "fact.reactivate", f"Reactivado al deshacer la corrección #{p.id}: «{(f['fact'] or '')[:60]}»",
                 uuid=f["uuid"], before={"invalid_at": f["invalid_at"], "expired_at": f["expired_at"]})
    c.update(reverted_at=datetime.now(timezone.utc).isoformat(), reverted_by=ctx.user.id, revert_op=op.id)
    p.correction = c
    ctx.db.commit()
    audit(ctx.db, ctx.user, "proposal.reactivate", ctx.brain, id=p.id, fact=f["uuid"], op=op.id)
    return _out(p, full=True)
