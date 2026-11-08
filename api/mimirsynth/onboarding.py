"""The getting-started checklist on the home screen (#363): what someone new does after the first recall, each step ticked by what
already happened in their brains, without anyone marking it.

The steps are read from data the application keeps anyway: the recall log (with the token a recall came through, so an agent's recall
is told from a question in Ask), the proposals and their decision, the documents and document sources, the API tokens, and the members
and users. They cover the brains the person can see: all of them for an instance administrator, their own for anyone else. A step seen
done once is kept, with the time it was first seen, in `onboarding_states`: a recall log goes with its retention period and a token may be
revoked, and a step does not untick itself. The same row keeps whether the person closed the card. The card shows until every step is
done or the person closes it; neither brings it back.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .deps import aware, current_user
from .models import ApiToken, Brain, DocSource, Document, Membership, OnboardingState, Proposal, RecallLog, User
from .store import get_db

router = APIRouter(prefix="/api/onboarding")

# In the order the card lists them: an agent connected and recalling, its first proposal, the first one approved, documents, a question
# of one's own in Ask, and someone or something more using the memory.
STEPS = ("agent_recall", "proposal_received", "proposal_approved", "document", "ask", "second")
APPROVED = ("approved", "ingested", "failed")      # a proposal approved, whether or not its ingestion went well (categories.APPROVED)
NOT_REVIEWED = ("", "direct")                      # direct: a curator's own proposal, approved as it was sent, not reviewed


def _brain_ids(db: Session, user: User) -> list[int]:
    if user.is_admin:
        return list(db.scalars(select(Brain.id)))
    return list(db.scalars(select(Membership.brain_id).where(Membership.user_id == user.id)))


def _some(db: Session, stmt) -> bool:
    return db.scalar(stmt.limit(1)) is not None


def _check(db: Session, user: User, step: str, ids: list[int]) -> bool:
    """Whether `step` has happened in the brains `ids` (or, for a question in Ask, by this person)."""
    if step == "ask":  # a recall through a session, not a token: Ask (Context or Answer) in the web interface
        return _some(db, select(RecallLog.id).where(RecallLog.user_id == user.id, RecallLog.token_id.is_(None)))
    if not ids:
        return False
    if step == "agent_recall":
        return _some(db, select(RecallLog.id).where(RecallLog.brain_id.in_(ids), RecallLog.token_id.is_not(None)))
    if step == "proposal_received":  # from an agent: sent with a token, or declared by its client as an agent's
        return _some(db, select(Proposal.id).where(Proposal.brain_id.in_(ids), (Proposal.token_id.is_not(None)) | (Proposal.origin.in_(("agent", "auto")))))
    if step == "proposal_approved":  # by a curator, the decider or an auto-approval tier
        return _some(db, select(Proposal.id).where(Proposal.brain_id.in_(ids), Proposal.status.in_(APPROVED), Proposal.review_kind.not_in(NOT_REVIEWED)))
    if step == "document":  # a document of any source, or a source that brings them (a folder, a wiki, a repository) before it has any
        return (_some(db, select(Document.id).where(Document.brain_id.in_(ids)))
                or _some(db, select(DocSource.id).where(DocSource.brain_id.in_(ids), DocSource.kind != "upload")))
    if step == "second":  # a second agent (a live token) or a second person (another member, or another user for an administrator)
        tokens = db.scalar(select(func.count(ApiToken.id)).where(ApiToken.brain_id.in_(ids), ApiToken.revoked.is_(False), ApiToken.replaced_by.is_(None)))
        if (tokens or 0) >= 2:
            return True
        if user.is_admin:
            people = db.scalar(select(func.count(User.id)).where(User.status.in_(("active", "invited"))))
        else:
            people = db.scalar(select(func.count(func.distinct(Membership.user_id))).where(Membership.brain_id.in_(ids)))
        return (people or 0) >= 2
    raise ValueError(step)


def token_activity(db: Session, tok: ApiToken) -> dict:
    """What an agent has done with one token (#362, the «Connect an agent» panel), from what every call already records: its last
    authenticated call (each one refreshes `last_used_at`, whatever it asks for) and the recalls it made, by the same
    `recall_logs.token_id` that ticks `agent_recall` above. A recall log goes with its retention period, so `recalls` counts the kept ones."""
    n, last = db.execute(select(func.count(RecallLog.id), func.max(RecallLog.created_at))
                         .where(RecallLog.brain_id == tok.brain_id, RecallLog.token_id == tok.id)).one()
    return {"id": tok.id, "connected": tok.last_used_at is not None, "last_used_at": aware(tok.last_used_at), "recalls": n or 0,
            "last_recall_at": aware(last)}


def _state(db: Session, user: User) -> OnboardingState:
    st = db.get(OnboardingState, user.id)
    if st is None:
        st = OnboardingState(user_id=user.id, done={})
        db.add(st)
        try:
            db.commit()
        except IntegrityError:  # two tabs opened the home screen at once: the other request created it
            db.rollback()
            st = db.get(OnboardingState, user.id)
    return st


def _out(st: OnboardingState) -> dict:
    done = st.done or {}
    steps = [{"key": k, "done": k in done, "done_at": done.get(k)} for k in STEPS]
    n = sum(1 for s in steps if s["done"])
    dismissed = st.dismissed_at is not None
    return {"steps": steps, "done": n, "total": len(STEPS), "dismissed": dismissed, "show": not dismissed and n < len(STEPS)}


def refresh(db: Session, user: User) -> dict:
    """The checklist of `user`, after ticking the steps that have happened since it was last read. Once the card is closed or complete
    nothing more is looked up."""
    st = _state(db, user)
    done = dict(st.done or {})
    if st.dismissed_at is None and len(done) < len(STEPS):
        ids = _brain_ids(db, user)
        at = datetime.now(timezone.utc).isoformat()
        new = {k: at for k in STEPS if k not in done and _check(db, user, k, ids)}
        if new:
            st.done, st.updated_at = {**done, **new}, datetime.now(timezone.utc)
            db.commit()
    return _out(st)


@router.get("")
def get_onboarding(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """The getting-started checklist of the person asking: each step, whether it is done and since when, and whether the card shows."""
    return refresh(db, user)


@router.post("/dismiss")
def dismiss(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Closes the card for good, whatever is left undone."""
    st = _state(db, user)
    if st.dismissed_at is None:
        st.dismissed_at = st.updated_at = datetime.now(timezone.utc)
        db.commit()
    return _out(st)
