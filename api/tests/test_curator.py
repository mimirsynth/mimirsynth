"""Scheduled curator (#300, first part): off by default, the contradiction pass turns clear groups into proposals in quarantine with
their evidence, a pass that would change more than its batch waits for a person to confirm a sample, one run per brain and day, the
precision of a pass comes from the curators' decisions, and approving a curator's proposal invalidates the old fact without an LLM."""
import os

import pytest

from test_control import client  # noqa: F401

from mimirsynth import curator as K

FALKOR = os.environ.get("MIMIRSYNTH_TEST_FALKOR")
GRAPH = "zz-test-curator"
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
    for n in range(7):   # seven services, each «located at» two hosts: the newest one is clearly the current one
        g.query("CREATE (:Entity {uuid:$s, name:$sn}), (:Entity:Host {uuid:$a, name:$an}), (:Entity:Host {uuid:$b, name:$bn})",
                {"s": f"s{n}", "sn": f"svc{n}", "a": f"a{n}", "an": f"old{n}", "b": f"b{n}", "bn": f"new{n}"})
        for u, t, when in ((f"o{n}", f"a{n}", "2024-01-01T00:00:00Z"), (f"n{n}", f"b{n}", "2026-01-01T00:00:00Z")):
            g.query("MATCH (a:Entity {uuid:$s}), (b:Entity {uuid:$t}) CREATE (a)-[:RELATES_TO {uuid:$u, name:'LOCATED_AT', fact:$f, valid_at:$w, "
                    "created_at:$w}]->(b)", {"s": f"s{n}", "t": t, "u": u, "f": f"svc{n} at {t}", "w": when})
    for n in range(30):  # and thirty with a single host: the relation does not look multi-valued
        g.query("CREATE (a:Entity {uuid:$s, name:$sn})-[:RELATES_TO {uuid:$u, name:'LOCATED_AT', fact:'one host', valid_at:'2025-01-01T00:00:00Z', "
                "created_at:'2025-01-01T00:00:00Z'}]->(:Entity:Host {uuid:$h, name:$hn})", {"s": f"x{n}", "sn": f"single{n}", "u": f"x{n}f", "h": f"h{n}", "hn": f"host{n}"})
    yield g
    c.delete_graph(GRAPH)
    dbm.backend.cache_clear()


def _setup(client, slug):  # noqa: F811
    assert client.post("/api/brains", json={"slug": slug, "name": slug.upper(), "graph_name": GRAPH}).status_code == 201
    assert client.post(f"/api/brains/{slug}/vocab/relations", json={"name": "LocatedAt", "description": "Está en un sitio", "functional": True}).status_code == 201


@needs_falkor
def test_off_by_default_preview_and_the_sample_gate(client, graph):  # noqa: F811
    from mimirsynth.models import CuratorRun, Proposal
    from mimirsynth.store import _factory
    _setup(client, "cu1")
    s = client.get("/api/brains/cu1/curator/settings").json()
    assert s["enabled"] is False and s["precision"]["contradictions"]["precision"] is None
    pv = client.post("/api/brains/cu1/curator/preview").json()
    assert pv["count"] == 7 and pv["findings"][0]["keep"]["uuid"].startswith("n") and pv["findings"][0]["replace"][0]["uuid"].startswith("o")
    client.put("/api/brains/cu1/curator/settings", json={"enabled": True, "batch": 5})
    assert client.post("/api/brains/cu1/curator/run").status_code == 202
    run = client.get("/api/brains/cu1/curator/runs").json()["items"][0]
    assert run["status"] == "waiting" and run["findings"] == {"contradictions": 7} and len(run["sample"]["contradictions"]) == 7
    with _factory()() as db:
        from mimirsynth.models import Brain
        bid = db.query(Brain).filter(Brain.slug == "cu1").one().id
        assert db.query(Proposal).filter(Proposal.brain_id == bid, Proposal.category == "curator.contradictions").count() == 0   # nothing proposed yet
    assert client.post("/api/brains/cu1/curator/run").status_code == 409                    # it waits: not run again
    done = client.post(f"/api/brains/cu1/curator/runs/{run['id']}/confirm").json()
    assert done["status"] == "done" and len(done["proposals"]) == 7
    with _factory()() as db:
        p = db.get(Proposal, done["proposals"][0])
        assert p.status == "pending" and p.body == "" and p.claims[0]["verdict"] == "replaces" and p.decision["curator"]["pass"] == "contradictions"
        assert db.query(CuratorRun).filter(CuratorRun.id == run["id"]).one().status == "done"
    assert client.post("/api/brains/cu1/curator/preview").json()["count"] == 0              # already proposed: not twice


