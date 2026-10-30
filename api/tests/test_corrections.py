"""Fact corrections from agents (#109): proposal by uuid, quarantine, application, replacement and reactivation."""
import os

import pytest
from fastapi.testclient import TestClient

from test_control import client  # noqa: F401
from test_mcp import rpc
from test_mcp_tools import _tok, call

from mimirsynth.main import app

FALKOR = os.environ.get("MIMIRSYNTH_TEST_FALKOR")
OWN, LENT = "zz-test-corr-own", "zz-test-corr-lent"


@pytest.fixture()
def graphs(monkeypatch):
    from mimirsynth import db as dbm
    from mimirsynth.config import settings
    monkeypatch.setattr(settings, "falkor_host", FALKOR)
    dbm.client.cache_clear()
    c = dbm.client()
    for name in (OWN, LENT):
        if name in c.list_graphs():
            c.select_graph(name).delete()
    g = c.select_graph(OWN)
    g.query("CREATE (a:Entity {uuid:'nc', name:'Nextcloud'}), (b:Entity {uuid:'er', name:'Eridani'}), (n:Entity {uuid:'no', name:'Notus'})")
    for u, fact, b, inv in [("f1", "Nextcloud corre en Eridani", "er", None), ("f2", "Nextcloud corría en Notus", "no", "2025-01-01T00:00:00Z"),
                            ("f3", "Nextcloud usa PHP 8.1", "er", None), ("f4", "Nextcloud tiene 40 usuarios", "no", None)]:
        g.query("MATCH (a:Entity {uuid:'nc'}), (b:Entity {uuid:$b}) CREATE (a)-[:RELATES_TO {uuid:$u, name:'RUNS_ON', fact:$f, valid_at:'2024-01-01T00:00:00Z', "
                "created_at:'2024-01-01T00:00:00Z', invalid_at:$i, expired_at:$i}]->(b)", {"u": u, "f": fact, "b": b, "i": inv})
    c.select_graph(LENT).query("CREATE (:Entity {uuid:'x', name:'X'})-[:RELATES_TO {uuid:'g1', name:'R', fact:'X es prestado', created_at:'2024-01-01T00:00:00Z'}]->(:Entity {uuid:'y', name:'Y'})")
    yield g
    for name in (OWN, LENT):
        c.select_graph(name).delete()
    dbm.client.cache_clear()


def _state(g, uuid):
    return g.query("MATCH ()-[r:RELATES_TO {uuid:$u}]->() RETURN r.invalid_at, r.expired_at", {"u": uuid}).result_set[0]


