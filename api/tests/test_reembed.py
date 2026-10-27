"""Cambio de modelo de embeddings, paso 1 (relleno en sombra), contra un FalkorDB real: los vectores nuevos se calculan aparte sin
tocar los que se usan, el motor por defecto no cambia, reanudar no recalcula lo hecho y cancelar o descartar no deja nada auxiliar."""
import hashlib
import os

import httpx
import pytest

from test_control import client  # noqa: F401

FALKOR = os.environ.get("MIMIRSYNTH_TEST_FALKOR")
pytestmark = pytest.mark.skipif(not FALKOR, reason="necesita un FalkorDB desechable (MIMIRSYNTH_TEST_FALKOR=host)")
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

    from mimirsynth import db as fdb, embeddings_admin as ea, reembed
    from mimirsynth.config import settings
    from mimirsynth.models import EmbeddingEngine, Job
    from mimirsynth.store import _factory
    monkeypatch.setattr(settings, "falkor_host", FALKOR)
    fdb.client.cache_clear()
    monkeypatch.setattr(settings, "embedding_dim", 4)
    monkeypatch.setattr(settings, "reindex_batch", 2)  # varios lotes por tipo
    monkeypatch.setattr(ea, "_probe", lambda url, model, key: {"viejo": 4, "nuevo": 8}[model])
    monkeypatch.setattr(reembed, "RETRY_WAIT", 0)
    reembed._cache.clear()  # las estimaciones se guardan por motor, y los ids se reutilizan entre pruebas
    fakes = {"viejo": Fake("viejo", 4), "nuevo": Fake("nuevo", 8)}
    monkeypatch.setattr(reembed, "_embedder", lambda e: fakes[e.model])
    from mimirsynth.models import AppSetting, Notification
    with _factory()() as db:
        db.execute(delete(EmbeddingEngine)); db.execute(delete(Job).where(Job.kind == reembed.KIND))
        db.execute(delete(AppSetting).where(AppSetting.key == reembed.MARKER)); db.execute(delete(Notification).where(Notification.event == "reindex.orphan"))
        db.commit()
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


def in_use(g) -> dict:
    out = {r[0]: r[1] for r in g.query("MATCH (x) WHERE x:Entity OR x:Community RETURN x.name, x.name_embedding").result_set}
    out.update({r[0]: r[1] for r in g.query("MATCH ()-[r:RELATES_TO]->() RETURN r.fact, r.fact_embedding").result_set})
    return out


def shadow(g) -> dict:
    out = {r[0]: r[1] for r in g.query("MATCH (x) WHERE x:Entity OR x:Community RETURN x.name, x.name_embedding_reindex").result_set}
    out.update({r[0]: r[1] for r in g.query("MATCH ()-[r:RELATES_TO]->() RETURN r.fact, r.fact_embedding_reindex").result_set})
    return out


def aux_props(g) -> int:
    """Propiedades auxiliares de cualquier nodo o arista (las sombras y cualquier otra que hubiera dejado el cambio de modelo)."""
    nodes = one(g, "MATCH (x) UNWIND keys(x) AS k WITH k WHERE k STARTS WITH 'name_embedding_' OR k STARTS WITH 'fact_embedding_' RETURN count(k)")
    edges = one(g, "MATCH ()-[x]->() UNWIND keys(x) AS k WITH k WHERE k STARTS WITH 'name_embedding_' OR k STARTS WITH 'fact_embedding_' RETURN count(k)")
    return nodes + edges


def all_with(vectors: dict, model: str, dim: int) -> bool:
    return all(close(v, vec(model, dim, t.replace("\n", " "))) for t, v in vectors.items())


def default_model(client) -> str:  # noqa: F811
    return next(e["model"] for e in client.get("/api/embedding-engines").json() if e["is_default"])


