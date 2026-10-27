"""Cambio de modelo de embeddings, paso 2 (intercambio), contra un FalkorDB real: el motor por defecto solo cambia si todo se
confirma; un fallo de la transacción final o una caída a mitad del cambio dejan todo con el motor anterior; la compuerta pausa las
escrituras como mucho el tiempo configurado y, si no puede, el cambio se aplaza."""
import os
import threading
import time

import pytest

from test_control import client  # noqa: F401
from test_reembed import FACTS, GRAPH, all_with, aux_props, default_model, env, in_use, one, shadow, vec  # noqa: F401

pytestmark = pytest.mark.skipif(not os.environ.get("MIMIRSYNTH_TEST_FALKOR"), reason="necesita un FalkorDB desechable (MIMIRSYNTH_TEST_FALKOR=host)")


@pytest.fixture()
def ready(env, client):  # noqa: F811
    """Un relleno terminado hacia el motor nuevo."""
    client.post(f"/api/embedding-engines/{env['new']['id']}/reindex")
    st = client.get("/api/embedding-engines/reindex").json()
    assert st["shadow"]["state"] == "ready", st
    return env


def switch(client, confirmed=True):  # noqa: F811
    return client.post("/api/embedding-engines/reindex/switch", json={"backup_confirmed": confirmed})


def prev_props(g) -> int:
    return (one(g, "MATCH (x) WHERE x.name_embedding_prev IS NOT NULL RETURN count(x)")
            + one(g, "MATCH ()-[x]->() WHERE x.fact_embedding_prev IS NOT NULL RETURN count(x)"))


def test_switch_swaps_everything_and_changes_the_default(ready, client):  # noqa: F811
    g = ready["g"]
    assert switch(client, confirmed=False).status_code == 400                           # la copia de seguridad, paso explícito
    r = switch(client)
    assert r.status_code == 202
    st = client.get("/api/embedding-engines/reindex").json()
    job = st["switch_job"]
    assert job["status"] == "done" and job["result"]["switched"] is True and job["result"]["previous"]["model"] == "viejo", job
    assert any("copia de seguridad" in x["msg"] for x in job["log"]) and any(x["msg"].startswith("pausa de escrituras:") for x in job["log"])
    assert any("Graphiti" in x["msg"] for x in job["log"])                              # aviso para los agentes que escriben directo
    assert all_with(in_use(g), "nuevo", 8) and aux_props(g) == 0 and default_model(client) == "nuevo"
    assert st["shadow"] is None and st["orphan"] is False                               # el marcador se borra con el cambio
    from mimirsynth import recall
    hits = recall.search_facts(GRAPH, vec("nuevo", 8, FACTS["f1"]), 5)
    assert hits[0]["fact"] == FACTS["f1"] and hits[0]["score"] > 0.99
    audit = [a for a in client.get("/api/audit").json() if a["action"] == "embedding.switch"]
    assert audit and audit[0]["detail"]["backup_confirmed"] is True


def test_switch_needs_a_finished_fill(env, client):  # noqa: F811
    assert switch(client).status_code == 409                                            # sin relleno
    calls = {"n": 0}

    def hook(f, texts):
        calls["n"] += 1
        f.fail = calls["n"] >= 2
    env["fakes"]["nuevo"].hook = hook
    client.post(f"/api/embedding-engines/{env['new']['id']}/reindex")                   # relleno fallido: no está «ready»
    assert switch(client).status_code == 409 and default_model(client) == "viejo"


def test_changes_after_the_fill_are_caught_up_before_switching(ready, client):  # noqa: F811
    g = ready["g"]
    g.query("MATCH (x:Entity {uuid:'e1'}) SET x.name = 'Cloudco Europa'")              # cambia después del relleno
    g.query("CREATE (:Entity {uuid:'e9', name:'Nueva', name_embedding: vecf32($v)})", {"v": vec("viejo", 4, "Nueva")})
    switch(client)
    assert client.get("/api/embedding-engines/reindex").json()["switch_job"]["status"] == "done"
    v = in_use(g)
    assert all_with(v, "nuevo", 8) and close8(v["Cloudco Europa"], "Cloudco Europa") and close8(v["Nueva"], "Nueva")


def close8(a, t):
    b = vec("nuevo", 8, t)
    return a is not None and all(abs(x - y) < 1e-5 for x, y in zip(a, b))


def test_final_transaction_failure_rolls_the_graphs_back(ready, client, monkeypatch):  # noqa: F811
    from mimirsynth import reembed
    g = ready["g"]
    real = reembed._switch_tx
    monkeypatch.setattr(reembed, "_switch_tx", lambda eid, note=None: (_ for _ in ()).throw(RuntimeError("base de datos caída")))
    switch(client)
    st = client.get("/api/embedding-engines/reindex").json()
    assert st["switch_job"]["status"] == "failed" and "base de datos caída" in st["switch_job"]["error"]
    assert default_model(client) == "viejo" and all_with(in_use(g), "viejo", 4) and prev_props(g) == 0
    assert all_with(shadow(g), "nuevo", 8) and st["shadow"]["state"] == "ready"         # lo calculado se conserva para reintentar
    monkeypatch.setattr(reembed, "_switch_tx", real)
    n = len(ready["fakes"]["nuevo"].texts)
    switch(client)
    assert client.get("/api/embedding-engines/reindex").json()["switch_job"]["status"] == "done"
    assert len(ready["fakes"]["nuevo"].texts) == n and all_with(in_use(g), "nuevo", 8) and default_model(client) == "nuevo"


