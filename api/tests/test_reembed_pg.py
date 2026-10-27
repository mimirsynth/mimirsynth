"""Relleno en sombra contra PostgreSQL + pgvector y FalkorDB reales: los trozos de episodios y documentos reciben su vector nuevo en una
columna sombra con la dimensión nueva y su propio índice HNSW, sin tocar la columna en uso; cancelar o descartar no deja ninguna
columna ni índice auxiliar. Se ejecuta SOLO (proceso aparte):
    MIMIRSYNTH_TEST_PG=postgresql+psycopg://... MIMIRSYNTH_TEST_FALKOR=host pytest tests/test_reembed_pg.py"""
import hashlib
import os
import tempfile

PG = os.environ.get("MIMIRSYNTH_TEST_PG")
FALKOR = os.environ.get("MIMIRSYNTH_TEST_FALKOR")
if PG and FALKOR:
    os.environ["MIMIRSYNTH_DATABASE_URL"] = PG
    os.environ["MIMIRSYNTH_AUTH_MODE"] = "off"
    os.environ["MIMIRSYNTH_DOC_STORE"] = tempfile.mkdtemp()
    os.environ["MIMIRSYNTH_EMBEDDING_DIM"] = "16"
    os.environ["MIMIRSYNTH_FALKOR_HOST"] = FALKOR
    os.environ["MIMIRSYNTH_REINDEX_BATCH"] = "3"

import pytest  # noqa: E402

pytestmark = pytest.mark.skipif(not (PG and FALKOR), reason="necesita PostgreSQL con pgvector (MIMIRSYNTH_TEST_PG) y FalkorDB (MIMIRSYNTH_TEST_FALKOR)")
GRAPH = "zz-test-reembed-pg"


def vec(model: str, dim: int, t: str) -> list[float]:
    v = [0.0] * dim
    for w in t.lower().split():
        v[int(hashlib.md5(f"{model}:{w.strip('.,;:()#')}".encode()).hexdigest(), 16) % dim] += 1.0
    n = sum(x * x for x in v) ** 0.5 or 1.0
    return [x / n for x in v]


class Fake:
    def __init__(self, model: str, dim: int):
        self.model, self.dim, self.calls, self.fail_at, self.hook = model, dim, 0, None, None

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        if self.hook:
            self.hook()
        if self.fail_at and self.calls >= self.fail_at:
            raise RuntimeError("motor caído")
        return [vec(self.model, self.dim, t) for t in texts]


def _sql(sql: str, **p):
    from sqlalchemy import text

    from mimirsynth.store import engine
    with engine().begin() as c:
        return c.execute(text(sql), p).scalar()


def _drop_index_tables():
    from sqlalchemy import text

    from mimirsynth.store import engine
    with engine().begin() as c:  # otras pruebas de la misma base pueden haberlas creado con otra dimensión
        c.execute(text("DROP TABLE IF EXISTS episode_chunks, doc_chunks CASCADE"))


@pytest.fixture()
def client(monkeypatch):
    from fastapi.testclient import TestClient
    from sqlalchemy import delete

    from mimirsynth import docs, embeddings_admin as ea, jobs, reembed
    from mimirsynth.main import app
    from mimirsynth.models import EmbeddingEngine, Job
    from mimirsynth.store import _factory, init_db
    init_db()
    _drop_index_tables()
    fakes = {"viejo": Fake("viejo", 16), "nuevo": Fake("nuevo", 8)}
    monkeypatch.setattr(ea, "_probe", lambda url, model, key: fakes[model].dim)
    monkeypatch.setattr(reembed, "_embedder", lambda e: fakes[e.model])
    monkeypatch.setattr(reembed, "RETRY_WAIT", 0)
    reembed._cache.clear()
    monkeypatch.setattr(docs, "get_embedder", lambda: fakes["viejo"])
    monkeypatch.setattr(docs, "start_index", lambda doc_id, user_id=None: docs.run_index(doc_id))
    jobs.INLINE = True
    from mimirsynth.models import AppSetting
    with TestClient(app) as c:
        with _factory()() as db:
            db.execute(delete(EmbeddingEngine)); db.execute(delete(Job).where(Job.kind == reembed.KIND))
            db.execute(delete(AppSetting).where(AppSetting.key == reembed.MARKER)); db.commit()
        c.fakes = fakes
        yield c
    jobs.INLINE = False
    _drop_index_tables()


