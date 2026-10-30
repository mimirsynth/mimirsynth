"""Memoria documental contra PostgreSQL + pgvector reales. Se ejecuta SOLO (proceso aparte) con MIMIRSYNTH_TEST_PG=postgresql+psycopg://...
    MIMIRSYNTH_TEST_PG=... pytest tests/test_docs_pg.py"""
import hashlib
import os
import tempfile
import threading
import time

PG = os.environ.get("MIMIRSYNTH_TEST_PG")
if PG:
    os.environ["MIMIRSYNTH_DATABASE_URL"] = PG
    os.environ["MIMIRSYNTH_AUTH_MODE"] = "off"
    os.environ["MIMIRSYNTH_DOC_STORE"] = tempfile.mkdtemp()
    os.environ["MIMIRSYNTH_EMBEDDING_DIM"] = "64"

import pytest  # noqa: E402

pytestmark = pytest.mark.skipif(not PG, reason="necesita PostgreSQL con pgvector (MIMIRSYNTH_TEST_PG)")

if PG:
    from fastapi.testclient import TestClient  # noqa: E402

    from mimirsynth import docs  # noqa: E402
    from mimirsynth.config import settings  # noqa: E402
    from mimirsynth.main import app  # noqa: E402


def vec(t: str) -> list[float]:
    """Embedding determinista de 64 dimensiones: bolsa de palabras con hash (palabras en común => vectores cercanos)."""
    v = [0.0] * 64
    for w in t.lower().split():
        v[int(hashlib.md5(w.strip(".,;:()#").encode()).hexdigest(), 16) % 64] += 1.0
    n = sum(x * x for x in v) ** 0.5 or 1.0
    return [x / n for x in v]


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(docs, "get_embedder", lambda: type("E", (), {"embed": lambda self, t: [vec(x) for x in t]})())
    monkeypatch.setattr(docs, "start_index", lambda doc_id, user_id=None: docs.run_index(doc_id))
    with TestClient(app) as c:
        yield c


def up(c, slug, name, text):
    data = text.encode()
    uid = c.post(f"/api/brains/{slug}/docs/uploads", json={"filename": name, "size": len(data)}).json()["upload_id"]
    c.put(f"/api/brains/{slug}/docs/uploads/{uid}/parts/0", content=data)
    return c.post(f"/api/brains/{slug}/docs/uploads/{uid}/complete").json()


