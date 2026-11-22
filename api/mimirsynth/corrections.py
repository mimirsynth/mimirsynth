"""Fact corrections from agents (#109): a proposal that points to one fact by its uuid and asks to invalidate it or, with
`action: "reactivate"`, to make a fact that was invalidated by mistake current again (a wrong supersession, for example).

It goes through the same quarantine as `remember`: a contributor proposes it (also with the MCP tool `correct`) and a curator
approves it; the decider never approves it on its own, because invalidating is more delicate than adding. Over MCP it always stays
pending, even with a curator token: only the REST endpoint applies it at once when a curator sends it. On approval the fact is
invalidated as of the correction date (the given one or the proposal's) and, if it carries a replacement text, that text is ingested
as a normal episode with that same date. The invalidation goes to the vocabulary history like any other (the same operation that
Facts and Contradictions use, #113), and the proposal keeps the previous state for «Reactivate the fact».
A reactivation goes through the same gate: it is decided by a person, and approving it clears the fact's invalid_at/expired_at
(recorded as `fact.reactivate` in the vocabulary history); undoing it puts the invalidation back. A free-text proposal never does this:
its text is extracted into new facts and an invalidated fact stays invalidated.
The proposal stores in `correction` {action, fact_uuid, fact (the fact as it was), reason, invalid_at, op, applied_at, reverted_at};
`body` is the replacement text (empty if there is none). A correction without `action` invalidates.
One pending correction per fact and action (#460): sending one that would wait for a curator while another for the same fact and action is
pending returns that one (200 over REST, said over MCP) instead of a second. A curator who applies one when sending it is not stopped.
Groups (#457): pending invalidations with the same author, token and `source_description` (not empty) are reviewed together, a table
with each fact ticked; approving applies the ticked ones, each as its own correction (same audit, same undo), and rejects the others with
the group's note. Reactivations, and corrections that arrive alone or without `source_description`, are decided one at a time."""
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

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
    action: Literal["invalidate", "reactivate"] = "invalidate"


def _fact(ctx: BrainCtx, uuid: str) -> dict | None:
    r = rows(ctx.graph.query(FACT, {"u": uuid}))
    return r[0] if r else None


REACTIVATE = "reactivate"


def action(c: dict | None) -> str:
    """What a correction does: «invalidate» (the default, also for the corrections stored before reactivations existed) or «reactivate»."""
    return (c or {}).get("action") or "invalidate"


def _check(ctx: BrainCtx, uuid: str, lang: str, act: str = "invalidate") -> dict:
    """The fact must belong to this brain and be current (to invalidate it) or invalidated (to reactivate it). A fact lent by another
    brain is read-only."""
    f = _fact(ctx, uuid)
    if f is None:
        from .db import graph
        from .federation import sources_for
        for src in sources_for(ctx.db, ctx.brain):
            if src.scope in ("graph", "both") and rows(graph(src.graph_name).query("MATCH ()-[r:RELATES_TO {uuid:$u}]->() RETURN r.uuid AS u", {"u": uuid})):
                raise HTTPException(409, tr("El hecho es de «{{origin}}», que lo presta a este brain: es de solo lectura. Corrígelo en ese brain.", lang, origin=src.slug))
        raise HTTPException(404, tr("No hay ningún hecho con el uuid {{uuid}} en este brain.", lang, uuid=uuid))
    if act == REACTIVATE:
        if not f["invalid_at"]:
            raise HTTPException(409, tr("El hecho está vigente: no hay nada que reactivar.", lang))
    elif f["invalid_at"]:
        raise HTTPException(409, tr("El hecho ya está invalidado desde {{date}}: no hay nada que corregir.", lang, date=str(f["invalid_at"])[:10]))
    return f


def _iso(d: datetime) -> str:
    return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).astimezone(timezone.utc).isoformat()


def pending_for(ctx: BrainCtx, uuid: str, act: str, author: int | None = None) -> Proposal | None:
    """The pending correction of this fact that does the same (invalidate or reactivate), if there is one; only `author`'s when given.
    Narrowed by the fact in SQL; the action is told apart here, since older corrections have none (they invalidate)."""
    q = select(Proposal).where(Proposal.brain_id == ctx.brain.id, Proposal.kind == "correction", Proposal.status == "pending",
                               Proposal.correction["fact_uuid"].as_string() == uuid)
    if author is not None:
        q = q.where(Proposal.author_id == author)
    return next((p for p in ctx.db.scalars(q.order_by(Proposal.id)) if action(p.correction) == act), None)