def up(c, slug, name, body):
    data = body.encode()
    uid = c.post(f"/api/brains/{slug}/docs/uploads", json={"filename": name, "size": len(data)}).json()["upload_id"]
    c.put(f"/api/brains/{slug}/docs/uploads/{uid}/parts/0", content=data)
    return c.post(f"/api/brains/{slug}/docs/uploads/{uid}/complete").json()


def coltype(table: str, col: str = "embedding"):
    return _sql("SELECT format_type(atttypid, atttypmod) FROM pg_attribute WHERE attrelid = to_regclass(:t) AND attname = :c AND NOT attisdropped", t=table, c=col)


def indexdef(name: str):
    return _sql("SELECT indexdef FROM pg_indexes WHERE indexname = :n", n=name)


def aux_pg() -> int:
    """Columnas e índices auxiliares que quedan en PostgreSQL."""
    return (_sql("SELECT count(*) FROM information_schema.columns WHERE table_name IN ('episode_chunks', 'doc_chunks') AND column_name <> 'embedding' AND column_name LIKE '%embedding%'")
            + _sql("SELECT count(*) FROM pg_indexes WHERE tablename IN ('episode_chunks', 'doc_chunks') AND indexname LIKE '%reindex%'"))


def aux_graph(g) -> int:
    q = "UNWIND keys(x) AS k WITH k WHERE k STARTS WITH 'name_embedding_' OR k STARTS WITH 'fact_embedding_' RETURN count(k)"
    return g.query(f"MATCH (x) {q}").result_set[0][0] + g.query(f"MATCH ()-[x]->() {q}").result_set[0][0]


@pytest.fixture()
def brain(client):
    import falkordb
    from sqlalchemy import select

    from mimirsynth import index
    from mimirsynth.models import Brain
    from mimirsynth.store import _factory
    fc = falkordb.FalkorDB(host=FALKOR, port=6379)
    try:
        fc.select_graph(GRAPH).delete()
    except Exception:  # noqa: BLE001
        pass
    g = fc.select_graph(GRAPH)
    g.query("CREATE (:Episodic {uuid:'ep1', name:'Copias', content:'Las copias de seguridad se hacen cada noche a las tres.', valid_at:'2026-01-01T00:00:00Z'}), "
            "(:Episodic {uuid:'ep2', name:'Red', content:'El resolvedor DNS interno escucha en el puerto 53.', valid_at:'2026-01-02T00:00:00Z'})")
    g.query("CREATE (a:Entity {uuid:'e1', name:'Resolvedor', name_embedding: vecf32($v)})", {"v": vec("viejo", 16, "Resolvedor")})
    old = client.post("/api/embedding-engines", json={"name": "viejo", "base_url": "http://o/v1", "model": "viejo"}).json()
    new = client.post("/api/embedding-engines", json={"name": "nuevo", "base_url": "http://n/v1", "model": "nuevo"}).json()
    assert old["is_default"] and old["dim"] == 16 and new["dim"] == 8
    client.post("/api/brains", json={"slug": "rp", "name": "RP", "graph_name": GRAPH})
    with _factory()() as db:
        bid = db.scalar(select(Brain.id).where(Brain.slug == "rp"))
    assert index.sync_brain(bid, GRAPH, client.fakes["viejo"])["reindexed"] == 2
    d = up(client, "rp", "red.md", "# Red\n\n## Servidor DNS\n\nEl resolvedor interno escucha en el puerto 53.\n\n## Copias\n\nLas copias se hacen cada noche.\n")
    assert client.get(f"/api/brains/rp/docs/{d['id']}").json()["status"] == "active"
    yield {"g": g, "new": new, "bid": bid, "doc": d}
    client.post("/api/brains/rp/delete", json={"confirm": "rp"})
    g.delete()


