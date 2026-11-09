"""The setup wizard (#361): a guided first run, from the administrator's account to an agent's first recall, that an administrator can leave
at any step and resume where it stopped, on any device.

Steps, in order: admin → graph → embedding → llm → decider → brain → token → agent.
- **What is kept.** One row in `app_settings` (`setup_wizard`): each step marked done or skipped, the brain and the token the wizard made
  or chose, and whether the wizard was finished. The step to resume on is the first one neither done nor skipped.
- **What blocks.** The graph and the embedding steps are only marked done after the server checks them: the graph connection in force
  passes its full test (`graphconn.probe`), and the embedding engine in use answers with the dimension the instance indexes. Neither
  can be skipped. The LLM and the decider can: without an LLM, approved proposals are not ingested, and the home screen says so for as
  long as there is none.
- **Who sees it.** Only instance administrators. A fresh instance (no brains and no wizard row yet) opens it on the first visit; an
  instance that had brains before this version counts as set up, and an administrator can reopen the wizard from Administration.
- **Ollama.** The embedding step looks for a local Ollama at the usual addresses (the bundled one, the host, this machine), lists its
  models and can pull `nomic-embed-text`, as a background job.
"""
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import graphconn, i18n, jobs
from .config import settings
from .deps import audit, require_admin
from .models import ApiToken, AppSetting, Brain, Job, RecallLog, User
from .store import get_db

router = APIRouter(prefix="/api/setup")
log = logging.getLogger("mimirsynth")

KEY = "setup_wizard"
STEPS = ("admin", "graph", "embedding", "llm", "decider", "brain", "token", "agent")
BLOCKING = ("graph", "embedding")  # checked by the server, never skipped
SKIPPABLE = ("llm", "decider", "agent")
OLLAMA = ("http://ollama:11434", "http://host.docker.internal:11434", "http://localhost:11434")  # bundled, the host, this machine
OLLAMA_MODEL = "nomic-embed-text"
FIND_WAIT = 4.0  # seconds the search for a local Ollama may take in all
_FIND = ThreadPoolExecutor(max_workers=6, thread_name_prefix="ollama-find")
PULL = "setup.ollama_pull"


# --- the state -------------------------------------------------------------------------------------

def _row(db: Session) -> AppSetting | None:
    return db.get(AppSetting, KEY)


def _state(db: Session) -> dict | None:
    row = _row(db)
    return dict((row.value or {}).get("v") or {}) if row else None


def _save(db: Session, st: dict, user: User | None) -> None:
    row = _row(db) or AppSetting(key=KEY)
    row.value = {"v": st}
    row.updated_at = datetime.now(timezone.utc)
    row.updated_by = user.id if user else None
    db.add(row)
    db.commit()


def _fresh() -> dict:
    return {"marks": {"admin": "done"}, "brain": None, "token_id": None, "finished": False}


def finished(db: Session) -> bool:
    """Whether the instance counts as set up: the wizard was finished or, before this version existed, there was already a brain."""
    st = _state(db)
    if st is None:
        return db.scalar(select(Brain.id).limit(1)) is not None
    return bool(st.get("finished"))


def _brain(db: Session, st: dict) -> Brain | None:
    return db.scalar(select(Brain).where(Brain.slug == st["brain"])) if st.get("brain") else None


def _agent_connected(db: Session, st: dict) -> bool:
    """The agent's first recall through the wizard's token (or any token of its brain), even one that found nothing (#421)."""
    b = _brain(db, st)
    if not b:
        return False
    q = select(RecallLog.id).where(RecallLog.brain_id == b.id, RecallLog.token_id.is_not(None))
    return db.scalar(q.limit(1)) is not None