def brief(p: Proposal, ctx: BrainCtx) -> dict:
    """What someone who sent the same correction gets back: all of it when it is theirs or they curate; another author's only by its number."""
    if p.author_id == ctx.user.id or allows(ctx.role, "curator"):
        return {**_out(p), "duplicate": True}
    return {"id": p.id, "status": p.status, "kind": "correction", "duplicate": True, "mine": False}


def create(ctx: BrainCtx, request: Request, body: CorrectionIn, direct: bool = True) -> Proposal:
    """Creates a correction (also used by the MCP tool `correct`). With `direct`, a curator applies it when sending it, as with `remember`.
    One that would only wait in the queue, while another for the same fact and action is pending, returns that one (`p.duplicate`)."""
    lang = language(request)
    f = _check(ctx, body.fact_uuid.strip(), lang, body.action)
    try:
        reason, in_reason = secretguard.guard(ctx.brain, body.reason)
        text, in_body = secretguard.guard(ctx.brain, body.replacement)
    except secretguard.Blocked:
        audit(ctx.db, ctx.user, "proposal.blocked", ctx.brain, reason="secrets", kind="correction")
        raise HTTPException(422, tr("La corrección contiene secretos. Quítalos y guarda solo dónde están (por ejemplo, en qué gestor de contraseñas).", lang))
    found = [{**x, "field": "reason"} for x in in_reason] + [{**x, "field": "body"} for x in in_body]
    if not (direct and allows(ctx.role, "curator") and not secretguard.flagged(found)):   # it would wait: one per fact and action (#460)
        same = pending_for(ctx, f["uuid"], body.action)
        if same is not None:
            same.duplicate = True
            audit(ctx.db, ctx.user, "proposal.duplicate", ctx.brain, id=same.id, kind="correction", fact=f["uuid"])
            return same
    tok = getattr(request.state, "token", None)  # the title stays in memory (it names the replacement's episode): in the instance language
    when = body.invalid_at or datetime.now(timezone.utc)
    short = (f["fact"] or "")[:200]
    title = (tr("Reactivación: {{fact}}", secretguard.instance_lang(), fact=short) if body.action == REACTIVATE
             else tr("Corrección: {{fact}}", secretguard.instance_lang(), fact=short))
    p = Proposal(brain_id=ctx.brain.id, author_id=ctx.user.id, token_id=tok.id if tok else None, kind="correction",
                 name=title[:255], body=text, source="text",
                 source_description=body.source_description, reference_time=when, confidence=body.confidence, status="pending",
                 secret_findings=found or None,
                 correction={"action": body.action, "fact_uuid": f["uuid"], "fact": f, "reason": reason, "invalid_at": _iso(when)})
    ctx.db.add(p); ctx.db.commit()
    audit(ctx.db, ctx.user, "proposal.submit", ctx.brain, id=p.id, status=p.status, kind="correction", correction=body.action, fact=f["uuid"])
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
    act = action(c)
    f = _check(ctx, c["fact_uuid"], lang, act)
    now = datetime.now(timezone.utc)
    if act == REACTIVATE:   # only if it is still invalidated at this moment: never half done
        done = ctx.graph.query("MATCH ()-[r:RELATES_TO {uuid:$u}]->() WHERE r.invalid_at IS NOT NULL SET r.invalid_at = NULL, r.expired_at = NULL RETURN count(r)",
                               {"u": f["uuid"]}).result_set[0][0]
        if not done:
            raise HTTPException(409, tr("El hecho volvió a estar vigente mientras se revisaba la reactivación: recházala.", lang))
    else:
        done = ctx.graph.query("MATCH ()-[r:RELATES_TO {uuid:$u}]->() WHERE r.invalid_at IS NULL SET r.invalid_at = $i, r.expired_at = $n RETURN count(r)",
                               {"u": f["uuid"], "i": c["invalid_at"], "n": now.isoformat()}).result_set[0][0]
        if not done:
            raise HTTPException(409, tr("El hecho dejó de estar vigente mientras se revisaba la corrección: recházala.", lang))
    c["applied_at"] = now.isoformat()
    p.correction = c
    p.status, p.reviewer_id, p.reviewed_at, p.review_kind, p.review_note = "approved", ctx.user.id, now, kind, note
    if not p.body.strip():  # without a replacement there is nothing to ingest: it is already applied
        p.status, p.ingested_at = "ingested", now
    op = (_record(ctx, "fact.reactivate", f"Reactivado por la corrección #{p.id}: «{(f['fact'] or '')[:60]}»",   # commits proposal and operation together
                  uuid=f["uuid"], before={"invalid_at": f["invalid_at"], "expired_at": f["expired_at"]}) if act == REACTIVATE else
          _record(ctx, "fact.invalidate", f"Invalidado por la corrección #{p.id}: «{(f['fact'] or '')[:60]}»",
                  uuid=f["uuid"], before={"invalid_at": f["invalid_at"], "expired_at": f["expired_at"]}))
    p.correction = {**c, "op": op.id}
    ctx.db.commit()
    if kind == "human":
        audit(ctx.db, ctx.user, "proposal.approved", ctx.brain, id=p.id, note=note)
    audit(ctx.db, ctx.user, "proposal.correction", ctx.brain, id=p.id, correction=act, fact=f["uuid"], op=op.id)
    if p.status == "approved" and ingest.enabled():
        ingest.submit_ingest(p.id, ctx.brain.id, secretguard.safe_name(p), ctx.user.id)


