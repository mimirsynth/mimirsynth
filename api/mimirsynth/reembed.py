"""Cambio de modelo de embeddings, primer paso: relleno en sombra (#48). Un trabajo de la cola, reanudable, con progreso y
cancelación, que calcula con el motor nuevo todos los vectores sin tocar los que se usan. Sin LLM.

Qué se calcula, para cada brain:
- FalkorDB, en el formato de graphiti-core 0.30.2 (`vecf32`): `name_embedding` de las entidades (y de las comunidades, si las hay)
  y `fact_embedding` de los hechos (aristas RELATES_TO). Entrada: el nombre o el hecho con los saltos de línea como espacios, como Graphiti.
  Se guarda en `<vector>_reindex`, junto al texto del que sale en `<vector>_reindex_src`.
- pgvector: los trozos de episodios (`episode_chunks`) y de documentos (`doc_chunks`), con el mismo texto que al indexarlos. Se guarda
  en una columna sombra `embedding_reindex vector(<dimensión nueva>)` con su propio índice HNSW.

Nada de lo que usan el recall, la ingesta o el índice cambia: el motor por defecto sigue siendo el mismo. El intercambio llega en un
paso posterior. Al reanudar o reintentar solo se calcula lo que falta o lo que ha cambiado (el texto ya no coincide con `_src`).
Cancelar (o descartar) borra todas las propiedades sombra de FalkorDB y la columna y el índice sombra de PostgreSQL.
Los grafos sin brain no se tocan.
"""
import logging
import math
import time

import httpx
from sqlalchemy import select, text

from . import appsettings, index, jobs
from .db import client, graph, list_graphs, rows
from .embed import OpenAICompatEmbedder
from .models import Brain, EmbeddingEngine, Job
from .secretbox import unseal
from .store import _factory, engine

log = logging.getLogger("mimirsynth.reembed")
KIND = "embedding.reindex"
RETRY_WAIT = 4.0  # segundos (por intento) antes de reintentar una llamada fallida al motor
MAX_RETRY_AFTER = 300.0  # tope de espera que se acepta de un `Retry-After`
FALKOR_MARGIN = 1.5  # la memoria libre de FalkorDB debe superar la estimación por este factor
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


def _retry_after(ex: httpx.HTTPStatusError) -> float | None:
    try:
        return min(float(ex.response.headers.get("retry-after", "")), MAX_RETRY_AFTER)
    except ValueError:
        return None


def _embed(emb, texts: list[str], dim: int, note=None) -> list[list[float]]:
    """Una llamada al motor con reintentos. Ante un 429 se espera lo que diga `Retry-After` (con tope) y se insiste más veces."""
    attempt, limited = 0, 0
    while True:
        attempt += 1
        try:
            vecs = emb.embed(texts)
            break
        except httpx.HTTPStatusError as ex:
            if ex.response.status_code == 429 and limited < 6:
                limited += 1
                wait = _retry_after(ex) or RETRY_WAIT * limited
                if note:
                    note(f"límite de tasa del motor (429): espero {wait:.0f}s")
                time.sleep(wait)
                continue
            if attempt >= 3:
                raise
        except Exception:  # noqa: BLE001
            if attempt >= 3:
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
    k = " {uuid: u}" if by_uuid else ""
    return f"(x:{label}{k})" if kind == "node" else f"()-[x:{label}{k}]->()"


def _pending(txt: str, vec: str) -> str:
    return (f"x.uuid IS NOT NULL AND x.{txt} IS NOT NULL AND x.{txt} <> '' "
            f"AND (x.{vec}_reindex IS NULL OR x.{vec}_reindex_src IS NULL OR x.{vec}_reindex_src <> x.{txt})")


def _count_graph(name: str) -> tuple[int, int]:
    """(elementos pendientes, bytes de su texto) de un grafo."""
    g, n, size = graph(name), 0, 0
    for kind, label, txt, vec in ITEMS:
        c, s = g.query(f"MATCH {_match(kind, label)} WHERE {_pending(txt, vec)} RETURN count(x), sum(size(x.{txt}))").result_set[0]
        n, size = n + int(c or 0), size + int(s or 0)
    return n, size


