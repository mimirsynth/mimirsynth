"""Posibles contradicciones entre hechos vigentes (#113): agrupación, relaciones funcionales, resolución reversible y aviso."""
import os

import pytest

from test_control import client  # noqa: F401

from mimirsynth import conflicts as C

FALKOR = os.environ.get("MIMIRSYNTH_TEST_FALKOR")
GRAPH = "zz-test-conflicts"


def _f(uuid, src, rel, tgt, when, kind="Place", valid=True):
    return {"uuid": uuid, "name": rel, "fact": f"{src} {rel} {tgt}", "valid_at": when if valid else None, "created_at": when,
            "source_uuid": f"s-{src}", "source": src, "target_uuid": f"t-{tgt}", "target": tgt, "target_labels": ["Entity", kind]}


def test_find_groups_only_distinct_targets_of_the_same_type():
    facts = [_f("1", "nas01", "LocatedAt", "Sala A", "2026-01-01"), _f("2", "nas01", "LOCATED_AT", "Sala B", "2026-06-01"),
             _f("7", "nas01", "LocatedAt", "VLAN 10", "2026-07-01", kind="Network"),                  # otro tipo: no se compara
             _f("3", "nas02", "LocatedAt", "Sala A", "2026-01-01"), _f("4", "nas02", "LocatedAt", "sala  a", "2026-03-01"),   # mismo destino
             _f("5", "vw", "HostedOn", "altair", "2026-01-01", kind="Host"), _f("6", "vw", "HostedOn", "antares", "2026-01-01", kind="Host")]
    groups, stats = C.find(facts, only={"LOCATED_AT"})
    assert [(g["source"], g["relation"], g["target_type"]) for g in groups] == [("nas01", "LOCATED_AT", "Place")]   # HostedOn no es funcional
    g = groups[0]
    assert g["suggestion"] == {"keep": "2", "invalidate": ["1"], "clear": True, "dated_by": "valid_at"} and [f["uuid"] for f in g["facts"]] == ["2", "1"]
    assert stats == [{"relation": "LOCATED_AT", "sources": 2, "groups": 1, "ratio": 0.5}]
    every, stats = C.find(facts)                                                                 # medición: todas las relaciones
    assert {(g["source"], g["relation"]) for g in every} == {("nas01", "LOCATED_AT"), ("vw", "HOSTED_ON")}
    vw = next(g for g in every if g["source"] == "vw")
    assert vw["suggestion"]["clear"] is False                                                    # misma fecha: lo decide una persona
    assert [s["relation"] for s in stats] == ["LOCATED_AT", "HOSTED_ON"]                         # de menor a mayor proporción (0,5 y 1)


def test_learning_date_is_never_a_clear_suggestion():
    """Sin `valid_at`, la fecha es la de aprendizaje: un dato antiguo reingerido hoy «ganaría». No se da por clara."""
    facts = [_f("1", "lxc151", "LocatedAt", "Eridani", "2026-01-01", kind="Host", valid=False),
             _f("2", "lxc151", "LocatedAt", "EPSILON", "2026-09-01", kind="Host", valid=False)]
    s = C.find(facts)[0][0]["suggestion"]
    assert s["keep"] == "2" and s["clear"] is False and s["dated_by"] == "created_at"


def test_aliases_and_functional_marks():
    facts = [_f("1", "ana", "REPORTS_TO", "Luis", "2026-01-01", kind="Person"), _f("2", "ana", "MANAGED_BY", "Marta", "2026-05-01", kind="Person")]
    assert C.find(facts, only={"REPORTS_TO"})[0] == []
    groups, _ = C.find(facts, amap={"MANAGED_BY": "REPORTS_TO"}, only={"REPORTS_TO"})       # el alias cuenta como la misma relación
    assert len(groups) == 1 and groups[0]["suggestion"]["keep"] == "2"
    onto = {"edge_types": [{"name": "ReportsTo", "description": "x", "functional": True}, {"name": "Owns", "description": "x"}]}
    assert C.functional_relations(onto) == {"REPORTS_TO"} and C.functional_relations(None) == set()


def test_functional_flag_in_the_ontology_api(client):  # noqa: F811
    client.post("/api/brains", json={"slug": "cf-onto", "name": "CF"})
    assert client.post("/api/brains/cf-onto/vocab/relations", json={"name": "LocatedAt", "description": "Está en un sitio", "functional": True}).status_code == 201
    assert client.post("/api/brains/cf-onto/vocab/relations", json={"name": "Owns", "description": "Es dueño de algo"}).status_code == 201
    edges = {e["name"]: e for e in client.get("/api/brains/cf-onto/ontology").json()["ontology"]["edge_types"]}
    assert edges["LocatedAt"]["functional"] is True and "functional" not in edges["Owns"]
    assert client.put("/api/brains/cf-onto/vocab/relations/LocatedAt", json={"description": "Está en un sitio", "functional": False}).status_code == 200
    assert "functional" not in client.get("/api/brains/cf-onto/ontology").json()["ontology"]["edge_types"][0]
    assert client.put("/api/brains/cf-onto/vocab/relations/Owns", json={"description": "Es dueño"}).status_code == 200   # sin tocar la marca


