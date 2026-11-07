"""Relevance threshold of the recall (#281): facts and episode fragments too far from the query stay out, each one says how close it
is, a request can ask for another threshold, and the reference queries can simulate it. The graph and the index are fakes."""
from test_control import client  # noqa: F401

from mimirsynth import appsettings, memory, recall as R, refqueries as RQ, shelflife


class Emb:
    def embed(self, xs):
        return [[0.0] * 3 for _ in xs]


def _fact(text, similarity, status="current"):
    return {"uuid": text, "name": "R", "fact": text, "valid_at": "2026-01-01T00:00:00Z", "invalid_at": None, "expired_at": None,
            "created_at": "2026-01-01T00:00:00Z", "score": round((1 + similarity) / 2, 4), "similarity": similarity, "status": status}


def _chunk(cid, text, similarity):
    return {"id": cid, "name": f"ep {cid}", "text": text, "valid_at": "2026-01-01", "episode_uuid": f"e{cid}", "score": similarity,
            "similarity": similarity, "rrf": 0.03}


def _graph(monkeypatch, facts, chunks):
    asked = {}

    def search(bid, qvec, query, k=4, **kw):
        asked["k"] = k
        return [dict(c) for c in chunks][:k]
    monkeypatch.setattr(R, "search_facts", lambda g, qvec, n, amap=None: [dict(f) for f in facts])
    monkeypatch.setattr(R.index, "search", search)
    monkeypatch.setattr(R.index, "enabled", lambda: False)
    monkeypatch.setattr(R, "alias_map", lambda db, bid: {})
    monkeypatch.setattr(shelflife, "mark", lambda bid, facts, amap=None: facts)   # no shelf lives here
    return asked


FACTS = [_fact("El SAI del rack lo vigila NUT en el host nas01", 0.71), _fact("Sonarr no pide autenticación en la red local", 0.38),
         _fact("El proveedor LLM por defecto es local", 0.33, "invalidated")]
CHUNKS = [_chunk(1, "Instalamos NUT en nas01 para vigilar el SAI", 0.66), _chunk(2, "Se colgó el nodo de Lidarr", 0.31),
          _chunk(3, "La IP del servidor NUT cambió tras mover el SAI", 0.50)]


def test_only_what_passes_the_threshold(monkeypatch):
    _graph(monkeypatch, FACTS, CHUNKS)
    out = R.recall(1, "g", "¿Cuál es la IP del servidor NUT?", 6, 3, 4000, embedder=Emb(), n_docs=0, min_similarity=0.55)
    assert [f["fact"] for f in out["facts"]] == ["El SAI del rack lo vigila NUT en el host nas01"]
    # chunk 3 is 0.05 under the threshold but shares «servidor» and «nut» with the query; chunk 2 shares nothing
    assert [c["id"] for c in out["chunks"]] == [1, 3]
    assert "Sonarr" not in out["context"] and "Lidarr" not in out["context"] and "dejaron de ser ciertos" not in out["context"]
    assert out["min_similarity"] == 0.55 and out["facts"][0]["similarity"] == 0.71


def test_nothing_relevant_returns_an_empty_context(monkeypatch):
    _graph(monkeypatch, FACTS, CHUNKS)
    out = R.recall(1, "g", "ok, sigue con lo de antes", 6, 3, 4000, embedder=Emb(), n_docs=0, min_similarity=0.75)
    assert out["facts"] == [] and out["chunks"] == [] and out["context"] == ""


def test_zero_turns_it_off_and_the_setting_is_the_default(monkeypatch):
    _graph(monkeypatch, FACTS, CHUNKS)
    out = R.recall(1, "g", "x", 6, 3, 4000, embedder=Emb(), n_docs=0, min_similarity=0)
    assert len(out["facts"]) == 3 and len(out["chunks"]) == 3
    monkeypatch.setattr(R.appsettings, "get", lambda k, real=appsettings.get: 0.7 if k == "recall_min_similarity" else real(k))
    out = R.recall(1, "g", "x", 6, 3, 4000, embedder=Emb(), n_docs=0)
    assert out["min_similarity"] == 0.7 and [f["similarity"] for f in out["facts"]] == [0.71]


def test_fragments_are_asked_for_twice_so_the_threshold_does_not_leave_them_short(monkeypatch):
    asked = _graph(monkeypatch, [], [_chunk(i, f"texto {i}", 0.2 if i % 2 else 0.8) for i in range(1, 9)])
    out = R.recall(1, "g", "q", 6, 3, 4000, embedder=Emb(), n_docs=0, min_similarity=0.55)
    assert asked["k"] == 6 and [c["id"] for c in out["chunks"]] == [2, 4, 6]


def test_a_fact_without_similarity_is_judged_by_its_score():
    old = {"fact": "a", "score": 0.7}   # (1 + cosine) / 2: a cosine of 0.4
    assert R.keep_facts([old], 0.5) == [] and R.keep_facts([old], 0.4) == [old] and R.keep_facts([{"fact": "b"}], 0.9) == [{"fact": "b"}]


def test_the_request_and_the_mcp_tool_pass_it_on(client, monkeypatch):  # noqa: F811
    seen = []
    monkeypatch.setattr(memory, "recall", lambda *a, **k: seen.append(k) or {"context": "", "facts": [], "chunks": []})
    client.post("/api/brains", json={"slug": "th1", "name": "TH1"})
    assert client.post("/api/brains/th1/recall", json={"query": "q", "min_similarity": 0.6}).status_code == 200
    assert client.post("/api/brains/th1/recall", json={"query": "q"}).status_code == 200
    assert client.post("/api/brains/th1/recall", json={"query": "q", "min_similarity": 1.5}).status_code == 422
    assert [k["min_similarity"] for k in seen] == [0.6, None]


def test_reference_queries_simulate_the_facts_threshold(client, monkeypatch):  # noqa: F811
    used = []

    def fake(bid, graph, query, *a, min_similarity=None, **k):
        used.append(min_similarity)
        facts = [{"fact": "Vaultwarden corre en Altair", "status": "current"}] if (min_similarity or 0) <= 0.6 else []
        return {"facts": facts, "chunks": [], "documents": [], "documents_state": "ok", "ms": {"total": 1}}
    monkeypatch.setattr(R, "recall", fake)
    client.post("/api/brains", json={"slug": "th2", "name": "TH2"})
    client.post("/api/brains/th2/refqueries", json={"query": "¿Dónde corre Vaultwarden?", "expect": [{"text": "Altair", "kind": "fact"}]})
    runs = client.post("/api/brains/th2/refqueries/runs", json={"sweep": [0.7, 0.5], "sweep_of": "min_similarity"}).json()["runs"]
    got = {x["params"].get("min_similarity"): x["summary"]["found"] for x in client.get("/api/brains/th2/refqueries/runs").json()["items"] if x["id"] in runs}
    assert got == {0.5: 1, 0.7: 0} and sorted(used) == [0.5, 0.7]
    assert client.post("/api/brains/th2/refqueries/runs", json={"sweep": [0.5], "sweep_of": "facts"}).status_code == 422
    assert RQ.RunIn().sweep_of == "min_sim"   # the passages' threshold stays the default