def view(db: Session) -> dict:
    st = _state(db)
    done = finished(db)
    st = st or {**_fresh(), "finished": done}
    marks = st.get("marks") or {}
    steps = [{"key": k, "status": marks.get(k, "todo"), "blocking": k in BLOCKING, "skippable": k in SKIPPABLE} for k in STEPS]
    current = next((s["key"] for s in steps if s["status"] == "todo"), STEPS[-1])
    from .deciders_admin import default_decider
    from .embed import resolve_embedding
    from .llm import default_engine
    emb, llm, dec = resolve_embedding(), default_engine(db), default_decider(db)
    return {
        "finished": bool(st.get("finished")), "current": current, "steps": steps, "brain": st.get("brain"), "token_id": st.get("token_id"),
        "graph": graphconn.describe(db),
        "embedding": {"model": emb["model"], "base_url": emb["base_url"], "dim": emb["dim"], "index_dim": settings.embedding_dim},
        "llm": {"configured": bool(llm) or bool(settings.llm_base_url and settings.llm_model), "name": llm.name if llm else None},
        "decider": {"configured": bool(dec), "name": dec.name if dec else None},
        "agent_connected": _agent_connected(db, st),
    }


@router.get("")
def get_wizard(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return view(db)


# --- marking a step --------------------------------------------------------------------------------

class MarkIn(BaseModel):
    action: str = Field(pattern="^(done|skip)$")
    brain: str | None = None
    token_id: int | None = None


def _check_graph(lang: str) -> None:
    r = graphconn.probe(graphconn.current()[0], lang)
    if not r["ok"]:
        raise HTTPException(409, f"la base de datos del grafo no pasa la prueba: {r['error']['message']}")


def _check_embedding(lang: str) -> None:
    from .embed import resolve_embedding
    from .embeddings_admin import _probe
    e = resolve_embedding()
    try:
        dim = _probe(e["base_url"], e["model"], e["api_key"])
    except HTTPException as ex:
        raise HTTPException(409, f"el motor de embeddings no responde: {ex.detail}") from None
    if dim != settings.embedding_dim:
        raise HTTPException(409, f"el modelo de embeddings da {dim} dimensiones y el índice de esta instancia es de {settings.embedding_dim}: "
                                 "usa un modelo de esa dimensión, o pásate a este con «Reindexar»")


def _check_llm() -> None:
    from .aistatus import _llm_ping
    from .llm import resolve
    from .store import _factory
    with _factory()() as s:
        e = resolve(s)
    if not e and settings.llm_base_url and settings.llm_model:
        e = {"base_url": settings.llm_base_url, "model": settings.llm_model, "api_key": settings.llm_api_key}
    if not e:
        raise HTTPException(409, "no hay ningún motor LLM: añade uno, o sáltate este paso")
    try:
        _llm_ping(e["base_url"], e["model"], e["api_key"])
    except RuntimeError as ex:
        raise HTTPException(409, f"el motor LLM no responde: {ex}") from None


@router.post("/steps/{step}")
def mark(step: str, body: MarkIn, request: Request, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    if step not in STEPS:
        raise HTTPException(404, "paso desconocido")
    if body.action == "skip" and step not in SKIPPABLE:
        raise HTTPException(409, "este paso no se puede saltar")
    lang = i18n.language(request)
    st = _state(db) or _fresh()
    if body.action == "done":
        if step == "graph":
            _check_graph(lang)
        elif step == "embedding":
            _check_embedding(lang)
        elif step == "llm":
            _check_llm()
        elif step == "decider":
            from .deciders_admin import default_decider
            if not default_decider(db):
                raise HTTPException(409, "no hay ningún decisor: añade uno, o sáltate este paso")
        elif step == "brain":
            if not body.brain or not db.scalar(select(Brain.id).where(Brain.slug == body.brain)):
                raise HTTPException(409, "elige o crea un brain")
            st["brain"] = body.brain
        elif step == "token":
            b = _brain(db, st)
            tok = db.get(ApiToken, body.token_id) if body.token_id else None
            if not b or not tok or tok.brain_id != b.id or tok.revoked:
                raise HTTPException(409, "crea un token para el brain del asistente")
            st["token_id"] = tok.id
    st.setdefault("marks", {})[step] = "done" if body.action == "done" else "skipped"
    if step == "agent":
        st["finished"] = True
        audit(db, user, "setup.finish", None, skipped=[k for k, v in st["marks"].items() if v == "skipped"])
    _save(db, st, user)
    return view(db)


@router.post("/reopen")
def reopen(user: User = Depends(require_admin), db: Session = Depends(get_db)):
    """From Administration: back to the wizard, with what was done kept."""
    st = _state(db) or _fresh()
    st["finished"] = False
    _save(db, st, user)
    return view(db)


@router.post("/close")
def close(user: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Leaves the wizard for good without going through the rest (the instance is configured by hand)."""
    st = _state(db) or _fresh()
    st["finished"] = True
    _save(db, st, user)
    audit(db, user, "setup.close", None, step=view(db)["current"])
    return view(db)


# --- Ollama --------------------------------------------------------------------------------------------

def _ollama_bases() -> list[str]:
    """Where a local Ollama may answer: the configured embedding endpoint's host when it is Ollama's port, then the usual addresses."""
    out = []
    base = settings.embedding_base_url.split("/v1")[0].rstrip("/")
    if base.endswith(":11434"):
        out.append(base)
    return list(dict.fromkeys(out + list(OLLAMA)))


@router.get("/ollama")
def find_ollama(_: User = Depends(require_admin)):
    """The first local Ollama that answers, in the order of `_ollama_bases`, with its models; `found` is null when none does. Every address
    is asked at once and the whole search takes at most FIND_WAIT seconds: a name that does not resolve can make the system's DNS lookup
    wait far longer than any connect timeout."""
    def tags(base: str) -> list[str] | None:
        try:
            r = httpx.get(f"{base}/api/tags", timeout=2)
            return sorted(m.get("name", "") for m in r.json().get("models", [])) if r.status_code == 200 else None
        except (httpx.HTTPError, ValueError):
            return None
    bases = _ollama_bases()
    futures = {b: _FIND.submit(tags, b) for b in bases}
    deadline = time.monotonic() + FIND_WAIT
    for base in bases:
        try:
            models = futures[base].result(timeout=max(0.0, deadline - time.monotonic()))
        except Exception:  # noqa: BLE001  (still resolving when the wait ran out)
            models = None
        if models is not None:
            return {"found": base, "openai_base": f"{base}/v1", "models": models, "suggested": OLLAMA_MODEL,
                    "has_suggested": any(m.split(":")[0] == OLLAMA_MODEL for m in models)}
    return {"found": None, "openai_base": None, "models": [], "suggested": OLLAMA_MODEL, "has_suggested": False, "tried": bases}


class PullIn(BaseModel):
    base: str
    model: str = Field(OLLAMA_MODEL, pattern=r"^[A-Za-z0-9._:/-]{1,120}$")


@jobs.register(PULL, "Descargar un modelo de Ollama", limit=1)
def _pull(ctx: jobs.JobCtx, p: dict) -> dict:
    with httpx.stream("POST", f"{p['base']}/api/pull", json={"model": p["model"], "stream": True}, timeout=httpx.Timeout(30, read=600)) as r:
        if r.status_code != 200:
            raise RuntimeError(f"Ollama respondió HTTP {r.status_code}")
        for line in r.iter_lines():
            ctx.check()
            if not line:
                continue
            m = json.loads(line)
            if m.get("error"):
                raise RuntimeError(f"Ollama: {m['error'][:200]}")
            if m.get("total"):
                ctx.progress(int(m.get("completed") or 0), int(m["total"]), m.get("status"))
            elif m.get("status"):
                ctx.note(m["status"])
    return {"model": p["model"]}


@router.post("/ollama/pull", status_code=202)
def pull(body: PullIn, user: User = Depends(require_admin)):
    if body.base not in _ollama_bases():  # only the addresses the wizard looks at, never one from the request
        raise HTTPException(400, "dirección de Ollama no reconocida")
    jid = jobs.submit(PULL, None, {"base": body.base, "model": body.model}, f"Descargar {body.model}", user.id, dedupe_key=f"{PULL}:{body.model}")
    return {"job_id": jid}


@router.get("/jobs/{jid}")
def pull_status(jid: int, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    j = db.get(Job, jid)
    if not j or j.kind != PULL:
        raise HTTPException(404, "trabajo no encontrado")
    return jobs.out(j, detail=True)
