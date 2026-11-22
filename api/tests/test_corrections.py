"""Fact corrections from agents (#109): proposal by uuid, quarantine, application, replacement and reactivation."""
import os

import pytest
from fastapi.testclient import TestClient

from test_control import client  # noqa: F401
from test_mcp import rpc
from test_mcp_tools import _tok, call

from mimirsynth.db import parse_ts  # a date as Graphiti stores it: a string on FalkorDB, a temporal on Neo4j
from mimirsynth.main import app

FALKOR = os.environ.get("MIMIRSYNTH_TEST_FALKOR")
OWN, LENT = "zz-test-corr-own", "zz-test-corr-lent"


@pytest.fixture()
def graphs(monkeypatch):
    from mimirsynth import db as dbm
    from mimirsynth.config import settings
    monkeypatch.setattr(settings, "falkor_host", FALKOR)
    dbm.backend.cache_clear()
    c = dbm.backend()
    for name in (OWN, LENT):
        if name in c.list_graphs():
            c.delete_graph(name)
    g = c.graph(OWN)
    g.query("CREATE (a:Entity {uuid:'nc', name:'Nextcloud'}), (b:Entity {uuid:'er', name:'Eridani'}), (n:Entity {uuid:'no', name:'Notus'})")
    for u, fact, b, inv in [("f1", "Nextcloud corre en Eridani", "er", None), ("f2", "Nextcloud corría en Notus", "no", "2025-01-01T00:00:00Z"),
                            ("f3", "Nextcloud usa PHP 8.1", "er", None), ("f4", "Nextcloud tiene 40 usuarios", "no", None)]:
        g.query("MATCH (a:Entity {uuid:'nc'}), (b:Entity {uuid:$b}) CREATE (a)-[:RELATES_TO {uuid:$u, name:'RUNS_ON', fact:$f, valid_at:'2024-01-01T00:00:00Z', "
                "created_at:'2024-01-01T00:00:00Z', invalid_at:$i, expired_at:$i}]->(b)", {"u": u, "f": fact, "b": b, "i": inv})
    c.graph(LENT).query("CREATE (:Entity {uuid:'x', name:'X'})-[:RELATES_TO {uuid:'g1', name:'R', fact:'X es prestado', created_at:'2024-01-01T00:00:00Z'}]->(:Entity {uuid:'y', name:'Y'})")
    yield g
    for name in (OWN, LENT):
        c.delete_graph(name)
    dbm.backend.cache_clear()


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
    monkeypatch.setattr(corrections, "_check", lambda ctx, u, lang, act="invalidate": {"uuid": u, "fact": "x", "invalid_at": None, "expired_at": None})
    r = client.post(f"/api/brains/co/proposals/{p5}/approve", json={})
    assert r.status_code == 409 and "mientras se revisaba" in r.json()["detail"]
    monkeypatch.setattr(corrections, "_check", check)
    d = client.get(f"/api/brains/co/proposals/{p5}").json()
    assert d["status"] == "pending" and "applied_at" not in d["correction"] and d["reviewed_at"] is None
    assert parse_ts(_state(graphs, "f1")[0]) == parse_ts("2026-10-01T00:00:00Z")           # the graph was not touched

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


@pytest.mark.skipif(not FALKOR, reason="necesita un FalkorDB desechable (MIMIRSYNTH_TEST_FALKOR=host)")
def test_list_filters_and_counts_by_kind(client, graphs):  # noqa: F811
    """rc.1 feedback on #143: a curator must tell corrections from memories at a glance, filter them and see how many wait."""
    assert client.post("/api/brains", json={"slug": "cok", "name": "COK", "graph_name": OWN}).status_code == 201
    h = {"Authorization": "Bearer " + _tok(client, "cok", "contributor")}
    fix = client.post("/api/brains/cok/proposals/corrections", headers=h, json={"fact_uuid": "f1", "reason": "Ya no corre ahí"})
    assert fix.status_code == 201 and fix.json()["status"] == "pending"
    mem = client.post("/api/brains/cok/proposals", headers=h, json={"name": "Nota", "body": "Nextcloud tiene copia diaria"}).json()
    items = client.get("/api/brains/cok/proposals", params={"kind": "correction"}).json()["items"]
    assert [(p["id"], p["kind"]) for p in items] == [(fix.json()["id"], "correction")]
    assert [p["id"] for p in client.get("/api/brains/cok/proposals", params={"kind": "memory"}).json()["items"]] == [mem["id"]]
    assert [p["id"] for p in client.get("/api/brains/cok/proposals", params={"sort": "id", "order": "asc"}).json()["items"]] == [fix.json()["id"], mem["id"]]
    assert client.get("/api/brains/cok/proposals", params={"kind": "otra"}).status_code == 400
    c = client.get("/api/brains/cok/proposals/counts").json()
    assert c["kinds"] == {"correction": 1, "memory": 1} and c["corrections_pending"] == 1 and c["all"] == 2
    only = client.get("/api/brains/cok/proposals/counts", params={"kind": "correction"}).json()
    assert only["all"] == only["pending"] == 1 and only["corrections_pending"] == 1      # the state tabs count only that kind


