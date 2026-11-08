"""Structured claims in a proposal, the write gate (#295): compared with the subject's current facts when sent (confirms, replaces,
may replace, new), a repeat becomes a confirmation instead of a new fact and never revives a fact no longer true, a replacement is
applied after the text is ingested and can be undone, and a proposal that replaces facts is left to a person."""
import os

import pytest
from fastapi.testclient import TestClient

from test_control import client  # noqa: F401
from test_mcp import rpc

from mimirsynth import claims as C
from mimirsynth.main import app

FALKOR = os.environ.get("MIMIRSYNTH_TEST_FALKOR")
GRAPH = "zz-test-claims"
needs_falkor = pytest.mark.skipif(not FALKOR, reason="necesita un FalkorDB desechable (MIMIRSYNTH_TEST_FALKOR=host)")


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
    g.query("CREATE (:Entity {uuid:'nc', name:'Nextcloud', aliases:['NC']}), (:Entity {uuid:'er', name:'Eridani'}), "
            "(:Entity {uuid:'no', name:'Notus', aliases:['notus.lan']}), (:Entity {uuid:'pg', name:'PostgreSQL'}), (:Entity {uuid:'ops', name:'Ops'})")
    for u, rel, target, fact, inv in (("f1", "RUNS_ON", "er", "Nextcloud corre en Eridani", None),
                                      ("f2", "RUNS_ON", "no", "Nextcloud corría en Notus", "2025-01-01T00:00:00Z"),
                                      ("f3", "USES", "pg", "Nextcloud usa PostgreSQL", None),
                                      ("f4", "OWNED_BY", "ops", "Nextcloud es de Ops", None)):
        g.query("MATCH (a:Entity {uuid:'nc'}), (b:Entity {uuid:$b}) CREATE (a)-[:RELATES_TO {uuid:$u, name:$r, fact:$f, valid_at:'2024-01-01T00:00:00Z', "
                "created_at:'2024-01-01T00:00:00Z', invalid_at:$i, expired_at:$i}]->(b)", {"u": u, "r": rel, "f": fact, "b": target, "i": inv})
    yield g
    c.delete_graph(GRAPH)
    dbm.backend.cache_clear()


def _claim(subject, relation, value, **k):
    return {"subject": subject, "relation": relation, "value": value, "valid_from": None, "supersedes": None, **k}


@needs_falkor
def test_each_claim_gets_its_verdict(graph):
    v = lambda c, functional=frozenset(): C.compare(graph, c, None, set(functional))  # noqa: E731
    assert v(_claim("nextcloud", "RunsOn", "eridani"))["verdict"] == "confirms"                # case, format of the relation
    assert v(_claim("NC", "runs-on", "Eridani"))["facts"][0]["uuid"] == "f1"                   # a merged name of the subject
    assert v(_claim("Nextcloud", "RUNS_ON", "notus.lan"))["verdict"] == "may_replace"          # f2 is no longer true: not a repeat
    assert v(_claim("Nextcloud", "RUNS_ON", "Notus"), {"RUNS_ON"})["verdict"] == "replaces"   # functional: the other value goes
    assert v(_claim("Nextcloud", "BACKED_UP_TO", "Notus"))["verdict"] == "new"
    r = v(_claim("Nextcloud", "USES", "MariaDB", supersedes="f3"))
    assert r["verdict"] == "replaces" and [f["uuid"] for f in r["facts"]] == ["f3"]
    with pytest.raises(C.ClaimError) as e:
        v(_claim("Nextcloud", "RUNS_ON", "Notus", supersedes="f2"))
    assert e.value.code == "not_current"
    with pytest.raises(C.ClaimError):
        v(_claim("Nextcloud", "RUNS_ON", "Notus", supersedes="nope"))


def _tok(client, slug, role):  # noqa: F811
    return client.post(f"/api/brains/{slug}/tokens", json={"name": role, "role": role}).json()["token"]


