"""Curation by category (#299): the review queue grouped by what produced each proposal, decided a whole category at a time after a look
at a sample, and **auto-approval tiers** that a category earns by its measured precision.

- **Category** of a pending proposal: what produced it (`curator.contradictions`, `verifier.refuted`…, #300 and #293), else a
  correction, else what the brain already knew close to it (`duplicate`, `stale`), else `new`.
- **Precision** of a category: the share of approvals among the last PRECISION_WINDOW proposals of that category **a person**
  decided (`review_kind: human`). Automatic approvals never count: a tier cannot earn its own precision.
- **Deciding a category** (`POST /review/categories/{category}/decide`, curators): approves or rejects every pending proposal of the
  category, up to BATCH, after the screen has shown a sample. What the secret scanner flagged is always left out, and an approval
  waits the usual grace period before ingestion, so it can still be undone.
- **Auto-approval tiers** (`PUT /review/categories/{category}/auto`, brain administrators): a category can be switched to automatic
  approval only while its precision over at least `min` decisions is at or above `bar` (95 % of 20 by default). Every few minutes the
  brains with a tier approve the pending proposals of that category (`review_kind: auto`, in the audit log, undoable like any other)
  and check its precision again: below the bar, the tier switches itself back to manual and a `autoapprove.disabled` notification
  says so. The decider and quarantine keep working as before; nothing flagged by the secret scanner is ever approved this way.
"""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from . import claims as claims_mod
from . import ingest, secretguard
from .deps import BrainCtx, admin_of_brain, audit, brain_access
from .models import Brain, Proposal
from .store import _factory

log = logging.getLogger("mimirsynth.categories")
router = APIRouter(prefix="/api/brains/{slug}/review/categories")
curator = brain_access("curator")
PRECISION_WINDOW = 50
BATCH = 200
SAMPLE = 5
DEFAULT_TIER = {"enabled": False, "bar": 0.95, "min": 20}
APPROVED = ("approved", "ingested", "failed")


def category_of(p: Proposal) -> str:
    if p.category:
        return p.category
    if p.kind == "correction":
        return "correction"
    return p.related_verdict if p.related_verdict in ("duplicate", "stale") else "new"


def precision(db, brain_id: int, cat: str, window: int = PRECISION_WINDOW) -> dict:
    """Approvals among the last `window` proposals of the category that a person decided."""
    q = (select(Proposal).where(Proposal.brain_id == brain_id, Proposal.review_kind == "human", Proposal.status.in_((*APPROVED, "rejected")))
         .order_by(Proposal.reviewed_at.desc()).limit(2000))
    decided = [p for p in db.scalars(q) if category_of(p) == cat][:window]
    approved = sum(1 for p in decided if p.status in APPROVED)
    return {"decided": len(decided), "approved": approved, "precision": round(approved / len(decided), 3) if decided else None}


def tiers(brain: Brain) -> dict[str, dict]:
    return {k: {**DEFAULT_TIER, **v} for k, v in (brain.auto_approve or {}).items()}


def _pending(db, brain_id: int) -> dict[str, list[Proposal]]:
    out: dict[str, list[Proposal]] = {}
    for p in db.scalars(select(Proposal).where(Proposal.brain_id == brain_id, Proposal.status == "pending").order_by(Proposal.created_at)):
        out.setdefault(category_of(p), []).append(p)
    return out


def _sample(p: Proposal) -> dict:
    return {"id": p.id, "name": p.name, "body": (p.body or "")[:300], "created_at": p.created_at, "related_verdict": p.related_verdict or "",
            "claims": [{k: c.get(k) for k in ("subject", "relation", "value", "verdict")} | {"facts": [f.get("fact") for f in c.get("facts") or []][:3]}
                       for c in p.claims or []]}


def _approve(db, brain: Brain, p: Proposal, user_id: int | None, kind: str, note: str = "") -> None:
    from .proposals import UNDO_SECONDS
    p.status, p.reviewer_id, p.reviewed_at, p.review_kind, p.review_note = "approved", user_id, datetime.now(timezone.utc), kind, note
    db.commit()
    if ingest.enabled() or claims_mod.actions_only(p):
        ingest.submit_ingest(p.id, brain.id, secretguard.safe_name(p), user_id, delay=UNDO_SECONDS)


# --- API --------------------------------------------------------------------------------------

@router.get("")
def list_categories(ctx: BrainCtx = Depends(curator)):
    """The pending proposals by category: how many, the oldest, a sample, the category's precision and its tier."""
    pend, t = _pending(ctx.db, ctx.brain.id), tiers(ctx.brain)
    cats = sorted(set(pend) | set(t), key=lambda c: (-len(pend.get(c, [])), c))
    return {"items": [{"category": c, "pending": len(pend.get(c, [])), "oldest": pend[c][0].created_at if pend.get(c) else None,
                       "flagged": sum(1 for p in pend.get(c, []) if secretguard.flagged(p.secret_findings)),
                       "sample": [_sample(p) for p in pend.get(c, [])[:SAMPLE]], "precision": precision(ctx.db, ctx.brain.id, c),
                       "auto": t.get(c, DEFAULT_TIER)} for c in cats]}