@pytest.mark.skipif(not FALKOR, reason="necesita un FalkorDB desechable (MIMIRSYNTH_TEST_FALKOR=host)")
def test_correction_quarantine_apply_replacement_and_reactivate(client, graphs, monkeypatch):  # noqa: F811
    from mimirsynth import deciders_admin, ingest
    from mimirsynth.models import Proposal, VocabOp
    from mimirsynth.store import _factory
    queued = []
    monkeypatch.setattr(ingest, "enabled", lambda: True)
    monkeypatch.setattr(ingest, "submit_ingest", lambda pid, brain_id, name, user_id=None: queued.append(pid) or 1)
    assert client.post("/api/brains", json={"slug": "co", "name": "CO", "graph_name": OWN}).status_code == 201
    assert client.post("/api/brains", json={"slug": "col", "name": "COL", "graph_name": LENT}).status_code == 201
    assert client.post("/api/brains/col/grants", json={"target": "co", "scope": "graph"}).status_code == 201
    reader, contrib, curator = _tok(client, "co", "reader"), _tok(client, "co", "contributor"), _tok(client, "co", "curator")
    c = TestClient(app, headers={"Accept-Language": "es"})
    assert "correct" in [t["name"] for t in rpc(c, "co", "tools/list", token=reader).json()["result"]["tools"]]

    # who can propose, and which facts can be corrected
    err, txt = call(c, "co", reader, "correct", fact_uuid="f1", reason="Ya no corre ahí")
    assert err and "solo puede leer" in txt
    assert "No hay ningún hecho con el uuid nada" in call(c, "co", contrib, "correct", fact_uuid="nada", reason="motivo")[1]
    assert "ya está invalidado desde 2025-01-01" in call(c, "co", contrib, "correct", fact_uuid="f2", reason="motivo")[1]
    err, txt = call(c, "co", contrib, "correct", fact_uuid="g1", reason="motivo")
    assert err and "es de «col»" in txt and "solo lectura" in txt                          # a lent fact is not corrected from here

    # a contributor proposes it: quarantine, the fact does not change and the decider leaves it alone
    err, txt = call(c, "co", contrib, "correct", fact_uuid="f1", reason="Se migró a Notus el 1 de septiembre",
                    replacement="Nextcloud corre en Notus desde el 1 de septiembre de 2026.", invalid_at="2026-09-01T00:00:00Z")
    assert not err and "cuarentena" in txt
    with _factory()() as db:
        p = db.query(Proposal).filter(Proposal.kind == "correction").one()
        pid = p.id
        assert p.status == "pending" and p.name == "Corrección: Nextcloud corre en Eridani" and p.body.startswith("Nextcloud corre en Notus")
        assert p.correction["fact"]["target"] == "Eridani" and p.correction["invalid_at"] == "2026-09-01T00:00:00+00:00"
    assert _state(graphs, "f1") == [None, None]
    monkeypatch.setattr(deciders_admin, "default_decider", lambda db: object())               # there is a decider, but it does not look at it
    monkeypatch.setattr(deciders_admin.decider, "triage", lambda *a, **k: (_ for _ in ()).throw(AssertionError("el decisor no debe mirarla")))
    deciders_admin.triage_proposal(pid)
    d = client.get(f"/api/brains/co/proposals/{pid}").json()
    assert d["kind"] == "correction" and d["status"] == "pending" and d["decision"] is None and d["correction"]["reason"].startswith("Se migró")

    # approve: invalidated as of the given date, recorded in the history, and the replacement goes to ingestion with that date
    r = client.post(f"/api/brains/co/proposals/{pid}/approve", json={"note": "comprobado"})
    assert r.status_code == 200, r.text
    inv, exp = _state(graphs, "f1")
    assert inv == "2026-09-01T00:00:00+00:00" and exp
    assert queued == [pid]
    with _factory()() as db:
        p = db.get(Proposal, pid)
        assert p.status == "approved" and p.correction["applied_at"] and p.reference_time.isoformat().startswith("2026-09-01")
        assert db.get(VocabOp, p.correction["op"]).kind == "fact.invalidate"

    # reactivate from the proposal: the previous state comes back, only once
    r = client.post(f"/api/brains/co/proposals/{pid}/reactivate")
    assert r.status_code == 200 and r.json()["correction"]["reverted_at"]
    assert _state(graphs, "f1") == [None, None]
    assert client.post(f"/api/brains/co/proposals/{pid}/reactivate").status_code == 409

    # rejecting changes nothing; approving something no longer current gives 409 and it stays pending
    call(c, "co", contrib, "correct", fact_uuid="f3", reason="Ahora usa PHP 8.3")
    call(c, "co", contrib, "correct", fact_uuid="f4", reason="Ya son 60")
    with _factory()() as db:
        p3, p4 = (db.query(Proposal).filter(Proposal.kind == "correction", Proposal.correction["fact_uuid"].as_string() == u).one().id for u in ("f3", "f4"))
    assert client.post(f"/api/brains/co/proposals/{p3}/reject", json={"note": "no"}).status_code == 200
    assert _state(graphs, "f3") == [None, None]
    assert client.post("/api/brains/co/facts/f4/invalidate").status_code == 200
    r = client.post(f"/api/brains/co/proposals/{p4}/approve", json={})
    assert r.status_code == 409 and "ya está invalidado" in r.json()["detail"]
    assert client.get(f"/api/brains/co/proposals/{p4}").json()["status"] == "pending"
    assert client.post(f"/api/brains/co/proposals/{p3}/reactivate").status_code == 409     # not applied

    # race: the fact stops being current between the check and the write; the proposal is never left half approved
    from mimirsynth import corrections
    call(c, "co", contrib, "correct", fact_uuid="f1", reason="Otra vez")
    with _factory()() as db:
        p5 = db.query(Proposal).filter(Proposal.kind == "correction", Proposal.status == "pending", Proposal.correction["fact_uuid"].as_string() == "f1").one().id
    graphs.query("MATCH ()-[r:RELATES_TO {uuid:'f1'}]->() SET r.invalid_at = '2026-10-01T00:00:00Z'")
    check = corrections._check
    monkeypatch.setattr(corrections, "_check", lambda ctx, u, lang: {"uuid": u, "fact": "x", "invalid_at": None, "expired_at": None})
    r = client.post(f"/api/brains/co/proposals/{p5}/approve", json={})
    assert r.status_code == 409 and "mientras se revisaba" in r.json()["detail"]
    monkeypatch.setattr(corrections, "_check", check)
    d = client.get(f"/api/brains/co/proposals/{p5}").json()
    assert d["status"] == "pending" and "applied_at" not in d["correction"] and d["reviewed_at"] is None
    assert _state(graphs, "f1")[0] == "2026-10-01T00:00:00Z"                                # the graph was not touched

    # over MCP it stays pending even with a curator token; over REST a curator applies it and, without a replacement, it is done
    err, txt = call(c, "co", curator, "correct", fact_uuid="f3", reason="Ahora usa PHP 8.3")
    assert not err and "cuarentena" in txt and _state(graphs, "f3") == [None, None]
    r = client.post("/api/brains/co/proposals/corrections", json={"fact_uuid": "f3", "reason": "Ahora usa PHP 8.3"})
    assert r.status_code == 201 and r.json()["status"] == "ingested"
    assert _state(graphs, "f3")[0]
    with _factory()() as db:
        p = db.query(Proposal).filter(Proposal.kind == "correction", Proposal.review_kind == "direct").one()
        assert p.status == "ingested" and p.body == "" and len(queued) == 1
    assert client.post(f"/api/brains/co/proposals/{p.id}/ingest").status_code == 409        # nothing to ingest
    items = client.get("/api/brains/co/proposals").json()["items"]
    assert {i["kind"] for i in items} == {"correction"}
