"""Conector EmbeddingProvider: cualquier endpoint OpenAI-compatible (Ollama, OpenAI, vLLM...)."""
from typing import Protocol

import httpx

from .config import settings


class EmbeddingProvider(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class OpenAICompatEmbedder:
    def __init__(self, base_url: str, model: str, api_key: str = "", timeout: float = 60.0):
        self.base_url, self.model, self.api_key, self.timeout = base_url.rstrip("/"), model, api_key, timeout

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        out: list[list[float]] = []
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        with httpx.Client(timeout=self.timeout) as c:
            for i in range(0, len(texts), 16):  # lotes
                r = c.post(f"{self.base_url}/embeddings", json={"model": self.model, "input": texts[i : i + 16]}, headers=headers)
                r.raise_for_status()
                out += [d["embedding"] for d in sorted(r.json()["data"], key=lambda d: d["index"])]
        return out


def resolve_embedding() -> dict:
    """Motor de embeddings por defecto de la base de datos; si no hay, el de las variables de entorno."""
    try:
        from .embeddings_admin import default_embedding
        from .store import _factory
        with _factory()() as db:
            e = default_embedding(db)
            if e:
                from .secretbox import unseal
                return {"base_url": e.base_url, "model": e.model, "api_key": unseal(e.api_key_enc), "dim": e.dim}
    except Exception:  # noqa: BLE001
        pass
    return {"base_url": settings.embedding_base_url, "model": settings.embedding_model, "api_key": settings.embedding_api_key, "dim": settings.embedding_dim}


def get_embedder() -> EmbeddingProvider:
    e = resolve_embedding()
    return OpenAICompatEmbedder(e["base_url"], e["model"], e["api_key"])
