"""Federación entre brains: concesiones, permisos, fusión en la consulta y etiquetado del origen."""
from datetime import timedelta

from fastapi.testclient import TestClient

from test_control import _as, client  # noqa: F401

from mimirsynth import memory, recall as R
from mimirsynth.main import app
from mimirsynth.models import BrainGrant, now
from mimirsynth.store import _factory


def _brains(client, *slugs):  # noqa: F811
    for s in slugs:
        client.post("/api/brains", json={"slug": s, "name": s.upper()})


def test_grant_lifecycle_and_audit(client):  # noqa: F811
    _brains(client, "fa", "fb")
    assert client.post("/api/brains/fa/grants", json={"target": "fa"}).status_code == 400            # a sí mismo
    assert client.post("/api/brains/fa/grants", json={"target": "no-existe"}).status_code == 404
    assert client.post("/api/brains/fa/grants", json={"target": "fb", "scope": "todo"}).status_code == 400
    assert client.post("/api/brains/fa/grants", json={"target": "fb", "days": 0}).status_code == 400
    g = client.post("/api/brains/fa/grants", json={"target": "fb", "scope": "graph", "days": 30})
    assert g.status_code == 201 and g.json()["scope"] == "graph" and g.json()["active"] is True and g.json()["expires_at"]
    gid = g.json()["id"]
    assert client.post("/api/brains/fa/grants", json={"target": "fb"}).status_code == 409           # una por pareja
    assert [x["target"]["slug"] for x in client.get("/api/brains/fa/grants").json()["given"]] == ["fb"]
    assert [x["source"]["slug"] for x in client.get("/api/brains/fb/grants").json()["received"]] == ["fa"]
    assert client.get("/api/brains/fb/grants").json()["given"] == []
    up = client.patch(f"/api/brains/fa/grants/{gid}", json={"scope": "both", "no_expiry": True}).json()
    assert up["scope"] == "both" and up["expires_at"] is None
    assert client.patch(f"/api/brains/fb/grants/{gid}", json={"scope": "docs"}).status_code == 403   # el destino no cambia lo que se le presta
    assert client.patch(f"/api/brains/fa/grants/{gid}", json={"scope": "x"}).status_code == 400
    assert client.delete(f"/api/brains/fa/grants/{gid}").json() == {"ok": True}
    assert client.get("/api/brains/fb/grants").json()["received"] == []
    assert client.delete(f"/api/brains/fa/grants/{gid}").status_code == 404
    acts = [a["action"] for a in client.get("/api/audit").json()]
    assert {"grant.create", "grant.update", "grant.revoke"} <= set(acts)


def test_target_can_renounce(client):  # noqa: F811
    _brains(client, "fc", "fd")
    gid = client.post("/api/brains/fc/grants", json={"target": "fd"}).json()["id"]
    assert client.delete(f"/api/brains/fd/grants/{gid}").status_code == 200   # el destino renuncia
    assert client.delete(f"/api/brains/fc/grants/{gid}").status_code == 404
    _brains(client, "fe")
    gid = client.post("/api/brains/fc/grants", json={"target": "fd"}).json()["id"]
    assert client.delete(f"/api/brains/fe/grants/{gid}").status_code == 404   # un tercero no la ve


def test_permissions(client):  # noqa: F811
    _brains(client, "pa", "pb", "pc")
    client.put("/api/brains/pa/members", json={"email": "ana@x.com", "role": "admin"})
    client.put("/api/brains/pb/members", json={"email": "ana@x.com", "role": "reader"})
    client.put("/api/brains/pa/members", json={"email": "luis@x.com", "role": "curator"})
    _as("luis@x.com", "Luis")
    assert client.post("/api/brains/pa/grants", json={"target": "pb"}).status_code == 403     # prestar exige administrar el origen
    _as("ana@x.com", "Ana")
    assert client.post("/api/brains/pa/grants", json={"target": "pc"}).status_code == 404     # y tener acceso al destino (sin revelar brains ajenos)
    gid = client.post("/api/brains/pa/grants", json={"target": "pb"}).json()["id"]
    assert client.get("/api/brains/pb/grants").json() == {"received": client.get("/api/brains/pb/grants").json()["received"], "given": []}
    assert len(client.get("/api/brains/pb/grants").json()["received"]) == 1                    # un lector del destino ve de dónde le llega
    assert client.delete(f"/api/brains/pb/grants/{gid}").status_code == 403                    # pero renunciar exige administrar el destino
    app.dependency_overrides.clear()


