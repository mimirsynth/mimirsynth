"""Índice de texto de episodios (DocumentIndex): chunks + embeddings (pgvector) + texto completo, por brain."""
import hashlib
import math
import re
from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import Computed, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from .config import settings
from .db import graph, rows
from .embed import EmbeddingProvider, get_embedder
from .store import engine


class IndexBase(DeclarativeBase):
    pass


class EpisodeChunk(IndexBase):
    __tablename__ = "episode_chunks"
    __table_args__ = (
        UniqueConstraint("brain_id", "episode_uuid", "chunk_idx"),
        Index("ix_chunks_tsv", "tsv", postgresql_using="gin"),
        Index("ix_chunks_emb", "embedding", postgresql_using="hnsw", postgresql_with={"m": 16, "ef_construction": 64},
              postgresql_ops={"embedding": "vector_cosine_ops"}),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    brain_id: Mapped[int] = mapped_column(Integer, index=True)
    episode_uuid: Mapped[str] = mapped_column(String(64), index=True)
    chunk_idx: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(Text, default="")
    text: Mapped[str] = mapped_column(Text)
    valid_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64))
    embedding = mapped_column(Vector(settings.embedding_dim))
    tsv = mapped_column(TSVECTOR, Computed("to_tsvector('simple', coalesce(name,'') || ' ' || text)", persisted=True))


def enabled() -> bool:
    return settings.database_url.startswith("postgresql")


def init_index() -> None:
    if not enabled():
        return
    with engine().begin() as c:
        c.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    IndexBase.metadata.create_all(engine())


def chunk_text(body: str, size: int = 900, overlap: int = 120) -> list[str]:
    """Trocea por párrafos hasta ~`size` caracteres, con solape; los párrafos largos se parten por frases/longitud."""
    body = (body or "").strip()
    if not body:
        return []
    pieces: list[str] = []
    for para in re.split(r"\n\s*\n", body):
        para = para.strip()
        while len(para) > size:
            cut = max(para.rfind(". ", 0, size), para.rfind("\n", 0, size))
            cut = cut + 1 if cut > size // 2 else size
            pieces.append(para[:cut].strip()); para = para[max(cut - overlap, 1):].strip()
        if para:
            pieces.append(para)
    chunks, cur = [], ""
    for p in pieces:
        if cur and len(cur) + len(p) + 1 > size:
            chunks.append(cur); cur = cur[-overlap:] + "\n" + p if overlap else p
        else:
            cur = f"{cur}\n{p}" if cur else p
    if cur:
        chunks.append(cur)
    return chunks


def rrf(rankings: list[list], k: int = 60) -> list[tuple]:
    """Reciprocal Rank Fusion: fusiona listas ordenadas de ids. Devuelve [(id, score)] de mayor a menor."""
    score: dict = {}
    for lst in rankings:
        for i, x in enumerate(lst):
            score[x] = score.get(x, 0.0) + 1.0 / (k + i + 1)
    return sorted(score.items(), key=lambda kv: -kv[1])


def recency_factor(valid_at: str | None, weight: float, now: datetime | None = None, half_life_days: float = 45.0) -> float:
    """1 + weight * exp(-edad/vida): refuerza lo reciente sin descartar lo antiguo."""
    if not valid_at or weight <= 0:
        return 1.0
    try:
        d = datetime.fromisoformat(str(valid_at).replace("Z", "+00:00"))
    except ValueError:
        return 1.0
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    age = max(((now or datetime.now(timezone.utc)) - d).total_seconds() / 86400, 0.0)
    return 1.0 + weight * math.exp(-age / half_life_days)


