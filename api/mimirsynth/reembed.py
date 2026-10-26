"""Cambio de modelo de embeddings con reindexado completo: un trabajo de la cola, reanudable, con progreso y cancelación. Sin LLM.

Qué se recalcula con el motor nuevo, para cada brain:
- FalkorDB, en el formato de graphiti-core 0.30.2 (`vecf32`): `name_embedding` de las entidades (y de las comunidades, si las hay)
  y `fact_embedding` de los hechos (aristas RELATES_TO). Entrada: el nombre o el hecho con los saltos de línea como espacios, como Graphiti.
- pgvector: los trozos de episodios (`episode_chunks`) y de documentos (`doc_chunks`), con el mismo texto que al indexarlos.

Cómo, sin que nada deje de funcionar mientras tanto:
1. Relleno. Los vectores nuevos se guardan aparte: en propiedades sombra (`<vector>_reindex`, junto al texto del que salen en
   `<vector>_reindex_src`) y en una columna sombra `embedding_reindex vector(<dimensión nueva>)` con su propio índice HNSW. El recall,
   la ingesta y el índice siguen con el motor anterior. Al reanudar o reintentar solo se calcula lo que falta o lo que ha cambiado.
2. Cambio. Con las escrituras de vectores en pausa (`embed.gate`) se completa lo que haya cambiado entretanto, se intercambian los
   vectores de cada grafo (los anteriores quedan en `<vector>_prev`) y, en una sola transacción, se sustituyen columnas e índices de
   pgvector y se marca el motor nuevo como el por defecto. Si algo falla, los grafos recuperan sus vectores y todo sigue con el motor
   anterior. Tras el éxito se borran los vectores anteriores.
Los grafos sin brain no se tocan.
"""
import logging
import time

from sqlalchemy import select, text

from . import index, jobs
from .db import graph, list_graphs, rows
from .embed import OpenAICompatEmbedder, gate, resolve_embedding
from .models import Brain, EmbeddingEngine, Job
from .secretbox import unseal
from .store import _factory, engine

log = logging.getLogger("mimirsynth.reembed")
KIND = "embedding.reindex"
BATCH = 64
RETRY_WAIT = 4.0  # segundos (por intento) antes de reintentar una llamada fallida al motor
# (tipo, etiqueta, propiedad con el texto, propiedad con el vector)
ITEMS = (
    ("node", "Entity", "name", "name_embedding"),
    ("node", "Community", "name", "name_embedding"),
    ("edge", "RELATES_TO", "fact", "fact_embedding"),
)
# (tabla, índice HNSW, trozos sin vector nuevo, columnas, texto de entrada tal como se calculó al indexarlos)
TABLES = (
    ("episode_chunks", "ix_chunks_emb", "FROM episode_chunks c WHERE c.embedding_reindex IS NULL", "c.id, c.name, c.text",
     lambda r: f"{r.name}\n{r.text}"),
    ("doc_chunks", "ix_doc_chunks_emb", "FROM doc_chunks c JOIN documents d ON d.id = c.document_id WHERE c.embedding_reindex IS NULL",
     "c.id, d.title, c.heading_path, c.text", lambda r: f"{r.title}\n{r.heading_path}\n{r.text}"),
)


def is_shadow(prop: str) -> bool:
    """Propiedades auxiliares del cambio de modelo: no se muestran ni se copian."""
    return prop.startswith(("name_embedding_", "fact_embedding_"))


def _embedder(e: EmbeddingEngine) -> OpenAICompatEmbedder:
    return OpenAICompatEmbedder(e.base_url, e.model, unseal(e.api_key_enc))


def _embed(emb, texts: list[str], dim: int) -> list[list[float]]:
    for attempt in range(1, 4):
        try:
            vecs = emb.embed(texts)
            break
        except Exception:  # noqa: BLE001
            if attempt == 3:
                raise
            time.sleep(RETRY_WAIT * attempt)
    if len(vecs) != len(texts):
        raise RuntimeError(f"el motor devolvió {len(vecs)} vectores para {len(texts)} textos")
    bad = next((len(v) for v in vecs if len(v) != dim), None)
    if bad is not None:
        raise RuntimeError(f"el motor devolvió vectores de {bad} dimensiones; se esperaban {dim}")
    return vecs


