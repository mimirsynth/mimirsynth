"""Superseded episode fragments (#282) and document passages (#286): a fragment of an episode whose facts stopped being true, or a
passage that states such a fact, says so, with what is true now, and goes after the others; the current fact that replaced it joins
the recall even when the question did not bring it."""
import os

import pytest

from test_control import client  # noqa: F401

from mimirsynth import recall as R, shelflife

FALKOR = os.environ.get("MIMIRSYNTH_TEST_FALKOR")
GRAPH = "zz-test-superseded"


def _f(uuid, fact, src, tgt, name, valid, invalid=None, status=None, episodes=()):
    return {"uuid": uuid, "fact": fact, "source_uuid": src, "target_uuid": tgt, "name": name, "valid_at": valid, "invalid_at": invalid,
            "expired_at": invalid, "created_at": valid, "episodes": list(episodes), "status": status or ("invalidated" if invalid else "current")}


OLD = _f("old", "La wiki corre en altair, 10.0.0.5", "wiki", "altair", "RUNS_ON", "2026-01-01T00:00:00Z", "2026-06-01T10:00:00Z", episodes=["ep-old"])
NEW = _f("new", "La wiki corre en vega, 10.0.0.9", "wiki", "vega", "RUNS_ON", "2026-06-01T10:00:00Z", episodes=["ep-new"])
SAME_TIME_ELSEWHERE = _f("printer", "La impresora está en la sala B", "printer", "sala-b", "LOCATED_AT", "2026-06-01T10:00:00Z", episodes=["ep-new"])
OTHER_OF_WIKI = _f("db", "La wiki usa PostgreSQL", "wiki", "postgres", "USES", "2026-02-01T00:00:00Z", episodes=["ep-db"])
LATER_SAME_RELATION = _f("later", "La wiki corre en deneb", "deneb", "wiki", "RUNS_ON", "2026-08-01T00:00:00Z")


def test_the_replacement_shares_an_entity_and_starts_when_the_old_one_stopped():
    assert R.replacements(OLD, [SAME_TIME_ELSEWHERE, OTHER_OF_WIKI, NEW]) == [NEW]           # same time, but no shared entity: not it
    assert R.replacements(OLD, [LATER_SAME_RELATION, NEW]) == [NEW, LATER_SAME_RELATION]   # the same instant first, then the same relation
    assert R.replacements(OLD, [OTHER_OF_WIKI, {**NEW, "status": "invalidated"}]) == []     # what is no longer true replaces nothing


def _chunk(cid, episode, text="texto"):
    return {"id": cid, "name": f"ep {cid}", "text": text, "valid_at": "2026-01-01", "episode_uuid": episode, "similarity": 0.8, "rrf": 0.03}


def test_marking_moves_the_fragment_last_and_puts_the_replacement_first(monkeypatch):
    monkeypatch.setattr(R, "superseded", lambda g, eps, gone, amap=None, entities=(): ([OLD] if "ep-old" in eps else [], {"old": [NEW]}))
    chunks, cur, old, _ = R.mark_superseded([_chunk(1, "ep-old"), _chunk(2, "ep-other")], [dict(OTHER_OF_WIKI)], [], {None: "g"}, {})
    assert [c["id"] for c in chunks] == [2, 1]
    assert chunks[1]["superseded"] == [{"uuid": "old", "fact": OLD["fact"], "invalid_at": OLD["invalid_at"], "replaced_by": [{"uuid": "new", "fact": NEW["fact"]}]}]
    assert [f["uuid"] for f in cur] == ["new", "db"] and cur[0]["replaces"] == OLD["fact"]
    assert [f["uuid"] for f in old] == ["old"]                                              # what the fragment states and is no longer true
    assert cur[0]["similarity"] is None and old[0]["similarity"] is None                     # they join by their link, not by closeness: no number
    ctx = R.build_context(cur + old, chunks, 6000)
    assert "- La wiki corre en vega, 10.0.0.9 (desde 2026-06-01) [sustituye a «La wiki corre en altair, 10.0.0.5»]" in ctx
    assert "> Puede estar superado: «La wiki corre en altair, 10.0.0.5» dejó de ser cierto el 2026-06-01. Ahora: «La wiki corre en vega, 10.0.0.9»." in ctx


def _passage(chunk, text="texto", document=5):
    return {"id": 100 + chunk, "document_id": document, "chunk_idx": chunk, "title": "Wiki de sistemas", "heading_path": "Servicios", "page": None,
            "text": text, "similarity": 0.8, "source_updated_at": "2026-07-15T09:00:00+00:00"}


def test_a_passage_states_a_fact_learned_from_it_or_naming_both_its_ends_but_not_the_update():
    repl = {"old": [NEW]}
    assert R._states(OLD, {"ep-old"}, set(), repl)                         # promoted to memory: the fact was learned from it
    assert R._states(OLD, set(), {"wiki", "altair"}, repl)                 # names the service and the old host
    assert not R._states(OLD, set(), {"wiki", "altair", "vega"}, repl)     # names the new host too: it is the update, not the old decision
    assert not R._states(OLD, set(), {"wiki"}, repl)                       # one end is not enough


