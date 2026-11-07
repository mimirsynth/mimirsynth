"""Ranking by source trust and decay by relation type (#298).

**Trust tier of a fact**, from where it came, highest first:
- `verified`: a probe checked it against a live system and it held (#293);
- `human`: a person approved it, or wrote it themself in the application;
- `agent`: an agent chose to write it (`origin: "agent"`), approved by the decider, a webhook or a curator's token;
- `auto`: captured automatically from a session (`origin: "auto"`), or a client that did not say (the lowest tier by default).

The client says what it is with `origin` on a proposal, but the **token** sets the most it can claim (`max_trust`, `agent` by default,
`auto` for a hook's token): the field can only lower it, never raise it, since a hook and an agent may share a token. A fact learned
from several proposals takes the best of them. Facts learned before this existed have no tier and keep their score.

**Weighting**, off by default (`recall_trust`): an `agent` fact's score is multiplied by `recall_trust_agent` and an `auto` one's by
`recall_trust_auto`; `verified` and `human` keep theirs. **Decay** (`recall_decay`, off by default): a current fact whose relation has
a shelf life loses weight gradually as it ages, from 1 when it was last confirmed (or became valid) down to `recall_stale_weight` when
its shelf life ends, instead of all at once at the end. Reference queries can simulate either without changing the settings.
Every fact says its tier in the recall's JSON (`trust`).
"""
from datetime import datetime, timezone

from sqlalchemy import select

from . import appsettings
from .models import Proposal
from .store import _factory

TIERS = ("auto", "agent", "human", "verified")   # lowest first
RANK = {t: i for i, t in enumerate(TIERS)}
ORIGINS = ("agent", "auto")


def effective_origin(requested: str | None, token) -> str:
    """What a proposal's origin is recorded as: a person in the application is `person`; through a token, what the client says (the
    lowest when it says nothing), never above the token's `max_trust`."""
    if token is None:
        return "person"
    cap = getattr(token, "max_trust", None) or "agent"
    want = requested if requested in ORIGINS else "auto"
    return want if RANK[want] <= RANK[cap] else cap


def proposal_tier(origin: str | None, review_kind: str | None) -> str | None:
    if review_kind == "human" or origin == "person":
        return "human"
    return origin if origin in ORIGINS else None   # before #298: no tier


def _on(override: bool | None, key: str) -> bool:
    return bool(override) if override is not None else appsettings.get(key) == "yes"


def mark(brain_id: int, facts: list[dict], trust: bool | None = None) -> list[dict]:
    """Adds `trust` to the recall's own facts and, with the weighting on, scales their score. Returns them reordered if anything moved."""
    own = [f for f in facts if not f.get("origin") and f.get("episodes")]
    eps = {e for f in own for e in f["episodes"] or []}
    tiers: dict[str, str] = {}
    if eps:
        with _factory()() as db:
            for ep, origin, kind in db.execute(select(Proposal.episode_uuid, Proposal.origin, Proposal.review_kind)
                                               .where(Proposal.brain_id == brain_id, Proposal.episode_uuid.in_(list(eps)))):
                t = proposal_tier(origin, kind)
                if t and (ep not in tiers or RANK[t] > RANK[tiers[ep]]):
                    tiers[ep] = t
    for f in facts:
        best = max((tiers[e] for e in f.get("episodes") or [] if e in tiers), key=RANK.get, default=None)
        if (f.get("verification") or {}).get("state") == "verified":
            best = "verified"
        if best:
            f["trust"] = best
    if not _on(trust, "recall_trust"):
        return facts
    w = {"agent": float(appsettings.get("recall_trust_agent")), "auto": float(appsettings.get("recall_trust_auto"))}
    moved = False
    for f in facts:
        if f.get("trust") in w and isinstance(f.get("score"), (int, float)):
            f["score"] = round(f["score"] * w[f["trust"]], 4)
            moved = True
    return sorted(facts, key=lambda f: -(f.get("score") or 0)) if moved else facts


def decay(age_days: float, life_days: int, floor: float) -> float:
    """The weight of a fact `age_days` after its last confirmation, for a relation of `life_days`: 1 at 0, `floor` at the end."""
    if life_days <= 0:
        return 1.0
    return 1.0 - (1.0 - floor) * min(1.0, max(0.0, age_days / life_days))


def apply_decay(facts: list[dict], lives: dict[str, int], confirmed: dict[str, datetime], amap: dict | None = None,
                on: bool | None = None, now: datetime | None = None) -> list[dict]:
    """With decay on, scales the score of current facts that are not yet stale by how far into their relation's shelf life they are."""
    from .db import parse_ts
    from .vocab import canon_rel
    if not lives or not _on(on, "recall_decay"):
        return facts
    floor, now, moved = float(appsettings.get("recall_stale_weight")), now or datetime.now(timezone.utc), False
    for f in facts:
        life = lives.get(canon_rel(f.get("name") or ""))
        base = confirmed.get(f.get("uuid")) or parse_ts(f.get("valid_at"))
        if not life or f.get("stale_since") or f.get("origin") or f.get("status") != "current" or base is None or not isinstance(f.get("score"), (int, float)):
            continue
        f["score"] = round(f["score"] * decay((now - base).total_seconds() / 86400, life, floor), 4)
        moved = True
    return sorted(facts, key=lambda f: -(f.get("score") or 0)) if moved else facts