# --- FalkorDB -------------------------------------------------------------------------------------

def _graphs() -> list[str]:
    with _factory()() as db:
        names = list(dict.fromkeys(db.scalars(select(Brain.graph_name).order_by(Brain.id))))
    have = set(list_graphs())
    return [g for g in names if g in have]


def _match(kind: str, label: str, by_uuid: bool = False) -> str:
    k = " {uuid: r.u}" if by_uuid else ""
    return f"(x:{label}{k})" if kind == "node" else f"()-[x:{label}{k}]->()"


def _pending(txt: str, vec: str) -> str:
    return (f"x.uuid IS NOT NULL AND x.{txt} IS NOT NULL AND x.{txt} <> '' "
            f"AND (x.{vec}_reindex IS NULL OR x.{vec}_reindex_src IS NULL OR x.{vec}_reindex_src <> x.{txt})")


def _count_graph(name: str) -> int:
    g = graph(name)
    return sum(rows(g.query(f"MATCH {_match(k, lb)} WHERE {_pending(t, v)} RETURN count(x) AS n"))[0]["n"] for k, lb, t, v in ITEMS)


def _fill_graph(name: str, emb, dim: int, tick) -> dict:
    g, out = graph(name), {}
    for kind, label, txt, vec in ITEMS:
        n, last = 0, None
        while True:
            batch = rows(g.query(f"MATCH {_match(kind, label)} WHERE {_pending(txt, vec)} RETURN x.uuid AS u, x.{txt} AS t LIMIT {BATCH}"))
            if not batch:
                break
            uuids = [b["u"] for b in batch]
            if uuids == last:
                raise RuntimeError(f"no se pudieron guardar los vectores nuevos en el grafo «{name}» ({label})")
            last = uuids
            vecs = _embed(emb, [str(b["t"]).replace("\n", " ") for b in batch], dim)
            g.query(f"UNWIND $rows AS r MATCH {_match(kind, label, True)} SET x.{vec}_reindex = vecf32(r.v), x.{vec}_reindex_src = r.t",
                    {"rows": [{"u": b["u"], "t": b["t"], "v": v} for b, v in zip(batch, vecs)]})
            n += len(batch)
            tick(len(batch), f"grafo «{name}»: {label}")
        if n:
            out[label] = n
    return out


def _swap_graph(name: str) -> None:
    g = graph(name)
    for kind, label, _, vec in ITEMS:
        g.query(f"MATCH {_match(kind, label)} WHERE x.{vec}_reindex IS NOT NULL WITH x, x.{vec} AS old, x.{vec}_reindex AS new "
                f"SET x.{vec}_prev = old, x.{vec} = new, x.{vec}_reindex = NULL, x.{vec}_reindex_src = NULL")


def _unswap_graph(name: str) -> None:
    """Deshace el intercambio: vuelve el vector anterior y deja el nuevo como sombra (un reintento no tendrá que recalcularlo)."""
    g = graph(name)
    for kind, label, txt, vec in ITEMS:
        g.query(f"MATCH {_match(kind, label)} WHERE x.{vec}_prev IS NOT NULL WITH x, x.{vec} AS new, x.{vec}_prev AS old "
                f"SET x.{vec}_reindex = new, x.{vec}_reindex_src = x.{txt}, x.{vec} = old, x.{vec}_prev = NULL")


def _has_prev(name: str) -> bool:
    g = graph(name)
    return any(rows(g.query(f"MATCH {_match(k, lb)} WHERE x.{v}_prev IS NOT NULL RETURN count(x) AS n"))[0]["n"] for k, lb, _, v in ITEMS)


def _drop_prev(name: str) -> None:
    g = graph(name)
    for kind, label, _, vec in ITEMS:
        g.query(f"MATCH {_match(kind, label)} WHERE x.{vec}_prev IS NOT NULL SET x.{vec}_prev = NULL")