def test_crash_before_the_transaction_is_undone_at_startup(ready, client):  # noqa: F811
    """Caída simulada: los grafos ya intercambiados, pero la transacción de PostgreSQL no llegó a hacerse."""
    from mimirsynth import reembed
    g = ready["g"]
    reembed._set_state("switching")
    reembed._swap_graph(GRAPH)
    assert all_with(in_use(g), "nuevo", 8) and default_model(client) == "viejo"        # el estado incoherente que deja la caída
    out = reembed.recover_switch()                                                      # lo que hace el arranque antes de servir
    assert out["restored"] >= 1 and all_with(in_use(g), "viejo", 4) and prev_props(g) == 0 and all_with(shadow(g), "nuevo", 8)
    assert reembed.marker()["state"] == "ready" and default_model(client) == "viejo"
    switch(client)                                                                      # y el cambio se puede reintentar
    assert client.get("/api/embedding-engines/reindex").json()["switch_job"]["status"] == "done" and all_with(in_use(g), "nuevo", 8)


def test_crash_after_the_transaction_only_cleans_up_at_startup(ready, client):  # noqa: F811
    """Caída simulada justo después de confirmar: el cambio está hecho y solo quedan los vectores anteriores."""
    from mimirsynth import reembed
    g = ready["g"]
    reembed._set_state("switching")
    reembed._swap_graph(GRAPH)
    reembed._switch_tx(ready["new"]["id"])
    assert prev_props(g) > 0
    out = reembed.recover_switch()
    assert out["cleaned"] >= 1 and prev_props(g) == 0 and all_with(in_use(g), "nuevo", 8) and default_model(client) == "nuevo"
    assert reembed.marker() is None


def test_long_writes_postpone_the_switch_without_cutting_them(ready, client, monkeypatch):  # noqa: F811
    from mimirsynth import reembed
    from mimirsynth.config import settings
    from mimirsynth.embed import gate
    g = ready["g"]
    monkeypatch.setattr(settings, "reindex_switch_wait", 0.2)
    monkeypatch.setattr(reembed, "SWITCH_ATTEMPTS", 2)
    monkeypatch.setattr(reembed, "SWITCH_RETRY_WAIT", 0)
    started, finish, finished = threading.Event(), threading.Event(), threading.Event()

    def long_write():  # una ingesta larga
        with gate.writing():
            started.set()
            finish.wait(10)
        finished.set()
    t = threading.Thread(target=long_write)
    t.start()
    started.wait(5)
    switch(client)
    job = client.get("/api/embedding-engines/reindex").json()["switch_job"]
    assert job["status"] == "failed" and "aplazado" in job["error"] and sum("cambio aplazado" in x["msg"] for x in job["log"]) == 2
    assert not finished.is_set()                                                        # la escritura sigue, no se ha cortado
    assert default_model(client) == "viejo" and all_with(in_use(g), "viejo", 4)
    assert reembed.marker()["state"] == "ready"
    finish.set()
    t.join(5)
    switch(client)
    assert client.get("/api/embedding-engines/reindex").json()["switch_job"]["status"] == "done" and default_model(client) == "nuevo"


def test_writers_wait_while_switching_and_resume_after():
    from mimirsynth.embed import GateBusy, _Gate
    gate, log = _Gate(), []
    writing = threading.Event()

    def writer(name, hold):
        with gate.writing():
            writing.set(); log.append(f"{name}+"); time.sleep(hold); log.append(f"{name}-")

    def switcher():
        with gate.switching(timeout=5):
            log.append("S+"); time.sleep(0.1); log.append("S-")
    a = threading.Thread(target=writer, args=("A", 0.2)); a.start(); writing.wait()
    s = threading.Thread(target=switcher); s.start(); time.sleep(0.05)
    b = threading.Thread(target=writer, args=("B", 0)); b.start()
    for t in (a, s, b):
        t.join(5)
    assert log == ["A+", "A-", "S+", "S-", "B+", "B-"]                                  # el cambio espera a A; B espera al cambio
    # sin tiempo suficiente, el cambio se retira y las escrituras siguen
    log.clear(); writing.clear()
    a = threading.Thread(target=writer, args=("A", 0.3)); a.start(); writing.wait()
    with pytest.raises(GateBusy):
        with gate.switching(timeout=0.05):
            pass
    with gate.writing():
        log.append("C")                                                                 # entra sin esperar a nadie
    a.join(5)
    assert log[:2] == ["A+", "C"]