@needs_falkor
def test_a_small_batch_is_proposed_and_approving_applies_it(client, graph, monkeypatch):  # noqa: F811
    from mimirsynth import ingest
    from mimirsynth.models import Proposal
    from mimirsynth.store import _factory
    monkeypatch.setattr(ingest, "enabled", lambda: False)                                   # no LLM: the curator's proposals still apply
    _setup(client, "cu2")
    client.put("/api/brains/cu2/curator/settings", json={"enabled": True, "batch": 10})
    assert len(K.due()) >= 1 and K.due() == []                                               # once a day
    run = client.get("/api/brains/cu2/curator/runs").json()["items"][0]
    assert run["status"] == "done" and len(run["proposals"]) == 7
    pid, other = run["proposals"][:2]
    r = client.post(f"/api/brains/cu2/proposals/{pid}/approve", json={})
    assert r.status_code == 200 and r.json().get("undo_seconds")
    ingest.ingest_proposal(pid)
    with _factory()() as db:
        p = db.get(Proposal, pid)
        old = p.claims[0]["supersedes"]
        assert p.status == "ingested" and p.ingest_report["claims"]["superseded"] == [old]
    assert graph.query("MATCH ()-[r:RELATES_TO {uuid:$u}]->() RETURN r.invalid_at", {"u": old}).result_set[0][0] == "2026-01-01T00:00:00Z"
    client.post(f"/api/brains/cu2/proposals/{other}/reject", json={"note": "the old host is still in use"})
    prec = client.get("/api/brains/cu2/curator/settings").json()["precision"]["contradictions"]
    assert prec == {"approved": 1, "rejected": 1, "pending": 5, "precision": 0.5}


def test_settings_are_for_administrators_and_known_passes(client):  # noqa: F811
    client.post("/api/brains", json={"slug": "cu3", "name": "CU3"})
    assert client.put("/api/brains/cu3/curator/settings", json={"enabled": True, "passes": {"nope": True}}).status_code == 422   # not a pass
    tok = client.post("/api/brains/cu3/tokens", json={"name": "c", "role": "curator"}).json()["token"]
    h = {"Authorization": f"Bearer {tok}"}
    assert client.get("/api/brains/cu3/curator/settings", headers=h).status_code == 200
    assert client.put("/api/brains/cu3/curator/settings", headers=h, json={"enabled": True}).status_code == 403


@pytest.fixture()
def repeated(monkeypatch):
    from mimirsynth import db as dbm
    from mimirsynth.config import settings
    monkeypatch.setattr(settings, "falkor_host", FALKOR)
    dbm.backend.cache_clear()
    c = dbm.backend()
    name = GRAPH + "-rep"
    if name in c.list_graphs():
        c.delete_graph(name)
    g = c.graph(name)
    g.query("CREATE (:Entity {uuid:'vw', name:'Vaultwarden'}), (:Entity {uuid:'al', name:'altair'}), (:Entity {uuid:'pg', name:'PostgreSQL'})")
    for u, s, t, fact, vec, when in (("r1", "vw", "al", "Vaultwarden runs on altair", [1, 0, 0], "2025-01-01T00:00:00Z"),
                                     ("r2", "vw", "al", "Vaultwarden is hosted on altair", [0.99, 0.05, 0], "2026-01-01T00:00:00Z"),
                                     ("r3", "al", "vw", "altair hosts Vaultwarden", [0.98, 0.1, 0], "2025-06-01T00:00:00Z"),
                                     ("r4", "vw", "al", "Vaultwarden is backed up from altair", [0.2, 0.9, 0], "2025-01-01T00:00:00Z"),
                                     ("r5", "vw", "pg", "Vaultwarden uses PostgreSQL 14", [0, 0, 1], "2025-01-01T00:00:00Z"),
                                     ("r6", "vw", "pg", "Vaultwarden uses PostgreSQL 16", [0, 0, 1], "2026-01-01T00:00:00Z")):
        g.query("MATCH (a:Entity {uuid:$s}), (b:Entity {uuid:$t}) CREATE (a)-[:RELATES_TO {uuid:$u, name:'RUNS_ON', fact:$f, valid_at:$w, "
                "created_at:$w, fact_embedding: vecf32($v)}]->(b)", {"s": s, "t": t, "u": u, "f": fact, "v": vec, "w": when})
    yield name
    c.delete_graph(name)
    dbm.backend.cache_clear()