def test_presets_mark_nothing():
    """Medido en un grafo real, «ubicado en» mezclaba hosts, URLs y VLANs: una marca de antemano daba sobre todo falsos positivos."""
    from mimirsynth.ontology import presets
    assert [(n, e["name"]) for n, p in presets().items() for e in p["edge_types"] if e.get("functional")] == []


@pytest.fixture()
def falkor(monkeypatch):
    from mimirsynth import db as dbm
    from mimirsynth.config import settings
    monkeypatch.setattr(settings, "falkor_host", FALKOR)
    dbm.client.cache_clear()
    c = dbm.client()
    if GRAPH in c.list_graphs():
        c.select_graph(GRAPH).delete()
    g = c.select_graph(GRAPH)
    for i, (src, rel, tgt, kind, when) in enumerate([("nas01", "LOCATED_AT", "Sala A", "Place", "2026-01-01T00:00:00Z"),
                                                      ("nas01", "LOCATED_AT", "Sala B", "Place", "2026-06-01T00:00:00Z"),
                                                      ("nas01", "LOCATED_AT", "VLAN 10", "Network", "2026-07-01T00:00:00Z"),
                                                      ("nas02", "LOCATED_AT", "Sala A", "Place", "2026-01-01T00:00:00Z"),
                                                      ("vw", "HOSTED_ON", "altair", "Host", "2026-01-01T00:00:00Z"),
                                                      ("vw", "HOSTED_ON", "antares", "Host", "2026-02-01T00:00:00Z")], 1):
        g.query(f"MERGE (a:Entity {{uuid:$sa, name:$s, group_id:$g}}) MERGE (b:Entity:{kind} {{uuid:$ta, name:$t, group_id:$g}}) "
                "CREATE (a)-[:RELATES_TO {uuid:$u, name:$r, fact:$fact, valid_at:$w, created_at:$w, group_id:$g}]->(b)",
                {"sa": f"s-{src}", "s": src, "ta": f"t-{tgt}", "t": tgt, "u": f"f{i}", "r": rel, "fact": f"{src} {rel} {tgt}", "w": when, "g": GRAPH})
    yield g
    c.select_graph(GRAPH).delete()
    dbm.client.cache_clear()


@pytest.mark.skipif(not FALKOR, reason="necesita un FalkorDB desechable (MIMIRSYNTH_TEST_FALKOR=host)")
def test_scan_resolve_undo_and_notice(client, falkor):  # noqa: F811
    from mimirsynth.models import Notification
    from mimirsynth.store import _factory
    assert client.post("/api/brains", json={"slug": "cf", "name": "CF", "graph_name": GRAPH}).status_code == 201
    assert client.get("/api/brains/cf/conflicts").json()["total"] == 0                    # sin relaciones funcionales, nada
    measure = client.get("/api/brains/cf/conflicts", params={"all": True}).json()          # medición: solo lee
    assert measure["total"] == 2 and {s["relation"]: s["groups"] for s in measure["by_relation"]} == {"HOSTED_ON": 1, "LOCATED_AT": 1}
    client.post("/api/brains/cf/vocab/relations", json={"name": "LocatedAt", "description": "Está en un sitio", "functional": True})
    out = client.get("/api/brains/cf/conflicts").json()
    assert out["functional"] == ["LOCATED_AT"] and out["total"] == 1                       # la VLAN, de otro tipo, no cuenta
    assert out["groups"][0]["suggestion"] == {"keep": "f2", "invalidate": ["f1"], "clear": True, "dated_by": "valid_at"}
    assert client.post("/api/brains/cf/conflicts/resolve", json={"keep": "f2", "invalidate": ["f5"]}).status_code == 400   # otro sujeto
    assert client.post("/api/brains/cf/conflicts/resolve", json={"keep": "f2", "invalidate": ["f3"]}).status_code == 400   # otro tipo
    r = client.post("/api/brains/cf/conflicts/resolve", json={"keep": "f2", "invalidate": ["f1"]}).json()
    assert r["ok"] and len(r["ops"]) == 1
    f1 = falkor.query("MATCH ()-[r:RELATES_TO {uuid:'f1'}]->() RETURN r.invalid_at").result_set[0][0]
    assert f1 == "2026-06-01T00:00:00Z"                                                   # se invalida con la fecha del que se queda
    assert client.get("/api/brains/cf/conflicts").json()["total"] == 0
    assert client.post("/api/brains/cf/conflicts/resolve", json={"keep": "f2", "invalidate": ["f1"]}).status_code == 409
    assert client.post("/api/brains/cf/conflicts/resolve", json={"keep": "f1", "invalidate": ["f2"]}).status_code == 409   # el que se queda ya no está vigente
    assert client.post(f"/api/brains/cf/vocab/ops/{r['ops'][0]}/revert").status_code == 200   # reversible como cualquier invalidación
    assert client.get("/api/brains/cf/conflicts").json()["total"] == 1
    from mimirsynth import jobs
    jobs.INLINE = True
    try:
        assert C.check_all()                                                              # el aviso periódico
    finally:
        jobs.INLINE = False
    with _factory()() as db:
        n = db.query(Notification).filter(Notification.event == "conflicts.found", Notification.key == "conflicts:cf").one()
        assert n.severity == "info" and "1 posibles contradicciones" in n.title