def test_fill_computes_shadow_vectors_and_changes_nothing_in_use(env, client):  # noqa: F811
    g = env["g"]
    est = client.get(f"/api/embedding-engines/{env['new']['id']}/reindex/estimate").json()
    assert est["graph_items"] == 6 and est["calls"] == 1 and est["falkor"]["ok"] and est["falkor"]["need_bytes"] > 6 * 8 * 4 and not est["partial"]
    r = client.post(f"/api/embedding-engines/{env['new']['id']}/reindex")
    assert r.status_code == 202
    job = client.get("/api/embedding-engines/reindex").json()["job"]
    assert job["status"] == "done" and job["result"]["switched"] is False, job
    assert job["result"]["counts"] == {"Entity": 3, "Community": 1, "RELATES_TO": 2} and job["done"] == job["total"] == 6
    assert all_with(shadow(g), "nuevo", 8)                                              # todo calculado con el modelo nuevo
    assert all_with(in_use(g), "viejo", 4) and default_model(client) == "viejo"         # y nada de lo que se usa ha cambiado
    assert one(g, "MATCH ()-[r {uuid:'f2'}]->() RETURN r.fact_embedding_reindex_src") == FACTS["f2"]
    assert "Plex corre en Vesta" in env["fakes"]["nuevo"].texts                         # como Graphiti: saltos de línea como espacios
    from mimirsynth import recall
    assert recall.search_facts(GRAPH, vec("viejo", 4, FACTS["f1"]), 5)[0]["fact"] == FACTS["f1"]   # el recall sigue con el modelo viejo
    from mimirsynth.graphapi import _props
    assert _props({"name": "x", "name_embedding_reindex": [0.1], "fact_embedding_reindex_src": "t"}) == {"name": "x"}
    # reanudar sin cambios no vuelve a llamar al motor
    n = len(env["fakes"]["nuevo"].texts)
    assert client.post(f"/api/embedding-engines/{env['new']['id']}/reindex").status_code == 202
    assert len(env["fakes"]["nuevo"].texts) == n


def test_failure_keeps_what_was_done_and_retry_only_computes_the_rest(env, client):  # noqa: F811
    g, fake = env["g"], env["fakes"]["nuevo"]
    calls = {"n": 0}

    def hook(f, texts):
        calls["n"] += 1
        f.fail = calls["n"] >= 3  # las dos primeras llamadas (las entidades) van bien; luego el motor se cae
    fake.hook = hook
    jid = client.post(f"/api/embedding-engines/{env['new']['id']}/reindex").json()["job"]
    job = client.get("/api/embedding-engines/reindex").json()["job"]
    assert job["status"] == "failed" and "motor caído" in job["error"]
    assert one(g, "MATCH (x:Entity) WHERE x.name_embedding_reindex IS NOT NULL RETURN count(x)") == 3
    assert all_with(in_use(g), "viejo", 4) and default_model(client) == "viejo"
    fake.hook, fake.fail = None, False
    before = len(fake.texts)
    assert client.post(f"/api/embedding-engines/reindex/{jid}/retry").status_code == 201
    assert client.get("/api/embedding-engines/reindex").json()["job"]["status"] == "done"
    assert sorted(fake.texts[before:]) == sorted(["Servidores", FACTS["f1"], "Plex corre en Vesta"])   # solo lo que faltaba
    assert all_with(shadow(g), "nuevo", 8)


def test_changes_during_the_fill_are_caught_up(env, client):  # noqa: F811
    g, fake = env["g"], env["fakes"]["nuevo"]

    def hook(f, texts):  # mientras se calculan los hechos, alguien renombra una entidad ya calculada y corrige un hecho
        if FACTS["f1"] in texts:
            g.query("MATCH (x:Entity {uuid:'e0'}) SET x.name = 'Vesta 2'")
            g.query("MATCH ()-[r {uuid:'f1'}]->() SET r.fact = 'Vesta está en Cloudco desde enero'")
    fake.hook = hook
    client.post(f"/api/embedding-engines/{env['new']['id']}/reindex")
    assert client.get("/api/embedding-engines/reindex").json()["job"]["status"] == "done"
    s = shadow(g)
    assert close(s["Vesta 2"], vec("nuevo", 8, "Vesta 2")) and close(s["Vesta está en Cloudco desde enero"], vec("nuevo", 8, "Vesta está en Cloudco desde enero"))
    assert all_with(s, "nuevo", 8)


def test_cancel_discards_everything(env, client):  # noqa: F811
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
    st = client.get("/api/embedding-engines/reindex").json()
    assert st["job"]["status"] == "cancelled" and st["shadow"] is None and st["orphan"] is False
    assert aux_props(g) == 0                                                            # ninguna propiedad auxiliar
    assert all_with(in_use(g), "viejo", 4) and default_model(client) == "viejo"


def test_discard_after_a_finished_fill(env, client):  # noqa: F811
    g = env["g"]
    client.post(f"/api/embedding-engines/{env['new']['id']}/reindex")
    assert aux_props(g) == 12                                                           # vector y texto de origen de 6 elementos
    assert client.post("/api/embedding-engines/reindex/discard").json() == {"ok": True}
    assert aux_props(g) == 0 and all_with(in_use(g), "viejo", 4)