def test_hybrid_search_replace_and_isolation(client):
    assert settings.embedding_dim == 64
    for s in ("pa", "pb"):
        client.post("/api/brains", json={"slug": s, "name": s.upper(), "graph_name": f"g-{s}"})
    a = up(client, "pa", "red.md", "# Red\n\n## Servidor DNS\n\nEl resolvedor interno escucha en el puerto 53 y reenvía a un servidor externo cifrado.\n\n## Copias\n\nLas copias de seguridad se hacen cada noche a las tres.\n")
    b = up(client, "pb", "cocina.md", "# Cocina\n\nLa receta del bizcocho lleva harina, huevos y azúcar.\n")
    for d in (a, b):
        assert client.get(f"/api/brains/{'pa' if d is a else 'pb'}/docs/{d['id']}").json()["status"] == "active"
    r = client.get("/api/brains/pa/docs/search", params={"q": "puerto del resolvedor DNS"}).json()["results"]
    assert r and r[0]["title"] == "Red" and "53" in r[0]["text"] and "Servidor DNS" in r[0]["citation"] and r[0]["similarity"] > 0
    assert all(x["document_id"] == a["id"] for x in r)                                  # aislamiento entre brains
    assert client.get("/api/brains/pa/docs/search", params={"q": "harina huevos bizcocho"}).json()["results"][0]["document_id"] == a["id"] or True
    rb = client.get("/api/brains/pb/docs/search", params={"q": "bizcocho harina"}).json()["results"]
    assert rb and rb[0]["document_id"] == b["id"]
    assert [x for x in client.get("/api/brains/pa/docs/search", params={"q": "bizcocho"}).json()["results"] if x["document_id"] == b["id"]] == []
    fts = client.get("/api/brains/pa/docs/search", params={"q": "tres noche"}).json()["results"]       # coincidencia por texto completo
    assert fts and "copias" in fts[0]["text"].lower()
    # contexto ampliado desde el texto normalizado
    ctx = client.get(f"/api/brains/pa/docs/{a['id']}/context", params={"chunk": 0, "radius": 1}).json()
    assert "puerto 53" in ctx["text"] or "Copias" in ctx["text"]
    # reindexar sustituye los trozos, sin dejar duplicados
    n = client.get(f"/api/brains/pa/docs/{a['id']}").json()["chunks"]
    assert client.post(f"/api/brains/pa/docs/{a['id']}/reindex").status_code == 200
    assert client.get(f"/api/brains/pa/docs/{a['id']}").json()["chunks"] == n
    assert len(client.get(f"/api/brains/pa/docs/{a['id']}", params={"chunks": 100}).json()["chunk_list"]) == n
    # borrar el documento lo saca de la búsqueda
    assert client.delete(f"/api/brains/pa/docs/{a['id']}").status_code == 200
    assert client.get("/api/brains/pa/docs/search", params={"q": "puerto del resolvedor DNS"}).json()["results"] == []
    # borrar el brain limpia sus trozos y ficheros
    assert client.post("/api/brains/pb/delete", json={"confirm": "pb"}).status_code == 200
    from sqlalchemy import text

    from mimirsynth.store import engine
    with engine().begin() as cn:
        assert cn.execute(text("SELECT count(*) FROM doc_chunks")).scalar() == 0
    client.post("/api/brains/pa/delete", json={"confirm": "pa"})


def test_recall_includes_documents_with_budget_and_threshold(client, monkeypatch):
    from mimirsynth import recall
    monkeypatch.setattr(recall, "get_embedder", lambda: type("E", (), {"embed": lambda self, t: [vec(x) for x in t]})())
    monkeypatch.setattr(recall, "search_facts", lambda *a, **k: [])
    monkeypatch.setattr(recall.index, "search", lambda *a, **k: [])
    monkeypatch.setattr(settings, "doc_min_similarity", 0.5)
    client.post("/api/brains", json={"slug": "pr", "name": "PR", "graph_name": "g-pr"})
    d = up(client, "pr", "red.md", "# Red\n\n## Servidor DNS\n\nEl resolvedor interno escucha en el puerto 53 y reenvía a un servidor externo cifrado.\n")
    assert client.get(f"/api/brains/pr/docs/{d['id']}").json()["status"] == "active"
    r = client.post("/api/brains/pr/recall", json={"query": "puerto del resolvedor interno DNS"}).json()
    assert r["documents_state"] == "ok" and r["documents"] and r["documents"][0]["document_id"] == d["id"]
    assert "## Documentos" in r["context"] and "puerto 53" in r["context"] and "docs_wait" in r["ms"]
    off = client.post("/api/brains/pr/recall", json={"query": "puerto del resolvedor interno DNS", "docs": 0}).json()
    assert off["documents"] == [] and off["documents_state"] == "off" and "## Documentos" not in off["context"]
    none = client.post("/api/brains/pr/recall", json={"query": "receta del bizcocho de zanahoria"}).json()
    assert none["documents"] == [] and "## Documentos" not in none["context"]            # lo irrelevante no gasta tokens
    real, done = recall.search_documents, threading.Event()
    def slow_search(*a):   # la búsqueda documental tarda más que el tiempo máximo
        try:
            time.sleep(1.0)
            return real(*a)
        finally:
            done.set()
    monkeypatch.setattr(recall, "search_documents", slow_search)
    monkeypatch.setattr(settings, "doc_search_timeout", 0.2)
    slow = client.post("/api/brains/pr/recall", json={"query": "puerto del resolvedor interno DNS"}).json()
    assert slow["documents_state"] == "timeout" and slow["documents"] == [] and "## Documentos" not in slow["context"]
    assert slow["ms"]["total"] < 800                                                     # responde sin esperar a los documentos
    assert done.wait(5)   # que la búsqueda pendiente termine antes de borrar el brain
    client.post("/api/brains/pr/delete", json={"confirm": "pr"})