def _wipe_graph(name: str) -> None:
    g = graph(name)
    for kind, label, _, vec in ITEMS:
        g.query(f"MATCH {_match(kind, label)} WHERE x.{vec}_reindex IS NOT NULL OR x.{vec}_reindex_src IS NOT NULL "
                f"SET x.{vec}_reindex = NULL, x.{vec}_reindex_src = NULL")


# --- pgvector -------------------------------------------------------------------------------------

def _tables(c) -> list[tuple]:
    return [t for t in TABLES if c.execute(text("SELECT to_regclass(:t)"), {"t": t[0]}).scalar()]


def _shadow_type(c, table: str) -> str | None:
    return c.execute(text("SELECT format_type(atttypid, atttypmod) FROM pg_attribute WHERE attrelid = to_regclass(:t) "
                          "AND attname = 'embedding_reindex' AND NOT attisdropped"), {"t": table}).scalar()


def _prepare_pg(dim: int) -> None:
    """Columna sombra con la dimensión nueva (se rehace si quedó de un intento con otra dimensión)."""
    with engine().begin() as c:
        for table, ix, *_ in _tables(c):
            cur = _shadow_type(c, table)
            if cur and cur != f"vector({dim})":
                c.execute(text(f"DROP INDEX IF EXISTS {ix}_reindex"))
                c.execute(text(f"ALTER TABLE {table} DROP COLUMN embedding_reindex"))
                cur = None
            if not cur:
                c.execute(text(f"ALTER TABLE {table} ADD COLUMN embedding_reindex vector({dim})"))


def _count_pg() -> int:
    with engine().begin() as c:
        return sum(c.execute(text(f"SELECT count(*) {where}")).scalar() for _, _, where, *_ in _tables(c))


def _fill_pg(emb, dim: int, tick) -> dict:
    out = {}
    with engine().begin() as c:
        present = _tables(c)
    for table, _, where, cols, txt in present:
        n = 0
        while True:
            with engine().begin() as c:
                batch = c.execute(text(f"SELECT {cols} {where} ORDER BY c.id LIMIT :n"), {"n": BATCH}).all()
            if not batch:
                break
            vecs = _embed(emb, [txt(r) for r in batch], dim)
            with engine().begin() as c:
                c.execute(text(f"UPDATE {table} SET embedding_reindex = CAST(:v AS vector) WHERE id = :i"),
                          [{"i": r.id, "v": str(v)} for r, v in zip(batch, vecs)])
            n += len(batch)
            tick(len(batch), f"índice de texto: {table}")
        if n:
            out[table] = n
    return out


def _index_pg() -> None:
    with engine().begin() as c:
        for table, ix, *_ in _tables(c):
            c.execute(text(f"CREATE INDEX IF NOT EXISTS {ix}_reindex ON {table} USING hnsw (embedding_reindex vector_cosine_ops) "
                           "WITH (m = 16, ef_construction = 64)"))


def _wipe_pg() -> None:
    with engine().begin() as c:
        for table, ix, *_ in _tables(c):
            c.execute(text(f"DROP INDEX IF EXISTS {ix}_reindex"))
            c.execute(text(f"ALTER TABLE {table} DROP COLUMN IF EXISTS embedding_reindex"))


def _switch(eid: int) -> None:
    """En una sola transacción: columnas e índices de pgvector pasan a los nuevos y el motor nuevo queda como el por defecto."""
    with engine().begin() as c:
        if index.enabled():
            present = _tables(c)
            for table, *_ in present:
                c.execute(text(f"LOCK TABLE {table} IN ACCESS EXCLUSIVE MODE"))
            for table, ix, *_ in present:
                c.execute(text(f"DROP INDEX IF EXISTS {ix}"))
                c.execute(text(f"ALTER TABLE {table} DROP COLUMN embedding"))
                c.execute(text(f"ALTER TABLE {table} RENAME COLUMN embedding_reindex TO embedding"))
                c.execute(text(f"ALTER INDEX {ix}_reindex RENAME TO {ix}"))
        c.execute(text("UPDATE embedding_engines SET is_default = (id = :e)"), {"e": eid})


# --- trabajo --------------------------------------------------------------------------------------

def _wipe(graphs: list[str]) -> None:
    for g in graphs:
        _wipe_graph(g)
    if index.enabled():
        _wipe_pg()