def test_space_check_blocks_the_start(env, client, monkeypatch):  # noqa: F811
    from mimirsynth import reembed
    monkeypatch.setattr(reembed, "_falkor_memory", lambda: (1000, 1100))  # 100 bytes libres
    est = client.get(f"/api/embedding-engines/{env['new']['id']}/reindex/estimate").json()
    assert est["falkor"]["ok"] is False and est["falkor"]["free_bytes"] == 100
    r = client.post(f"/api/embedding-engines/{env['new']['id']}/reindex")
    assert r.status_code == 409 and "memoria" in r.json()["detail"]
    assert client.get("/api/embedding-engines/reindex").json()["job"] is None and aux_props(env["g"]) == 0


def test_rate_limit_waits_for_retry_after(env, client, monkeypatch):  # noqa: F811
    from mimirsynth import reembed
    from mimirsynth.config import settings
    waits = []
    monkeypatch.setattr(reembed.time, "sleep", lambda s: waits.append(s))
    monkeypatch.setattr(settings, "reindex_pause", 1.5)
    fake, seen = env["fakes"]["nuevo"], {"n": 0}

    def hook(f, texts):
        seen["n"] += 1
        if seen["n"] == 1:
            req = httpx.Request("POST", "http://n/v1/embeddings")
            raise httpx.HTTPStatusError("429", request=req, response=httpx.Response(429, headers={"Retry-After": "7"}, request=req))
    fake.hook = hook
    client.post(f"/api/embedding-engines/{env['new']['id']}/reindex")
    job = client.get("/api/embedding-engines/reindex").json()["job"]
    assert job["status"] == "done" and waits[0] == 7.0 and 1.5 in waits                # Retry-After y pausa entre lotes
    assert any("429" in x["msg"] for x in job["log"])


def test_guards(env, client):  # noqa: F811
    old, new = env["old"], env["new"]
    assert client.post(f"/api/embedding-engines/{old['id']}/reindex").status_code == 409           # ya es el por defecto
    assert client.post(f"/api/embedding-engines/{new['id']}/default").status_code == 409           # otro modelo: no se cambia sin reindexar
    client.patch(f"/api/embedding-engines/{new['id']}", json={"name": "local-nuevo", "base_url": "http://n/v1", "model": "nuevo", "enabled": False})
    assert client.post(f"/api/embedding-engines/{new['id']}/reindex").status_code == 409           # desactivado
    assert client.post("/api/embedding-engines/reindex/999999/cancel").status_code == 404



class Counting:
    """Envuelve un grafo y apunta cada consulta que recibe."""
    def __init__(self, g, log):
        self.g, self.log = g, log

    def query(self, q, params=None):
        self.log.append(q)
        return self.g.query(q, params or {})


def test_estimate_uses_a_bounded_number_of_cheap_queries(env, client, monkeypatch):  # noqa: F811
    from mimirsynth import reembed
    g = env["g"]
    g.query("UNWIND range(1, 400) AS i CREATE (:Entity {uuid: 'm' + toString(i), name: 'Entidad número ' + toString(i)})")
    g.query("MATCH (a:Entity), (b:Entity {uuid:'e0'}) WHERE a.uuid STARTS WITH 'm' CREATE (a)-[:RELATES_TO {uuid: 'r' + a.uuid, fact: a.name + ' depende de Vesta'}]->(b)")
    seen = []
    real = reembed.graph
    monkeypatch.setattr(reembed, "graph", lambda name: Counting(real(name), seen))
    est = client.get(f"/api/embedding-engines/{env['new']['id']}/reindex/estimate").json()
    assert est["graph_items"] == 806 and not est["partial"]                             # 403 entidades, 1 comunidad, 402 hechos
    assert 200 * 400 < est["falkor"]["need_bytes"]                                      # y el texto se estima con la muestra
    assert len(seen) <= 2 * len(reembed.ITEMS) * est["graphs"]                          # por grafo, un recuento y una muestra por tipo como mucho
    assert not [q for q in seen if "sum(" in q or "WHERE" in q]                         # sin agregar el texto ni filtrar todo el grafo
    assert all("LIMIT" in q or q.rstrip().endswith("RETURN count(x)") for q in seen)


