"""Cambio de modelo de embeddings (reembed) contra un FalkorDB real: los vectores nuevos se calculan aparte, el motor por defecto
solo cambia si todo termina bien, un fallo deja todo como estaba, cancelar limpia y reintentar no recalcula lo ya hecho."""
import hashlib
import os
import threading
import time

import pytest
from test_control import client  # noqa: F401

FALKOR = os.environ.get("MIMIRSYNTH_TEST_FALKOR")
needs_falkor = pytest.mark.skipif(not FALKOR, reason="necesita un FalkorDB desechable (MIMIRSYNTH_TEST_FALKOR=host)")
GRAPH = "zz-test-reembed"
ENTITIES = ["Vesta", "Cloudco", "Plex"]
FACTS = {"f1": "Vesta está alojado en Cloudco", "f2": "Plex corre\nen Vesta"}


def vec(model: str, dim: int, t: str) -> list[float]:
    """Embedding determinista: bolsa de palabras con hash, distinta para cada modelo."""
    v = [0.0] * dim
    for w in t.lower().split():
        v[int(hashlib.md5(f"{model}:{w}".encode()).hexdigest(), 16) % dim] += 1.0
    n = sum(x * x for x in v) ** 0.5 or 1.0
    return [x / n for x in v]


class Fake:
    def __init__(self, model: str, dim: int):
        self.model, self.dim, self.texts, self.fail, self.hook = model, dim, [], False, None

    def embed(self, texts: list[str]) -> list[list[float]]:
        if self.hook:
            self.hook(self, texts)
        if self.fail:
            raise RuntimeError("motor caído")
        self.texts += texts
        return [vec(self.model, self.dim, t) for t in texts]


def close(a, b) -> bool:
    return a is not None and len(a) == len(b) and all(abs(x - y) < 1e-5 for x, y in zip(a, b))


@pytest.fixture()
def env(client, monkeypatch):  # noqa: F811
    import falkordb
    from sqlalchemy import delete

    from mimirsynth import db as fdb
    from mimirsynth import embeddings_admin as ea
    from mimirsynth import reembed
    from mimirsynth.config import settings
    from mimirsynth.models import EmbeddingEngine, Job
    from mimirsynth.store import _factory
    monkeypatch.setattr(settings, "falkor_host", FALKOR)
    fdb.client.cache_clear()
    monkeypatch.setattr(settings, "embedding_dim", 4)
    monkeypatch.setattr(ea, "_probe", lambda url, model, key: {"viejo": 4, "nuevo": 8}[model])
    monkeypatch.setattr(reembed, "RETRY_WAIT", 0)
    monkeypatch.setattr(reembed, "BATCH", 2)  # varios lotes por tipo
    fakes = {"viejo": Fake("viejo", 4), "nuevo": Fake("nuevo", 8)}
    monkeypatch.setattr(reembed, "_embedder", lambda e: fakes[e.model])
    with _factory()() as db:
        db.execute(delete(EmbeddingEngine)); db.execute(delete(Job).where(Job.kind == reembed.KIND)); db.commit()
    c = falkordb.FalkorDB(host=FALKOR, port=6379)
    try:
        c.select_graph(GRAPH).delete()
    except Exception:  # noqa: BLE001
        pass
    g = c.select_graph(GRAPH)
    for i, n in enumerate(ENTITIES):
        g.query("CREATE (:Entity {uuid:$u, name:$n, name_embedding: vecf32($v)})", {"u": f"e{i}", "n": n, "v": vec("viejo", 4, n)})
    g.query("CREATE (:Community {uuid:'c1', name:'Servidores', name_embedding: vecf32($v)})", {"v": vec("viejo", 4, "Servidores")})
    for (u, f), (a, b) in zip(FACTS.items(), [("e0", "e1"), ("e2", "e0")]):
        g.query("MATCH (a:Entity {uuid:$a}), (b:Entity {uuid:$b}) CREATE (a)-[:RELATES_TO {uuid:$u, name:'X', fact:$f, group_id:$g, "
                "created_at:'2026-01-01T00:00:00+00:00', fact_embedding: vecf32($v)}]->(b)", {"a": a, "b": b, "u": u, "f": f, "g": GRAPH, "v": vec("viejo", 4, f)})
    client.post("/api/brains", json={"slug": "reemb", "name": "Reemb", "graph_name": GRAPH})
    old = client.post("/api/embedding-engines", json={"name": "local-viejo", "base_url": "http://o/v1", "model": "viejo"}).json()
    new = client.post("/api/embedding-engines", json={"name": "local-nuevo", "base_url": "http://n/v1", "model": "nuevo"}).json()
    assert old["is_default"] and not new["is_default"]
    yield {"g": g, "old": old, "new": new, "fakes": fakes}
    client.post("/api/brains/reemb/delete", json={"confirm": "reemb"})
    g.delete()