@needs_falkor
def test_send_approve_confirm_replace_and_undo(client, graph, monkeypatch):  # noqa: F811
    from mimirsynth import ingest
    from mimirsynth.models import FactConfirmation, Proposal, VocabOp
    from mimirsynth.store import _factory
    monkeypatch.setattr(ingest, "enabled", lambda: True)
    eps = []

    async def fake(*a, **k):
        eps.append(a[2])
        return "ep-1"
    monkeypatch.setattr(ingest, "add_episode", fake)
    assert client.post("/api/brains", json={"slug": "cl", "name": "CL", "graph_name": GRAPH}).status_code == 201
    contrib = {"Authorization": f"Bearer {_tok(client, 'cl', 'contributor')}"}

    # a repeat: pending, then approved by a curator -> a confirmation, nothing ingested
    r = client.post("/api/brains/cl/proposals", headers=contrib, json={"name": "Nextcloud", "body": "Nextcloud sigue en Eridani.",
                                                                         "claims": [{"subject": "Nextcloud", "relation": "RUNS_ON", "value": "Eridani"}]})
    assert r.status_code == 201 and r.json()["claims"][0]["verdict"] == "confirms" and r.json()["status"] == "pending"
    pid = r.json()["id"]
    assert client.post(f"/api/brains/cl/proposals/{pid}/approve", json={}).status_code == 200
    assert ingest.ingest_proposal(pid) == "" and eps == []
    with _factory()() as db:
        p = db.get(Proposal, pid)
        assert p.status == "ingested" and p.ingest_report == {"claims": {"confirmed": ["f1"], "superseded": []}}
        assert db.query(FactConfirmation).filter(FactConfirmation.brain_id == p.brain_id, FactConfirmation.fact_uuid == "f1").one().user_id is not None

    # a replacement: the decider and a batch leave it to a person; approved, the text is ingested and only then f3 is invalidated
    r = client.post("/api/brains/cl/proposals", headers=contrib, json={"name": "BD", "body": "Nextcloud usa MariaDB desde octubre.",
                    "claims": [{"subject": "Nextcloud", "relation": "USES", "value": "MariaDB", "supersedes": "f3", "valid_from": "2026-10-01T00:00:00Z"}]})
    pid = r.json()["id"]
    assert r.json()["claims"][0]["verdict"] == "replaces"
    assert client.post("/api/brains/cl/proposals/bulk", json={"verb": "approve", "ids": [pid]}).json()["skipped"] == [{"id": pid, "reason": "replaces"}]
    client.post(f"/api/brains/cl/proposals/{pid}/approve", json={})
    assert graph.query("MATCH ()-[r:RELATES_TO {uuid:'f3'}]->() RETURN r.invalid_at").result_set[0][0] is None   # not before ingesting
    assert ingest.ingest_proposal(pid) == "" and eps == ["Nextcloud usa MariaDB desde octubre."]
    assert graph.query("MATCH ()-[r:RELATES_TO {uuid:'f3'}]->() RETURN r.invalid_at").result_set[0][0] == "2026-10-01T00:00:00+00:00"
    with _factory()() as db:
        p = db.get(Proposal, pid)
        applied = p.claims[0]["applied"]
        assert applied["action"] == "supersede" and p.ingest_report["claims"]["superseded"] == ["f3"]
        op = db.get(VocabOp, applied["facts"][0]["op"])
        assert op.kind == "fact.invalidate"
    assert client.post(f"/api/brains/cl/vocab/ops/{op.id}/revert").status_code == 200                  # undoable from the history
    assert graph.query("MATCH ()-[r:RELATES_TO {uuid:'f3'}]->() RETURN r.invalid_at").result_set[0][0] is None
    assert ingest.ingest_proposal(pid) == ""                                                      # a retry does not apply it twice

    # a supersedes that is not current is refused when sent
    r = client.post("/api/brains/cl/proposals", headers=contrib, json={"name": "x", "body": "y",
                    "claims": [{"subject": "Nextcloud", "relation": "RUNS_ON", "value": "Notus", "supersedes": "f2"}]})
    assert r.status_code == 409


@needs_falkor
def test_the_agent_hears_what_its_claims_do(client, graph):  # noqa: F811
    client.post("/api/brains", json={"slug": "cl2", "name": "CL2", "graph_name": GRAPH})
    tok = _tok(client, "cl2", "contributor")
    c = TestClient(app, headers={"Accept-Language": "es"})
    r = rpc(c, "cl2", "tools/call", {"name": "remember", "arguments": {"name": "NC", "body": "Nextcloud en Notus",
            "claims": [{"subject": "Nextcloud", "relation": "RUNS_ON", "value": "Eridani"}, {"subject": "Nextcloud", "relation": "OWNED_BY", "value": "Infra"}]}},
            token=tok).json()["result"]["content"][0]["text"]
    assert "ya es un hecho vigente" in r and "parece sustituir a: «Nextcloud es de Ops» [f4]" in r and "supersedes" in r
