"""The Phase 0 corpus census (#514): classification, counts, blind samples and label summaries, on data built in memory, plus one
run of `count` and `sample` against a disposable FalkorDB graph and the test database."""
import importlib.util
import os
import random
from datetime import UTC, datetime
from pathlib import Path

import pytest
from test_control import client  # noqa: F401

_spec = importlib.util.spec_from_file_location("census", Path(__file__).resolve().parents[2] / "eval" / "census" / "census.py")
census = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(census)


def P(**kw):
    base = {"id": 1, "status": "ingested", "kind": "memory", "origin": "", "review_kind": "", "category": "",
            "source_description": "", "reference_time": None, "episode_uuid": None, "purged_at": None, "created_at": "2026-11-01",
            "ingested_at": "2026-11-01"}
    return {**base, **kw}


def test_stratum_tells_apart_where_an_episode_came_from():
    s = census.stratum
    assert s(None) == "no-proposal"
    assert s(P(category="curator.distil", origin="person")) == "distil"
    assert s(P(category="forget.rewrite")) == "forget-rewrite"
    assert s(P(kind="correction", origin="agent")) == "correction"
    assert s(P(source_description="documento 4 · trozo 2", origin="person")) == "document"
    assert s(P(source_description="webhook «checkmk» (CheckMK)", review_kind="decider")) == "webhook"
    assert s(P(category="topic.gap")) == "machine"
    assert s(P(origin="auto", source_description="Claude Code session")) == "capture"
    assert s(P(origin="auto", source_description="cli")) == "auto"
    assert s(P(origin="person")) == "person"
    assert s(P(origin="agent")) == "agent"
    assert s(P(origin="")) == "unknown"


def test_approved_by_names_who_let_it_in():
    assert census.approved_by(P(review_kind="direct")) == "direct (nobody reviewed)"
    assert census.approved_by(P(review_kind="human")) == "person"
    assert census.approved_by(None) == "no-proposal"


def test_percentile_and_bands():
    assert census.percentile([], 90) == 0.0
    assert census.percentile([5], 90) == 5
    assert census.percentile(list(range(1, 11)), 90) == 9
    assert census.percentile(list(range(1, 11)), 50) == 5
    assert census.length_band(0) == "<200"
    assert census.length_band(499) == "200-499"
    assert census.length_band(3000) == ">=3000"


def test_episode_census_counts_deleted_episodes_and_dates():
    episodes = [{"uuid": "e1", "content": "x" * 100}, {"uuid": "e2", "content": "y" * 800}, {"uuid": "e3", "content": ""}]
    proposals = [
        P(id=1, origin="person", review_kind="human", episode_uuid="e1", reference_time="2026-10-01"),
        P(id=2, origin="auto", source_description="Codex session", review_kind="decider", episode_uuid="e2"),
        P(id=3, origin="person", episode_uuid="gone"),   # distil deleted its episode
        P(id=4, kind="correction", episode_uuid="e1"),   # a second proposal on the same episode
        P(id=5, status="ingested", episode_uuid=None),   # claims only
        P(id=6, status="rejected", purged_at="2026-11-02"),
    ]
    c = census.episode_census(episodes, proposals)
    strata = {r["key"]: r["n"] for r in c["by_stratum"]}
    assert strata == {"person": 1, "capture": 1, "no-proposal": 1}
    assert {r["key"]: r["n"] for r in c["date"]} == {"own date": 1, "ingest time": 1, "no proposal": 1}
    pr = c["proposals"]
    assert pr["ingested"] == 5
    assert pr["ingested_episode_deleted"] == 1
    assert pr["ingested_without_episode"] == 1
    assert pr["ingested_episode_in_graph"] == 3
    assert pr["episodes_with_several_proposals"] == 1
    assert pr["purged"] == 1


NOW = datetime(2026, 11, 24, tzinfo=UTC)