def one(g, q: str, p: dict | None = None):
    return g.query(q, p or {}).result_set[0][0]


def vectors(g) -> dict:
    out = {r[0]: r[1] for r in g.query("MATCH (x) WHERE x:Entity OR x:Community RETURN x.name, x.name_embedding").result_set}
    out.update({r[0]: r[1] for r in g.query("MATCH ()-[r:RELATES_TO]->() RETURN r.fact, r.fact_embedding").result_set})
    return out


def shadows(g) -> int:
    return (one(g, "MATCH (x) WHERE x.name_embedding_reindex IS NOT NULL OR x.name_embedding_prev IS NOT NULL RETURN count(x)")
            + one(g, "MATCH ()-[r]->() WHERE r.fact_embedding_reindex IS NOT NULL OR r.fact_embedding_prev IS NOT NULL RETURN count(r)"))


def default_model(client) -> str:  # noqa: F811
    return next(e["model"] for e in client.get("/api/embedding-engines").json() if e["is_default"])


def all_with(g, model: str, dim: int) -> bool:
    return all(close(v, vec(model, dim, t.replace("\n", " "))) for t, v in vectors(g).items())


@needs_falkor
def test_reindex_recomputes_everything_and_switches_at_the_end(env, client):  # noqa: F811
    g = env["g"]
    r = client.post(f"/api/embedding-engines/{env['new']['id']}/reindex")
    assert r.status_code == 202
    job = client.get("/api/embedding-engines/reindex").json()["job"]
    assert job["id"] == r.json()["job"] and job["status"] == "done", job
    assert job["result"]["counts"] == {"Entity": 3, "Community": 1, "RELATES_TO": 2} and job["result"]["previous"]["model"] == "viejo"
    assert job["done"] == job["total"] == 6 and any("recalibra" in x["msg"] for x in job["log"])
    assert all_with(g, "nuevo", 8) and shadows(g) == 0
    assert "Plex corre en Vesta" in env["fakes"]["nuevo"].texts                   # como Graphiti: saltos de línea como espacios
    assert default_model(client) == "nuevo"
    from mimirsynth import recall
    hits = recall.search_facts(GRAPH, vec("nuevo", 8, FACTS["f1"]), 5)
    assert hits[0]["fact"] == FACTS["f1"] and hits[0]["score"] > 0.99               # el recall de hechos funciona con el modelo nuevo
    from mimirsynth.graphapi import _props
    assert _props({"name": "x", "name_embedding_reindex": [0.1], "fact_embedding_prev": [0.2]}) == {"name": "x"}   # nunca se muestran


@needs_falkor
def test_failure_keeps_the_old_engine_and_retry_resumes(env, client):  # noqa: F811
    g, fake = env["g"], env["fakes"]["nuevo"]
    calls = {"n": 0}

    def hook(f, texts):
        calls["n"] += 1
        f.fail = calls["n"] >= 3  # las dos primeras llamadas (las entidades) van bien; luego el motor se cae
    fake.hook = hook
    jid = client.post(f"/api/embedding-engines/{env['new']['id']}/reindex").json()["job"]
    job = client.get("/api/embedding-engines/reindex").json()["job"]
    assert job["status"] == "failed" and "motor caído" in job["error"]
    assert default_model(client) == "viejo" and all_with(g, "viejo", 4)            # nada cambia: todo sigue con el motor anterior
    assert one(g, "MATCH (x:Entity) WHERE x.name_embedding_reindex IS NOT NULL RETURN count(x)") == 3
    from mimirsynth import recall
    assert recall.search_facts(GRAPH, vec("viejo", 4, FACTS["f1"]), 5)[0]["fact"] == FACTS["f1"]
    fake.hook, fake.fail = None, False
    done_before = list(fake.texts)
    r = client.post(f"/api/embedding-engines/reindex/{jid}/retry")
    assert r.status_code == 201
    assert client.get("/api/embedding-engines/reindex").json()["job"]["status"] == "done"
    assert sorted(fake.texts[len(done_before):]) == sorted(["Servidores", FACTS["f1"], "Plex corre en Vesta"])   # solo lo que faltaba
    assert all_with(g, "nuevo", 8) and shadows(g) == 0 and default_model(client) == "nuevo"


