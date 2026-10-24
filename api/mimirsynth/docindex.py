"""Índice de la memoria documental: trozos con vector (pgvector) y texto completo, por brain. Reconstruible desde el almacén de ficheros."""
from pgvector.sqlalchemy import Vector
from sqlalchemy import Computed, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from .config import settings
from .index import IndexBase, _tsquery, enabled, rrf
from .store import engine


class DocChunk(IndexBase):
    __tablename__ = "doc_chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_idx"),
        Index("ix_doc_chunks_tsv", "tsv", postgresql_using="gin"),
        Index("ix_doc_chunks_emb", "embedding", postgresql_using="hnsw", postgresql_with={"m": 16, "ef_construction": 64},
              postgresql_ops={"embedding": "vector_cosine_ops"}),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    brain_id: Mapped[int] = mapped_column(Integer, index=True)
    document_id: Mapped[int] = mapped_column(Integer, index=True)
    chunk_idx: Mapped[int] = mapped_column(Integer)
    heading_path: Mapped[str] = mapped_column(Text, default="")
    char_start: Mapped[int] = mapped_column(Integer)
    char_end: Mapped[int] = mapped_column(Integer)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    text: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))
    embedding = mapped_column(Vector(settings.embedding_dim))
    tsv = mapped_column(TSVECTOR, Computed("to_tsvector('simple', coalesce(heading_path,'') || ' ' || text)", persisted=True))


def replace_chunks(brain_id: int, document_id: int, chunks: list[dict], vecs: list[list[float]], content_hash: str) -> None:
    """Sustituye en una sola transacción todos los trozos de un documento: una consulta nunca lo ve a medias."""
    with engine().begin() as c:
        c.execute(text("DELETE FROM doc_chunks WHERE document_id=:d"), {"d": document_id})
        if chunks:
            c.execute(text("INSERT INTO doc_chunks (brain_id, document_id, chunk_idx, heading_path, char_start, char_end, page, text, content_hash, embedding) "
                           "VALUES (:b,:d,:i,:h,:s,:e,:p,:t,:ch,CAST(:v AS vector))"),
                      [{"b": brain_id, "d": document_id, "i": ch["idx"], "h": ch["heading_path"], "s": ch["char_start"], "e": ch["char_end"], "p": ch["page"],
                        "t": ch["text"], "ch": content_hash, "v": str(v)} for ch, v in zip(chunks, vecs)])


def delete_document(document_id: int) -> None:
    if enabled():
        with engine().begin() as c:
            c.execute(text("DELETE FROM doc_chunks WHERE document_id=:d"), {"d": document_id})


def delete_brain(brain_id: int) -> None:
    if enabled():
        with engine().begin() as c:
            c.execute(text("DELETE FROM doc_chunks WHERE brain_id=:b"), {"b": brain_id})


def neighbors(document_id: int, idx: int, radius: int = 1) -> list[dict]:
    if not enabled():
        return []
    with engine().begin() as c:
        r = c.execute(text("SELECT chunk_idx, heading_path, char_start, char_end, page, text FROM doc_chunks WHERE document_id=:d AND chunk_idx BETWEEN :a AND :b ORDER BY chunk_idx"),
                      {"d": document_id, "a": idx - radius, "b": idx + radius}).mappings().all()
    return [dict(x) for x in r]


def list_chunks(document_id: int, limit: int = 200, offset: int = 0) -> list[dict]:
    if not enabled():
        return []
    with engine().begin() as c:
        r = c.execute(text("SELECT chunk_idx, heading_path, char_start, char_end, page, text FROM doc_chunks WHERE document_id=:d ORDER BY chunk_idx LIMIT :l OFFSET :o"),
                      {"d": document_id, "l": limit, "o": offset}).mappings().all()
    return [dict(x) for x in r]


_SEL = ("c.id AS id, c.document_id, c.chunk_idx, c.heading_path, c.char_start, c.char_end, c.page, c.text, d.title, d.filename, d.url, d.source_id, "
        "d.source_updated_at, d.last_seen_at")


def search(brain_id: int, qvec: list[float], qtext: str, k: int = 8, pool: int = 40, source_id: int | None = None) -> list[dict]:
    """Búsqueda híbrida: vectorial (coseno) + texto completo (OR de términos), fusionadas con RRF. Solo documentos activos."""
    if not enabled():
        return []
    src = " AND d.source_id=:s" if source_id else ""
    par = {"b": brain_id, "n": pool, **({"s": source_id} if source_id else {})}
    with engine().begin() as c:
        vec = c.execute(text(f"SELECT {_SEL}, 1 - (c.embedding <=> CAST(:q AS vector)) AS score FROM doc_chunks c JOIN documents d ON d.id=c.document_id "
                             f"WHERE c.brain_id=:b AND d.status='active'{src} ORDER BY c.embedding <=> CAST(:q AS vector) LIMIT :n"), {**par, "q": str(qvec)}).mappings().all()
        tsq = _tsquery(qtext)
        fts = c.execute(text(f"SELECT {_SEL}, ts_rank(c.tsv, to_tsquery('simple', :t)) AS score FROM doc_chunks c JOIN documents d ON d.id=c.document_id "
                             f"WHERE c.brain_id=:b AND d.status='active'{src} AND c.tsv @@ to_tsquery('simple', :t) ORDER BY score DESC LIMIT :n"), {**par, "t": tsq}).mappings().all() if tsq else []
    byid = {r["id"]: dict(r) for r in [*vec, *fts]}
    vscore = {r["id"]: float(r["score"]) for r in vec}
    out = []
    for cid, sc in rrf([[r["id"] for r in vec], [r["id"] for r in fts]])[:k]:
        d = byid[cid]
        d["rrf"] = round(sc, 5)
        d["similarity"] = round(vscore.get(cid, 0.0), 4)  # coseno; 0 si solo salió por texto completo
        d["score"] = d["rrf"]
        out.append(d)
    return out


def mentions(brain_id: int, phrases: list[str], limit: int = 20) -> list[dict]:
    """Documentos activos cuyo texto contiene alguna de las frases (búsqueda de frase en el índice de texto completo, sin embeddings).
    Devuelve por documento cuántos trozos coinciden y el mejor fragmento resaltado."""
    phrases = [p.strip() for p in phrases if p and len(p.strip()) >= 3][:8]
    if not enabled() or not phrases:
        return []
    q = " || ".join(f"phraseto_tsquery('simple', :p{i})" for i in range(len(phrases)))
    par = {f"p{i}": p for i, p in enumerate(phrases)} | {"b": brain_id, "n": limit}
    with engine().begin() as c:
        return [dict(r) for r in c.execute(text(
            f"WITH m AS (SELECT c.document_id, c.chunk_idx, c.heading_path, c.text, ts_rank(c.tsv, ({q})) AS r FROM doc_chunks c "
            f"JOIN documents d ON d.id=c.document_id WHERE c.brain_id=:b AND d.status='active' AND c.tsv @@ ({q})) "
            f"SELECT DISTINCT ON (m.document_id) m.document_id, d.title, d.url, d.filename, m.chunk_idx AS chunk, m.heading_path, "
            f"(SELECT count(*) FROM m m2 WHERE m2.document_id=m.document_id) AS chunks, "
            f"ts_headline('simple', m.text, ({q}), 'MaxWords=30, MinWords=12, StartSel=«, StopSel=»') AS snippet "
            f"FROM m JOIN documents d ON d.id=m.document_id ORDER BY m.document_id, m.r DESC"), par).mappings().all()][:limit]
