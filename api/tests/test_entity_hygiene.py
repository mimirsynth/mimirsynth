"""Entity hygiene (#467): names that are a detail of a fact never become entities, the type corrector can fold a name that is not an
entity into the one it belongs to, duplicate names ignore dots and the prefixes the pack declares equivalent, and bulk apply waits until
the decider's confidence has been measured against the curators' own decisions."""
import asyncio
import os
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from test_control import _as, client  # noqa: F401  (first: it sets the test environment before mimirsynth reads its settings)

from mimirsynth import decider, hygiene, retype
from mimirsynth.graphapi import _entity_key, duplicates, equivalent_prefixes
from mimirsynth.main import app
from mimirsynth.models import Brain, RetypeSuggestion
from mimirsynth.store import _factory

FALKOR = os.environ.get("MIMIRSYNTH_TEST_FALKOR")
GRAPH = "zz-test-hygiene"


# --- what never becomes an entity -------------------------------------------------------------------

@pytest.mark.parametrize("name,kind", [
    ("--help", "flag"), ("-config-file flag", "flag"), ("tool --help flag", "flag"), ("--dry-run option", "flag"),
    ("SectionVMInfo.uptime", "field"), ("config.max_retries", "field"),
    ("utils/secrets.py", "path"), ("llm_client/openai_base_client.py", "path"), ("/etc/nginx/nginx.conf", "path"), ("README.md", "path"),
    ("docker-compose.yml", "path"), ("https://example.org/a", "url"), ("www.example.org", "url"),
    ("1 October 2026", "date"), ("2026-10-01", "date"), ("octubre de 2026", "date"), ("May 2026", "date"), ("01/10/2026", "date"),
    ("2026/10/01", "date"), ("1st of October 2026", "date"), ("el 1 de octubre", "date"), ("01.10.2026", "date"),
    ("self.db", "field"), ("os.path.join()", "field"), ("obj.maxRetries", "field"), ("src/", "path"), ("example.org/path", "url"),
    ("tool -v flag", "flag"),
    ("sync push from A to B", "clause"), ("budget limit of 5 dollars a month", "clause"), ("cómo restablecer la contraseña del usuario", "clause"),
])
def test_details_of_a_fact_are_not_entities(name, kind):
    assert hygiene.kind(name) == kind


@pytest.mark.parametrize("name", [
    "api.example.com", "Node.js", "Vue.js", "ASP.NET", "TCP/IP", "AC/DC", "Ministry of Health and Social Services", "iPhone 15 Pro Max case",
    "Debian 13", "Web-Vault 2026.4.1", "VM 201", "ProtectHome=yes", "May", "March", "Mailer", "Wi-Fi", "10.0.0.4", "ups@10.0.0.4", "", None,
    # products written like files, namespaces, units, and proper names that start with a particle (reviews of #467)
    "three.js", "next.js", "node.js", "Newtonsoft.Json", "System.Text.Json", "Microsoft.AspNetCore", "Microsoft.AspNetCore.Mvc", "pandas.DataFrame",
    "nginx.service", "docker.socket", "backup.timer", "docs.rs", "bun.sh", "AC -DC", "Jean -Luc", "Plan -B", "Ryzen 7 -X",
    "el Ministerio de Sanidad y Consumo de España", "de la Fuente y García Abogados", "de Havilland Aircraft Company of Canada",
    "la Caixa Bank foundation of Spain", "3.12.10", "2.1.10", "1.26.10", "user.email", "gpt-4o-mini",
])
def test_names_that_may_be_entities_are_kept(name):
    assert hygiene.kind(name) is None


def test_extraction_drops_them_before_they_are_written_and_counts_them(monkeypatch):
    import graphiti_core.graphiti as gg
    nodes = [SimpleNamespace(uuid="a", name="tool"), SimpleNamespace(uuid="b", name="tool --help flag"),
             SimpleNamespace(uuid="c", name="utils/secrets.py"), SimpleNamespace(uuid="d", name="Mailer")]

    async def extract(*args, **kwargs):
        return list(nodes), {"a": [0], "b": [0], "c": [0], "d": [0]}
    monkeypatch.setattr(gg, "extract_nodes", extract)
    assert hygiene.install() and hygiene.install()                  # once per process: a second call does not wrap it again
    assert getattr(gg.extract_nodes, "_mimirsynth_hygiene", False)

    async def run():
        counts: dict = {}
        token = hygiene.dropped.set(counts)
        try:
            kept, index = await gg.extract_nodes(None, None, [])
        finally:
            hygiene.dropped.reset(token)
        return kept, index, counts
    kept, index, counts = asyncio.run(run())
    assert [n.name for n in kept] == ["tool", "Mailer"] and set(index) == {"a", "d"} and counts == {"flag": 1, "path": 1}