@needs_falkor
def test_changes_during_the_fill_are_caught_up(env, client):  # noqa: F811
    g, fake = env["g"], env["fakes"]["nuevo"]

    def hook(f, texts):  # mientras se calculan los hechos, alguien renombra una entidad ya calculada y corrige un hecho
        if FACTS["f1"] in texts:
            g.query("MATCH (x:Entity {uuid:'e0'}) SET x.name = 'Vesta 2'")
            g.query("MATCH ()-[r {uuid:'f1'}]->() SET r.fact = 'Vesta está en Cloudco desde enero'")
    fake.hook = hook
    client.post(f"/api/embedding-engines/{env['new']['id']}/reindex")
    assert client.get("/api/embedding-engines/reindex").json()["job"]["status"] == "done"
    v = vectors(g)
    assert close(v["Vesta 2"], vec("nuevo", 8, "Vesta 2")) and close(v["Vesta está en Cloudco desde enero"], vec("nuevo", 8, "Vesta está en Cloudco desde enero"))
    assert all_with(g, "nuevo", 8) and shadows(g) == 0


@needs_falkor
def test_switch_failure_rolls_the_graphs_back(env, client, monkeypatch):  # noqa: F811
    from mimirsynth import reembed
    g = env["g"]
    real = reembed._switch
    monkeypatch.setattr(reembed, "_switch", lambda eid: (_ for _ in ()).throw(RuntimeError("base de datos caída")))
    jid = client.post(f"/api/embedding-engines/{env['new']['id']}/reindex").json()["job"]
    job = client.get("/api/embedding-engines/reindex").json()["job"]
    assert job["status"] == "failed" and "base de datos caída" in job["error"]
    assert default_model(client) == "viejo" and all_with(g, "viejo", 4)            # los grafos ya intercambiados vuelven atrás
    assert one(g, "MATCH (x) WHERE x.name_embedding_prev IS NOT NULL RETURN count(x)") == 0
    assert one(g, "MATCH (x) WHERE x.name_embedding_reindex IS NOT NULL RETURN count(x)") == 4   # el trabajo hecho se conserva
    monkeypatch.setattr(reembed, "_switch", real)
    n = len(env["fakes"]["nuevo"].texts)
    client.post(f"/api/embedding-engines/reindex/{jid}/retry")
    assert client.get("/api/embedding-engines/reindex").json()["job"]["status"] == "done"
    assert len(env["fakes"]["nuevo"].texts) == n and all_with(g, "nuevo", 8) and default_model(client) == "nuevo"


@needs_falkor
def test_cancel_cleans_up_and_keeps_the_old_engine(env, client):  # noqa: F811
    from sqlalchemy import select

    from mimirsynth import jobs, reembed
    from mimirsynth.models import Job
    from mimirsynth.store import _factory
    g, fake = env["g"], env["fakes"]["nuevo"]

    def hook(f, texts):
        if f.texts:  # tras el primer lote, alguien cancela
            with _factory()() as db:
                jobs.cancel(db.scalar(select(Job.id).where(Job.kind == reembed.KIND, Job.status == "running")))
    fake.hook = hook
    client.post(f"/api/embedding-engines/{env['new']['id']}/reindex")
    job = client.get("/api/embedding-engines/reindex").json()["job"]
    assert job["status"] == "cancelled" and shadows(g) == 0
    assert default_model(client) == "viejo" and all_with(g, "viejo", 4)


@needs_falkor
def test_reindex_guards(env, client):  # noqa: F811
    old, new = env["old"], env["new"]
    assert client.post(f"/api/embedding-engines/{old['id']}/reindex").status_code == 409                 # ya es el por defecto
    r = client.post(f"/api/embedding-engines/{new['id']}/default")
    assert r.status_code == 409 and "Reindexar" in r.json()["detail"]                                     # cambiar de modelo, solo reindexando
    client.patch(f"/api/embedding-engines/{new['id']}", json={"name": "local-nuevo", "base_url": "http://n/v1", "model": "nuevo", "enabled": False})
    assert client.post(f"/api/embedding-engines/{new['id']}/reindex").status_code == 409                 # desactivado
    assert client.get("/api/embedding-engines/reindex").json()["job"] is None
    assert client.post("/api/embedding-engines/reindex/999999/cancel").status_code == 404


def test_gate_pauses_writers_while_switching():
    from mimirsynth.embed import _Gate
    gate, log = _Gate(), []
    writing = threading.Event()

    def writer(name, hold):
        with gate.writing():
            writing.set(); log.append(f"{name}+"); time.sleep(hold); log.append(f"{name}-")

    def switcher():
        with gate.switching():
            log.append("S+"); time.sleep(0.1); log.append("S-")
    a = threading.Thread(target=writer, args=("A", 0.2)); a.start(); writing.wait()
    s = threading.Thread(target=switcher); s.start(); time.sleep(0.05)
    b = threading.Thread(target=writer, args=("B", 0)); b.start()
    for t in (a, s, b):
        t.join(5)
    assert log == ["A+", "A-", "S+", "S-", "B+", "B-"]   # el cambio espera a A; B espera al cambio
