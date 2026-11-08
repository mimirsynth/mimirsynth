"""Verifiable facts (#293): a probe checks a fact against a live system through a verifier plugin; `verified` renews its confirmation,
`refuted` becomes a proposal that replaces it (decided by a person), an error is `unverifiable`, secrets of a verifier's settings are
sealed and never returned, external verifiers only load from the administrator's folder, and the recall says each fact's state."""
import json
import os

import pytest

from test_control import client  # noqa: F401

from mimirsynth import verify as V

FALKOR = os.environ.get("MIMIRSYNTH_TEST_FALKOR")
GRAPH = "zz-test-verify"
needs_falkor = pytest.mark.skipif(not FALKOR, reason="necesita un FalkorDB desechable (MIMIRSYNTH_TEST_FALKOR=host)")


def test_the_example_verifier(tmp_path):
    inv = tmp_path / "inv.json"
    inv.write_text(json.dumps({"vaultwarden": "altair", "wiki": ["pve1", "pve2"]}), encoding="utf-8")
    v = V.REGISTRY["json_inventory"]({"path": str(inv)})
    assert v.check({"target": "Altair"}, {"key": "vaultwarden"}).state == "verified"
    r = v.check({"target": "eridani"}, {"key": "vaultwarden"})
    assert (r.state, r.value) == ("refuted", "altair") and "altair" in r.evidence
    assert v.check({"target": "pve3"}, {"key": "wiki"}).value is None                 # several values: no single replacement
    assert v.check({"target": "x"}, {"key": "nope"}).state == "unverifiable"
    with pytest.raises(ValueError):
        V.REGISTRY["json_inventory"]({})                                                # its file is required


def test_external_verifiers_only_from_the_administrators_folder(tmp_path, monkeypatch):
    (tmp_path / "always.py").write_text("from mimirsynth.verify import Verifier, Result, register\n\n"
                                        "@register\nclass Always(Verifier):\n    id = 'always_ok'\n    label = 'Always'\n\n"
                                        "    def check(self, fact, params):\n        return Result('verified', 'ok')\n", encoding="utf-8")
    (tmp_path / "broken.py").write_text("raise RuntimeError('broken')\n", encoding="utf-8")
    monkeypatch.delenv("MIMIRSYNTH_VERIFIERS_DIR", raising=False)
    assert V.load_dir() == [] and "always_ok" not in V.REGISTRY
    assert V.load_dir(str(tmp_path)) == ["always_ok"]                                   # the broken one is skipped
    V.REGISTRY.pop("always_ok")


@pytest.fixture()
def graph(monkeypatch):
    from mimirsynth import db as dbm
    from mimirsynth.config import settings
    monkeypatch.setattr(settings, "falkor_host", FALKOR)
    dbm.backend.cache_clear()
    c = dbm.backend()
    if GRAPH in c.list_graphs():
        c.delete_graph(GRAPH)
    g = c.graph(GRAPH)
    g.query("CREATE (:Entity {uuid:'vw', name:'Vaultwarden'}), (:Entity {uuid:'al', name:'altair'}), (:Entity {uuid:'er', name:'eridani'}), "
            "(:Entity {uuid:'wk', name:'Wiki'})")
    for u, s, t, fact in (("f1", "vw", "al", "Vaultwarden corre en altair"), ("f2", "wk", "er", "Wiki corre en eridani")):
        g.query("MATCH (a:Entity {uuid:$s}), (b:Entity {uuid:$t}) CREATE (a)-[:RELATES_TO {uuid:$u, name:'RUNS_ON', fact:$f, valid_at:'2025-01-01T00:00:00Z', "
                "created_at:'2025-01-01T00:00:00Z', fact_embedding: vecf32([1.0, 0.0])}]->(b)", {"s": s, "t": t, "u": u, "f": fact})
    yield g
    c.delete_graph(GRAPH)
    dbm.backend.cache_clear()