def test_sources_ignore_expired_and_deleted_brain(client):  # noqa: F811
    from mimirsynth.federation import sources_for
    from mimirsynth.models import Brain
    from sqlalchemy import select
    _brains(client, "xa", "xb", "xc")
    client.post("/api/brains/xa/grants", json={"target": "xc", "scope": "docs"})
    client.post("/api/brains/xb/grants", json={"target": "xc"})
    with _factory()() as db:
        xc = db.scalar(select(Brain).where(Brain.slug == "xc"))
        assert [(s.slug, s.scope) for s in sources_for(db, xc)] == [("xa", "docs"), ("xb", "both")]
        g = db.scalar(select(BrainGrant).where(BrainGrant.source.has(slug="xa")))
        g.expires_at = now() - timedelta(minutes=1); db.commit()
        assert [s.slug for s in sources_for(db, xc)] == ["xb"]                                   # la caducada deja de valer sola
    assert client.post("/api/brains/xb/delete", json={"confirm": "xb"}).status_code == 200
    with _factory()() as db:
        assert db.scalar(select(BrainGrant).where(BrainGrant.source_brain_id.is_not(None), BrainGrant.target_brain_id == xc.id,
                                                  BrainGrant.source.has(slug="xb"))) is None
        assert [s.slug for s in sources_for(db, db.scalar(select(Brain).where(Brain.slug == "xc")))] == []


def _fact(text, score, status="valid", **kw):
    return {"uuid": text, "name": "R", "fact": text, "valid_at": "2026-01-01T00:00:00Z", "invalid_at": None, "expired_at": None, "created_at": "2026-01-01T00:00:00Z",
            "score": score, "status": status, **kw}


def test_recall_merges_labels_and_dedupes(monkeypatch):
    class Emb:
        def embed(self, xs): return [[0.0] * 3 for _ in xs]
    graphs = {"own": [_fact("Vaultwarden corre en Altair", .9), _fact("Plex corre en Antares", .8)],
              "prestado": [_fact("vaultwarden corre en altair", .95), _fact("Grafana corre en LXC 9", .85)],
              "roto": None}
    def fake_facts(g, qvec, n, amap=None):
        if graphs[g] is None:
            raise RuntimeError("FalkorDB caído")
        return [dict(f) for f in graphs[g]]
    chunks = {1: [{"id": 1, "name": "ep propio", "text": "texto propio", "valid_at": "2026-01-01", "rrf": .03}],
              2: [{"id": 7, "name": "ep prestado", "text": "texto prestado", "valid_at": "2026-01-01", "rrf": .03}]}
    monkeypatch.setattr(R, "search_facts", fake_facts)
    monkeypatch.setattr(R.index, "search", lambda bid, *a, **k: [dict(c) for c in chunks.get(bid, [])])
    monkeypatch.setattr(R.index, "enabled", lambda: False)
    monkeypatch.setattr(R, "alias_map", lambda db, bid: {})
    out = R.recall(1, "own", "dónde corre algo", 8, 4, 6000, embedder=Emb(), n_docs=0,
                   sources=[R.Source(2, "prestado", "otro", "Otro", "both"), R.Source(3, "roto", "caido", "Caído", "graph"), R.Source(4, "d", "solodocs", "D", "docs")])
    texts = [f["fact"] for f in out["facts"]]
    assert texts.count("Vaultwarden corre en Altair") == 1 and "vaultwarden corre en altair" not in texts   # el duplicado prestado cede ante lo propio
    assert "Grafana corre en LXC 9" in texts
    assert "- Grafana corre en LXC 9 (desde 2026-01-01) · de «otro»" in out["context"]
    assert "- Plex corre en Antares (desde 2026-01-01)\n" in out["context"] + "\n"                              # lo propio no lleva etiqueta
    assert "ep prestado · de «otro»" in out["context"] and "ep propio\n" in out["context"]
    states = {f["slug"]: f["state"] for f in out["federated"]}
    assert states["otro"] == "ok" and states["caido"] == "error" and states["solodocs"] == "off"             # un origen caído no tumba la consulta
    own = R.recall(1, "own", "x", 8, 4, 6000, embedder=Emb(), n_docs=0)
    assert "federated" not in own and all("origin" not in f for f in own["facts"])