def test_a_graphiti_without_extract_nodes_is_left_alone(monkeypatch):
    import graphiti_core.graphiti as gg
    monkeypatch.delattr(gg, "extract_nodes")
    assert hygiene.install() is False


# --- duplicate names --------------------------------------------------------------------------------

def test_dots_and_the_equivalent_prefixes_of_the_pack_make_one_group(client, monkeypatch):  # noqa: F811
    assert _entity_key("VM 201") == _entity_key("VM201") == _entity_key("VM.201")
    assert _entity_key("printer 10.0.1.12") != _entity_key("printer 10.0.11.2")              # a dot between digits is part of an address
    assert _entity_key("CT147") != _entity_key("LXC147")                                  # without a pack, two names
    prefixes = equivalent_prefixes({"preset": {"name": "infrastructure"}})
    assert prefixes == {"lxc": "ct", "qemu": "vm"}
    assert _entity_key("CT147", prefixes) == _entity_key("LXC 147", prefixes) == _entity_key("lxc-147", prefixes)
    assert _entity_key("Lxcfs", prefixes) == "lxcfs"                                      # only a prefix followed by its number
    assert equivalent_prefixes({"preset": {"name": "personal-family"}}) == {} and equivalent_prefixes(None) == {}
    assert client.post("/api/brains", json={"slug": "hyg1", "name": "H1"}).status_code == 201
    assert client.post("/api/brains/hyg1/ontology/preset/infrastructure").status_code == 200

    class G:
        def query(self, q, params=None):
            return [{"uuid": u, "name": n, "labels": [], "degree": 1} for u, n in (("1", "CT147"), ("2", "LXC147"), ("3", "VM 201"), ("4", "VM201"), ("5", "Mailer"))]
    monkeypatch.setattr("mimirsynth.graphapi.rows", lambda res: res)
    with _factory()() as db:
        bid = db.scalar(select(Brain.id).where(Brain.slug == "hyg1"))
        _, dups, _ = duplicates(G(), db, bid)
    assert sorted(sorted(m["name"] for m in d["members"]) for d in dups) == [["CT147", "LXC147"], ["VM 201", "VM201"]]


def test_the_packs_offer_software_and_model():
    from mimirsynth.ontology import presets
    p = presets()
    infra = [t["name"] for t in p["infrastructure"]["entity_types"]]
    assert {"Software", "Model"} <= set(infra) and p["infrastructure"]["version"] == 3
    assert "Model" in [t["name"] for t in p["software-knowledge"]["entity_types"]] and p["software-knowledge"]["version"] == 2


# --- the corrector: not an entity → fold into X ------------------------------------------------------

def _scan_brain(client, slug, monkeypatch, ents, near, answers):  # noqa: F811
    assert client.post("/api/brains", json={"slug": slug, "name": slug}).status_code == 201
    client.post(f"/api/brains/{slug}/ontology/preset/infrastructure")
    client.post("/api/decision-engines", json={"name": f"dec-{slug}", "base_url": "http://o/v1", "model": "tev1"})
    monkeypatch.setattr(retype, "_candidates", lambda g, prof, skip, limit: [e for e in ents if e["uuid"] not in skip])
    monkeypatch.setattr(retype, "_facts", lambda g, u: ["tool accepts --help"])
    monkeypatch.setattr(retype, "neighbours", lambda g, u: near.get(u, []))
    monkeypatch.setattr(retype, "graph", lambda name: None)
    asked = []

    def fake(base, model, key, state, q, opts, **k):
        asked.append((q, opts))
        return answers(q, opts, state)
    monkeypatch.setattr(decider, "decide", fake)
    assert client.post(f"/api/brains/{slug}/retype/scan", json={"limit": 10}).status_code == 202
    return asked


