"""Does MIMIRSYNTH_SESSION_SECRET still open what the instance sealed? (#193)

A restore on another host, a copy of the database in a test stack or a wrong `.env` start the app with another secret: the stored
secrets (two-factor seeds, AI engine keys, the SMTP password…) can no longer be read. The check notices it so the instance can say so:
one line in the log at start, a notice for the instance administrators and a field in `/api/health`.

- **The canary.** A fixed text sealed in `app_settings`. If it reads back, the secret is the right one and nothing else is read.
- **Otherwise every sealed value is tried**, and the ones that fail are counted by kind (never shown). With none failing (a first start,
  or every secret entered again after the right key was lost) the canary is sealed again with the current secret and the notice goes.
"""
import logging
from collections import Counter
from collections.abc import Iterator

from sqlalchemy import select
from sqlalchemy.orm import Session

from .secretbox import SealedSecretError, seal, unseal

CANARY_KEY = "sealed_canary"
CANARY = "mimirsynth sealed canary"
log = logging.getLogger("mimirsynth")
_last: dict[str, int] = {}  # what the last check found unreadable, by kind: /api/health reads it without touching the database


def _sealed(db: Session) -> Iterator[tuple[str, str]]:
    """Every sealed value the instance keeps, with its kind."""
    from . import appsettings
    from .models import AppSetting, DecisionEngine, DocSource, EmbeddingEngine, LlmEngine, NotifyChannel, OidcProvider, User, Webhook
    for (v,) in db.execute(select(User.totp_secret).where(User.totp_enabled, User.totp_secret != "")):
        yield "two_factor", v
    for kind, model in (("llm", LlmEngine), ("embedding", EmbeddingEngine), ("decider", DecisionEngine)):
        for (v,) in db.execute(select(model.api_key_enc).where(model.api_key_enc != "")):
            yield kind, v
    for (v,) in db.execute(select(OidcProvider.client_secret).where(OidcProvider.client_secret != "")):
        yield "oidc", v
    for row in db.scalars(select(AppSetting).where(AppSetting.key.in_(appsettings.SECRET_KEYS))):
        if (row.value or {}).get("v"):
            yield "smtp", row.value["v"]
    for (v,) in db.execute(select(NotifyChannel.secret).where(NotifyChannel.secret != "")):
        yield "notifications", v
    for (v,) in db.execute(select(Webhook.secret_enc).where(Webhook.secret_enc != "")):
        yield "webhooks", v
    from .models import GraphConnection
    for (v,) in db.execute(select(GraphConnection.password_enc).where(GraphConnection.password_enc != "")):
        yield "graph", v
    for (cfg,) in db.execute(select(DocSource.config)):
        for v in ((cfg or {}).get("secrets") or {}).values():
            if v:
                yield "doc_sources", v


def _reads(token: str) -> bool:
    try:
        unseal(token)
        return True
    except SealedSecretError:
        return False


def check(db: Session) -> dict[str, int]:
    """The sealed values that cannot be read, counted by kind; empty when the secret is the right one."""
    from .models import AppSetting
    global _last
    row = db.get(AppSetting, CANARY_KEY)
    canary = (row.value or {}).get("v") if row else ""
    try:
        if canary and unseal(canary) == CANARY:
            _last = {}
            return _last
    except SealedSecretError:
        pass
    bad = Counter(kind for kind, v in _sealed(db) if not _reads(v))
    if not bad:  # nothing sealed yet, or everything was entered again with this secret: from now on the canary answers
        if row:
            row.value = {"v": seal(CANARY)}
        else:
            db.add(AppSetting(key=CANARY_KEY, value={"v": seal(CANARY)}))
        db.commit()
    _last = dict(bad)
    return _last


def unreadable() -> dict[str, int]:
    """What the last check found, without reading the database again."""
    return _last


def at_start(db: Session) -> None:
    """Checks at start and, if the secret is not the one that sealed the stored secrets, says so in one line of the log."""
    bad = check(db)
    if bad:
        log.error("MIMIRSYNTH_SESSION_SECRET does not match the one that sealed the stored secrets: %d sealed value(s) cannot be read (%s). "
                  "Restore the secret the instance was installed with; if it is lost, enter those secrets again and remove two-factor "
                  "authentication from the affected accounts. See Administration.", sum(bad.values()), ", ".join(f"{k}: {n}" for k, n in sorted(bad.items())))
