"""Estado de los proveedores IA: qué está configurado y, para administradores, si responde."""
import time
from concurrent.futures import ThreadPoolExecutor
from functools import partial

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
    try:
        r = httpx.post(f"{base_url.rstrip('/')}/chat/completions", timeout=30, headers={"Authorization": f"Bearer {key}"} if key else {},
                       json={"model": model, "messages": [{"role": "user", "content": "ok"}], "max_tokens": 4})
    except Exception as ex:  # noqa: BLE001
        raise RuntimeError(f"no se pudo contactar con el endpoint: {str(ex)[:150]}")
    if r.status_code != 200:
        raise RuntimeError(f"el endpoint respondió HTTP {r.status_code}: {r.text[:150]}")


@router.get("/ai-status")
def ai_status(check: bool = False, user: User = Depends(current_user), db: Session = Depends(get_db)):
    from .deciders_admin import default_decider
    llm, emb, dec = default_engine(db), default_embedding(db), default_decider(db)
    llm_env = not llm and bool(settings.llm_base_url and settings.llm_model)
    out = {
        "llm": {"configured": bool(llm) or llm_env, "source": "db" if llm else ("env" if settings.llm_base_url else None), "name": llm.name if llm else None},
        "embedding": {"configured": True, "source": "db" if emb else "env", "name": emb.name if emb else None},
        "decider": {"configured": bool(dec), "source": "db" if dec else None, "name": dec.name if dec else None},
    }
    if check and user.is_admin:
        # Se sondea lo que de verdad se usa: el motor por defecto o, sin él, las variables MIMIRSYNTH_LLM_* y MIMIRSYNTH_EMBEDDING_*.
        probes = []
        if llm:
            probes.append(("llm", llm.model, partial(_llm_ping, llm.base_url, llm.model, unseal(llm.api_key_enc))))
        elif llm_env:
            probes.append(("llm", settings.llm_model, partial(_llm_ping, settings.llm_base_url, settings.llm_model, settings.llm_api_key)))
        if emb:
            probes.append(("embedding", emb.model, partial(_probe, emb.base_url, emb.model, unseal(emb.api_key_enc))))
        else:
            probes.append(("embedding", settings.embedding_model, partial(_probe, settings.embedding_base_url, settings.embedding_model, settings.embedding_api_key)))
        if dec:
            probes.append(("decider", dec.model, partial(_decider.decide, dec.base_url, dec.model, unseal(dec.api_key_enc), "x", "¿ok?", ["Sí", "No"], timeout=30)))

        def run(kind, model, fn):
            t0 = time.monotonic()
            try:
                fn(); out[kind]["healthy"] = True
            except Exception as e:  # noqa: BLE001
                out[kind]["healthy"] = False; out[kind]["error"] = str(getattr(e, "detail", None) or e)[:160]
            out[kind].update(model=model, ms=round((time.monotonic() - t0) * 1000))
        with ThreadPoolExecutor(max_workers=3) as pool:  # en paralelo: la espera es la del más lento, no la suma
            list(pool.map(lambda p: run(*p), probes))
    return out