@router.post("/corrections", status_code=201)
def submit(body: CorrectionIn, request: Request, ctx: BrainCtx = Depends(contributor)):
    """Contributor: it stays in quarantine. Curator or above: it is applied when sent. The same correction pending already: that one, 200."""
    p = create(ctx, request, body)
    if getattr(p, "duplicate", False):
        return JSONResponse(jsonable_encoder(brief(p, ctx)), status_code=200)
    return _out(p)


@router.post("/{pid}/reactivate")
def reactivate(pid: int, request: Request, ctx: BrainCtx = Depends(curator)):
    """Undoes an applied correction: the fact goes back to its previous state (current again after an invalidation, invalidated again
    after a reactivation). An ingested replacement is left alone."""
    lang = language(request)
    p = _get(ctx, pid)
    c = dict(p.correction or {})
    if p.kind != "correction" or not c.get("applied_at"):
        raise HTTPException(409, tr("La propuesta no es una corrección aplicada.", lang))
    back = action(c) == REACTIVATE   # undoing a reactivation invalidates the fact again, as it was
    if c.get("reverted_at"):
        raise HTTPException(409, tr("La reactivación ya se deshizo.", lang) if back else tr("El hecho ya se reactivó.", lang))
    f = _fact(ctx, c["fact_uuid"])
    if f is None:
        raise HTTPException(404, tr("El hecho ya no existe: se borró después de la corrección.", lang))
    if back and f["invalid_at"]:
        raise HTTPException(409, tr("El hecho ya está invalidado.", lang))
    if not back and not f["invalid_at"]:
        raise HTTPException(409, tr("El hecho ya está vigente.", lang))
    before = c["fact"]
    ctx.graph.query("MATCH ()-[r:RELATES_TO {uuid:$u}]->() SET r.invalid_at = $i, r.expired_at = $e",
                    {"u": f["uuid"], "i": before.get("invalid_at"), "e": before.get("expired_at")})
    op = (_record(ctx, "fact.invalidate", f"Invalidado otra vez al deshacer la reactivación #{p.id}: «{(f['fact'] or '')[:60]}»",
                  uuid=f["uuid"], before={"invalid_at": f["invalid_at"], "expired_at": f["expired_at"]}) if back else
          _record(ctx, "fact.reactivate", f"Reactivado al deshacer la corrección #{p.id}: «{(f['fact'] or '')[:60]}»",
                  uuid=f["uuid"], before={"invalid_at": f["invalid_at"], "expired_at": f["expired_at"]}))
    c.update(reverted_at=datetime.now(timezone.utc).isoformat(), reverted_by=ctx.user.id, revert_op=op.id)
    p.correction = c
    ctx.db.commit()
    audit(ctx.db, ctx.user, "proposal.reactivate", ctx.brain, id=p.id, fact=f["uuid"], op=op.id)
    return _out(p, full=True)


# --- groups (#457) ------------------------------------------------------------------------------------

groups_router = APIRouter(prefix="/api/brains/{slug}/correction-groups")
GROUP_MAX = 200   # rows of a group shown and decided at once


def _group_key(p: Proposal) -> tuple | None:
    """The group a pending correction belongs to, or None when it is decided alone: a reactivation, or one without a source."""
    sd = (p.source_description or "").strip()
    if p.kind != "correction" or p.status != "pending" or p.purged_at or not sd or action(p.correction) != "invalidate":
        return None
    return (p.author_id, p.token_id or 0, sd)