def test_fact_census_separates_automatic_invalidations():
    edges = [
        {"uuid": "f1", "fact": "X runs on node 1", "episodes": ["e1"], "invalid_at": "2026-11-01"},
        {"uuid": "f2", "fact": "X runs on node 2", "episodes": ["e2"]},
        {"uuid": "f3", "fact": "x  runs on NODE 2", "episodes": ["e2", "e3"]},
        {"uuid": "f4", "fact": "Y was retired", "episodes": ["e3"], "invalid_at": "2026-11-02"},
        {"uuid": "f5", "fact": "Z", "episodes": [], "expired_at": "2026-11-03"},
    ]
    edges += [{"uuid": "f6", "fact": "W ran on node 3 until 2023", "episodes": ["e3"], "invalid_at": "2023-01-01",
               "created_at": "2026-11-05T10:00:00Z", "expired_at": "2026-11-05T10:01:30Z"},           # dated as past at creation
              {"uuid": "f7", "fact": "contract valid until 2027", "episodes": ["e3"], "invalid_at": "2027-06-01"},  # still true
              {"uuid": "f8", "fact": "starts next year", "episodes": ["e3"], "valid_at": "2099-01-01"}]
    c = census.fact_census(edges, ["e1", "e2", "e3", "e4"], manual={"f4"}, now=NOW)
    assert {r["key"]: r["n"] for r in c["by_state"]} == {"current": 3, "invalidated": 3, "expired": 1, "future": 1}
    assert c["identical_current"] == {"groups": 1, "facts": 2, "extra": 1}
    iv = c["invalidations"]
    assert (iv["total"], iv["through_mimirsynth"], iv["graphiti_born_invalid"], iv["graphiti_later"]) == (4, 1, 1, 2)
    assert c["per_episode"]["episodes_without_facts"] == 1
    assert c["without_episode"] == 1


def test_prompt_census_counts_the_hooks_samples():
    samples = [{"via": "http", "params": {"facts": 6, "chunks": 3, "max_chars": 4000}, "created_at": "2026-11-25"},
               {"via": "http", "params": {"facts": 8}, "created_at": "2026-11-26"},
               {"via": "mcp", "params": {}, "created_at": "2026-11-24"}]
    c = census.prompt_census([{"query_text": None}, {"query_text": "hola"}], samples)
    assert c["recall_logs_with_text"] == 1
    assert c["samples_hook_like"] == 1
    assert (c["samples_from"], c["samples_to"]) == ("2026-11-24", "2026-11-26")


def test_cost_estimate_per_note_and_arm():
    usage = [{"day": "2026-11-10", "kind": "llm", "purpose": "extraction", "calls": 30, "errors_5xx": 2, "prompt_tokens": 9000,
              "completion_tokens": 1000},
             {"day": "2026-11-11", "kind": "llm", "purpose": "recall", "calls": 99},
             {"day": "2026-11-11", "kind": "embedding", "purpose": "extraction", "calls": 50}]
    c = census.cost_estimate(usage, ["2026-11-09", "2026-11-10", "2026-11-11", None], {"all": 100})
    assert c["notes"] == 2 and c["calls_per_note"] == 15.0 and c["tokens_per_note"] == 5000 and c["failed_calls"] == 2
    assert c["arms"]["all"] == {"episodes": 100, "llm_calls": 1500, "tokens": 500000}
    odd = census.cost_estimate([{"day": "2026-11-10", "kind": "llm", "purpose": "extraction", "calls": 10}],
                               ["2026-11-10"] * 3, {"big": 10000})
    assert odd["arms"]["big"]["llm_calls"] == 33333 and odd["arms"]["big"]["tokens"] == 0   # the raw ratio, rounded at the end


def test_cost_counts_only_proposals_that_reached_extraction():
    usage = [{"day": "2026-11-01", "kind": "llm", "purpose": "extraction", "calls": 50}]
    proposals = [P(id=i, episode_uuid=f"e{i}") for i in range(10)] + [P(id=100 + i, category="curator.noise") for i in range(90)]
    c = census.census([], proposals, [], set(), [], [], usage)
    assert c["cost"]["notes"] == 10 and c["cost"]["calls_per_note"] == 5.0


def test_manual_invalidations_follow_the_latest_op_of_each_fact():
    ops = [{"id": 1, "kind": "fact.invalidate", "status": "applied", "detail": {"uuid": "a"}},
           {"id": 2, "kind": "fact.reactivate", "status": "applied", "detail": {"uuid": "a"}},   # a was reactivated
           {"id": 3, "kind": "fact.invalidate", "status": "applied", "detail": {"uuid": "b"}},
           {"id": 4, "kind": "fact.invalidate", "status": "reverted", "detail": {"uuid": "c"}},
           {"id": 5, "kind": "fact.reactivate", "status": "applied", "detail": {"uuid": "d"}},
           {"id": 6, "kind": "fact.invalidate", "status": "applied", "detail": {"uuid": "d"}}]  # invalidated again
    assert census.manual_invalidations(ops) == {"b", "d"}
    assert census.cost_estimate([], [], {})["available"] is False


def test_allocate_splits_evenly_and_gives_the_rest_to_bigger_strata():
    assert census.allocate({"a": 100, "b": 100}, 10) == {"a": 5, "b": 5}
    assert census.allocate({"a": 2, "b": 100, "c": 100}, 30) == {"a": 2, "b": 14, "c": 14}
    assert sum(census.allocate({"a": 3, "b": 4}, 100).values()) == 7
    assert census.allocate({"a": 0, "b": 5}, 3) == {"a": 0, "b": 3}