@pytest.mark.skipif(not FALKOR, reason="necesita un FalkorDB desechable (MIMIRSYNTH_TEST_FALKOR=host)")
def test_reactivation_of_a_fact_invalidated_by_mistake(client, graphs, monkeypatch):  # noqa: F811
    from mimirsynth import ingest
    from mimirsynth.models import Proposal, VocabOp
    from mimirsynth.store import _factory
    monkeypatch.setattr(ingest, "enabled", lambda: True)
    monkeypatch.setattr(ingest, "submit_ingest", lambda pid, brain_id, name, user_id=None: 1)
    assert client.post("/api/brains", json={"slug": "cor", "name": "COR", "graph_name": OWN}).status_code == 201
    contrib = _tok(client, "cor", "contributor")
    c = TestClient(app, headers={"Accept-Language": "es"})

    # only an invalidated fact can be reactivated; the default action stays «invalidate»
    err, txt = call(c, "cor", contrib, "correct", fact_uuid="f1", reason="Sigue siendo cierto", action="reactivate")
    assert err and "está vigente" in txt
    err, txt = call(c, "cor", contrib, "correct", fact_uuid="f2", reason="La sustitución fue un error: sigue en Notus", action="reactivate")
    assert not err and "Reactivación propuesta" in txt
    with _factory()() as db:
        p = db.query(Proposal).filter(Proposal.kind == "correction", Proposal.correction["action"].as_string() == "reactivate").one()
        pid = p.id
        assert p.correction["action"] == "reactivate" and p.name == "Reactivación: Nextcloud corría en Notus" and p.status == "pending"
    assert _state(graphs, "f2")[0]                                                           # nothing changes while it waits
    assert client.post("/api/brains/cor/proposals/bulk", json={"ids": [pid], "verb": "approve"}).json()["skipped"][0]["reason"] == "correction"

    # approve: the fact is current again, recorded in the history
    r = client.post(f"/api/brains/cor/proposals/{pid}/approve", json={})
    assert r.status_code == 200, r.text
    assert _state(graphs, "f2") == [None, None]
    with _factory()() as db:
        p = db.get(Proposal, pid)
        assert p.status == "ingested" and p.correction["applied_at"]                           # no replacement: nothing to ingest
        assert db.get(VocabOp, p.correction["op"]).kind == "fact.reactivate"

    # undo: invalidated again as it was, only once
    r = client.post(f"/api/brains/cor/proposals/{pid}/reactivate")
    assert r.status_code == 200 and r.json()["correction"]["reverted_at"]
    assert parse_ts(_state(graphs, "f2")[0]) == parse_ts("2025-01-01T00:00:00Z")
    assert client.post(f"/api/brains/cor/proposals/{pid}/reactivate").status_code == 409

    # a reactivation of a fact that became current while it waited gives 409 and stays pending
    call(c, "cor", contrib, "correct", fact_uuid="f2", reason="Otra vez", action="reactivate")
    with _factory()() as db:
        p2 = db.query(Proposal).filter(Proposal.correction["action"].as_string() == "reactivate", Proposal.status == "pending").one().id
    assert client.post("/api/brains/cor/facts/f2/reactivate").status_code == 200
    r = client.post(f"/api/brains/cor/proposals/{p2}/approve", json={})
    assert r.status_code == 409 and "está vigente" in r.json()["detail"]
    assert client.get(f"/api/brains/cor/proposals/{p2}").json()["status"] == "pending"