@needs_falkor
def test_the_redundancy_pass_keeps_the_newest_repeat(client, repeated):  # noqa: F811
    from mimirsynth.models import Proposal
    from mimirsynth.store import _factory
    assert client.post("/api/brains", json={"slug": "cu4", "name": "CU4", "graph_name": repeated}).status_code == 201
    s = client.get("/api/brains/cu4/curator/settings").json()
    assert s["passes"] == {"contradictions": True, "redundancy": False, "obsolescence": False, "noise": False, "archive": False, "distil": False}  # off until an administrator turns it on
    pv = client.post("/api/brains/cu4/curator/preview?pass=redundancy").json()
    assert pv["count"] == 1                                                                     # PostgreSQL 14 / 16 is a change, not a repeat
    f = pv["findings"][0]
    assert f["keep"]["uuid"] == "r2" and sorted(x["uuid"] for x in f["replace"]) == ["r1", "r3"]
    client.put("/api/brains/cu4/curator/settings", json={"enabled": True, "passes": {"contradictions": False, "redundancy": True}})
    client.post("/api/brains/cu4/curator/run")
    run = client.get("/api/brains/cu4/curator/runs").json()["items"][0]
    assert run["status"] == "done" and run["findings"] == {"redundancy": 1} and len(run["proposals"]) == 1
    with _factory()() as db:
        p = db.get(Proposal, run["proposals"][0])
        assert p.category == "curator.redundancy" and p.name.startswith("Curador: repite") and sorted(c["supersedes"] for c in p.claims) == ["r1", "r3"]
    assert client.post("/api/brains/cu4/curator/preview?pass=redundancy").json()["count"] == 0     # pending: not proposed twice


@needs_falkor
def test_the_obsolescence_pass_proposes_facts_past_their_shelf_life(client, repeated, monkeypatch):  # noqa: F811
    from mimirsynth import ingest
    from mimirsynth.models import Proposal
    from mimirsynth.store import _factory
    assert client.post("/api/brains", json={"slug": "cu5", "name": "CU5", "graph_name": repeated}).status_code == 201
    assert client.post("/api/brains/cu5/curator/preview?pass=obsolescence").json()["count"] == 0          # no shelf life: nothing
    client.post("/api/brains/cu5/vocab/relations", json={"name": "RunsOn", "description": "Dónde corre algo", "shelf_life_days": 365})
    pv = client.post("/api/brains/cu5/curator/preview?pass=obsolescence").json()
    olds = sorted(f["replace"][0]["uuid"] for f in pv["findings"])
    assert olds == ["r1", "r3", "r4", "r5"] and all(f["keep"] is None for f in pv["findings"])           # the 2026 ones are within it
    assert pv["findings"][0]["why"].startswith("not confirmed since")
    client.put("/api/brains/cu5/curator/settings", json={"enabled": True, "batch": 10, "passes": {"contradictions": False, "obsolescence": True}})
    client.post("/api/brains/cu5/curator/run")
    run = client.get("/api/brains/cu5/curator/runs").json()["items"][0]
    assert run["findings"] == {"obsolescence": 4} and len(run["proposals"]) == 4
    with _factory()() as db:
        p = db.get(Proposal, run["proposals"][0])
        assert p.category == "curator.obsolescence" and p.name.startswith("Curador: sin confirmar") and p.claims[0]["verdict"] == "replaces"
    monkeypatch.setattr(ingest, "enabled", lambda: False)                                    # no LLM: it still applies
    client.post(f"/api/brains/cu5/proposals/{p.id}/approve", json={})
    ingest.ingest_proposal(p.id)
    gone = p.claims[0]["supersedes"]
    from mimirsynth import db as dbm
    assert dbm.backend().graph(repeated).query("MATCH ()-[r:RELATES_TO {uuid:$u}]->() RETURN r.invalid_at", {"u": gone}).result_set[0][0]


def test_the_noise_rules_are_conservative():
    nr = K.noise_reason
    assert nr({"source": "Vaultwarden", "target": "it", "name": "RUNS_ON", "fact": "Vaultwarden runs on it"}, []) == "one end is a placeholder, not a thing of the world"
    assert nr({"source": "El grafo", "target": "Vaultwarden", "name": "MENTIONS", "fact": "El grafo menciona a Vaultwarden"}, []).startswith("it is about the memory")
    assert nr({"source": "web01", "target": "Node", "name": "USES", "fact": "web01 uses Node 20 to build the frontend"}, []) is None   # Node.js, not a graph node
    assert nr({"source": "Vaultwarden", "target": "altair", "name": "RELATES_TO", "fact": "Vaultwarden is related to altair"}, []).startswith("a generic relation")
    assert nr({"source": "Vaultwarden", "target": "altair", "name": "RELATES_TO", "fact": "Vaultwarden backups are copied nightly to altair storage"}, []) is None
    moved = {"source": "Vaultwarden", "target": "altair", "name": "MOVED_TO", "fact": "Vaultwarden was moved to altair"}
    assert nr(moved, [{"fact": "Vaultwarden runs on altair"}]).startswith("a change told as an event")
    assert nr(moved, []) is None                                                              # the only trace of the change: kept
    assert nr({**moved, "fact": "Vaultwarden se migró a altair"}, [{"fact": "Vaultwarden corre en altair"}]) is not None


