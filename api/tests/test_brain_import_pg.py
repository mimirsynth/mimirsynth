"""Import of a brain against real PostgreSQL + pgvector and FalkorDB (#136): with the same embedding model the package's vectors are
reused (graph, episode index and documents); with another model all of them are computed again. Runs ALONE (its own process):
    MIMIRSYNTH_TEST_PG=postgresql+psycopg://... MIMIRSYNTH_TEST_FALKOR=host pytest tests/test_brain_import_pg.py"""
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
GRAPH = "zz-test-import-pg"
NEW = ("pgimp1", "pgimp2")


class Fake:
    """Deterministic vectors that depend on the model, so that reused and computed ones can be told apart."""

    def __init__(self, model: str):
        self.model, self.calls = model, 0

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        out = []
        for t in texts:
            v = [0.0] * 16
            for w in t.lower().split():
                v[int(hashlib.md5(f"{self.model}:{w}".encode()).hexdigest(), 16) % 16] += 1.0
            n = sum(x * x for x in v) ** 0.5 or 1.0
            out.append([x / n for x in v])
        return out


def _sql(sql: str, **p):
    from sqlalchemy import text

    from mimirsynth.store import engine
    with engine().begin() as c:
        return c.execute(text(sql), p).all()


def _graphs(*names):
    from mimirsynth.db import client
    for g in names:
        if g in client().list_graphs():
            client().select_graph(g).delete()


@pytest.fixture()
def client(monkeypatch):
    from fastapi.testclient import TestClient
    from sqlalchemy import text

    from mimirsynth import docs, embed, index, jobs
    from mimirsynth.main import app
    from mimirsynth.models import Base
    from mimirsynth.store import engine, init_db
    init_db()
    with engine().begin() as c:  # other tests of the same database may have made them with another dimension
        c.execute(text("DROP TABLE IF EXISTS episode_chunks, doc_chunks CASCADE"))
        ids = [r[0] for r in c.execute(text("SELECT id FROM brains WHERE slug IN ('pgsrc', 'pgimp1', 'pgimp2')"))]
        for t in reversed(Base.metadata.sorted_tables):  # the brains of a previous run, with everything that hangs from them
            if ids and "brain_id" in t.c:
                c.execute(t.delete().where(t.c.brain_id.in_(ids)))
        c.execute(text("DELETE FROM brains WHERE id = ANY(:i)"), {"i": ids})
        c.execute(text("DELETE FROM embedding_engines"))  # the model switch tests leave theirs: the one in use is the environment's
        c.execute(text("DELETE FROM app_settings WHERE key = 'reindex_shadow'"))
    index.init_index()
    fake = Fake("viejo")
    for mod in (embed, index, docs):
        monkeypatch.setattr(mod, "get_embedder", lambda: fake)
    monkeypatch.setattr(docs, "start_index", lambda doc_id, user_id=None: docs.run_index(doc_id))
    _graphs(GRAPH, *NEW)
    jobs.INLINE = True
    with TestClient(app) as c:
        c.fake = fake
        yield c
    jobs.INLINE = False
    _graphs(GRAPH, *NEW)


def _source(c) -> int:
    """A brain with a graph whose entities and facts have their vectors, its episode index and an indexed document."""
    from mimirsynth import index
    from mimirsynth.db import client as fc
    from mimirsynth.models import Brain
    from mimirsynth.store import _factory
    v = c.fake.embed(["x"])[0]
    fc().select_graph(GRAPH).query(
        "CREATE (:Episodic {uuid:'e1', name:'nota', content:'Nextcloud runs on Notus, in rack 4', group_id:$g, valid_at:'2026-10-01T00:00:00Z'}) "
        "CREATE (a:Entity {uuid:'a', name:'Nextcloud', group_id:$g, name_embedding: vecf32($v)})"
        "-[:RELATES_TO {uuid:'f1', name:'HOSTED_ON', fact:'Nextcloud runs on Notus', group_id:$g, fact_embedding: vecf32($v)}]->"
        "(:Entity {uuid:'b', name:'Notus', group_id:$g, name_embedding: vecf32($v)})", {"g": GRAPH, "v": v})
    assert c.post("/api/brains", json={"slug": "pgsrc", "name": "Source", "graph_name": GRAPH}).status_code == 201
    body = b"# Racks\n\nNotus is in rack 4.\n\nPolaris is in rack 7.\n"
    up = c.post("/api/brains/pgsrc/docs/uploads", json={"filename": "racks.md", "size": len(body)}).json()
    c.put(f"/api/brains/pgsrc/docs/uploads/{up['upload_id']}/parts/0", content=body)
    assert c.post(f"/api/brains/pgsrc/docs/uploads/{up['upload_id']}/complete").status_code == 201
    with _factory()() as db:
        bid = db.query(Brain).filter(Brain.slug == "pgsrc").one().id
    assert index.sync_brain(bid, GRAPH)["chunks_written"] >= 1
    return bid


