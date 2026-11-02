"""Search every brain a person can read at once (#129): the same recall as Ask, run over each brain, grouped by brain.

- **Whose brains:** the person's own, with at least the reader role (their membership, or all of them for an instance administrator).
  Federation does not enter: a brain that only lends to another is not searched through it, and the answer never mentions a brain the
  person cannot read, not even as a count.
- **Not for API tokens:** they stay bound to one brain, so a token gets 403.
- **The query's vector is computed once** and given to every brain: they share the instance's embedding engine. That is the costly
  part of a recall, so it is paid once instead of once per brain.
- **In parallel, with a limit:** at most PARALLEL brains at a time, and the answer waits at most WAIT_SECONDS. A brain that is not
  done by then is marked `timeout`, and one that fails `error`; neither stops the others. Each brain also keeps the timeout of its
  own document search, as in Ask.
- The result of each brain is the recall's, without the context text (the agents' injection, not wanted here) and without its rating
  log: there is no `recall_id` to rate from here.
"""
import logging
import time
from concurrent.futures import ThreadPoolExecutor, wait

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .deps import current_user, effective_role
from .i18n import language
from .models import Brain, User
from .roles import allows
from .store import get_db

log = logging.getLogger("mimirsynth.search")
router = APIRouter(prefix="/api/search")
PARALLEL = 4
WAIT_SECONDS = 8.0
_pool = ThreadPoolExecutor(max_workers=PARALLEL, thread_name_prefix="search")


class SearchIn(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    facts: int = Field(5, ge=0, le=20)
    chunks: int = Field(3, ge=0, le=10)


class _Fixed:
    """An embedder that gives back a vector already computed: the query's, for every brain."""

    def __init__(self, vec: list[float]):
        self.vec = vec

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self.vec for _ in texts]


def readable(db: Session, user: User) -> list[tuple[Brain, str]]:
    """The brains the person can read, with their role, by name."""
    out = []
    for b in db.scalars(select(Brain).order_by(Brain.name)):
        role = effective_role(db, user, b)
        if allows(role, "reader"):
            out.append((b, role))
    return out


def _one(brain_id: int, graph_name: str, body: SearchIn, vec: list[float], lang: str) -> dict:
    from .recall import recall
    out = recall(brain_id, graph_name, body.query, body.facts, body.chunks, embedder=_Fixed(vec), lang=lang)
    return {k: out.get(k) for k in ("facts", "chunks", "documents", "documents_state")}


@router.post("")
def search(body: SearchIn, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """The recall of `query` in each brain the person can read, grouped by brain, with the state of each: ok, timeout or error."""
    if getattr(request.state, "token", None) is not None:
        raise HTTPException(403, "la búsqueda en todos los brains no está disponible para tokens de API")
    t0 = time.time()
    brains = readable(db, user)
    if not brains:
        return {"query": body.query, "brains": [], "ms": 0}
    from .embed import get_embedder
    from .usage import scope
    try:
        with scope(None, "recall"):
            vec = get_embedder().embed([body.query])[0]
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"el modelo de embeddings no responde: {str(e)[:200]}") from e
    lang = language(request)
    futures = {_pool.submit(_one, b.id, b.graph_name, body, vec, lang): (b, role) for b, role in brains}
    wait(futures, timeout=WAIT_SECONDS)
    out = []
    for fut, (b, role) in futures.items():
        item = {"slug": b.slug, "name": b.name, "role": role, "state": "ok", "facts": [], "chunks": [], "documents": []}
        if not fut.done():
            item["state"] = "timeout"
            fut.cancel()   # if it has not started yet, it will not
        elif fut.exception() is not None:
            item["state"] = "error"
            log.warning("búsqueda global: falló el brain %s: %s", b.slug, fut.exception())
        else:
            res = fut.result()
            item.update(facts=res["facts"] or [], chunks=res["chunks"] or [], documents=res["documents"] or [],
                        documents_state=res["documents_state"])
        out.append(item)
    out.sort(key=lambda i: (not (i["facts"] or i["chunks"] or i["documents"]), i["name"].lower()))
    return {"query": body.query, "brains": out, "ms": round((time.time() - t0) * 1000)}