def test_recall_scope_docs_only_skips_graph(monkeypatch):
    class Emb:
        def embed(self, xs): return [[0.0] for _ in xs]
    called = []
    monkeypatch.setattr(R, "search_facts", lambda g, *a, **k: called.append(g) or [])
    monkeypatch.setattr(R.index, "search", lambda *a, **k: [])
    monkeypatch.setattr(R, "alias_map", lambda db, bid: {})
    R.recall(1, "own", "q", 3, 2, 3000, embedder=Emb(), n_docs=0, sources=[R.Source(2, "otro", "o", "O", "docs")])
    assert called == ["own"]                                                                                  # solo-documentos no abre el grafo del origen


def test_documents_fused_with_origin(monkeypatch):
    from mimirsynth import docindex
    hit = lambda i, sim, **k: {"id": i, "document_id": i, "chunk_idx": 0, "heading_path": "", "page": None, "title": f"Doc{i}", "text": "alpha beta gamma", "similarity": sim, **k}
    monkeypatch.setattr(R.index, "enabled", lambda: True)
    monkeypatch.setattr(R.appsettings, "get", lambda k: 0.5)
    monkeypatch.setattr(docindex, "search", lambda bid, *a, **k: [hit(1, .9)] if bid == 1 else [hit(1, .9, text="alpha beta delta")])   # mismo id de trozo en ambos brains: no se confunden
    passages, state = R.search_documents(1, [0.0], "alpha beta", 4, [R.Source(2, "g", "otro", "O", "both"), R.Source(3, "g", "solografo", "S", "graph")])
    assert state == "ok" and [p.get("origin") for p in passages] == [None, "otro"]
    assert "· de «otro»" in R.docs_block(passages)
    monkeypatch.setattr(docindex, "search", lambda bid, *a, **k: [hit(1, .9)])   # el mismo texto en el origen no se repite: manda lo propio
    passages, _ = R.search_documents(1, [0.0], "alpha beta", 4, [R.Source(2, "g", "otro", "O", "both")])
    assert [p.get("origin") for p in passages] == [None]


def test_memory_endpoint_passes_sources_only_when_granted(client, monkeypatch):  # noqa: F811
    _brains(client, "ma", "mb")
    seen = []
    monkeypatch.setattr(memory, "recall", lambda *a, **k: seen.append(k) or {"context": "", "facts": [], "chunks": []})
    assert client.post("/api/brains/mb/recall", json={"query": "q"}).status_code == 200
    assert "sources" not in seen[-1]                                                                          # sin concesiones: llamada idéntica a la de siempre
    client.post("/api/brains/ma/grants", json={"target": "mb", "scope": "graph"})
    client.post("/api/brains/mb/recall", json={"query": "q"})
    assert [s.slug for s in seen[-1]["sources"]] == ["ma"]
    client.post("/api/brains/mb/recall", json={"query": "q", "federated": False})
    assert "sources" not in seen[-1]                                                                          # «solo lo propio»
    client.post("/api/brains/ma/recall", json={"query": "q"})
    assert "sources" not in seen[-1]                                                                          # la concesión es en un solo sentido