def test_a_generic_relation_is_judged_by_its_text():
    """Issue 325: on a real brain the generic rule flagged facts whose text carried the information."""
    rule = lambda s, t, fact: K.noise_rule({"source": s, "target": t, "name": "RelatesTo", "fact": fact}, [])
    assert rule("Plex LXC150", "Plex", "Plex LXC150 en 1.43.5.11079 (fix 1.43.3.10861)") is None                    # a version
    assert rule("Vaultwarden", "Epsilon", "Epsilon ya no aloja Vaultwarden") is None                                 # a negation
    assert rule("claude-home", "Epsilon", "claude-home is not hosted on Epsilon.") is None
    assert rule("canal GitHub", "GitHub", "el canal es GitHub (PRs con etiqueta ready-for-review)") is None          # an identifier
    assert rule("Vaultwarden", "altair", "Vaultwarden runs there since March") is None                               # a date
    assert rule("Vaultwarden", "altair", "Vaultwarden is related to altair") == "generic"                            # plain filler
    assert rule("Vaultwarden", "altair", "Vaultwarden está relacionado con altair") == "generic"
    assert K.noise_reason({"source": "Vaultwarden", "target": "altair", "name": "RelatesTo", "fact": "Vaultwarden is related to altair"},
                          []) == K.NOISE_RULES["generic"]


@needs_falkor
def test_the_noise_pass_and_the_stop_on_a_coverage_drop(client, repeated, monkeypatch):  # noqa: F811
    from datetime import date, datetime, timedelta, timezone
    from mimirsynth import db as dbm
    from mimirsynth.config import settings
    from mimirsynth.models import Brain, CuratorRun, HealthRun, Notification, Proposal, User
    from mimirsynth.store import _factory
    g = dbm.backend().graph(repeated)
    g.query("MATCH (a:Entity {uuid:'vw'}) CREATE (a)-[:RELATES_TO {uuid:'nz', name:'RELATES_TO', fact:'Vaultwarden is related to it', "
            "created_at:'2026-01-01T00:00:00Z'}]->(:Entity {uuid:'it', name:'it'})")
    assert client.post("/api/brains", json={"slug": "cu6", "name": "CU6", "graph_name": repeated}).status_code == 201
    pv = client.post("/api/brains/cu6/curator/preview?pass=noise").json()
    assert [f["replace"][0]["uuid"] for f in pv["findings"]] == ["nz"]
    assert pv["by_rule"] == {"placeholder": 1} and pv["findings"][0]["rule"] == "placeholder"   # grouped by rule (issue 325)
    client.put("/api/brains/cu6/curator/settings", json={"enabled": True, "batch": 10, "passes": {"contradictions": False, "noise": True}})
    client.post("/api/brains/cu6/curator/run")
    run = client.get("/api/brains/cu6/curator/runs").json()["items"][0]
    assert run["findings"] == {"noise": 1} and len(run["proposals"]) == 1
    with _factory()() as db:
        p = db.get(Proposal, run["proposals"][0])
        assert p.category == "curator.noise" and p.name.startswith("Curador: ruido") and p.decision["curator"]["rule"] == "placeholder"
        bid, uid = p.brain_id, db.query(User).first().id
        today = date.today()
        db.add(HealthRun(brain_id=bid, day=today - timedelta(days=1), status="done", metrics={"coverage_items": {"a": 1, "b": 1}},
                         finished_at=datetime.now(timezone.utc) - timedelta(days=1)))
        db.add(HealthRun(brain_id=bid, day=today, status="done", metrics={"coverage_items": {"a": 1, "b": 0}}))
        p.status, p.reviewed_at, p.reviewer_id, p.review_kind = "ingested", datetime.now(timezone.utc), uid, "human"
        db.query(CuratorRun).filter(CuratorRun.brain_id == bid).delete()
        db.commit()
    monkeypatch.setattr(settings, "health_coverage_drop", 0.05)
    client.post("/api/brains/cu6/curator/run")
    run = client.get("/api/brains/cu6/curator/runs").json()["items"][0]
    assert run["status"] == "stopped" and "100 % al 50 %" in run["error"] and run["proposals"] == []
    with _factory()() as db:
        assert db.query(Notification).filter(Notification.event == "curator.stopped", Notification.brain_id == bid).count() == 1