def test_blind_sheets_hide_the_stratum_and_keep_only_current_facts():
    episodes = [{"uuid": f"p{i}", "name": f"n{i}", "content": f"note {i}", "valid_at": "2026-11-01T10:00:00Z"} for i in range(10)]
    episodes += [{"uuid": f"c{i}", "name": f"s{i}", "content": f"session {i}"} for i in range(10)]
    proposals = [P(id=i, origin="person", episode_uuid=f"p{i}") for i in range(10)]
    proposals += [P(id=100 + i, origin="auto", source_description="Claude Code session", episode_uuid=f"c{i}") for i in range(10)]
    edges = [{"uuid": f"fp{i}", "fact": f"fact p{i}", "episodes": [f"p{i}"]} for i in range(10)]
    edges += [{"uuid": f"fc{i}", "fact": f"fact c{i}", "episodes": [f"c{i}"]} for i in range(10)]
    edges += [{"uuid": "old", "fact": "stale", "episodes": ["p0"], "invalid_at": "2026-11-02"}]
    eps, facts, keys = census.blind_sheets(episodes, proposals, edges, n_eps=8, n_facts=8, seed=1, now=NOW)
    assert len(eps) == 8 and len(facts) == 8
    assert all("stratum" not in r and "uuid" not in r and "origin" not in r and "title" not in r for r in eps + facts)
    assert {k["population"] for k in keys if k["kind"] == "episode"} == {10}
    kinds = {k["id"]: k for k in keys}
    assert sorted(k["stratum"] for k in keys if k["kind"] == "episode") == ["capture"] * 4 + ["person"] * 4
    assert "old" not in {k["uuid"] for k in keys}
    assert all(kinds[r["id"]]["kind"] == "fact" for r in facts)
    again = census.blind_sheets(episodes, proposals, edges, n_eps=8, n_facts=8, seed=1, now=NOW)
    assert again[2] == keys   # the same seed gives the same sample


def test_summarize_labels_by_stratum_and_weights_the_brain_row():
    keys = [{"id": "F001", "stratum": "person", "population": "30"}, {"id": "F002", "stratum": "person", "population": "30"},
            {"id": "F003", "stratum": "capture", "population": "70"}, {"id": "F004", "stratum": "capture", "population": "70"}]
    rows = [{"id": "F001", "label": "true"}, {"id": "F002", "label": " Trivial "}, {"id": "F003", "label": "wrong"},
            {"id": "F004", "label": ""}, {"id": "F005", "label": "maybe"}]
    s = census.summarize_labels(rows, keys, census.FACT_LABELS)
    assert s["by_stratum"]["person"] == {"n": 2, "margin": census.margin(2), "true": 50.0, "trivial": 50.0, "stale": 0.0, "wrong": 0.0}
    assert s["by_stratum"]["capture"]["wrong"] == 100.0
    w = s["by_stratum"]["(brain, weighted)"]
    assert w["n"] == 3 and w["wrong"] == 70.0 and w["true"] == 15.0   # 70 % of the brain is captures, all wrong in the sample
    assert (s["unlabelled"], s["unknown_label"]) == (1, 1)


def test_margin_shrinks_with_rows():
    assert census.margin(0) == 100.0
    assert 28 < census.margin(8) < 29 and 9 < census.margin(100) < 10