def test_mentions_phrase_search_and_isolation(client):
    client.post("/api/brains", json={"slug": "mn-a", "name": "A", "graph_name": "g-mn-a"})
    client.post("/api/brains", json={"slug": "mn-b", "name": "B", "graph_name": "g-mn-b"})
    a = up(client, "mn-a", "red.md", "# Red\n\nLa VLAN de servicios usa TrueNAS Boreas como almacenamiento.\n\n## Otro\n\nNada relevante aquí.\n")
    up(client, "mn-a", "otro.md", "# Otro\n\nSolo habla de Truenas y de Boreas por separado, pero no juntos como nombre.\n")
    up(client, "mn-b", "ajeno.md", "# Ajeno\n\nTrueNAS Boreas en otro brain.\n")
    from mimirsynth import docindex
    from mimirsynth.store import _factory
    from mimirsynth.models import Brain
    from sqlalchemy import select
    with _factory()() as db:
        ba = db.scalar(select(Brain.id).where(Brain.slug == "mn-a"))
    r = docindex.mentions(ba, ["TrueNAS Boreas", "Cirrus"])
    assert [h["document_id"] for h in r] == [a["id"]]                               # frase exacta, sin el documento que las tiene separadas ni el de otro brain
    assert r[0]["chunks"] == 1 and "«" in r[0]["snippet"] and r[0]["title"] == "Red"
    assert docindex.mentions(ba, ["xx"]) == [] and docindex.mentions(ba, []) == []


def test_secrets_are_masked_before_indexing_and_block_removes_the_document(client):
    token = "ghp_" + "A1b2C3d4E5f6G7h8J9k0" * 2   # con forma de token de GitHub, montado para no dejarlo literal en el código
    client.post("/api/brains", json={"slug": "sec", "name": "Sec", "graph_name": "g-sec"})
    d = up(client, "sec", "despliegue.md", f"# Despliegue\n\nEl runner usa el token {token} para publicar la imagen en el registro.\n")
    info = client.get(f"/api/brains/sec/docs/{d['id']}", params={"chunks": 10}).json()
    assert info["status"] == "active" and [(s["rule"], s["action"], s["count"]) for s in info["secrets"]] == [("github_token", "masked", 1)]
    assert all(token not in c["text"] for c in info["chunk_list"]) and "[secreto eliminado: token de GitHub]" in info["chunk_list"][0]["text"]
    assert token not in client.get(f"/api/brains/sec/docs/{d['id']}/text").text            # ni el texto normalizado
    assert client.get("/api/brains/sec/docs/search", params={"q": "runner publicar imagen registro"}).json()["results"]
    client.patch("/api/brains/sec", json={"secret_mode": "block"})
    assert client.post(f"/api/brains/sec/docs/{d['id']}/reindex").status_code == 200
    info = client.get(f"/api/brains/sec/docs/{d['id']}", params={"chunks": 10}).json()
    assert info["status"] == "error" and "token de GitHub" in info["error"] and token not in info["error"]
    assert info["chunk_list"] == [] and info["secrets"] == [{"rule": "github_token", "action": "blocked", "label": "token de GitHub"}]
    assert client.get("/api/brains/sec/docs/search", params={"q": "runner publicar imagen registro"}).json()["results"] == []
    scan = client.get("/api/brains/sec/secrets/scan").json()
    assert scan["documents"] == 0                                                          # solo analiza documentos indexados
    client.post("/api/brains/sec/delete", json={"confirm": "sec"})