@pytest.mark.skipif(not FALKOR, reason="necesita un FalkorDB desechable (MIMIRSYNTH_TEST_FALKOR=host)")
def test_one_pending_correction_per_fact_and_action(client, graphs):  # noqa: F811
    """#460: sending the same correction twice leaves one pending; a curator who applies one is not stopped by it."""
    from mimirsynth.models import Proposal
    from mimirsynth.store import _factory
    assert client.post("/api/brains", json={"slug": "co2", "name": "CO2", "graph_name": OWN}).status_code == 201
    contrib = _tok(client, "co2", "contributor")
    c = TestClient(app, headers={"Accept-Language": "es"})
    err, txt = call(c, "co2", contrib, "correct", fact_uuid="f3", reason="Ahora usa PHP 8.3")
    assert not err and "cuarentena" in txt
    err, txt = call(c, "co2", contrib, "correct", fact_uuid="f3", reason="Ahora usa PHP 8.4")
    assert not err and "Ya hay una corrección pendiente de ese hecho" in txt
    err, txt = call(c, "co2", contrib, "correct", fact_uuid="f2", reason="Volvió a Notus", action="reactivate")   # another action: its own
    assert not err and "cuarentena" in txt
    with _factory()() as db:
        bid = db.query(Proposal.brain_id).filter(Proposal.kind == "correction").order_by(Proposal.id.desc()).first()[0]
        fixes = db.query(Proposal).filter(Proposal.brain_id == bid, Proposal.kind == "correction", Proposal.status == "pending").all()
        assert sorted((p.correction["fact_uuid"], p.correction["action"]) for p in fixes) == [("f2", "reactivate"), ("f3", "invalidate")]
        first = next(p.id for p in fixes if p.correction["fact_uuid"] == "f3")

    # over REST, a contributor gets the pending one back (200); a curator applies a new one at once
    from test_control import _as
    assert client.put("/api/brains/co2/members", json={"email": "cleo@x.com", "role": "contributor"}).status_code == 200
    _as("cleo@x.com", "Cleo")
    r = client.post("/api/brains/co2/proposals/corrections", json={"fact_uuid": "f3", "reason": "Otra vez"})
    assert r.status_code == 200 and r.json()["id"] == first and r.json()["duplicate"] is True
    app.dependency_overrides.clear()
    r = client.post("/api/brains/co2/proposals/corrections", json={"fact_uuid": "f3", "reason": "Ahora usa PHP 8.3"})
    assert r.status_code == 201 and r.json()["status"] == "ingested" and _state(graphs, "f3")[0]


def _fake_fact(monkeypatch):
    from mimirsynth import corrections
    monkeypatch.setattr(corrections, "_check", lambda ctx, u, lang, act="invalidate": {
        "uuid": u, "name": "R", "fact": "Mailer sends through Sendgrid", "valid_at": "2023-01-01", "invalid_at": None, "expired_at": None,
        "source": "Mailer", "target": "Sendgrid"})


