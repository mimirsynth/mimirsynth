"""Consultas de referencia (#115): alta, importación, ejecución con métricas, simulación de umbral, comparación y aviso tras un
cambio de modelo de embeddings. El recall se sustituye por uno falso y determinista."""
from test_control import _as, client  # noqa: F401

from mimirsynth import appsettings, recall as R, refqueries as RQ
from mimirsynth.main import app
from mimirsynth.models import Brain, Notification, RefRun
from mimirsynth.store import _factory

STATE = {"worse": False}


def fake_recall(bid, graph, query, n_facts=8, n_chunks=4, max_chars=6000, n_docs=None, lang="es", min_sim=None, **k):
    """Hechos y fragmentos fijos; el pasaje de documentos solo sale con un umbral de 0,70 o menos (o el de la instancia)."""
    th = appsettings.get("doc_min_similarity") if min_sim is None else min_sim
    facts = [] if STATE["worse"] else [{"fact": "Vaultwarden corre en Altair", "status": "valid"}]
    docs = [{"text": "El puerto del resolvedor DNS es el 53."}] if th <= 0.70 and "dns" in query.lower() else []
    return {"facts": facts, "chunks": [{"text": "Episodio: migramos la base de datos a db02"}], "documents": docs, "documents_state": "ok",
            "ms": {"total": 12}}


def _setup(client, slug, monkeypatch):  # noqa: F811
    monkeypatch.setattr(R, "recall", fake_recall)
    STATE["worse"] = False
    client.post("/api/brains", json={"slug": slug, "name": slug.upper()})


def test_crud_validation_and_permissions(client, monkeypatch):  # noqa: F811
    _setup(client, "rq1", monkeypatch)
    q = {"query": "¿Dónde corre Vaultwarden?", "expect": [{"text": "Altair", "kind": "fact"}], "avoid": [{"text": "db02"}], "docs": False}
    r = client.post("/api/brains/rq1/refqueries", json=q)
    assert r.status_code == 201 and r.json()["avoid"] == [{"text": "db02", "kind": "any"}]
    qid = r.json()["id"]
    assert client.post("/api/brains/rq1/refqueries", json={**q, "expect": [{"text": "x", "kind": "nada"}]}).status_code == 422
    assert client.post("/api/brains/rq1/refqueries", json={**q, "query": ""}).status_code == 422
    up = client.patch(f"/api/brains/rq1/refqueries/{qid}", json={"note": "medida en #65", "clear_docs": True}).json()
    assert up["note"] == "medida en #65" and up["docs"] is None and up["query"] == q["query"]
    client.put("/api/brains/rq1/members", json={"email": "colab@x.com", "role": "contributor"})
    _as("colab@x.com", "Colab")
    assert client.get("/api/brains/rq1/refqueries").status_code == 403                    # solo curadores o superior
    app.dependency_overrides.clear()
    assert client.delete(f"/api/brains/rq1/refqueries/{qid}").json() == {"ok": True}
    assert client.get("/api/brains/rq1/refqueries").json()["items"] == []
    assert client.post("/api/brains/rq1/refqueries/runs", json={}).status_code == 409    # sin consultas no hay nada que medir


def test_import_export_roundtrip(client, monkeypatch):  # noqa: F811
    _setup(client, "rq2", monkeypatch)
    items = [{"query": "Puerto del DNS", "expect": [{"text": "puerto del resolvedor", "kind": "doc"}], "avoid": [], "docs": True, "note": ""},
             {"query": "Hay PR y comentarios nuevos", "expect": [], "avoid": [{"text": "resolvedor", "kind": "doc"}], "docs": False, "note": "negativo real"}]
    assert client.post("/api/brains/rq2/refqueries/import", json={"items": items}).json() == {"added": 2, "skipped": 0}
    assert client.post("/api/brains/rq2/refqueries/import", json={"items": [{**items[0], "query": "  puerto DEL dns "}]}).json() == {"added": 0, "skipped": 1}
    out = client.get("/api/brains/rq2/refqueries/export").json()["items"]
    assert out == items
    client.post("/api/brains", json={"slug": "rq2b", "name": "B"})
    assert client.post("/api/brains/rq2b/refqueries/import", json={"items": out}).json()["added"] == 2   # a otro brain
    assert client.post("/api/brains/rq2b/refqueries/import", json={"items": out[:1], "replace": True}).json()["added"] == 1
    assert len(client.get("/api/brains/rq2b/refqueries").json()["items"]) == 1