def _fill_graph(name: str, emb, dim: int, tick, batch: int, pause: float, note=None) -> dict:
    """Primero se leen una vez los uuid pendientes y se recorren por lotes (cada lote, búsqueda por índice de uuid); después, una
    última pasada recoge lo que haya cambiado mientras tanto."""
    g, out = graph(name), {}
    for kind, label, txt, vec in ITEMS:
        n = 0
        todo = [r[0] for r in g.query(f"MATCH {_match(kind, label)} WHERE {_pending(txt, vec)} RETURN x.uuid").result_set]
        last = None
        while True:
            if todo:
                part, todo = todo[:batch], todo[batch:]
                found = rows(g.query(f"UNWIND $uuids AS u MATCH {_match(kind, label, True)} WHERE {_pending(txt, vec)} "
                                     f"RETURN x.uuid AS u, x.{txt} AS t", {"uuids": part}))
            else:  # última pasada
                found = rows(g.query(f"MATCH {_match(kind, label)} WHERE {_pending(txt, vec)} RETURN x.uuid AS u, x.{txt} AS t LIMIT {batch}"))
                if not found:
                    break
                uuids = sorted(b["u"] for b in found)
                if uuids == last:
                    raise RuntimeError(f"no se pudieron guardar los vectores nuevos en el grafo «{name}» ({label})")
                last = uuids
            if not found:
                continue
            vecs = _embed(emb, [str(b["t"]).replace("\n", " ") for b in found], dim, note)
            g.query(f"UNWIND $rows AS r WITH r, r.u AS u MATCH {_match(kind, label, True)} "
                    f"SET x.{vec}_reindex = vecf32(r.v), x.{vec}_reindex_src = r.t",
                    {"rows": [{"u": b["u"], "t": b["t"], "v": v} for b, v in zip(found, vecs)]})
            n += len(found)
            tick(len(found), f"grafo «{name}»: {label}")
            if pause:
                time.sleep(pause)
        if n:
            out[label] = n
    return out


def _wipe_graph(name: str) -> None:
    g = graph(name)
    for kind, label, _, vec in ITEMS:
        g.query(f"MATCH {_match(kind, label)} WHERE x.{vec}_reindex IS NOT NULL OR x.{vec}_reindex_src IS NOT NULL "
                f"SET x.{vec}_reindex = NULL, x.{vec}_reindex_src = NULL")


def _falkor_memory() -> tuple[int, int]:
    """(usada, límite) de FalkorDB en bytes: `maxmemory` o, si no tiene, la memoria del sistema."""
    info = client().connection.info("memory")
    return int(info.get("used_memory", 0)), int(info.get("maxmemory") or info.get("total_system_memory") or 0)


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


def _count_pg(shadow: bool = True) -> int:
    """Trozos pendientes (con la columna sombra ya creada) o, antes de crearla, todos los trozos."""
    with engine().begin() as c:
        if shadow:
            return sum(c.execute(text(f"SELECT count(*) {where}")).scalar() for _, _, where, *_ in _tables(c))
        return sum(c.execute(text(f"SELECT count(*) FROM {t}")).scalar() for t, *_ in _tables(c))


def _fill_pg(emb, dim: int, tick, batch: int, pause: float, note=None) -> dict:
    """Por lotes en orden de id (clave primaria) y una última pasada para lo que se haya reescrito mientras tanto."""
    out = {}
    with engine().begin() as c:
        present = _tables(c)
    for table, _, where, cols, txt in present:
        n, after, final = 0, 0, False
        while True:
            with engine().begin() as c:
                cond = "" if final else " AND c.id > :after"
                found = c.execute(text(f"SELECT {cols} {where}{cond} ORDER BY c.id LIMIT :n"), {"n": batch, "after": after}).all()
            if not found:
                if final:
                    break
                final = True
                continue
            after = found[-1].id
            vecs = _embed(emb, [txt(r) for r in found], dim, note)
            with engine().begin() as c:
                c.execute(text(f"UPDATE {table} SET embedding_reindex = CAST(:v AS vector) WHERE id = :i"),
                          [{"i": r.id, "v": str(v)} for r, v in zip(found, vecs)])
            n += len(found)
            tick(len(found), f"índice de texto: {table}")
            if pause:
                time.sleep(pause)
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


# --- estimación, descarte y trabajo ---------------------------------------------------------------