def test_a_doubtful_entity_is_offered_the_neighbour_it_belongs_to(client, monkeypatch):  # noqa: F811
    ents = [{"uuid": "f", "name": "-config-file flag", "type": "Object", "summary": ""},       # doubtful by its name
            {"uuid": "o", "name": "Odd thing", "type": "Object", "summary": ""},                # doubtful by the decider, no neighbours
            {"uuid": "n", "name": "Lone flag", "type": "Object", "summary": ""}]                # doubtful, the decider picks «none of them»
    near = {"f": [{"uuid": "t", "name": "tool", "facts": 3}, {"uuid": "p", "name": "pro\nject", "facts": 1}],
            "n": [{"uuid": "t", "name": "tool", "facts": 1}]}

    def answers(q, opts, state):
        if "entidad concreta" in q:
            return {"index": 1, "letter": "B", "prob": 0.9, "probs": {}}
        if "no parece una entidad propia" in q:
            return {"index": 0 if "-config-file" in state else len(opts) - 1, "letter": "A", "prob": 0.8, "probs": {}}
        return {"index": 0, "letter": "A", "prob": 0.9, "probs": {}}
    asked = _scan_brain(client, "hyg2", monkeypatch, ents, near, answers)
    assert [o for q, o in asked if "no parece" in q][0] == ["tool", "pro ject", "De ninguna de ellas"]   # on one line
    assert all("-config-file" not in q for q, _ in asked if "no parece" in q)                 # the name is in the state, not the question
    assert sum(1 for q, _ in asked if "no parece" in q) == 2                                   # «Odd thing» has nowhere to go: not asked
    items = {i["name"]: i for i in client.get("/api/brains/hyg2/retype", params={"status": "doubtful"}).json()["items"]}
    assert items["-config-file flag"]["fold"] == {"uuid": "t", "name": "tool", "confidence": 0.8}
    assert items["Odd thing"]["fold"] is None and items["Lone flag"]["fold"] is None


def test_folding_is_refused_outside_its_neighbours_and_for_a_reader(client, monkeypatch):  # noqa: F811
    from mimirsynth import deps
    assert client.post("/api/brains", json={"slug": "hyg3", "name": "H3"}).status_code == 201
    with _factory()() as db:
        bid = db.scalar(select(Brain.id).where(Brain.slug == "hyg3"))
        s = RetypeSuggestion(brain_id=bid, entity_uuid="f", name="-config-file flag", status="doubtful", reason="opción", fold_uuid="t", fold_name="tool")
        p = RetypeSuggestion(brain_id=bid, entity_uuid="x", name="Plex", status="pending", suggested_type="Service", confidence=0.9)
        db.add_all([s, p])
        db.commit()
        sid, pid = s.id, p.id

    class G:
        def query(self, q, params=None):
            return [{"uuid": "t", "name": "tool", "facts": 2}] if "count(r) AS facts" in q else []
    monkeypatch.setattr(deps, "graph", lambda name: G())
    monkeypatch.setattr(retype, "rows", lambda res: res)
    assert client.get(f"/api/brains/hyg3/retype/{sid}/neighbours").json() == {"items": [{"uuid": "t", "name": "tool", "facts": 2}], "proposed": "t", "moves": 0}
    assert client.post(f"/api/brains/hyg3/retype/{sid}/fold", json={"into": "elsewhere"}).status_code == 409
    assert client.post(f"/api/brains/hyg3/retype/{pid}/fold", json={}).status_code == 404               # not a doubtful one
    assert client.post(f"/api/brains/hyg3/retype/{sid}/fold", json={}).status_code == 404               # the entity is no longer in the graph
    client.put("/api/brains/hyg3/members", json={"email": "rory@x.com", "role": "curator"})
    _as("rory@x.com", "Rory")
    assert client.post(f"/api/brains/hyg3/retype/{sid}/fold", json={}).status_code == 403              # the corrector is the administrator's
    app.dependency_overrides.clear()