def test_a_passage_of_the_old_decision_is_marked_and_goes_after_the_update(monkeypatch):
    old_section, update = _passage(1, "La wiki corre en altair, 10.0.0.5."), _passage(2, "La wiki se movió de altair a vega, 10.0.0.9.")
    seen = {}

    def fake(g, eps, gone, amap=None, entities=()):
        seen["entities"] = set(entities)
        return [OLD], {"old": [NEW]}
    monkeypatch.setattr(R, "superseded", fake)
    monkeypatch.setattr(R, "passage_links", lambda ps, g, b: [(set(), {"wiki", "altair"} | ({"vega"} if "vega" in p["text"] else set())) for p in ps])
    chunks, cur, old, passages = R.mark_superseded([], [], [], {None: "g"}, {}, [old_section, update], {None: 1})
    assert seen["entities"] == {"wiki", "altair", "vega"}
    assert [p["chunk_idx"] for p in passages] == [2, 1] and "superseded" not in passages[0]
    assert passages[1]["superseded"][0]["replaced_by"] == [{"uuid": "new", "fact": NEW["fact"]}]
    assert [f["uuid"] for f in cur] == ["new"] and cur[0]["replaces"] == OLD["fact"] and [f["uuid"] for f in old] == ["old"]
    ctx = R.build_context(cur + old, chunks, 6000, passages)
    assert "### Wiki de sistemas › Servicios · actualizado el 2026-07-15 [doc 5, trozo 1]" in ctx
    assert ctx.index("trozo 2]") < ctx.index("trozo 1]")
    assert "La wiki corre en altair, 10.0.0.5.\n> Puede estar superado: «La wiki corre en altair, 10.0.0.5» dejó de ser cierto el 2026-06-01. Ahora: «La wiki corre en vega, 10.0.0.9»." in ctx


def test_a_lent_brain_that_lends_only_its_documents_is_not_checked(monkeypatch):
    monkeypatch.setattr(R, "superseded", lambda *a, **k: ([OLD], {"old": [NEW]}))
    monkeypatch.setattr(R, "passage_links", lambda ps, g, b: [(set(), {"wiki", "altair"}) for _ in ps])
    lent = {**_passage(1), "origin": "otro"}
    _, cur, _, passages = R.mark_superseded([], [], [], {None: "g"}, {}, [lent], {None: 1})
    assert "superseded" not in passages[0] and cur == []


def test_a_promoted_passage_is_linked_to_its_episode(client):  # noqa: F811
    from mimirsynth.models import Brain, Proposal, User
    from mimirsynth.store import _factory
    client.post("/api/brains", json={"slug": "promovido", "name": "Promovido"})
    with _factory()() as db:
        bid, uid = db.query(Brain).filter_by(slug="promovido").one().id, db.query(User).first().id
        for desc, ep in (("documento 5 · trozo 1: «Wiki»", "ep-1"), ("documento 5 · trozo 12: «Wiki»", "ep-12"), ("documento 51 · trozo 1: «Otra»", "ep-51"),
                         ("documento 5 · trozo 2: «Wiki»", None)):
            db.add(Proposal(brain_id=bid, author_id=uid, name="p", body="b", status="ingested" if ep else "pending", source_description=desc, episode_uuid=ep))
        db.commit()
    assert R.promoted_episodes(bid, {(5, 1), (5, 2)}) == {(5, 1): {"ep-1"}}
    assert R.promoted_episodes(bid, set()) == {}


def test_a_replacement_already_in_the_result_is_marked_not_repeated(monkeypatch):
    monkeypatch.setattr(R, "superseded", lambda g, eps, gone, amap=None, entities=(): ([], {"old": [NEW]}))
    _, cur, _, _ = R.mark_superseded([], [dict(NEW)], [dict(OLD)], {None: "g"}, {})
    assert [f["uuid"] for f in cur] == ["new"] and cur[0]["replaces"] == OLD["fact"]


def test_a_graph_that_fails_leaves_the_recall_as_it_was(monkeypatch):
    monkeypatch.setattr(R, "superseded", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("FalkorDB caído")))
    p = _passage(4)
    chunks, cur, old, passages = R.mark_superseded([_chunk(1, "ep-old")], [dict(NEW)], [], {None: "g"}, {}, [p], {None: 1})
    assert [c["id"] for c in chunks] == [1] and "superseded" not in chunks[0] and [f["uuid"] for f in cur] == ["new"] and old == []
    assert passages == [p] and "superseded" not in p