def _recover(graphs: list[str], eid: int) -> None:
    """Un cambio interrumpido a medias (reinicio del servicio): si el motor nuevo no llegó a ser el por defecto, los grafos que ya
    se habían intercambiado vuelven a sus vectores; si llegó, solo queda borrar los vectores anteriores."""
    with _factory()() as db:
        current = db.scalar(select(EmbeddingEngine.id).where(EmbeddingEngine.is_default.is_(True)))
    for g in graphs:
        if _has_prev(g):
            (_drop_prev if current == eid else _unswap_graph)(g)


@jobs.register(KIND, "Cambio de modelo de embeddings", limit=1, resume=True)
def _job(ctx: "jobs.JobCtx", p: dict) -> dict:
    eid = p["engine_id"]
    with _factory()() as db:
        e = db.get(EmbeddingEngine, eid)
        if not e or not e.enabled:
            raise RuntimeError("el motor de embeddings ya no existe o está desactivado")
        target = {"name": e.name, "model": e.model, "dim": e.dim}
        emb = _embedder(e)
        prev = db.scalar(select(Job).where(Job.kind == KIND, Job.id < ctx.id).order_by(Job.id.desc()).limit(1))
        stale = prev is not None and (prev.params or {}).get("engine_id") != eid  # sombras de un intento hacia otro motor
    cur = resolve_embedding()
    before = {"model": cur["model"], "dim": cur["dim"]}
    dim, pg = target["dim"], index.enabled()
    graphs = _graphs()
    _recover(graphs, eid)
    if stale:
        _wipe(graphs)
    state = {"done": 0, "total": 0}

    def tick(n: int, msg: str) -> None:
        ctx.check()
        state["done"] += n
        state["total"] = max(state["total"], state["done"])
        ctx.progress(state["done"], state["total"], msg)

    try:
        if pg:
            _prepare_pg(dim)
        state["total"] = sum(_count_graph(g) for g in graphs) + (_count_pg() if pg else 0)
        ctx.progress(0, state["total"], "calculando los vectores nuevos")
        counts: dict = {}
        for g in graphs:
            for k, v in _fill_graph(g, emb, dim, tick).items():
                counts[k] = counts.get(k, 0) + v
        if pg:
            counts.update(_fill_pg(emb, dim, tick))
            ctx.progress(state["done"], state["total"], "creando los índices vectoriales nuevos")
            _index_pg()
        ctx.note("cambiando al motor nuevo: las escrituras de vectores esperan hasta que termine")
        with gate.switching():
            graphs = _graphs()  # también los brains creados mientras tanto
            for g in graphs:  # lo que haya cambiado entretanto
                _fill_graph(g, emb, dim, tick)
            if pg:
                _fill_pg(emb, dim, tick)
            with _factory()() as db:
                e = db.get(EmbeddingEngine, eid)
                if not e or not e.enabled:
                    raise RuntimeError("el motor de embeddings ya no existe o está desactivado")
            swapped: list[str] = []
            try:
                for g in graphs:
                    _swap_graph(g)
                    swapped.append(g)
                _switch(eid)
            except Exception:
                for g in swapped:
                    try:
                        _unswap_graph(g)
                    except Exception:  # noqa: BLE001
                        log.exception("no se pudo deshacer el cambio de vectores del grafo %s", g)
                raise
    except jobs.Cancelled:
        _wipe(_graphs())
        raise
    for g in graphs:
        try:
            _drop_prev(g)
        except Exception as ex:  # noqa: BLE001  (son vectores ya sin uso: no deshacen el cambio)
            ctx.note(f"no se pudieron borrar los vectores anteriores del grafo «{g}»: {str(ex)[:150]}")
    ctx.note("hecho: recalibra la similitud mínima de un pasaje del recall (Administración → Recuerdo) para el modelo nuevo")
    from .deps import audit
    with _factory()() as db:
        audit(db, None, "embedding.reindexed", None, name=target["name"], model=target["model"], dim=dim, previous=before["model"], counts=counts)
    return {"engine": target["name"], "model": target["model"], "dim": dim, "previous": before, "graphs": len(graphs), "counts": counts}
