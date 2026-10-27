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
Mientras haya sombras queda un marcador barato de consultar (`reindex_shadow` en `app_settings`): así se sabe, sin recorrer el grafo,
si hay un relleno sin terminar, y se avisa (`reindex.orphan`) si lleva tiempo parado. Los grafos sin brain no se tocan.
"""
import logging
import math
import threading
import time
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select, text
from sqlalchemy.exc import OperationalError

from . import appsettings, index, jobs
from .db import client, graph, list_graphs, rows
from .embed import OpenAICompatEmbedder
from .models import AppSetting, Brain, EmbeddingEngine, Job
from .secretbox import unseal
from .store import _factory, engine

log = logging.getLogger("mimirsynth.reembed")
KIND = "embedding.reindex"
MARKER = "reindex_shadow"
RETRY_WAIT = 4.0  # segundos (por intento) antes de reintentar una llamada fallida al motor
MAX_RETRY_AFTER = 300.0  # tope de espera que se acepta de un `Retry-After`
FALKOR_MARGIN = 1.5  # la memoria libre de FalkorDB debe superar la estimación por este factor
SAMPLE = 1000  # elementos por tipo con los que se estima el tamaño medio del texto
ESTIMATE_SECONDS = 5.0  # tiempo máximo de una estimación pedida por la API; si se pasa, la estimación es parcial
ESTIMATE_TTL = 300.0  # segundos que se reutiliza la última estimación de un motor
LOCK_TIMEOUT = "2s"  # espera máxima por el bloqueo de una tabla del índice al cambiar su estructura
LOCK_RETRIES = 5
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
_cache: dict[int, tuple[float, dict]] = {}
_cache_lock = threading.Lock()


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


# --- marcador de sombras --------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(timezone.utc)


def marker() -> dict | None:
    """Estado de las sombras sin recorrer el grafo: {engine_id, engine, model, dim, state: running|failed|ready, started_at, updated_at}."""
    with _factory()() as db:
        row = db.get(AppSetting, MARKER)
    v = (row.value or {}).get("v") if row else None
    return dict(v) if v else None


def _mark(e: EmbeddingEngine, state: str) -> None:
    with _factory()() as db:
        row = db.get(AppSetting, MARKER)
        cur = (row.value or {}).get("v", {}) if row else {}
        t = _now().isoformat(timespec="seconds")
        v = {"engine_id": e.id, "engine": e.name, "model": e.model, "dim": e.dim, "state": state,
             "started_at": cur.get("started_at") if cur.get("engine_id") == e.id else t, "updated_at": t}
        if row:
            row.value, row.updated_at = {"v": v}, _now()
        else:
            db.add(AppSetting(key=MARKER, value={"v": v}))
        db.commit()


def _unmark() -> None:
    with _factory()() as db:
        row = db.get(AppSetting, MARKER)
        if row:
            db.delete(row)
            db.commit()


def status() -> dict:
    """El marcador y si las sombras están huérfanas: las hay y ningún relleno está en cola ni en marcha."""
    m = marker()
    with _factory()() as db:
        running = db.scalar(select(Job.id).where(Job.kind == KIND, Job.status.in_(("queued", "running")))) is not None
    return {"shadow": m, "orphan": bool(m) and not running}


def check_orphan() -> None:
    """Ciclo de fondo de las notificaciones: avisa si un relleno lleva más de `reindex_orphan_hours` parado sin terminar (falló, o se
    cortó y nadie lo retoma) con las sombras ocupando memoria; el aviso se resuelve al descartarlas o al terminar el relleno.
    Un relleno terminado (`ready`) espera al intercambio y no avisa."""
    from . import notify
    st = status()
    m = st["shadow"]
    if not m or m.get("state") == "ready":
        notify.resolve("reindex.orphan", MARKER)
        return
    if not st["orphan"]:  # el relleno está en marcha
        return
    try:
        since = datetime.fromisoformat(m["updated_at"])
    except (KeyError, ValueError):
        return
    hours = float(appsettings.get("reindex_orphan_hours"))
    if _now() - since >= timedelta(hours=hours):
        notify.emit("reindex.orphan", "Hay un cambio de modelo de embeddings sin terminar",
                    f"El relleno hacia «{m.get('engine')}» ({m.get('model')}, {m.get('dim')}d) está {'fallido' if m.get('state') == 'failed' else 'parado'} "
                    f"desde {m['updated_at']} y sus vectores sombra siguen ocupando memoria. Reinténtalo o descártalo.", key=MARKER)


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


def _estimate_graph(name: str) -> tuple[int, int]:
    """(elementos, bytes de texto estimados) de un grafo con consultas acotadas: un recuento por tipo (sin filtros, que FalkorDB
    resuelve sin recorrer los elementos) y una muestra de SAMPLE elementos para el tamaño medio del texto. Cuenta todos los elementos,
    no solo los pendientes: es una cota superior."""
    g, n, size = graph(name), 0, 0
    for kind, label, txt, _ in ITEMS:
        c = int(g.query(f"MATCH {_match(kind, label)} RETURN count(x)").result_set[0][0] or 0)
        if c:
            lens = [int(r[0] or 0) for r in g.query(f"MATCH {_match(kind, label)} RETURN size(x.{txt}) LIMIT {SAMPLE}").result_set]
            size += int(c * (sum(lens) / len(lens))) if lens else 0
        n += c
    return n, size


def _count_graph(name: str) -> int:
    """Elementos pendientes de un grafo (exacto; lo usa el trabajo, no la API)."""
    g = graph(name)
    return sum(int(g.query(f"MATCH {_match(k, lb)} WHERE {_pending(t, v)} RETURN count(x)").result_set[0][0] or 0) for k, lb, t, v in ITEMS)


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


def _locked(ex: OperationalError) -> bool:
    return getattr(getattr(ex, "orig", None), "sqlstate", "") == "55P03"  # lock_not_available


def _ddl(fn, what: str, note=None) -> None:
    """Cambia la estructura de las tablas del índice con un `lock_timeout` corto: si la sincronización del índice o una indexación
    tienen la tabla, se reintenta en lugar de quedarse esperando (y de hacer esperar a todos los que vengan detrás)."""
    for attempt in range(1, LOCK_RETRIES + 1):
        try:
            with engine().begin() as c:
                c.execute(text(f"SET LOCAL lock_timeout = '{LOCK_TIMEOUT}'"))
                fn(c)
            return
        except OperationalError as ex:
            if not _locked(ex) or attempt == LOCK_RETRIES:
                if _locked(ex):
                    raise RuntimeError(f"no se pudo {what}: las tablas del índice siguen ocupadas tras {LOCK_RETRIES} intentos") from ex
                raise
            if note:
                note(f"tablas del índice ocupadas al {what}: reintento ({attempt}/{LOCK_RETRIES})")
            time.sleep(RETRY_WAIT * attempt / 4)


def _prepare_pg(dim: int, note=None) -> None:
    """Columna sombra con la dimensión nueva (se rehace si quedó de un intento con otra dimensión)."""
    def run(c):
        for table, ix, *_ in _tables(c):
            cur = _shadow_type(c, table)
            if cur and cur != f"vector({dim})":
                c.execute(text(f"DROP INDEX IF EXISTS {ix}_reindex"))
                c.execute(text(f"ALTER TABLE {table} DROP COLUMN embedding_reindex"))
                cur = None
            if not cur:
                c.execute(text(f"ALTER TABLE {table} ADD COLUMN embedding_reindex vector({dim})"))
    _ddl(run, "preparar la columna sombra", note)


def _pg_rows() -> int:
    """Trozos de las tablas del índice según las estadísticas de PostgreSQL (sin recorrerlas); si aún no hay estadísticas, se cuentan."""
    with engine().begin() as c:
        n = 0
        for table, *_ in _tables(c):
            est = c.execute(text("SELECT reltuples FROM pg_class WHERE oid = to_regclass(:t)"), {"t": table}).scalar()
            n += int(est) if est is not None and est >= 0 else int(c.execute(text(f"SELECT count(*) FROM {table}")).scalar())
        return n


def _count_pg() -> int:
    """Trozos pendientes (exacto, con la columna sombra ya creada; lo usa el trabajo)."""
    with engine().begin() as c:
        return sum(c.execute(text(f"SELECT count(*) {where}")).scalar() for _, _, where, *_ in _tables(c))


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
    """Índice HNSW de la columna sombra, con CONCURRENTLY: mientras se construye no bloquea las escrituras del índice."""
    with engine().connect() as c:
        present = _tables(c)
        c.commit()
        c = c.execution_options(isolation_level="AUTOCOMMIT")
        for table, ix, *_ in present:
            valid = c.execute(text("SELECT i.indisvalid FROM pg_index i WHERE i.indexrelid = to_regclass(:n)"), {"n": f"{ix}_reindex"}).scalar()
            if valid is False:  # una construcción concurrente interrumpida deja el índice inválido
                c.execute(text(f"DROP INDEX CONCURRENTLY IF EXISTS {ix}_reindex"))
            c.execute(text(f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {ix}_reindex ON {table} USING hnsw (embedding_reindex vector_cosine_ops) "
                           "WITH (m = 16, ef_construction = 64)"))


def _wipe_pg() -> None:
    def run(c):
        for table, ix, *_ in _tables(c):
            c.execute(text(f"DROP INDEX IF EXISTS {ix}_reindex"))
            c.execute(text(f"ALTER TABLE {table} DROP COLUMN IF EXISTS embedding_reindex"))
    _ddl(run, "borrar la columna sombra")


# --- estimación, descarte y trabajo ---------------------------------------------------------------

def estimate(e: EmbeddingEngine, deadline: float | None = None) -> dict:
    """Cuánto hay que calcular, cuántas llamadas al motor supone y si FalkorDB tiene memoria libre para los vectores sombra.
    Con consultas acotadas (ver `_estimate_graph`): es una cota superior, que no descuenta lo ya calculado. Con `deadline`
    (time.monotonic()) se para al llegar y la estimación queda marcada como parcial. En PostgreSQL se estima lo que ocuparán la columna
    y el índice HNSW, pero el espacio libre en disco no se puede consultar por SQL."""
    n_graph, text_bytes, partial, done, graphs = 0, 0, False, 0, _graphs()
    for g in graphs:
        if deadline is not None and time.monotonic() > deadline:
            partial = True
            break
        n, s = _estimate_graph(g)
        n_graph, text_bytes, done = n_graph + n, text_bytes + s, done + 1
    n_pg, pg_size = 0, None
    if index.enabled():
        n_pg = _pg_rows()
        with engine().begin() as c:
            pg_size = c.execute(text("SELECT pg_database_size(current_database())")).scalar()
    falkor_need = int(n_graph * (e.dim * 4 + 64) + text_bytes)  # vector float32 + sobrecoste por propiedad + copia del texto en _src
    used, limit = _falkor_memory()
    free = max(limit - used, 0) if limit else None
    batch = appsettings.get("reindex_batch")
    return {"engine": e.name, "model": e.model, "dim": e.dim, "partial": partial, "graphs": len(graphs), "graphs_estimated": done,
            "graph_items": n_graph, "chunks": n_pg, "calls": math.ceil((n_graph + n_pg) / 16), "batches": math.ceil(n_graph / batch) + math.ceil(n_pg / batch),
            "falkor": {"need_bytes": falkor_need, "free_bytes": free, "ok": free is None or free >= falkor_need * FALKOR_MARGIN},
            "postgres": {"need_bytes": int(n_pg * (e.dim * 4 + 8) * 2), "database_bytes": pg_size},  # la columna y, aprox., otro tanto el índice HNSW
            "at": _now().isoformat(timespec="seconds")}


def cached_estimate(e: EmbeddingEngine, refresh: bool = False) -> dict:
    """Estimación para la API: con tiempo máximo (ESTIMATE_SECONDS) y reutilizando la última de ese motor durante ESTIMATE_TTL."""
    with _cache_lock:
        hit = _cache.get(e.id)
        if hit and not refresh and time.monotonic() - hit[0] < ESTIMATE_TTL:
            return {**hit[1], "cached": True}
    est = estimate(e, deadline=time.monotonic() + ESTIMATE_SECONDS)
    with _cache_lock:
        _cache[e.id] = (time.monotonic(), est)
    return {**est, "cached": False}


def last_estimate(eid: int) -> dict | None:
    with _cache_lock:
        hit = _cache.get(eid)
        return hit[1] if hit and time.monotonic() - hit[0] < ESTIMATE_TTL else None


def check_space(est: dict) -> None:
    f = est["falkor"]
    if not f["ok"]:
        raise RuntimeError(f"FalkorDB no tiene memoria libre suficiente para los vectores nuevos: hacen falta unos {f['need_bytes'] * FALKOR_MARGIN / 2**20:.0f} MB "
                           f"(con margen) y quedan {f['free_bytes'] / 2**20:.0f} MB")


def discard() -> None:
    """Borra todo lo que deja el relleno: propiedades sombra en FalkorDB, columna e índice sombra en PostgreSQL y el marcador."""
    from . import notify
    for g in _graphs():
        _wipe_graph(g)
    if index.enabled():
        _wipe_pg()
    _unmark()
    notify.resolve("reindex.orphan", MARKER, "Se han descartado los vectores sombra.")


@jobs.register(KIND, "Cambio de modelo de embeddings (relleno en sombra)", limit=1, resume=True)
def _job(ctx: "jobs.JobCtx", p: dict) -> dict:
    eid = p["engine_id"]
    with _factory()() as db:
        e = db.get(EmbeddingEngine, eid)
        if not e or not e.enabled:
            raise RuntimeError("el motor de embeddings ya no existe o está desactivado")
        dim, emb = e.dim, _embedder(e)
        prev = db.scalar(select(Job).where(Job.kind == KIND, Job.id < ctx.id).order_by(Job.id.desc()).limit(1))
    m = marker()
    if (m and m.get("engine_id") != eid) or (prev is not None and (prev.params or {}).get("engine_id") != eid):
        discard()  # sombras de un intento hacia otro motor
    ctx.progress(0, 0, "estimando el trabajo")
    est = estimate(e)  # aquí, en el trabajo, y no en la petición que lo lanza
    check_space(est)
    ctx.note(f"estimación: hasta {est['graph_items']} elementos del grafo y {est['chunks']} trozos, unas {est['calls']} llamadas al motor; "
             f"memoria en FalkorDB: unos {est['falkor']['need_bytes'] / 2**20:.0f} MB")
    batch, pause = appsettings.get("reindex_batch"), appsettings.get("reindex_pause")
    _mark(e, "running")
    pg = index.enabled()
    counts: dict = {}
    try:
        if pg:
            _prepare_pg(dim, ctx.note)
        state = {"done": 0, "total": sum(_count_graph(g) for g in _graphs()) + (_count_pg() if pg else 0)}

        def tick(n: int, msg: str) -> None:
            ctx.check()
            state["done"] += n
            state["total"] = max(state["total"], state["done"])
            ctx.progress(state["done"], state["total"], msg)

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
    except Exception:
        _mark(e, "failed")  # las sombras se quedan para reintentar; si nadie lo hace, check_orphan avisa
        raise
    _mark(e, "ready")
    from . import notify
    notify.resolve("reindex.orphan", MARKER, "El relleno ha terminado.")
    ctx.note("vectores nuevos listos en sombra; el modelo en uso no ha cambiado")
    from .deps import audit
    with _factory()() as db:
        audit(db, None, "embedding.reindex.filled", None, name=e.name, model=e.model, dim=dim, counts=counts)
    return {"engine": e.name, "model": e.model, "dim": dim, "counts": counts, "switched": False}