def _group_row(p: Proposal) -> dict:
    c = p.correction or {}
    return {"id": p.id, "name": p.name, "fact_uuid": c.get("fact_uuid"), "fact": c.get("fact") or {}, "reason": c.get("reason") or "",
            "replacement": p.body, "invalid_at": c.get("invalid_at"), "created_at": p.created_at,
            "secrets": secretguard.describe(p.secret_findings), "flagged": secretguard.flagged(p.secret_findings)}


def _groups(ctx: BrainCtx) -> dict[tuple, list[Proposal]]:
    q = select(Proposal).where(Proposal.brain_id == ctx.brain.id, Proposal.kind == "correction", Proposal.status == "pending",
                               Proposal.source_description != "").order_by(Proposal.created_at, Proposal.id)
    out: dict[tuple, list[Proposal]] = {}
    for p in ctx.db.scalars(q):
        if (k := _group_key(p)) is not None:
            out.setdefault(k, []).append(p)
    return {k: v for k, v in out.items() if len(v) > 1}


@groups_router.get("")
def list_groups(ctx: BrainCtx = Depends(curator)):
    """The pending corrections sent together, as groups of two or more, the largest first."""
    groups = []
    for (_, tok, sd), ps in _groups(ctx).items():
        a = ps[0].author
        groups.append({"key": f"{ps[0].id}", "author": a.name or a.email, "token": bool(tok), "source_description": sd, "count": len(ps),
                       "first_at": ps[0].created_at, "last_at": ps[-1].created_at, "items": [_group_row(p) for p in ps[:GROUP_MAX]]})
    groups.sort(key=lambda g: (-g["count"], g["first_at"]))
    return {"groups": groups}


class GroupIn(BaseModel):
    approve: list[int] = Field(default_factory=list, max_length=GROUP_MAX)
    reject: list[int] = Field(default_factory=list, max_length=GROUP_MAX)
    note: str = Field("", max_length=2000)


@groups_router.post("/decide")
def decide_group(body: GroupIn, request: Request, ctx: BrainCtx = Depends(curator)):
    """Approves the ticked corrections of one group, each as if alone, and rejects the others with the group's note. A row whose fact
    changed meanwhile, or with a secret to review, is skipped and said; nothing is half applied."""
    from .proposals import _review
    lang = language(request)
    ids = list(dict.fromkeys(body.approve)) + list(dict.fromkeys(body.reject))
    if not ids:
        raise HTTPException(422, tr("No hay ninguna corrección marcada ni desmarcada.", lang))
    if set(body.approve) & set(body.reject):
        raise HTTPException(422, tr("Una corrección no puede aprobarse y rechazarse a la vez.", lang))
    found = {p.id: p for p in ctx.db.scalars(select(Proposal).where(Proposal.brain_id == ctx.brain.id, Proposal.id.in_(ids)))}
    missing = [i for i in ids if i not in found]
    if missing:
        raise HTTPException(404, tr("No hay ninguna propuesta con el número {{id}} en este brain.", lang, id=missing[0]))
    keys = {_group_key(found[i]) for i in ids}
    if None in keys:
        bad = next(i for i in ids if _group_key(found[i]) is None)
        raise HTTPException(409, tr("La propuesta #{{id}} ya no está pendiente o no va en grupo: decídela aparte.", lang, id=bad))
    if len(keys) > 1:
        raise HTTPException(422, tr("Las correcciones no son del mismo grupo.", lang))
    approved, rejected, skipped = [], [], []
    for pid in dict.fromkeys(body.approve):
        p = found[pid]
        if secretguard.flagged(p.secret_findings):   # what the detector flagged is masked by a person, one at a time
            skipped.append({"id": pid, "reason": "secret"})
            continue
        try:
            apply(ctx, p, lang, note=body.note)
        except HTTPException as e:   # the fact stopped being current, or went away: it stays pending, never half applied
            ctx.db.rollback()
            skipped.append({"id": pid, "reason": "changed", "detail": str(e.detail)[:300]})
            continue
        approved.append(pid)
    for pid in dict.fromkeys(body.reject):
        _review(ctx, pid, "rejected", body.note)
        rejected.append(pid)
    (_, _, sd), = keys
    audit(ctx.db, ctx.user, "proposal.group", ctx.brain, source=sd[:255], approved=len(approved), rejected=len(rejected), skipped=len(skipped))
    return {"approved": approved, "rejected": rejected, "skipped": skipped}
