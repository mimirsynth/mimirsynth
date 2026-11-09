"""When the full check of a model runs, what is kept of it and when it raises a notice (#424).

#420 made the LLM checks ask for what ingestion needs: graphiti's extraction request with its JSON schema (about 2,000 tokens), and the
decider's letter with logprobs. Sent by the periodic health check that was 144 requests a day per model on an idle instance. So:

- the periodic check (`notify.check_health`, every `notify_health_minutes`) is a cheap ping again (`llmcheck.ping`): it only says
  whether the model is there, and raises `model.unavailable` when it is not;
- the full check (`check`) runs on **Test**, **Add** and **Edit** of an engine and in the setup wizard's LLM and decider steps, and
  `due` runs it on the engine in use when it changed (another engine made default, its model or endpoint edited) and at most once a day;
- every full check is kept on the engine (`fitness`, shown in Administration); on the engine in use, a model that answers but fails it
  raises `model.unavailable` with the wording of #420 under its own key, `llm.fit` or `decider.fit`, so the ping answering does not close
  it, and a check that passes does. A failed ingestion caused by the model's answer still raises `ingest.failed` on its own (#423).

The record: {at, for, ok, fit, text, warning?, default}. `for` is the endpoint and model it was made with: an edit changes it. `fit` is the
verdict: True, False (the model answers, but not in the form it is used in) or None (it could not be asked: no verdict, retried after an
hour). `default` says whether the engine was the one in use; an engine made default after a check made while it was not is checked again.
"""
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from . import llmcheck
from .i18n import T

log = logging.getLogger("mimirsynth.fitness")

DAY = timedelta(days=1)
RETRY = timedelta(hours=1)  # a check that got no verdict (the endpoint did not answer) is tried again sooner than the next day
KINDS = ("llm", "decider")
TITLES = {
    "llm": T("El modelo LLM no devuelve la salida estructurada que necesita la ingesta"),  # #420's notice
    "decider": T("El decisor responde, pero no con una letra de las opciones y sus logprobs"),
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def fingerprint(e) -> str:
    return f"{e.base_url.rstrip('/')}|{e.model}"


def _key(e) -> str:
    from .secretbox import unseal
    return unseal(e.api_key_enc) if e.api_key_enc else ""


def check(db: Session, kind: str, e, quality: bool = False) -> dict:
    """The full check of engine `e` (an `LlmEngine` for "llm", a `DecisionEngine` for "decider"), kept on it. Returns the check's own
    answer ({ok, ms, reply | error, warning?, structured}). On the engine in use, a verdict also raises or closes the notice."""
    key = _key(e)  # a key that cannot be read raises here, before anything is sent: the caller's own clear answer (#193)
    r = llmcheck.structured(e.base_url, e.model, key, quality=quality) if kind == "llm" else llmcheck.decider(e.base_url, e.model, key)
    fit = r.get("structured")
    e.fitness = {"at": _now().isoformat(), "for": fingerprint(e), "ok": bool(r["ok"]), "fit": fit,
                 "text": (r.get("reply") if r["ok"] else r.get("error")) or "", "default": bool(e.is_default and e.enabled)}
    if r.get("warning"):
        e.fitness["warning"] = r["warning"]
    db.commit()
    if e.is_default and e.enabled and fit is not None:
        _notice(kind, e.name, fit, r.get("error") or "")
    return r


def _notice(kind: str, name: str, fit: bool, error: str) -> None:
    from . import notify
    if fit:
        notify.resolve("model.unavailable", f"{kind}.fit")
    else:
        notify.emit("model.unavailable", TITLES[kind], f"Motor «{name}»: {error[:400]}", key=f"{kind}.fit")


def made_default(e) -> None:
    """Called before an engine becomes the one in use: a check made while it was not counts no more, so `due` checks it once."""
    if not e.is_default and e.fitness:
        e.fitness = {**e.fitness, "default": False}


def needed(e, daily: bool = True) -> bool:
    """Whether the engine in use needs the full check now: never checked, changed since (endpoint, model, or made default), or its last
    check is older than a day (an hour when it got no verdict). Without `daily`, only the first two."""
    rec = e.fitness or {}
    if not rec.get("at") or rec.get("for") != fingerprint(e) or not rec.get("default"):
        return True
    if not daily:
        return False
    try:
        at = datetime.fromisoformat(rec["at"])
    except (TypeError, ValueError):
        return True
    return _now() - at >= (DAY if rec.get("fit") is not None else RETRY)


def due(daily: bool = True) -> int:
    """Runs the full check on the default LLM and decider where `needed`. Called every minute by the notifications worker, so a change of
    engine is checked within a minute; `daily` is off when the periodic health check is (`notify_health_minutes` = 0). Returns how many ran."""
    from .deciders_admin import default_decider
    from .llm import default_engine
    from .store import _factory
    n = 0
    with _factory()() as db:
        for kind, e in (("llm", default_engine(db)), ("decider", default_decider(db))):
            if e is None or not needed(e, daily):
                continue
            try:
                check(db, kind, e)
                n += 1
            except Exception:  # noqa: BLE001  (a key that cannot be read, a database error: the next round tries again)
                log.exception("no se pudo hacer la comprobación completa del %s «%s»", kind, e.name)
                db.rollback()
    return n


def view(e) -> dict | None:
    """What Administration shows of the last full check of an engine: {at, ok, fit, text, warning?}, or None before the first one."""
    rec = e.fitness if e is not None else None
    if not rec or not rec.get("at"):
        return None
    return {k: rec[k] for k in ("at", "ok", "fit", "text", "warning") if k in rec} | {"current": rec.get("for") == fingerprint(e)}