@needs_falkor
def test_probes_verify_refute_and_show_in_the_recall(client, graph, tmp_path):  # noqa: F811
    from mimirsynth.models import FactConfirmation, Proposal, VerifierConfig
    from mimirsynth.store import _factory
    inv = tmp_path / "inv.json"
    inv.write_text(json.dumps({"vaultwarden": "altair", "wiki": "pve2"}), encoding="utf-8")
    assert client.post("/api/brains", json={"slug": "vf", "name": "VF", "graph_name": GRAPH}).status_code == 201
    listed = client.get("/api/brains/vf/verifiers").json()["items"]
    assert [v["id"] for v in listed] == ["json_inventory"] and listed[0]["params"][0]["name"] == "key"
    assert client.put("/api/brains/vf/verifiers/json_inventory", json={"values": {"path": str(inv)}}).status_code == 200
    assert client.put("/api/brains/vf/facts/f1/probe", json={"verifier": "json_inventory", "params": {}}).status_code == 422   # its key
    assert client.put("/api/brains/vf/facts/nope/probe", json={"verifier": "json_inventory", "params": {"key": "x"}}).status_code == 404
    client.put("/api/brains/vf/facts/f1/probe", json={"verifier": "json_inventory", "params": {"key": "vaultwarden"}})
    client.put("/api/brains/vf/facts/f2/probe", json={"verifier": "json_inventory", "params": {"key": "wiki"}})
    assert client.post("/api/brains/vf/probes/run").status_code == 202                 # inline in tests
    probes = {p["fact_uuid"]: p for p in client.get("/api/brains/vf/probes").json()["items"]}
    assert probes["f1"]["state"] == "verified" and probes["f2"]["state"] == "refuted" and probes["f2"]["value"] == "pve2"
    assert probes["f1"]["fact"] == "Vaultwarden corre en altair" and probes["f1"]["source_uuid"] == "vw"         # what it checks, to read it
    with _factory()() as db:
        assert db.query(FactConfirmation).filter(FactConfirmation.brain_id == _bid(), FactConfirmation.fact_uuid == "f1").one()
        p = db.query(Proposal).filter(Proposal.brain_id == _bid(), Proposal.category == "verifier.refuted").one()
        assert p.status == "pending" and p.claims[0]["supersedes"] == "f2" and p.claims[0]["value"] == "pve2" and "pve2" in p.body
        assert db.query(VerifierConfig).one().values == {"path": str(inv)}
    client.post("/api/brains/vf/probes/run")                                             # refuted again: not proposed twice
    with _factory()() as db:
        assert db.query(Proposal).filter(Proposal.brain_id == _bid(), Proposal.category == "verifier.refuted").count() == 1
    assert graph.query("MATCH ()-[r:RELATES_TO {uuid:'f2'}]->() RETURN r.invalid_at").result_set[0][0] is None   # nothing on its own
    facts = V.mark(_bid(), [{"uuid": "f1", "fact": "x", "status": "current"}, {"uuid": "zz", "fact": "y", "status": "current"}])
    assert facts[0]["verification"]["state"] == "verified" and "verification" not in facts[1]
    from mimirsynth.recall import build_context
    ctx = build_context([{**facts[0], "valid_at": "2025-01-01T00:00:00Z", "created_at": None}], [], 6000)
    assert "[verificado el " in ctx
    assert client.delete("/api/brains/vf/facts/f1/probe").json() == {"ok": True}


def _bid():
    from mimirsynth.models import Brain
    from mimirsynth.store import _factory
    with _factory()() as db:
        return db.query(Brain).filter(Brain.slug == "vf").one().id


def test_secret_settings_are_sealed_and_never_returned(client, monkeypatch):  # noqa: F811
    class WithToken(V.Verifier):
        id, label = "with_token", "With token"
        config = [V.Param("url", "URL"), V.Param("token", "Token", secret=True)]
    monkeypatch.setitem(V.REGISTRY, "with_token", WithToken)
    client.post("/api/brains", json={"slug": "vf2", "name": "VF2"})
    out = client.put("/api/brains/vf2/verifiers/with_token", json={"values": {"url": "https://inv", "token": "s3cr3t-value"}}).json()["items"]
    w = next(v for v in out if v["id"] == "with_token")
    assert "s3cr3t-value" not in json.dumps(out) and {c["name"]: c["set"] for c in w["config"]} == {"url": True, "token": True}
    client.put("/api/brains/vf2/verifiers/with_token", json={"values": {"url": "https://inv2"}})       # an empty secret keeps the stored one
    from mimirsynth.models import Brain
    from mimirsynth.store import _factory
    with _factory()() as db:
        bid = db.query(Brain).filter(Brain.slug == "vf2").one().id
        assert V.make(db, bid, "with_token").v == {"url": "https://inv2", "token": "s3cr3t-value"}
    tok = client.post("/api/brains/vf2/tokens", json={"name": "c", "role": "curator"}).json()["token"]
    assert client.put("/api/brains/vf2/verifiers/with_token", headers={"Authorization": f"Bearer {tok}"}, json={"values": {}}).status_code == 403