def _package(c) -> str:
    jid = c.post("/api/brains/pgsrc/exports", json={"vectors": True}).json()["id"]
    data = c.get(f"/api/brains/pgsrc/exports/{jid}/download").content
    uid = c.post("/api/brain-imports/uploads", json={"filename": "p.tar.gz", "size": len(data)}).json()["upload_id"]
    c.put(f"/api/brain-imports/uploads/{uid}/parts/0", content=data)
    return c.post(f"/api/brain-imports/uploads/{uid}/complete").json()


def _import(c, uid: str, slug: str) -> dict:
    jid = c.post("/api/brain-imports", json={"upload_id": uid, "slug": slug, "name": slug}).json()["id"]
    return next(i for i in c.get("/api/brain-imports").json()["items"] if i["id"] == jid)


def _bid(slug: str) -> int:
    return _sql("SELECT id FROM brains WHERE slug = :s", s=slug)[0][0]


def test_same_model_reuses_every_vector(client):
    src = _source(client)
    up = _package(client)
    assert up["manifest"]["embedding"]["same"] is True
    calls = client.fake.calls
    item = _import(client, up["upload_id"], NEW[0])
    assert item["state"] == "done", item
    assert item["vectors"]["reused"] and item["vectors"]["graph_computed"] == 0
    assert item["vectors"]["doc_chunks"]["computed"] == 0 and item["vectors"]["doc_chunks"]["copied"] >= 1
    assert item["vectors"]["episode_chunks"] == {"copied": 1, "computed": 0}
    assert client.fake.calls == calls                                         # not a single call to the engine
    new = _bid(NEW[0])
    q = "SELECT text, CAST(embedding AS text) FROM {} WHERE brain_id = :b ORDER BY 1"
    assert _sql(q.format("doc_chunks"), b=new) == _sql(q.format("doc_chunks"), b=src)
    assert _sql(q.format("episode_chunks"), b=new) == _sql(q.format("episode_chunks"), b=src)
    assert _sql("SELECT status, chunks FROM documents WHERE brain_id = :b", b=new) == [("active", item["vectors"]["doc_chunks"]["copied"])]
    hits = client.get(f"/api/brains/{NEW[0]}/docs/search", params={"q": "Notus rack"}).json()["results"]
    assert hits and "rack 4" in hits[0]["text"]                              # the imported index answers


def test_another_model_computes_them_again(client, monkeypatch):
    from mimirsynth import embed
    _source(client)
    up = _package(client)
    real = embed.resolve_embedding
    monkeypatch.setattr(embed, "resolve_embedding", lambda: {**real(), "model": "nuevo"})
    for mod in ("embed", "index", "docs"):
        monkeypatch.setattr(f"mimirsynth.{mod}.get_embedder", lambda: Fake("nuevo"))
    item = _import(client, up["upload_id"], NEW[1])
    assert item["state"] == "done", item
    assert item["source"]["embedding"]["same"] is False and item["vectors"]["reused"] is False
    assert item["vectors"]["graph_computed"] == 3                             # both entities and the fact
    assert item["vectors"]["doc_chunks"]["copied"] == 0 and item["vectors"]["doc_chunks"]["computed"] >= 1
    assert item["vectors"]["episode_chunks"]["copied"] == 0 and item["vectors"]["episode_chunks"]["computed"] == 1
    from mimirsynth.db import client as fc
    v = fc().select_graph(NEW[1]).query("MATCH (n:Entity {uuid:'a'}) RETURN n.name_embedding").result_set[0][0]
    assert v == pytest.approx(Fake("nuevo").embed(["Nextcloud"])[0], abs=1e-6)
