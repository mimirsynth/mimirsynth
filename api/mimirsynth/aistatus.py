"""Estado de los proveedores IA: qué está configurado y, para administradores, si responde."""
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from . import decider as _decider
from .config import settings
from .deps import current_user
from .embeddings_admin import _probe, default_embedding
from .llm import default_engine
from .models import User
from .secretbox import unseal
from .store import get_db

router = APIRouter(prefix="/api")


def _llm_ping(base_url: str, model: str, key: str) -> None:
    import httpx
    r = httpx.post(f"{base_url.rstrip('/')}/chat/completions", timeout=30, headers={"Authorization": f"Bearer {key}"} if key else {},
                   json={"model": model, "messages": [{"role": "user", "content": "ok"}], "max_tokens": 4})
    r.raise_for_status()


@router.get("/ai-status")
def ai_status(check: bool = False, user: User = Depends(current_user), db: Session = Depends(get_db)):
    from .deciders_admin import default_decider
    llm, emb, dec = default_engine(db), default_embedding(db), default_decider(db)
    out = {
        "llm": {"configured": bool(llm or (settings.llm_base_url and settings.llm_model)), "source": "db" if llm else ("env" if settings.llm_base_url else None), "name": llm.name if llm else None},
        "embedding": {"configured": True, "source": "db" if emb else "env", "name": emb.name if emb else None},
        "decider": {"configured": bool(dec), "source": "db" if dec else None, "name": dec.name if dec else None},
    }
    if check and user.is_admin:
        def run(kind, fn):
            try:
                fn(); out[kind]["healthy"] = True
            except Exception as e:  # noqa: BLE001
                out[kind]["healthy"] = False; out[kind]["error"] = str(e)[:160]
        if llm:
            run("llm", lambda: _llm_ping(llm.base_url, llm.model, unseal(llm.api_key_enc)))
        if emb:
            run("embedding", lambda: _probe(emb.base_url, emb.model, unseal(emb.api_key_enc)) and None)
        if dec:
            run("decider", lambda: _decider.decide(dec.base_url, dec.model, unseal(dec.api_key_enc), "x", "¿ok?", ["Sí", "No"], timeout=30))
    return out