class DecideIn(BaseModel):
    verb: str = Field(pattern="^(approve|reject)$")
    seen: list[int] = Field(min_length=1, max_length=SAMPLE * 4, description="the ids of the sample the person looked at")
    note: str = Field("", max_length=2000)


@router.post("/{cat}/decide")
def decide(cat: str, body: DecideIn, ctx: BrainCtx = Depends(curator)):
    """Approves or rejects every pending proposal of the category (up to BATCH). `seen` must be proposals of the category: the decision
    is taken after looking at them. Flagged secrets are left out; each decision is audited as a person's."""
    pend = _pending(ctx.db, ctx.brain.id).get(cat, [])
    ids = {p.id for p in pend}
    if not pend:
        raise HTTPException(404, "no hay propuestas pendientes en esa categoría")
    if not set(body.seen) <= ids:
        raise HTTPException(409, "la muestra ya no corresponde a la categoría: vuelve a mirarla")
    done, skipped = [], []
    for p in pend[:BATCH]:
        if body.verb == "approve" and secretguard.flagged(p.secret_findings):
            skipped.append({"id": p.id, "reason": "secret"})
            continue
        if body.verb == "approve" and p.kind == "correction":   # a correction is applied when approved: one at a time, from its detail
            skipped.append({"id": p.id, "reason": "correction"})
            continue
        if body.verb == "approve":
            _approve(ctx.db, ctx.brain, p, ctx.user.id, "human", body.note)
        else:
            p.status, p.reviewer_id, p.reviewed_at, p.review_kind, p.review_note = "rejected", ctx.user.id, datetime.now(timezone.utc), "human", body.note
            ctx.db.commit()
        audit(ctx.db, ctx.user, f"proposal.{'approved' if body.verb == 'approve' else 'rejected'}", ctx.brain, id=p.id, category=cat, batch=True)
        done.append(p.id)
    return {"done": done, "skipped": skipped, "left": max(0, len(pend) - BATCH)}


class TierIn(BaseModel):
    enabled: bool
    bar: float = Field(DEFAULT_TIER["bar"], ge=0.5, le=1)
    min: int = Field(DEFAULT_TIER["min"], ge=5, le=PRECISION_WINDOW)


@router.put("/{cat}/auto")
def set_tier(cat: str, body: TierIn, ctx: BrainCtx = Depends(admin_of_brain)):
    """Switches a category to automatic approval, only while it has earned it; switching it off is always possible."""
    pr = precision(ctx.db, ctx.brain.id, cat)
    if body.enabled and (pr["decided"] < body.min or (pr["precision"] or 0) < body.bar):
        raise HTTPException(409, f"la categoría no lo ha ganado: {pr['approved']} aprobadas de {pr['decided']} decididas por personas; "
                                 f"hacen falta {body.min} decisiones y una precisión de {body.bar:g}")
    t = dict(ctx.brain.auto_approve or {})
    t[cat] = {"enabled": body.enabled, "bar": body.bar, "min": body.min}
    ctx.brain.auto_approve = t
    ctx.db.commit()
    audit(ctx.db, ctx.user, "autoapprove.settings", ctx.brain, category=cat, **t[cat], precision=pr["precision"], decided=pr["decided"])
    return {"category": cat, "auto": t[cat], "precision": pr}


# --- the tiers at work ------------------------------------------------------------------------

def run_tiers() -> int:
    """Every few minutes: for each enabled tier, its precision is checked again (below the bar it switches back to manual and notifies);
    otherwise the category's pending proposals are approved, except what the secret scanner flagged. Returns how many were approved."""
    from . import notify
    n = 0
    with _factory()() as db:
        for b in db.scalars(select(Brain).where(Brain.auto_approve.is_not(None))):
            on = {c: t for c, t in tiers(b).items() if t["enabled"]}
            if not on:
                continue
            pend = _pending(db, b.id)
            for cat, t in on.items():
                pr = precision(db, b.id, cat)
                if pr["decided"] < t["min"] or (pr["precision"] or 0) < t["bar"]:
                    cfg = dict(b.auto_approve)
                    cfg[cat] = {**t, "enabled": False}
                    b.auto_approve = cfg
                    db.commit()
                    audit(db, None, "autoapprove.disabled", b, category=cat, precision=pr["precision"], decided=pr["decided"])
                    notify.emit("autoapprove.disabled", f"«{b.name}»: la aprobación automática de «{cat}» vuelve a ser manual",
                                f"Su precisión bajó a {pr['precision']} ({pr['approved']} aprobadas de {pr['decided']} decididas por personas), por debajo de "
                                f"{t['bar']:g}. Sus propuestas vuelven a esperar a un curador.", brain_id=b.id, key=f"autoapprove:{b.slug}:{cat}")
                    continue
                for p in pend.get(cat, [])[:BATCH]:
                    if secretguard.flagged(p.secret_findings) or p.kind == "correction":
                        continue
                    _approve(db, b, p, None, "auto", f"aprobada automáticamente: precisión {pr['precision']} en {pr['decided']} decisiones")
                    audit(db, None, "proposal.approved", b, id=p.id, category=cat, by="auto", precision=pr["precision"])
                    n += 1
    return n