def test_a_repeated_correction_never_shows_another_authors_proposal(client, monkeypatch):  # noqa: F811
    """#460: a contributor who sends a correction someone else already sent gets its number, not its text, author or reason."""
    from test_control import _as
    from mimirsynth.models import Proposal
    from mimirsynth.store import _factory
    _fake_fact(monkeypatch)
    assert client.post("/api/brains", json={"slug": "co3", "name": "CO3"}).status_code == 201
    for email in ("ana@x.com", "bea@x.com"):
        assert client.put("/api/brains/co3/members", json={"email": email, "role": "contributor"}).status_code == 200
    url = "/api/brains/co3/proposals/corrections"
    _as("ana@x.com", "Ana")
    first = client.post(url, json={"fact_uuid": "fx", "reason": "Moved to Postmark; the old key was 1234", "replacement": "Mailer uses Postmark."})
    assert first.status_code == 201 and first.json()["status"] == "pending"
    again = client.post(url, json={"fact_uuid": "fx", "reason": "Still there"})
    assert again.status_code == 200 and again.json()["id"] == first.json()["id"] and again.json()["correction"]["reason"].startswith("Moved")   # her own: all of it
    _as("bea@x.com", "Bea")
    r = client.post(url, json={"fact_uuid": "fx", "reason": "Moved"})
    assert r.status_code == 200 and r.json() == {"id": first.json()["id"], "status": "pending", "kind": "correction", "duplicate": True, "mine": False}
    app.dependency_overrides.clear()

    # a curator whose correction would wait (a possible secret to review) gets the pending one too, never a second
    with _factory()() as db:
        from mimirsynth.models import Brain
        db.query(Brain).filter(Brain.slug == "co3").one().secret_mode = "warn"
        db.commit()
    r = client.post(url, json={"fact_uuid": "fx", "reason": "token ghp_" + "A1b2C3d4E5f6G7h8J9k0" + "A1b2C3d4E5f6G7h8"})
    assert r.status_code == 200 and r.json()["id"] == first.json()["id"]
    with _factory()() as db:
        bid = db.query(Proposal.brain_id).filter(Proposal.id == first.json()["id"]).scalar()
        assert db.query(Proposal).filter(Proposal.brain_id == bid, Proposal.kind == "correction").count() == 1
    assert client.get("/api/brains/co3/proposals", params={"q": "²"}).status_code == 200   # a digit to Python, not a number


def test_rating_a_fact_someone_else_is_correcting_says_so(client, monkeypatch):  # noqa: F811
    """#460: «incorrect» on a fact another person already asked to invalidate points to theirs, as existing, not as a new one."""
    from test_control import _as
    from mimirsynth import memory
    from test_recall_ratings import OUT
    _fake_fact(monkeypatch)
    monkeypatch.setattr(memory, "recall", lambda *a, **k: dict(OUT))
    assert client.post("/api/brains", json={"slug": "co4", "name": "CO4"}).status_code == 201
    for email in ("ana@x.com", "bea@x.com"):
        assert client.put("/api/brains/co4/members", json={"email": email, "role": "contributor"}).status_code == 200
    _as("ana@x.com", "Ana")
    pid = client.post("/api/brains/co4/proposals/corrections", json={"fact_uuid": "f1", "reason": "Moved"}).json()["id"]
    _as("bea@x.com", "Bea")
    rid = client.post("/api/brains/co4/recall", json={"query": "¿Dónde corre Nextcloud?"}).json()["recall_id"]
    r = client.post(f"/api/brains/co4/recall/{rid}/ratings", json={"kind": "fact", "id": "f1", "rating": "incorrect", "note": "ya no"}).json()
    assert r["proposal_id"] == pid and r["existing"] is True
    app.dependency_overrides.clear()