def test_a_fold_is_taken_once_and_one_that_fails_halfway_can_be_undone(client, monkeypatch):  # noqa: F811
    from mimirsynth import deps, entity_types
    from mimirsynth.models import VocabOp
    assert client.post("/api/brains", json={"slug": "hyg5", "name": "H5"}).status_code == 201
    with _factory()() as db:
        bid = db.scalar(select(Brain.id).where(Brain.slug == "hyg5"))
        rows_ = [RetypeSuggestion(brain_id=bid, entity_uuid=f"f{n}", name=f"flag {n}", status="doubtful", reason="opción", fold_uuid="t", fold_name="tool")
                 for n in range(3)]
        db.add_all(rows_)
        db.commit()
        ids = [r.id for r in rows_]

    class G:
        """Moves one edge, then fails on the tombstone: the first fold is left halfway."""
        def __init__(self, fail_on=None):
            self.fail_on = fail_on

        def query(self, q, params=None):
            if self.fail_on and self.fail_on in q:
                raise ConnectionError("graph down")
            if "count(r) AS facts" in q:
                return [{"uuid": "t", "name": "tool", "facts": 2}]
            if "RETURN n.name AS name" in q:
                return [{"name": "flag"}]
            if "RETURN r.uuid AS u" in q:
                return [{"u": "e1"}]
            if "RETURN k.name AS name" in q:
                return [{"name": "tool", "aliases": []}]
            return []
    monkeypatch.setattr(retype, "rows", lambda res: res)
    monkeypatch.setattr(entity_types, "rows", lambda res: res)
    monkeypatch.setattr(entity_types, "snapshot_graph", lambda name, tag="": "_snap_x")
    monkeypatch.setattr(deps, "graph", lambda name: G("SET d:Merged"))
    r = client.post(f"/api/brains/hyg5/retype/{ids[0]}/fold", json={})
    assert r.status_code == 500 and "Fusionadas" in r.json()["detail"]
    with _factory()() as db:
        s = db.get(RetypeSuggestion, ids[0])
        op = db.get(VocabOp, s.op_id)
        assert s.status == "folded" and op.kind == "entity.merge" and op.detail["snapshot"] == "_snap_x" and op.detail["entries"][0]["moved"]
    monkeypatch.setattr(entity_types, "snapshot_graph", lambda name, tag="": (_ for _ in ()).throw(ConnectionError("no copy")))
    r = client.post(f"/api/brains/hyg5/retype/{ids[1]}/fold", json={})                       # nothing done: back to doubtful
    assert r.status_code == 500
    with _factory()() as db:
        assert db.get(RetypeSuggestion, ids[1]).status == "doubtful" and db.get(RetypeSuggestion, ids[1]).op_id is None
        db.get(RetypeSuggestion, ids[2]).status = "folding"                                 # another administrator is folding it
        db.commit()
    assert client.post(f"/api/brains/hyg5/retype/{ids[2]}/fold", json={}).status_code == 404


def test_the_facts_between_both_ends_become_facts_of_the_entity(monkeypatch):
    calls = []

    class G:
        def query(self, q, params=None):
            calls.append(q)
            return [{"u": "loop1"}] if "(d)-[r:RELATES_TO]->(k) RETURN" in q else []
    monkeypatch.setattr(retype, "rows", lambda res: res)
    entry = {"moved": {"RELATES_TO:out": ["x"]}}
    retype._keep_between(G(), "t", "f", entry)
    assert entry["moved"]["RELATES_TO:out"] == ["x", "loop1"] and "RELATES_TO:in" not in entry["moved"]
    assert any("CREATE (k)-[r2:RELATES_TO]->(k)" in q for q in calls)


def test_ignoring_a_group_uses_the_prefixes_of_the_pack(client):  # noqa: F811
    from mimirsynth.models import VocabAlias
    assert client.post("/api/brains", json={"slug": "hyg6", "name": "H6"}).status_code == 201
    client.post("/api/brains/hyg6/ontology/preset/infrastructure")
    with _factory()() as db:
        bid = db.scalar(select(Brain.id).where(Brain.slug == "hyg6"))
        db.add(VocabAlias(brain_id=bid, kind="dup_ignore", alias="lxc147", canonical=""))           # saved before the prefixes
        db.commit()
    assert client.delete("/api/brains/hyg6/vocab/duplicates/ignore", params={"key": "ct147"}).status_code == 200
    with _factory()() as db:
        assert db.scalars(select(VocabAlias).where(VocabAlias.brain_id == bid, VocabAlias.kind == "dup_ignore")).all() == []
    assert client.post("/api/brains/hyg6/vocab/duplicates/ignore", json={"key": "LXC 147"}).status_code == 201
    with _factory()() as db:
        assert [a.alias for a in db.scalars(select(VocabAlias).where(VocabAlias.brain_id == bid, VocabAlias.kind == "dup_ignore"))] == ["ct147"]