def test_estimate_is_partial_after_its_time_limit_and_is_cached(env, client, monkeypatch):  # noqa: F811
    from mimirsynth import reembed
    monkeypatch.setattr(reembed, "ESTIMATE_SECONDS", -1)  # el tiempo ya se ha agotado al empezar
    est = client.get(f"/api/embedding-engines/{env['new']['id']}/reindex/estimate").json()
    assert est["partial"] is True and est["graphs_estimated"] == 0 and est["graphs"] >= 1 and est["cached"] is False
    seen = []
    real = reembed.graph
    monkeypatch.setattr(reembed, "graph", lambda name: Counting(real(name), seen))
    again = client.get(f"/api/embedding-engines/{env['new']['id']}/reindex/estimate").json()
    assert again["cached"] is True and again["at"] == est["at"] and seen == []          # se reutiliza sin tocar el grafo
    assert client.get(f"/api/embedding-engines/{env['new']['id']}/reindex/estimate", params={"refresh": True}).json()["cached"] is False


def test_start_does_not_estimate_in_the_request(env, client, monkeypatch):  # noqa: F811
    import threading
    import time

    from mimirsynth import jobs, reembed
    where = []
    real = reembed.estimate
    monkeypatch.setattr(reembed, "estimate", lambda e, deadline=None: (where.append(threading.current_thread().name), real(e, deadline))[1])
    monkeypatch.setattr(jobs, "INLINE", False)  # el trabajo en su hilo, como en producción
    r = client.post(f"/api/embedding-engines/{env['new']['id']}/reindex")
    assert r.status_code == 202 and "estimate" not in r.json()
    for _ in range(100):
        if client.get("/api/embedding-engines/reindex").json()["job"]["status"] in ("done", "failed"):
            break
        time.sleep(0.1)
    job = client.get("/api/embedding-engines/reindex").json()["job"]
    assert job["status"] == "done" and where and all(n.startswith("job-") for n in where)   # solo la hace el trabajo
    assert any(x["msg"].startswith("estimación:") for x in job["log"])                       # y la deja en su registro


def test_orphan_shadows_are_marked_exposed_notified_and_discarded(env, client, monkeypatch):  # noqa: F811
    from sqlalchemy import select

    from mimirsynth import reembed
    from mimirsynth.config import settings
    from mimirsynth.models import Notification
    from mimirsynth.store import _factory
    g, fake = env["g"], env["fakes"]["nuevo"]
    calls = {"n": 0}

    def hook(f, texts):
        calls["n"] += 1
        f.fail = calls["n"] >= 2
    fake.hook = hook
    client.post(f"/api/embedding-engines/{env['new']['id']}/reindex")
    st = client.get("/api/embedding-engines/reindex").json()
    assert st["job"]["status"] == "failed" and st["orphan"] is True
    assert st["shadow"]["state"] == "failed" and st["shadow"]["engine"] == "local-nuevo" and st["shadow"]["dim"] == 8

    def open_alerts():
        with _factory()() as db:
            return db.scalars(select(Notification).where(Notification.event == "reindex.orphan", Notification.resolved_at.is_(None))).all()
    monkeypatch.setattr(settings, "reindex_orphan_hours", 24.0)
    reembed.check_orphan()
    assert open_alerts() == []                                                          # aún no ha pasado el plazo
    monkeypatch.setattr(settings, "reindex_orphan_hours", 0.0)
    reembed.check_orphan()
    alerts = open_alerts()
    assert len(alerts) == 1 and "local-nuevo" in alerts[0].body and alerts[0].severity == "warning"
    assert client.post("/api/embedding-engines/reindex/discard").json() == {"ok": True}
    st = client.get("/api/embedding-engines/reindex").json()
    assert st["shadow"] is None and st["orphan"] is False and aux_props(g) == 0 and open_alerts() == []


def test_a_finished_fill_is_ready_and_does_not_notify(env, client, monkeypatch):  # noqa: F811
    from sqlalchemy import select

    from mimirsynth import reembed
    from mimirsynth.config import settings
    from mimirsynth.models import Notification
    from mimirsynth.store import _factory
    client.post(f"/api/embedding-engines/{env['new']['id']}/reindex")
    st = client.get("/api/embedding-engines/reindex").json()
    assert st["shadow"]["state"] == "ready" and st["orphan"] is True                    # hay sombras y ningún relleno en marcha
    monkeypatch.setattr(settings, "reindex_orphan_hours", 0.0)
    reembed.check_orphan()
    with _factory()() as db:
        assert db.scalars(select(Notification).where(Notification.event == "reindex.orphan")).all() == []   # espera al intercambio