def sync_brain(brain_id: int, graph_name: str, embedder: EmbeddingProvider | None = None) -> dict:
    """Sincroniza el índice con los episodios del grafo: solo reindexa los nuevos o modificados."""
    if not enabled():
        return {"enabled": False}
    embedder = embedder or get_embedder()
    eps = rows(graph(graph_name).query("MATCH (e:Episodic) RETURN e.uuid AS uuid, e.name AS name, e.content AS content, e.valid_at AS valid_at"))
    with engine().begin() as c:
        have = {r[0]: r[1] for r in c.execute(text("SELECT episode_uuid, min(content_hash) FROM episode_chunks WHERE brain_id=:b GROUP BY episode_uuid"), {"b": brain_id})}
    seen, todo = set(), []
    for e in eps:
        seen.add(e["uuid"])
        h = hashlib.sha256(f"{e['name']}\n{e['content']}".encode()).hexdigest()
        if have.get(e["uuid"]) != h:
            todo.append((e, h))
    removed = [u for u in have if u not in seen]
    n_chunks = 0
    for e, h in todo:
        chunks = chunk_text(e["content"] or "") or [e["name"] or ""]
        vecs = embedder.embed([f"{e['name']}\n{c}" for c in chunks])
        with engine().begin() as c:
            c.execute(text("DELETE FROM episode_chunks WHERE brain_id=:b AND episode_uuid=:u"), {"b": brain_id, "u": e["uuid"]})
            for i, (ch, v) in enumerate(zip(chunks, vecs)):
                c.execute(text("INSERT INTO episode_chunks (brain_id, episode_uuid, chunk_idx, name, text, valid_at, content_hash, embedding) "
                               "VALUES (:b,:u,:i,:n,:t,:v,:h,CAST(:e AS vector))"),
                          {"b": brain_id, "u": e["uuid"], "i": i, "n": e["name"], "t": ch, "v": e["valid_at"], "h": h, "e": str(v)})
        n_chunks += len(chunks)
    if removed:
        with engine().begin() as c:
            c.execute(text("DELETE FROM episode_chunks WHERE brain_id=:b AND episode_uuid = ANY(:u)"), {"b": brain_id, "u": removed})
    return {"enabled": True, "episodes": len(eps), "reindexed": len(todo), "chunks_written": n_chunks, "removed": len(removed)}


def status(brain_id: int) -> dict:
    if not enabled():
        return {"enabled": False, "chunks": 0, "episodes": 0}
    with engine().begin() as c:
        ch, ep = c.execute(text("SELECT count(*), count(DISTINCT episode_uuid) FROM episode_chunks WHERE brain_id=:b"), {"b": brain_id}).one()
    return {"enabled": True, "chunks": ch, "episodes": ep}


_STOP = set("""que qué como cómo donde dónde cuando cuándo cual cuál cuales quien quién esta está estan están estar ser son fue era
hay para por con los las del una uno unos unas sobre entre desde hasta pero porque ahora actual actualmente hoy sigue siguen
todavía aún existiendo existe existen cuál este estos esas esos más muy sin the and for with what where how does still now
current from that this are was were has have been""".split())


def _tsquery(q: str) -> str:
    toks = {t for t in re.findall(r"[\wáéíóúñü]{3,}", q.lower()) if t not in _STOP}  # solo alfanuméricos: no rompe tsquery
    return " | ".join(sorted(toks))


def search(brain_id: int, qvec: list[float], qtext: str, k: int = 4, pool: int = 40, recency: float = 0.12) -> list[dict]:
    """Búsqueda híbrida: vectorial (coseno) + texto completo (OR de términos), fusionadas con RRF."""
    if not enabled():
        return []
    with engine().begin() as c:
        vec = c.execute(text("SELECT id, name, text, valid_at, episode_uuid, 1 - (embedding <=> CAST(:q AS vector)) AS score FROM episode_chunks "
                             "WHERE brain_id=:b ORDER BY embedding <=> CAST(:q AS vector) LIMIT :n"), {"q": str(qvec), "b": brain_id, "n": pool}).mappings().all()
        tsq = _tsquery(qtext)
        fts = c.execute(text("SELECT id, name, text, valid_at, episode_uuid, ts_rank(tsv, to_tsquery('simple', :t)) AS score FROM episode_chunks "
                             "WHERE brain_id=:b AND tsv @@ to_tsquery('simple', :t) ORDER BY score DESC LIMIT :n"), {"t": tsq, "b": brain_id, "n": pool}).mappings().all() if tsq else []
    byid = {r["id"]: dict(r) for r in [*vec, *fts]}
    fused = rrf([[r["id"] for r in vec], [r["id"] for r in fts]])
    boosted = sorted(((cid, sc * recency_factor(byid[cid]["valid_at"], recency)) for cid, sc in fused), key=lambda kv: -kv[1])
    out = []
    for cid, sc in boosted[:k]:
        d = byid[cid]; d["rrf"] = round(sc, 5); d["score"] = round(float(d["score"]), 4); out.append(d)
    return out