def test_a_pack_with_a_software_type_keeps_versions_in_names():
    with_sw = retype.profile({"preset": {"name": "infrastructure"}, "entity_types": [{"name": "Software", "description": "x"}]})
    without = retype.profile({"preset": {"name": "infrastructure"}, "entity_types": [{"name": "Service", "description": "x"}]})
    assert "version" not in with_sw["rules"] and "version" in without["rules"]
    assert retype.doubtful_reason("Web-Vault 2026.4.1", with_sw["rules"]) == "" and retype.doubtful_reason("Web-Vault 2026.4.1", without["rules"])


# --- bulk apply, calibrated ----------------------------------------------------------------------------

def test_bulk_apply_waits_for_twenty_decisions_taken_one_by_one(client, monkeypatch):  # noqa: F811
    assert client.post("/api/brains", json={"slug": "hyg4", "name": "H4"}).status_code == 201
    client.post("/api/brains/hyg4/ontology/preset/infrastructure")
    monkeypatch.setattr(retype, "_set_label", lambda g, u, old, new: None)
    with _factory()() as db:
        bid = db.scalar(select(Brain.id).where(Brain.slug == "hyg4"))
        rows_ = [RetypeSuggestion(brain_id=bid, entity_uuid=f"e{n}", name=f"Thing {n}", current_type="Object", suggested_type="Service",
                                  confidence=0.95 if n % 2 else 0.6, status="pending") for n in range(retype.CALIBRATION + 4)]
        db.add_all(rows_)
        db.commit()
        ids = [r.id for r in rows_]
    url = "/api/brains/hyg4/retype"
    r = client.post(f"{url}/apply", json={"ids": ids[-2:]})
    assert r.status_code == 409 and str(retype.CALIBRATION) in r.json()["detail"]
    for i in ids[:retype.CALIBRATION - 4]:
        assert client.post(f"{url}/apply", json={"ids": [i]}).json()["applied"] == 1                   # one by one is always allowed
    for i in ids[retype.CALIBRATION - 4:retype.CALIBRATION - 1]:
        assert client.post(f"{url}/reject", json={"ids": [i]}).json()["rejected"] == 1
    assert client.post(f"{url}/reject", json={"ids": ids[-4:-2]}).json()["rejected"] == 2             # rejected in bulk: not counted
    cal = client.get(url, params={"min_conf": 0.9}).json()["calibration"]
    assert cal["decided"] == retype.CALIBRATION - 1 and cal["needed"] == retype.CALIBRATION
    assert client.post(f"{url}/apply", json={"ids": ids[-2:]}).status_code == 409
    assert client.post(f"{url}/{ids[0]}/revert").status_code == 200                                    # a revert counts as a «no»
    assert client.post(f"{url}/reject", json={"ids": [ids[retype.CALIBRATION - 1]]}).json()["rejected"] == 1
    cal = client.get(url, params={"min_conf": 0.9}).json()["calibration"]
    above = [n for n in range(retype.CALIBRATION) if n % 2]                                             # the ones at 0.95
    kept = [n for n in above if n < retype.CALIBRATION - 4 and n != 0]
    assert cal["decided"] == retype.CALIBRATION and cal["above"] == len(above) and cal["precision"] == round(len(kept) / len(above), 3)
    assert client.post(f"{url}/apply", json={"ids": ids[-2:]}).json()["applied"] == 2
    # applied as another type: decided, but the decider missed; it is shown as the type chosen and undone to the one it had
    with _factory()() as db:
        x = RetypeSuggestion(brain_id=bid, entity_uuid="ex", name="Thing x", current_type="Object", suggested_type="Service", confidence=0.95, status="pending")
        db.add(x)
        db.commit()
        xid = x.id
    assert client.post(f"{url}/{xid}/apply-as", json={"type": "Host"}).status_code == 200
    after = client.get(url, params={"min_conf": 0.9}).json()["calibration"]
    assert after["above"] == cal["above"] + 1 and after["precision"] == round(len(kept) / (len(above) + 1), 3)
    shown = {i["id"]: i for i in client.get(url, params={"status": "applied"}).json()["items"]}[xid]
    assert shown["suggested_type"] == "Service" and shown["chosen_type"] == "Host"
    labels = []
    monkeypatch.setattr(retype, "_set_label", lambda g, u, old, new: labels.append((old, new)))
    assert client.post(f"{url}/{xid}/revert").status_code == 200 and labels == [("Host", "Object")]