def test_run_measures_found_false_positives_and_docs(client, monkeypatch):  # noqa: F811
    _setup(client, "rq3", monkeypatch)
    monkeypatch.setattr(appsettings, "get", lambda k, _g=appsettings.get: 0.72 if k == "doc_min_similarity" else _g(k))
    client.post("/api/brains/rq3/refqueries", json={"query": "¿Dónde corre Vaultwarden?", "expect": [{"text": "vaultwarden  CORRE", "kind": "fact"},
                                                                                                    {"text": "db02", "kind": "fact"}],
                                                    "avoid": [{"text": "migramos", "kind": "any"}]})
    client.post("/api/brains/rq3/refqueries", json={"query": "Puerto del DNS", "expect": [{"text": "puerto del resolvedor", "kind": "doc"}], "docs": True})
    rid = client.post("/api/brains/rq3/refqueries/runs", json={}).json()["runs"][0]
    run = client.get(f"/api/brains/rq3/refqueries/runs/{rid}").json()
    s = run["summary"]
    assert run["status"] == "done" and run["params"] == {}
    assert (s["queries"], s["expected"], s["found"], s["false_positives"], s["docs_mismatch"]) == (2, 3, 1, 1, 1)   # con 0,72 el pasaje no sale
    assert s["recall"] == 0.333 and s["by_kind"]["fact"] == {"found": 1, "false_positives": 0} and s["by_kind"]["chunk"]["false_positives"] == 1
    first = run["results"][0]
    assert [i["found_in"] for i in first["expect"]] == [["fact"], []]                    # db02 está en un fragmento, no en un hecho
    assert first["avoid"][0]["found_in"] == ["chunk"] and s["delta"] is None
    assert client.get("/api/brains/rq3/refqueries").json()["last_run"]["id"] == rid


def test_sweep_simulates_without_changing_settings_and_compares(client, monkeypatch):  # noqa: F811
    _setup(client, "rq4", monkeypatch)
    before = appsettings.get("doc_min_similarity")
    client.post("/api/brains/rq4/refqueries", json={"query": "Puerto del DNS", "expect": [{"text": "puerto del resolvedor", "kind": "doc"}]})
    base = client.post("/api/brains/rq4/refqueries/runs", json={"params": {"min_sim": 0.9}}).json()["runs"]   # simulación: no es la referencia
    assert client.get(f"/api/brains/rq4/refqueries/runs/{base[0]}").json()["summary"]["delta"] is None
    real = client.post("/api/brains/rq4/refqueries/runs", json={}).json()["runs"][0]
    runs = client.post("/api/brains/rq4/refqueries/runs", json={"sweep": [0.72, 0.68]}).json()["runs"]
    got = {tuple(sorted(x["params"].items())): x["summary"] for x in client.get("/api/brains/rq4/refqueries/runs").json()["items"] if x["id"] in runs}
    assert got[(("min_sim", 0.68),)]["found"] == 1 and got[(("min_sim", 0.72),)]["found"] == 0
    assert got[(("min_sim", 0.72),)]["previous_run"] == real
    assert appsettings.get("doc_min_similarity") == before                                 # el ajuste no se toca


def test_after_embedding_switch_runs_and_warns_on_regression(client, monkeypatch):  # noqa: F811
    _setup(client, "rq5", monkeypatch)
    client.post("/api/brains/rq5/refqueries", json={"query": "¿Dónde corre Vaultwarden?", "expect": [{"text": "Altair"}]})
    client.post("/api/brains/rq5/refqueries/runs", json={})                                # referencia con el modelo anterior
    STATE["worse"] = True                                                                 # el modelo nuevo ya no encuentra el hecho
    runs = RQ.run_after_switch()                                                          # un brain por cada uno con consultas
    with _factory()() as db:
        bid = db.query(Brain.id).filter(Brain.slug == "rq5").scalar()
        mine = [r for r in (db.get(RefRun, x) for x in runs) if r.brain_id == bid]
        assert len(mine) == 1 and mine[0].reason == "embedding.switched" and mine[0].summary["delta"]["found"] == -1 and mine[0].summary["delta"]["regressed"]
        n = db.query(Notification).filter(Notification.event == "refquery.regressed", Notification.key == "refquery:rq5").one()
        assert "RQ5" in n.title


def test_evaluate_unit():
    q = {"id": 1, "query": "x", "expect": [{"text": "B  c", "kind": "any"}, {"text": "zz", "kind": "doc"}], "avoid": [{"text": "top", "kind": "chunk"}], "docs": False}   # «top» está, pero en un pasaje
    out = {"facts": [{"fact": "a b C d"}], "chunks": [{"text": "nada"}], "documents": [{"text": "zz top"}], "ms": {"total": 5}}
    r = RQ.evaluate(q, out)
    assert [i["found_in"] for i in r["expect"]] == [["fact"], ["doc"]] and r["found"] == 2 and r["false_positives"] == 0 and r["docs_ok"] is False
    assert RQ.compare({"found": 2, "false_positives": 0, "docs_mismatch": 0, "expected": 2}, {"found": 3, "false_positives": 0, "docs_mismatch": 0, "expected": 2})["regressed"]