@pytest.fixture()
def falkor(monkeypatch):
    from mimirsynth import db as dbm
    from mimirsynth.config import settings
    monkeypatch.setattr(settings, "falkor_host", FALKOR)
    dbm.backend.cache_clear()
    c = dbm.backend()
    if GRAPH in c.list_graphs():
        c.delete_graph(GRAPH)
    g = c.graph(GRAPH)
    for f in (OLD, NEW, SAME_TIME_ELSEWHERE, OTHER_OF_WIKI):
        g.query("MERGE (a:Entity {uuid:$s, name:$s}) MERGE (b:Entity {uuid:$t, name:$t}) "
                "CREATE (a)-[:RELATES_TO {uuid:$u, name:$n, fact:$fact, valid_at:$v, invalid_at:$i, expired_at:$i, created_at:$v, episodes:$eps}]->(b)",
                {"s": f["source_uuid"], "t": f["target_uuid"], "u": f["uuid"], "n": f["name"], "fact": f["fact"], "v": f["valid_at"],
                 "i": f["invalid_at"], "eps": f["episodes"]})
    yield g
    c.delete_graph(GRAPH)
    dbm.backend.cache_clear()


@pytest.mark.skipif(not FALKOR, reason="necesita un FalkorDB desechable (MIMIRSYNTH_TEST_FALKOR=host)")
def test_the_graph_says_what_an_episode_stated_and_what_replaced_it(falkor):
    found, repl = R.superseded(GRAPH, {"ep-old", "ep-db"}, [])
    assert [f["uuid"] for f in found] == ["old"]                       # a fragment of something still true: nothing
    assert [f["uuid"] for f in repl["old"]] == ["new"]
    found, _ = R.superseded(GRAPH, set(), [], entities={"wiki", "altair", "printer"})
    assert [f["uuid"] for f in found] == ["old"]                       # by what a passage names: the facts no longer true between them


@pytest.mark.skipif(not FALKOR, reason="necesita un FalkorDB desechable (MIMIRSYNTH_TEST_FALKOR=host)")
def test_recall_of_a_moved_service_warns_and_brings_the_current_address(client, falkor, monkeypatch):  # noqa: F811
    class Emb:
        def embed(self, xs):
            return [[0.0] * 3 for _ in xs]
    monkeypatch.setattr(R, "search_facts", lambda *a, **k: [])                       # the question does not bring the current fact
    monkeypatch.setattr(R.index, "search", lambda *a, **k: [_chunk(7, "ep-old", "La wiki corre en altair, en la 10.0.0.5."), _chunk(8, "ep-db")])
    monkeypatch.setattr(R, "alias_map", lambda db, bid: {})
    monkeypatch.setattr(shelflife, "mark", lambda bid, facts, amap=None: facts)
    out = R.recall(1, GRAPH, "¿Cuál es la dirección del servidor de la wiki?", 6, 3, 4000, embedder=Emb(), n_docs=0, min_similarity=0)
    assert [c["id"] for c in out["chunks"]] == [8, 7] and out["chunks"][1]["superseded"][0]["uuid"] == "old"
    assert [(f["uuid"], f["status"]) for f in out["facts"]] == [("new", "current"), ("old", "invalidated")]
    ctx = out["context"]
    assert ctx.index("La wiki corre en vega") < ctx.index("## Fragmentos de episodios") and "Ahora: «La wiki corre en vega, 10.0.0.9»" in ctx


@pytest.mark.skipif(not FALKOR, reason="necesita un FalkorDB desechable (MIMIRSYNTH_TEST_FALKOR=host)")
def test_recall_of_a_wiki_page_marks_the_old_section_and_not_the_update(client, falkor, monkeypatch):  # noqa: F811
    class Emb:
        def embed(self, xs):
            return [[0.0] * 3 for _ in xs]
    old_section, update = _passage(1, "Decisión: la wiki corre en altair, en la 10.0.0.5."), _passage(2, "Actualización: la wiki pasa de altair a vega.")
    monkeypatch.setattr(R, "search_facts", lambda *a, **k: [])
    monkeypatch.setattr(R.index, "search", lambda *a, **k: [])
    monkeypatch.setattr(R, "search_documents", lambda *a, **k: ([dict(old_section), dict(update)], "ok"))
    monkeypatch.setattr(R, "alias_map", lambda db, bid: {})
    monkeypatch.setattr(shelflife, "mark", lambda bid, facts, amap=None: facts)
    from mimirsynth import docbridge
    docbridge._CACHE.pop(GRAPH, None)
    out = R.recall(1, GRAPH, "¿Cuál es la dirección del servidor de la wiki?", 6, 3, 4000, embedder=Emb(), n_docs=2, min_similarity=0)
    assert [p["chunk_idx"] for p in out["documents"]] == [2, 1] and "superseded" not in out["documents"][0]
    assert out["documents"][1]["superseded"][0]["uuid"] == "old"
    assert [(f["uuid"], f["status"]) for f in out["facts"]] == [("new", "current"), ("old", "invalidated")]
    assert "Ahora: «La wiki corre en vega, 10.0.0.9»" in out["context"]
