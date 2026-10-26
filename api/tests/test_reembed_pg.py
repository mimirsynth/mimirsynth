"""Cambio de modelo de embeddings contra PostgreSQL + pgvector y FalkorDB reales: los trozos de episodios y documentos pasan a la
dimensión nueva (columnas e índices HNSW rehechos) y la búsqueda sigue funcionando. Se ejecuta SOLO (proceso aparte):
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
        self.model, self.dim, self.calls, self.fail_at = model, dim, 0, None

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        if self.fail_at and self.calls >= self.fail_at:
            raise RuntimeError("motor caído")
        return [vec(self.model, self.dim, t) for t in texts]


def _drop_index_tables():
    from sqlalchemy import text

    from mimirsynth.store import engine
    with engine().begin() as c:  # otras pruebas de la misma base pueden haberlas creado con otra dimensión
        c.execute(text("DROP TABLE IF EXISTS episode_chunks, doc_chunks CASCADE"))


@pytest.fixture()
def client(monkeypatch):
    from fastapi.testclient import TestClient

    from mimirsynth import docs, jobs, reembed
    from mimirsynth import embeddings_admin as ea
    from mimirsynth.main import app
    from mimirsynth.store import init_db
    init_db()
    _drop_index_tables()
    fakes = {"viejo": Fake("viejo", 16), "nuevo": Fake("nuevo", 8)}
    monkeypatch.setattr(ea, "_probe", lambda url, model, key: fakes[model].dim)
    monkeypatch.setattr(reembed, "_embedder", lambda e: fakes[e.model])
    monkeypatch.setattr(reembed, "RETRY_WAIT", 0)
    monkeypatch.setattr(reembed, "BATCH", 3)
    monkeypatch.setattr(docs, "get_embedder", lambda: fakes["viejo"])
    monkeypatch.setattr(docs, "start_index", lambda doc_id, user_id=None: docs.run_index(doc_id))
    jobs.INLINE = True
    with TestClient(app) as c:
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
    from sqlalchemy import text

    from mimirsynth.store import engine
    with engine().begin() as c:
        return c.execute(text("SELECT format_type(atttypid, atttypmod) FROM pg_attribute WHERE attrelid = to_regclass(:t) AND attname = :c "
                              "AND NOT attisdropped"), {"t": table, "c": col}).scalar()


def indexdef(name: str):
    from sqlalchemy import text

    from mimirsynth.store import engine
    with engine().begin() as c:
        return c.execute(text("SELECT indexdef FROM pg_indexes WHERE indexname = :n"), {"n": name}).scalar()


def test_reindex_changes_the_dimension_of_chunks_and_hnsw_indexes(client):
    import falkordb
    from sqlalchemy import delete, select

    from mimirsynth import docs, index
    from mimirsynth.models import Brain, EmbeddingEngine
    from mimirsynth.store import _factory
    with _factory()() as db:
        db.execute(delete(EmbeddingEngine)); db.commit()
    fc = falkordb.FalkorDB(host=FALKOR, port=6379)
    try:
        fc.select_graph(GRAPH).delete()
    except Exception:  # noqa: BLE001
        pass
    g = fc.select_graph(GRAPH)
    g.query("CREATE (:Episodic {uuid:'ep1', name:'Copias', content:'Las copias de seguridad se hacen cada noche a las tres.', valid_at:'2026-01-01T00:00:00Z'}), "
            "(:Episodic {uuid:'ep2', name:'Red', content:'El resolvedor DNS interno escucha en el puerto 53.', valid_at:'2026-01-02T00:00:00Z'})")
    g.query("CREATE (a:Entity {uuid:'e1', name:'Resolvedor', name_embedding: vecf32($v)})", {"v": vec("viejo", 16, "Resolvedor")})
    fakes = client.fakes
    try:
        old = client.post("/api/embedding-engines", json={"name": "viejo", "base_url": "http://o/v1", "model": "viejo"}).json()
        new = client.post("/api/embedding-engines", json={"name": "nuevo", "base_url": "http://n/v1", "model": "nuevo"}).json()
        assert old["is_default"] and old["dim"] == 16 and new["dim"] == 8
        client.post("/api/brains", json={"slug": "rp", "name": "RP", "graph_name": GRAPH})
        with _factory()() as db:
            bid = db.scalar(select(Brain.id).where(Brain.slug == "rp"))
        assert index.sync_brain(bid, GRAPH, fakes["viejo"])["reindexed"] == 2
        d = up(client, "rp", "red.md", "# Red\n\n## Servidor DNS\n\nEl resolvedor interno escucha en el puerto 53.\n\n## Copias\n\nLas copias se hacen cada noche.\n")
        assert client.get(f"/api/brains/rp/docs/{d['id']}").json()["status"] == "active"
        assert coltype("episode_chunks") == coltype("doc_chunks") == "vector(16)"

        # un fallo a mitad: las columnas siguen como estaban y la sombra (con la dimensión nueva) conserva lo calculado
        fakes["nuevo"].fail_at = 3
        jid = client.post(f"/api/embedding-engines/{new['id']}/reindex").json()["job"]
        assert client.get("/api/embedding-engines/reindex").json()["job"]["status"] == "failed"
        assert coltype("episode_chunks") == "vector(16)" and coltype("episode_chunks", "embedding_reindex") == "vector(8)"
        assert client.get("/api/brains/rp/docs/search", params={"q": "puerto del resolvedor"}).json()["results"]   # la búsqueda sigue con el motor anterior

        fakes["nuevo"].fail_at = None
        assert client.post(f"/api/embedding-engines/reindex/{jid}/retry").status_code == 201
        job = client.get("/api/embedding-engines/reindex").json()["job"]
        assert job["status"] == "done", job
        assert job["result"]["counts"].get("episode_chunks", 0) + job["result"]["counts"].get("doc_chunks", 0) >= 1
        for table, ix in (("episode_chunks", "ix_chunks_emb"), ("doc_chunks", "ix_doc_chunks_emb")):
            assert coltype(table) == "vector(8)" and coltype(table, "embedding_reindex") is None
            assert "hnsw" in indexdef(ix) and "embedding vector_cosine_ops" in indexdef(ix) and indexdef(f"{ix}_reindex") is None
        assert [e["model"] for e in client.get("/api/embedding-engines").json() if e["is_default"]] == ["nuevo"]
        # búsqueda con el modelo nuevo: documentos, fragmentos de episodios y hechos del grafo
        docs.get_embedder = lambda: fakes["nuevo"]
        r = client.get("/api/brains/rp/docs/search", params={"q": "puerto del resolvedor interno"}).json()["results"]
        assert r and r[0]["document_id"] == d["id"] and r[0]["similarity"] > 0.3
        q = vec("nuevo", 8, "Red\nEl resolvedor DNS interno escucha en el puerto 53.")   # el mismo texto con el que se indexó
        hits = index.search(bid, q, "resolvedor", k=2)
        assert hits and hits[0]["episode_uuid"] == "ep2"
        from sqlalchemy import text

        from mimirsynth.store import engine
        with engine().begin() as c:
            sim = c.execute(text("SELECT 1 - (embedding <=> CAST(:q AS vector)) FROM episode_chunks WHERE episode_uuid = 'ep2'"), {"q": str(q)}).scalar()
        assert sim > 0.99
        assert all(abs(x - y) < 1e-5 for x, y in zip(g.query("MATCH (x:Entity {uuid:'e1'}) RETURN x.name_embedding").result_set[0][0], vec("nuevo", 8, "Resolvedor")))
        # los trozos nuevos se escriben ya con la dimensión nueva
        g.query("CREATE (:Episodic {uuid:'ep3', name:'Nuevo', content:'Un episodio posterior al cambio.', valid_at:'2026-02-01T00:00:00Z'})")
        assert index.sync_brain(bid, GRAPH, fakes["nuevo"])["reindexed"] == 1
    finally:
        client.post("/api/brains/rp/delete", json={"confirm": "rp"})
        g.delete()


def test_cancel_drops_the_shadow_column(client):
    from sqlalchemy import delete, select

    from mimirsynth import jobs, reembed
    from mimirsynth.models import EmbeddingEngine, Job
    from mimirsynth.store import _factory
    with _factory()() as db:
        db.execute(delete(EmbeddingEngine)); db.execute(delete(Job).where(Job.kind == reembed.KIND)); db.commit()
    client.post("/api/embedding-engines", json={"name": "viejo", "base_url": "http://o/v1", "model": "viejo"})
    new = client.post("/api/embedding-engines", json={"name": "nuevo", "base_url": "http://n/v1", "model": "nuevo"}).json()
    client.post("/api/brains", json={"slug": "rc", "name": "RC", "graph_name": "g-rc"})
    try:
        up(client, "rc", "a.md", "# A\n\n" + "\n\n".join(f"Párrafo {i} con texto de relleno suficiente." for i in range(12)))
        fake = client.fakes["nuevo"]
        real = fake.embed

        def cancelling(texts):
            with _factory()() as db:
                jobs.cancel(db.scalar(select(Job.id).where(Job.kind == reembed.KIND, Job.status == "running")))
            return real(texts)
        fake.embed = cancelling
        client.post(f"/api/embedding-engines/{new['id']}/reindex")
        assert client.get("/api/embedding-engines/reindex").json()["job"]["status"] == "cancelled"
        assert coltype("doc_chunks", "embedding_reindex") is None and coltype("doc_chunks") == "vector(16)"
        assert [e["model"] for e in client.get("/api/embedding-engines").json() if e["is_default"]] == ["viejo"]
    finally:
        client.post("/api/brains/rc/delete", json={"confirm": "rc"})