def estimate(e: EmbeddingEngine) -> dict:
    """Cuánto queda por calcular, cuántas llamadas al motor supone y si FalkorDB tiene memoria libre para los vectores sombra.
    En PostgreSQL se estima lo que ocupará (columna e índice HNSW), pero el espacio libre en disco no se puede consultar por SQL."""
    n_graph, text_bytes = 0, 0
    for g in _graphs():
        n, s = _count_graph(g)
        n_graph, text_bytes = n_graph + n, text_bytes + s
    n_pg, pg_size = 0, None
    if index.enabled():
        with engine().begin() as c:
            shadow = all(_shadow_type(c, t) == f"vector({e.dim})" for t, *_ in _tables(c))
            pg_size = c.execute(text("SELECT pg_database_size(current_database())")).scalar()
        n_pg = _count_pg(shadow)
    falkor_need = int(n_graph * (e.dim * 4 + 64) + text_bytes)  # vector float32 + sobrecoste por propiedad + copia del texto en _src
    used, limit = _falkor_memory()
    free = max(limit - used, 0) if limit else None
    pg_need = int(n_pg * (e.dim * 4 + 8) * 2)  # la columna y, aproximadamente, lo mismo en el índice HNSW
    batch = appsettings.get("reindex_batch")
    return {"engine": e.name, "model": e.model, "dim": e.dim,
            "graph_items": n_graph, "chunks": n_pg, "calls": math.ceil((n_graph + n_pg) / 16), "batches": math.ceil(n_graph / batch) + math.ceil(n_pg / batch),
            "falkor": {"need_bytes": falkor_need, "free_bytes": free, "ok": free is None or free >= falkor_need * FALKOR_MARGIN},
            "postgres": {"need_bytes": pg_need, "database_bytes": pg_size}}


def check_space(est: dict) -> None:
    f = est["falkor"]
    if not f["ok"]:
        raise RuntimeError(f"FalkorDB no tiene memoria libre suficiente para los vectores nuevos: hacen falta unos {f['need_bytes'] * FALKOR_MARGIN / 2**20:.0f} MB "
                           f"(con margen) y quedan {f['free_bytes'] / 2**20:.0f} MB")


def discard() -> None:
    """Borra todo lo que deja el relleno: propiedades sombra en FalkorDB y columna e índice sombra en PostgreSQL."""
    for g in _graphs():
        _wipe_graph(g)
    if index.enabled():
        _wipe_pg()


@jobs.register(KIND, "Cambio de modelo de embeddings (relleno en sombra)", limit=1, resume=True)
def _job(ctx: "jobs.JobCtx", p: dict) -> dict:
    eid = p["engine_id"]
    with _factory()() as db:
        e = db.get(EmbeddingEngine, eid)
        if not e or not e.enabled:
            raise RuntimeError("el motor de embeddings ya no existe o está desactivado")
        dim, emb = e.dim, _embedder(e)
        prev = db.scalar(select(Job).where(Job.kind == KIND, Job.id < ctx.id).order_by(Job.id.desc()).limit(1))
        stale = prev is not None and (prev.params or {}).get("engine_id") != eid  # sombras de un intento hacia otro motor
        est = estimate(e)
    if stale:
        discard()
        with _factory()() as db:
            est = estimate(db.get(EmbeddingEngine, eid))
    check_space(est)
    batch, pause = appsettings.get("reindex_batch"), appsettings.get("reindex_pause")
    ctx.note(f"pendientes: {est['graph_items']} elementos del grafo y {est['chunks']} trozos, unas {est['calls']} llamadas al motor; "
             f"memoria estimada en FalkorDB: {est['falkor']['need_bytes'] / 2**20:.0f} MB")
    state = {"done": 0, "total": est["graph_items"] + est["chunks"]}

    def tick(n: int, msg: str) -> None:
        ctx.check()
        state["done"] += n
        state["total"] = max(state["total"], state["done"])
        ctx.progress(state["done"], state["total"], msg)

    pg = index.enabled()
    counts: dict = {}
    try:
        if pg:
            _prepare_pg(dim)
        ctx.progress(0, state["total"], "calculando los vectores nuevos")
        for g in _graphs():
            for k, v in _fill_graph(g, emb, dim, tick, batch, pause, ctx.note).items():
                counts[k] = counts.get(k, 0) + v
        if pg:
            counts.update(_fill_pg(emb, dim, tick, batch, pause, ctx.note))
        for g in _graphs():  # repaso final: lo que cambió en un tipo ya recorrido (y los brains creados mientras tanto)
            for k, v in _fill_graph(g, emb, dim, tick, batch, pause, ctx.note).items():
                counts[k] = counts.get(k, 0) + v
        if pg:
            ctx.progress(state["done"], state["total"], "creando los índices vectoriales nuevos")
            _index_pg()
    except jobs.Cancelled:
        discard()
        raise
    ctx.note("vectores nuevos listos en sombra; el modelo en uso no ha cambiado")
    from .deps import audit
    with _factory()() as db:
        audit(db, None, "embedding.reindex.filled", None, name=e.name, model=e.model, dim=dim, counts=counts)
    return {"engine": e.name, "model": e.model, "dim": dim, "counts": counts, "switched": False}