def test_corrections_sent_together_are_decided_as_a_group(client, monkeypatch):  # noqa: F811
    """#457: pending invalidations with the same author, token and source form a group; approving applies the ticked ones, each as its own
    correction, and rejects the others with the group's note; a fact that changed meanwhile is skipped and stays pending."""
    from fastapi import HTTPException
    from test_control import _as
    from mimirsynth import corrections
    from mimirsynth.models import Audit, Proposal
    from mimirsynth.store import _factory
    _fake_fact(monkeypatch)
    assert client.post("/api/brains", json={"slug": "cg", "name": "CG"}).status_code == 201
    for email, role in (("ana@x.com", "contributor"), ("bea@x.com", "contributor"), ("rita@x.com", "reader")):
        assert client.put("/api/brains/cg/members", json={"email": email, "role": role}).status_code == 200
    url = "/api/brains/cg/proposals/corrections"
    _as("ana@x.com", "Ana")
    ids = [client.post(url, json={"fact_uuid": f"g{n}", "reason": f"Old {n}", "source_description": "cleanup run 1"}).json()["id"] for n in range(4)]
    alone = client.post(url, json={"fact_uuid": "g9", "reason": "No source"}).json()["id"]
    back = client.post(url, json={"fact_uuid": "g8", "reason": "Back", "source_description": "cleanup run 1", "action": "reactivate"}).json()["id"]
    _as("bea@x.com", "Bea")
    other = client.post(url, json={"fact_uuid": "g7", "reason": "Hers", "source_description": "cleanup run 1"}).json()["id"]
    _as("rita@x.com", "Rita")
    assert client.get("/api/brains/cg/correction-groups").status_code == 403
    app.dependency_overrides.clear()

    groups = client.get("/api/brains/cg/correction-groups").json()["groups"]
    assert len(groups) == 1 and groups[0]["count"] == 4 and [i["id"] for i in groups[0]["items"]] == ids   # no reactivation, no lone one, not Bea's
    assert groups[0]["source_description"] == "cleanup run 1" and groups[0]["items"][0]["fact"]["fact"] == "Mailer sends through Sendgrid"

    applied = []
    def fake_apply(ctx, p, lang="es", note="", kind="human"):
        if p.correction["fact_uuid"] == "g1":
            raise HTTPException(409, "El hecho dejó de estar vigente")
        applied.append((p.id, note))
        p.status, p.reviewer_id = "ingested", ctx.user.id
        ctx.db.commit()
    monkeypatch.setattr(corrections, "apply", fake_apply)
    dec = "/api/brains/cg/correction-groups/decide"
    assert client.post(dec, json={}).status_code == 422
    assert client.post(dec, json={"approve": [ids[0]], "reject": [ids[0]]}).status_code == 422
    assert client.post(dec, json={"approve": [ids[0], other]}).status_code == 422             # another author's group
    assert client.post(dec, json={"approve": [ids[0], alone]}).status_code == 409             # decided alone
    assert client.post(dec, json={"approve": [ids[0], back]}).status_code == 409              # a reactivation never goes in a group
    assert client.post(dec, json={"approve": [999999]}).status_code == 404
    r = client.post(dec, json={"approve": [ids[0], ids[1], ids[2]], "reject": [ids[3]], "note": "Checked against the inventory"}).json()
    assert r["approved"] == [ids[0], ids[2]] and r["rejected"] == [ids[3]] and r["skipped"][0]["id"] == ids[1] and r["skipped"][0]["reason"] == "changed"
    assert applied == [(ids[0], "Checked against the inventory"), (ids[2], "Checked against the inventory")]
    with _factory()() as db:
        st = {p.id: (p.status, p.review_note) for p in db.query(Proposal).filter(Proposal.id.in_(ids))}
        assert st[ids[1]] == ("pending", "") and st[ids[3]] == ("rejected", "Checked against the inventory")
        a = db.query(Audit).filter(Audit.action == "proposal.group").order_by(Audit.id.desc()).first()
        assert a.detail["approved"] == 2 and a.detail["rejected"] == 1 and a.detail["skipped"] == 1
    assert client.get("/api/brains/cg/correction-groups").json()["groups"] == []              # one left pending: no longer a group


@pytest.mark.skipif(not FALKOR, reason="necesita un FalkorDB desechable (MIMIRSYNTH_TEST_FALKOR=host)")
def test_a_group_of_corrections_applies_each_one_undoable_on_its_own(client, graphs):  # noqa: F811
    """#457 against the graph: approving a group of N invalidates N facts, and each one is reactivated from its own correction."""
    assert client.post("/api/brains", json={"slug": "cg2", "name": "CG2", "graph_name": OWN}).status_code == 201
    contrib = _tok(client, "cg2", "contributor")
    c = TestClient(app, headers={"Accept-Language": "es"})
    for u in ("f3", "f4"):
        err, txt = call(c, "cg2", contrib, "correct", fact_uuid=u, reason="Limpieza", source_description="limpieza de Nextcloud")
        assert not err and "cuarentena" in txt
    g = client.get("/api/brains/cg2/correction-groups").json()["groups"]
    assert len(g) == 1 and g[0]["count"] == 2
    ids = [i["id"] for i in g[0]["items"]]
    r = client.post("/api/brains/cg2/correction-groups/decide", json={"approve": ids, "note": "revisado"}).json()
    assert r["approved"] == ids and r["skipped"] == [] and _state(graphs, "f3")[0] and _state(graphs, "f4")[0]
    assert client.post(f"/api/brains/cg2/proposals/{ids[0]}/reactivate").status_code == 200
    assert _state(graphs, "f3") == [None, None] and _state(graphs, "f4")[0]                # each undone on its own