def test_rejecting_a_doubtful_one_says_nothing_of_the_decider(client, monkeypatch):  # noqa: F811
    assert client.post("/api/brains", json={"slug": "hyg7", "name": "H7"}).status_code == 201
    client.post("/api/brains/hyg7/ontology/preset/infrastructure")
    with _factory()() as db:
        bid = db.scalar(select(Brain.id).where(Brain.slug == "hyg7"))
        r = RetypeSuggestion(brain_id=bid, entity_uuid="d", name="utils/secrets.py", current_type="Object", suggested_type="Service",
                             confidence=0.9, status="pending")                                   # pending, shown as doubtful by its name
        db.add(r)
        db.commit()
        rid = r.id
    assert client.post("/api/brains/hyg7/retype/reject", json={"ids": [rid]}).json()["rejected"] == 1
    assert client.get("/api/brains/hyg7/retype").json()["calibration"]["decided"] == 0


# --- against the graph ---------------------------------------------------------------------------------

@pytest.mark.skipif(not FALKOR, reason="needs a disposable FalkorDB (MIMIRSYNTH_TEST_FALKOR=host)")
def test_folding_moves_the_facts_keeps_the_name_as_an_alias_and_is_undone(client, monkeypatch):  # noqa: F811
    from mimirsynth import db as dbm
    from mimirsynth.config import settings
    monkeypatch.setattr(settings, "falkor_host", FALKOR)
    dbm.backend.cache_clear()
    c = dbm.backend()
    if GRAPH in c.list_graphs():
        c.delete_graph(GRAPH)
    g = c.graph(GRAPH)
    g.query("CREATE (t:Entity:Service {uuid:'t', name:'tool'}), (f:Entity {uuid:'f', name:'tool --help flag'}), (u:Entity {uuid:'u', name:'Ops'}),"
            " (t)-[:RELATES_TO {uuid:'r1', name:'HAS_OPTION', fact:'tool has a --help flag'}]->(f),"
            " (u)-[:RELATES_TO {uuid:'r2', name:'USES', fact:'Ops runs tool with --help'}]->(f)")
    try:
        assert client.post("/api/brains", json={"slug": "hygg", "name": "HG", "graph_name": GRAPH}).status_code == 201
        with _factory()() as db:
            bid = db.scalar(select(Brain.id).where(Brain.slug == "hygg"))
            s = RetypeSuggestion(brain_id=bid, entity_uuid="f", name="tool --help flag", status="doubtful", reason="opción", fold_uuid="t", fold_name="tool")
            db.add(s)
            db.commit()
            sid = s.id
        assert {x["uuid"] for x in client.get(f"/api/brains/hygg/retype/{sid}/neighbours").json()["items"]} == {"t", "u"}
        assert client.get(f"/api/brains/hygg/retype/{sid}/neighbours").json()["moves"] == 2
        assert client.post(f"/api/brains/hygg/retype/{sid}/fold", json={}).json()["folded"] == 1
        assert g.query("MATCH (n:Entity {uuid:'f'}) RETURN n").result_set == []                       # no orphan: a Merged tombstone
        # the fact between both ends is now a fact of the tool itself, still found by recall
        assert g.query("MATCH (t:Entity {uuid:'t'})-[r:RELATES_TO {uuid:'r1'}]->(t) RETURN r.fact").result_set
        assert g.query("MATCH (u:Entity {uuid:'u'})-[r:RELATES_TO {uuid:'r2'}]->(t:Entity {uuid:'t'}) RETURN r.fact").result_set
        assert "tool --help flag" in g.query("MATCH (t:Entity {uuid:'t'}) RETURN t.aliases").result_set[0][0]
        assert client.get("/api/brains/hygg/retype", params={"status": "folded"}).json()["items"][0]["op"]
        assert client.post(f"/api/brains/hygg/retype/{sid}/revert").status_code == 200
        assert g.query("MATCH (u:Entity {uuid:'u'})-[r:RELATES_TO {uuid:'r2'}]->(f:Entity {uuid:'f'}) RETURN r.fact").result_set
        assert g.query("MATCH (t:Entity {uuid:'t'})-[r:RELATES_TO {uuid:'r1'}]->(f:Entity {uuid:'f'}) RETURN r.fact").result_set
        assert "tool --help flag" not in (g.query("MATCH (t:Entity {uuid:'t'}) RETURN t.aliases").result_set[0][0] or [])
        assert client.get("/api/brains/hygg/retype", params={"status": "doubtful"}).json()["items"][0]["id"] == sid
    finally:
        c.delete_graph(GRAPH)
        dbm.backend.cache_clear()