def test_sheets_survive_a_spreadsheet_round_trip(tmp_path):
    rows = [{"id": "E001", "text": "«Vaultwarden» está en el LXC 104", "label": "", "comment": ""}]
    census._write_csv(tmp_path / "a.csv", rows)
    assert (tmp_path / "a.csv").read_bytes().startswith(b"\xef\xbb\xbf")    # a BOM, so a spreadsheet reads the accents
    assert census._read_csv(tmp_path / "a.csv", ("id", "label"))[0]["text"] == rows[0]["text"]
    (tmp_path / "b.csv").write_bytes("id;text;label\r\nE001;año;note\r\n".encode("cp1252"))   # Excel in a Spanish locale
    assert census._read_csv(tmp_path / "b.csv", ("id", "label")) == [{"id": "E001", "text": "año", "label": "note"}]
    (tmp_path / "c.csv").write_text("ID,Etiqueta\nE001,note\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="no column id, label"):
        census._read_csv(tmp_path / "c.csv", ("id", "label"))


def test_cells_are_never_read_as_formulas():
    assert census._cell("=HYPERLINK(1)") == "'=HYPERLINK(1)"
    assert census._cell("- a bullet") == "'- a bullet"
    assert census._cell("plain") == "plain"


def test_count_refuses_a_database_that_is_not_postgresql(client, monkeypatch, tmp_path):  # noqa: F811
    monkeypatch.delenv("MIMIRSYNTH_CENSUS_ALLOW_SQLITE", raising=False)
    with pytest.raises(SystemExit, match="must be PostgreSQL"):
        census.main(["count", "--brain", "x", "--out", str(tmp_path)])


def test_markdown_renders_counts_only():
    rng = random.Random(0)
    episodes = [{"uuid": f"e{i}", "content": "secret text " * rng.randint(1, 50)} for i in range(5)]
    c = census.census(episodes, [P(id=1, origin="person", episode_uuid="e0")], [], set(), [], [], [])
    md = census.to_markdown(c)
    assert "## Corpus census · 5 episodes, 0 facts" in md
    assert "secret text" not in md
    assert "no extraction counters" in md


# --- reading a snapshot: SQL through the app's engine, the graph through ro_query -------------------------------------------------

FALKOR = os.environ.get("MIMIRSYNTH_TEST_FALKOR")
GRAPH = "zz-test-census"
needs_falkor = pytest.mark.skipif(not FALKOR, reason="necesita un FalkorDB desechable (MIMIRSYNTH_TEST_FALKOR=host)")


@needs_falkor
def test_count_and_sample_read_a_brain_and_write_nothing(client, monkeypatch, tmp_path):  # noqa: F811
    from mimirsynth import db as dbm
    from mimirsynth.config import settings
    from mimirsynth.models import Brain, Proposal, User, VocabOp
    from mimirsynth.store import _factory
    monkeypatch.setattr(settings, "falkor_host", FALKOR)
    monkeypatch.setenv("MIMIRSYNTH_CENSUS_ALLOW_SQLITE", "1")
    dbm.backend.cache_clear()
    c = dbm.backend()
    if GRAPH in c.list_graphs():
        c.delete_graph(GRAPH)
    g = c.graph(GRAPH)
    g.query("CREATE (:Episodic {uuid:'e1', name:'n1', content:'Vaultwarden runs on LXC 104', valid_at:'2026-10-01T00:00:00Z'}),"
            "(:Episodic {uuid:'e2', name:'Claude Code session', content:'Task: x. Outcome: y', valid_at:'2026-11-01T00:00:00Z'})")
    g.query("CREATE (a:Entity {uuid:'vw', name:'Vaultwarden'})-[:RELATES_TO {uuid:'f1', fact:'Vaultwarden runs on LXC 104', "
            "episodes:['e1'], valid_at:'2026-10-01T00:00:00Z'}]->(:Entity {uuid:'lxc', name:'LXC 104'})")
    g.query("MATCH (a:Entity {uuid:'vw'}) CREATE (a)-[:RELATES_TO {uuid:'f2', fact:'Vaultwarden runs on LXC 9', episodes:['e2'], "
            "valid_at:'2026-09-01T00:00:00Z', invalid_at:'2026-10-01T00:00:00Z'}]->(:Entity {uuid:'l9', name:'LXC 9'})")
    try:
        assert client.post("/api/brains", json={"slug": "cen", "name": "Census"}).status_code in (200, 201)
        with _factory()() as db:
            b = db.query(Brain).filter(Brain.slug == "cen").one()
            b.graph_name = GRAPH
            uid = db.query(User).first().id
            db.add_all([Proposal(brain_id=b.id, author_id=uid, name="n1", body="b", status="ingested", origin="person",
                                 review_kind="human", episode_uuid="e1"),
                        Proposal(brain_id=b.id, author_id=uid, name="s", body="b", status="ingested", origin="auto",
                                 source_description="Claude Code session", review_kind="decider", episode_uuid="e2"),
                        VocabOp(brain_id=b.id, kind="type.create", detail={"uuid": "f2"})])
            db.commit()
            before = db.query(Proposal).count()
        assert census.main(["count", "--brain", "cen", "--out", str(tmp_path)]) == 0
        md = (tmp_path / "census.md").read_text(encoding="utf-8")
        assert "2 episodes, 2 facts" in md
        assert "| capture | 1 | 50.0 |" in md and "| person | 1 | 50.0 |" in md
        assert "by Graphiti later, through a newer fact: **1** (100.0 %)" in md   # an op that is not `fact.invalidate` does not count
        assert census.main(["sample", "--brain", "cen", "--out", str(tmp_path), "--episodes", "2", "--facts", "2"]) == 0
        keys = census._read_csv(tmp_path / "keys.csv")
        assert sorted(k["stratum"] for k in keys if k["kind"] == "episode") == ["capture", "person"]
        assert [k["uuid"] for k in keys if k["kind"] == "fact"] == ["f1"]   # only current facts
        with _factory()() as db:
            assert db.query(Proposal).count() == before
        assert len(dbm.rows(g.ro_query("MATCH ()-[r:RELATES_TO]->() RETURN r.uuid"))) == 2
    finally:
        c.delete_graph(GRAPH)
        dbm.backend.cache_clear()