def test_fill_writes_a_shadow_column_and_leaves_the_one_in_use(client, brain):
    new, fakes = brain["new"], client.fakes
    est = client.get(f"/api/embedding-engines/{new['id']}/reindex/estimate").json()
    assert est["chunks"] >= 3 and est["graph_items"] == 1 and est["postgres"]["need_bytes"] > 0 and est["postgres"]["database_bytes"] > 0
    # un fallo a mitad: la columna en uso sigue igual y la sombra (con la dimensión nueva) conserva lo calculado
    fakes["nuevo"].fail_at = 3
    jid = client.post(f"/api/embedding-engines/{new['id']}/reindex").json()["job"]
    assert client.get("/api/embedding-engines/reindex").json()["job"]["status"] == "failed"
    assert coltype("episode_chunks") == "vector(16)" and coltype("episode_chunks", "embedding_reindex") == "vector(8)"
    fakes["nuevo"].fail_at = None
    assert client.post(f"/api/embedding-engines/reindex/{jid}/retry").status_code == 201
    job = client.get("/api/embedding-engines/reindex").json()["job"]
    assert job["status"] == "done" and job["result"]["switched"] is False, job
    for table, ix in (("episode_chunks", "ix_chunks_emb"), ("doc_chunks", "ix_doc_chunks_emb")):
        assert coltype(table) == "vector(16)" and coltype(table, "embedding_reindex") == "vector(8)"           # la de uso, intacta
        assert _sql(f"SELECT count(*) FROM {table} WHERE embedding_reindex IS NULL") == 0
        assert "hnsw" in indexdef(f"{ix}_reindex") and "embedding_reindex vector_cosine_ops" in indexdef(f"{ix}_reindex")
        assert "embedding vector_cosine_ops" in indexdef(ix)
    q = vec("nuevo", 8, "Red\nEl resolvedor DNS interno escucha en el puerto 53.")   # el mismo texto con el que se indexó
    assert _sql("SELECT 1 - (embedding_reindex <=> CAST(:q AS vector)) FROM episode_chunks WHERE episode_uuid = 'ep2'", q=str(q)) > 0.99
    assert [e["model"] for e in client.get("/api/embedding-engines").json() if e["is_default"]] == ["viejo"]
    r = client.get("/api/brains/rp/docs/search", params={"q": "puerto del resolvedor"}).json()["results"]
    assert r and r[0]["document_id"] == brain["doc"]["id"]                                                     # la búsqueda sigue con el motor en uso
    # descartar después de terminar: no queda nada auxiliar
    assert client.post("/api/embedding-engines/reindex/discard").json() == {"ok": True}
    assert aux_pg() == 0 and aux_graph(brain["g"]) == 0 and coltype("doc_chunks") == "vector(16)"


def test_cancel_leaves_no_auxiliary_column_index_or_property(client, brain):
    from sqlalchemy import select

    from mimirsynth import jobs, reembed
    from mimirsynth.models import Job
    from mimirsynth.store import _factory
    fake = client.fakes["nuevo"]

    def cancelling():
        if fake.calls == 2:  # con el grafo ya calculado y a mitad de los trozos
            with _factory()() as db:
                jobs.cancel(db.scalar(select(Job.id).where(Job.kind == reembed.KIND, Job.status == "running")))
    fake.hook = cancelling
    client.post(f"/api/embedding-engines/{brain['new']['id']}/reindex")
    assert client.get("/api/embedding-engines/reindex").json()["job"]["status"] == "cancelled"
    assert aux_pg() == 0 and aux_graph(brain["g"]) == 0
    assert coltype("episode_chunks") == coltype("doc_chunks") == "vector(16)"



def test_ddl_waits_with_a_short_lock_timeout_and_retries(client, monkeypatch):
    """Si otra conexión tiene la tabla del índice, el cambio de estructura no se queda esperando: reintenta con lock_timeout corto."""
    import threading
    import time

    from sqlalchemy import text

    from mimirsynth import reembed
    from mimirsynth.store import engine
    monkeypatch.setattr(reembed, "LOCK_TIMEOUT", "100ms")
    monkeypatch.setattr(reembed, "LOCK_RETRIES", 30)
    held, release = threading.Event(), threading.Event()

    def locker():
        with engine().connect() as c:
            c.execute(text("BEGIN"))
            c.execute(text("LOCK TABLE episode_chunks IN ACCESS SHARE MODE"))  # como una lectura larga del índice
            held.set()
            release.wait(5)
            c.execute(text("COMMIT"))
    t = threading.Thread(target=locker)
    t.start()
    held.wait(5)
    notes = []
    threading.Timer(0.6, release.set).start()
    t0 = time.monotonic()
    reembed._prepare_pg(8, notes.append)
    t.join(5)
    assert coltype("episode_chunks", "embedding_reindex") == "vector(8)" and any("reintento" in n for n in notes) and time.monotonic() - t0 < 5
    # si la tabla sigue ocupada, se rinde con un error claro en lugar de quedarse bloqueado
    reembed._wipe_pg()
    monkeypatch.setattr(reembed, "LOCK_RETRIES", 2)
    held.clear(); release.clear()
    t = threading.Thread(target=locker)
    t.start()
    held.wait(5)
    try:
        with pytest.raises(RuntimeError, match="siguen ocupadas"):
            reembed._prepare_pg(8)
    finally:
        release.set()
        t.join(5)
    assert coltype("episode_chunks", "embedding_reindex") is None
