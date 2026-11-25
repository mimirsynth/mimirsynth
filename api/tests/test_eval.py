"""The Phase 0 retrieval eval (#492): gold-set checks, the split, scoring on the final context, the bootstrap, the paired comparison
and its verdict, and the question drafts, all on fixtures: no brain, no LLM."""
import importlib.util
import json
from pathlib import Path

import pytest

EVAL = Path(__file__).resolve().parents[2] / "eval"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ev = _load("eval_run", EVAL / "run.py")
drafts = _load("eval_drafts", EVAL / "drafts.py")


def F(uuid, text, episodes, status="current"):
    return {"uuid": uuid, "fact": text, "episodes": episodes, "status": status}


def C(cid, text, episode, superseded=None):
    return {"id": cid, "text": text, "episode_uuid": episode, **({"superseded": superseded} if superseded else {})}


def out(facts=(), chunks=(), docs=(), context=None, ms=10):
    """A recall's output; the context holds every item unless given, as build_context would write it."""
    facts, chunks, docs = list(facts), list(chunks), list(docs)
    if context is None:
        context = "\n".join([*(f"- {f['fact']} (desde x)" for f in facts), *(c["text"] for c in chunks), *(d["text"] for d in docs)])
    return {"facts": facts, "chunks": chunks, "documents": docs, "context": context, "ms": {"total": ms}}


Q = {"id": "q1", "class": "point", "query": "where does X run", "answer_episodes": ["e1"], "validated": True}


# --- gold set and split ----------------------------------------------------------------------------------------------------------

def test_check_gold_names_every_problem():
    rows = [Q, dict(Q), {"id": "q2", "class": "nope", "query": ""},
            {"id": "q3", "class": "ood", "query": "x", "answer_episodes": ["e1"]},
            {"id": "q4", "class": "entity", "query": "x", "answer_episodes": ["e1"]},
            {"id": "q5", "class": "temporal", "query": "x"}]
    p = ev.check_gold(rows)
    assert "question q1: repeated id" in p
    assert any("q2: class must be" in x for x in p) and any("q2: no query" in x for x in p)
    assert any("q3: an out-of-domain question has no answer" in x for x in p)
    assert any("q4: an entity question" in x for x in p)
    assert any("q5: no answer_episodes" in x for x in p)
    assert ev.check_gold([Q]) == []


def test_split_is_even_per_class_fixed_and_only_adds():
    qs = [{"id": f"p{i}", "class": "point"} for i in range(10)] + [{"id": f"t{i}", "class": "temporal"} for i in range(7)]
    sp = ev.make_split(qs)
    assert len(sp["tune"]) + len(sp["holdout"]) == 17
    hold_p = [i for i in sp["holdout"] if i.startswith("p")]
    hold_t = [i for i in sp["holdout"] if i.startswith("t")]
    assert len(hold_p) == 5 and len(hold_t) in (3, 4)
    assert ev.make_split(qs) == sp   # the same seed, the same split
    more = qs + [{"id": "p10", "class": "point"}, {"id": "p11", "class": "point"}]
    sp2 = ev.make_split(more, old=sp)
    assert set(sp["tune"]) <= set(sp2["tune"]) and set(sp["holdout"]) <= set(sp2["holdout"])   # nothing moves
    assert len([i for i in sp2["holdout"] if i.startswith("p")]) == 6
    with pytest.raises(SystemExit, match="in no split"):
        ev.pick_split(more, sp, "holdout")
    assert {q["id"] for q in ev.pick_split(qs, sp, "holdout")} == set(sp["holdout"])


# --- scoring --------------------------------------------------------------------------------------------------------------------

def test_only_what_reached_the_context_counts_in_its_order():
    o = out([F("f1", "X runs on node 1", ["e9"]), F("f2", "Y runs on node 2", ["e1"])], [C(7, "a long fragment about X", "e1")],
            context="- Y runs on node 2 (desde x)\n- X runs on node 1 (desde x)")   # the fragment did not fit
    items = ev.context_items(o)
    assert [i["id"] for i in items] == ["f2", "f1"]


def test_top3_noise_and_latency():
    o = out([F("a", "aaaa", ["x"]), F("b", "bbbb", ["x"]), F("c", "cccc", ["x"]), F("d", "dddddddd", ["e1"])], ms=42)
    r = ev.score(Q, ev.context_items(o), 42)
    assert r["m"]["top3"] == [0, 1]   # the answer is fourth
    assert r["m"]["noise"] == [12, 20] and r["ms"] == 42
    o2 = out([F("d", "dddddddd", ["e1"])])
    assert ev.score(Q, ev.context_items(o2))["m"] == {"noise": [0, 8], "top3": [1, 1]}


def test_entity_coverage_counts_distinct_answer_episodes():
    q = {"id": "q2", "class": "entity", "query": "all about X", "answer_episodes": ["e1", "e2", "e3", "e4"]}
    o = out([F("a", "X one", ["e1"]), F("b", "X two", ["e1", "e2"])], [C(1, "X three fragment", "e9")])
    r = ev.score(q, ev.context_items(o))
    assert r["m"]["coverage"] == [0.5, 1]
    assert "top3" not in r["m"]


def test_stale_as_current_and_what_does_not_count():
    q = {"id": "q3", "class": "temporal", "query": "where does X run now", "answer_episodes": ["new"], "stale": ["fold", "eold"]}
    shown_current = out([F("fold", "X runs on node 1", ["eold"]), F("fnew", "X runs on node 2", ["new"])])
    assert ev.score(q, ev.context_items(shown_current))["m"]["stale_as_current"] == [1, 1]
    in_old_section = out([F("fold", "X runs on node 1", ["eold"], status="invalidated"), F("fnew", "X runs on node 2", ["new"])])
    assert ev.score(q, ev.context_items(in_old_section))["m"]["stale_as_current"] == [0, 1]
    warned_chunk = out(chunks=[C(1, "note: X on node 1", "eold", superseded=[{"fact": "X runs on node 1"}])])
    assert ev.score(q, ev.context_items(warned_chunk))["m"]["stale_as_current"] == [0, 1]
    bare_chunk = out(chunks=[C(1, "note: X on node 1", "eold")])
    assert ev.score(q, ev.context_items(bare_chunk))["m"]["stale_as_current"] == [1, 1]
    sibling = out([F("other", "X has 4 GB", ["eold"])])   # a current fact from the old episode is not the stale value
    assert ev.score(q, ev.context_items(sibling))["m"]["stale_as_current"] == [0, 1]


def test_out_of_domain_wants_nothing_and_all_of_it_is_noise():
    q = {"id": "q4", "class": "ood", "query": "the payroll system", "answer_episodes": []}
    assert ev.score(q, ev.context_items(out()))["m"] == {"noise": [0, 0], "empty_ok": [1, 1]}
    r = ev.score(q, ev.context_items(out([F("a", "unrelated", ["e1"])])))
    assert r["m"] == {"noise": [9, 9], "empty_ok": [0, 1]}


def test_a_document_answers_by_its_id():
    q = {"id": "q5", "class": "point", "query": "x", "answer_docs": ["12"]}
    o = out(docs=[{"document_id": 12, "text": "the passage"}])
    assert ev.score(q, ev.context_items(o))["m"]["top3"] == [1, 1]


def test_hook_precision_and_silence():
    note = {"id": "h1", "query": "fix the build", "label": "e1"}
    nothing = {"id": "h2", "query": "thanks!", "label": "nothing"}
    hit = ev.score_hook(note, ev.context_items(out([F("a", "the build uses X", ["e1"])])))
    miss = ev.score_hook(note, ev.context_items(out([F("b", "other", ["e2"])])))
    quiet = ev.score_hook(note, [])
    silent = ev.score_hook(nothing, [])
    noisy = ev.score_hook(nothing, ev.context_items(out([F("b", "other", ["e2"])])))
    recs = [hit, miss, quiet, silent, noisy]
    assert ev.aggregate(recs, "hook_precision") == pytest.approx(1 / 3)   # 3 injected, 1 with the note
    assert ev.aggregate(recs, "hook_silence") == 0.5
    assert ev.label_hook({"label": "  "}) is None


def test_noise_weighs_characters_and_rates_weigh_questions():
    recs = [{"class": "point", "m": {"noise": [0, 100], "top3": [1, 1]}}, {"class": "point", "m": {"noise": [10, 10], "top3": [0, 1]}}]
    assert ev.aggregate(recs, "noise") == pytest.approx(10 / 110)
    assert ev.aggregate(recs, "top3") == 0.5
    assert ev.aggregate(recs, "coverage") is None


# --- intervals and comparison ---------------------------------------------------------------------------------------------------

def _recs(top3, noise_num, cls="point"):
    return [{"id": f"q{i}", "class": cls, "ms": 10 + i, "items": 1, "m": {"top3": [t, 1], "noise": [n, 100]}}
            for i, (t, n) in enumerate(zip(top3, noise_num, strict=True))]


def test_bootstrap_is_seeded_and_brackets_the_value():
    recs = _recs([1, 0] * 20, [30] * 40)
    s = ev.summarize(recs, n=500)
    row = next(r for r in s["rows"] if r["scope"] == "point" and r["metric"] == "top3")
    assert row["value"] == 0.5 and row["lo"] < 0.5 < row["hi"]
    assert ev.summarize(recs, n=500) == s
    assert s["latency_ms"] == {"p50": 29, "p95": 47}   # nearest rank over 10…49


def _run(recs, budget="2500"):
    return {"meta": {"budget": budget, "split": "holdout"}, "summary": ev.summarize(recs, n=50), "records": recs}


def _temporal(stale):
    return [{"id": f"t{i}", "class": "temporal", "ms": 1, "items": 1, "m": {"top3": [1, 1], "noise": [10, 100], "stale_as_current": [s, 1]}}
            for i, s in enumerate(stale)]


def test_verdict_yes_when_noise_falls_enough_and_answers_hold():
    a = _run(_recs([1] * 40, [40] * 40) + _temporal([1, 0] * 10))
    b = _run(_recs([1] * 40, [20] * 40) + _temporal([1, 0] * 10))   # noise −50 %, the same answers
    c = ev.compare(a, b, n=300)
    noise = next(r for r in c["rows"] if r["scope"] == "all" and r["metric"] == "noise")
    assert noise["rel"] < -0.30 and noise["diff_hi"] < 0
    assert c["verdict"]["yes"] and c["verdict"]["improved"] == ["noise"]


def test_verdict_no_on_a_small_effect_or_worse_answers():
    a = _run(_recs([1] * 40, [40] * 40))
    small = ev.compare(a, _run(_recs([1] * 40, [36] * 40)), n=300)   # −10 %: real but below the minimum
    assert not small["verdict"]["yes"]
    worse = ev.compare(a, _run(_recs([1, 0] * 20, [10] * 40)), n=300)   # far less noise, half the answers
    assert not worse["verdict"]["yes"] and any("worse answers" in x for x in worse["verdict"]["reasons"])
    tie = ev.compare(a, a, n=300)
    assert not tie["verdict"]["yes"]
    assert any("stale_as_current: not measured" in x for x in tie["verdict"]["reasons"])


def test_compare_refuses_runs_at_different_budgets():
    a = _run(_recs([1], [1]))
    with pytest.raises(SystemExit, match="differ in budget"):
        ev.compare(a, _run(_recs([1], [1]), budget="plugin"))


# --- the command, end to end with a fake recall ---------------------------------------------------------------------------------

def test_run_scores_validated_questions_at_the_plugin_budget(tmp_path):
    gold = [Q, {**Q, "id": "q2", "validated": False}, {"id": "o1", "class": "ood", "query": "payroll", "answer_episodes": [], "validated": True}]
    (tmp_path / "gold.jsonl").write_text("".join(json.dumps(q) + "\n" for q in gold), encoding="utf-8")
    (tmp_path / "hook.jsonl").write_text(json.dumps({"id": "h1", "query": "fix", "label": "e1"}) + "\n"
                                         + json.dumps({"id": "h2", "query": "todo", "label": ""}) + "\n", encoding="utf-8")
    calls = []

    def fake(query, **p):
        calls.append((query, p))
        return out([F("a", "X runs on node 1", ["e1"])]) if query != "payroll" else out()

    assert ev.main(["split", "--gold", str(tmp_path / "gold.jsonl"), "--out", str(tmp_path / "split.json")]) == 0
    with pytest.raises(SystemExit, match="fixed once"):
        ev.main(["split", "--gold", str(tmp_path / "gold.jsonl"), "--out", str(tmp_path / "split.json")])
    assert ev.main(["run", "--brain", "b", "--gold", str(tmp_path / "gold.jsonl"), "--hookset", str(tmp_path / "hook.jsonl"),
                    "--split", "all", "--budget", "plugin", "--out", str(tmp_path / "r.json")], recall_fn=fake) == 0
    res = json.loads((tmp_path / "r.json").read_text(encoding="utf-8"))
    assert {p["max_chars"] for _, p in calls} == {4000} and {p["n_facts"] for _, p in calls} == {6}
    assert [r["id"] for r in res["records"]] == ["q1", "o1", "h1"]   # the draft and the unlabelled prompt are left out
    assert res["meta"]["questions"] == 2 and res["meta"]["hook"] == 1
    rows = {(r["scope"], r["metric"]): r["value"] for r in res["summary"]["rows"]}
    assert rows[("point", "top3")] == 1 and rows[("ood", "empty_ok")] == 1 and rows[("hook", "hook_precision")] == 1


def test_a_gold_set_with_problems_stops_the_run(tmp_path):
    (tmp_path / "g.jsonl").write_text(json.dumps({"id": "x", "class": "entity", "query": "q", "answer_episodes": ["e1"]}) + "\n",
                                      encoding="utf-8")
    with pytest.raises(SystemExit, match="entity question"):
        ev.main(["run", "--brain", "b", "--gold", str(tmp_path / "g.jsonl"), "--split", "all"], recall_fn=lambda q, **p: out())


# --- drafts ---------------------------------------------------------------------------------------------------------------------

def test_parse_json_finds_the_object_in_a_chatty_answer():
    assert drafts.parse_json('Sure!\n```json\n{"query": "q?", "answer": "a"}\n```') == {"query": "q?", "answer": "a"}
    assert drafts.parse_json("no json here") is None
    assert drafts.parse_json("[1, 2]") is None
    filled = drafts.PROMPTS["temporal"].format(old="a", new="b", when="2026")   # the JSON example survives str.format
    assert '{"query": "...", "answer"' in filled
    assert '{"queries"' in drafts.PROMPTS["ood"].format(subjects="x", n=3)


def test_temporal_pairs_join_an_invalidated_fact_to_its_replacement():
    edges = [{"uuid": "old", "fact": "X on node 1", "episodes": ["e1"], "source_uuid": "x", "valid_at": "2025-01-01T00:00:00Z",
              "invalid_at": "2026-03-01T10:00:00Z"},
             {"uuid": "new", "fact": "X on node 2", "episodes": ["e2"], "source_uuid": "x", "valid_at": "2026-03-01T10:00:30Z"},
             {"uuid": "far", "fact": "X has 4 GB", "episodes": ["e3"], "source_uuid": "x", "valid_at": "2026-05-01T00:00:00Z"},
             {"uuid": "y", "fact": "Y on node 2", "episodes": ["e4"], "source_uuid": "y", "valid_at": "2026-03-01T10:00:00Z"}]
    pairs = drafts.temporal_pairs(edges)
    assert [(p["old"]["uuid"], p["new"]["uuid"]) for p in pairs] == [("old", "new")]


def test_build_drafts_only_from_the_chosen_strata_and_numbers_them():
    episodes = [{"uuid": "p1", "content": "Vaultwarden runs on LXC 104"}, {"uuid": "p2", "content": "Vaultwarden backups go to NAS"},
                {"uuid": "c1", "content": "Claude Code session: fixed a test"}]
    proposals = [{"id": 1, "origin": "person", "episode_uuid": "p1"}, {"id": 2, "origin": "person", "episode_uuid": "p2"},
                 {"id": 3, "origin": "auto", "source_description": "Claude Code session", "episode_uuid": "c1"}]
    mentions = [{"entity": "vw", "name": "Vaultwarden", "episodes": ["p1", "p2", "c1"]}]
    edges = [{"uuid": "old", "fact": "VW on LXC 9", "episodes": ["p1"], "source_uuid": "vw", "invalid_at": "2026-01-01T00:00:00Z"},
             {"uuid": "new", "fact": "VW on LXC 104", "episodes": ["p1"], "source_uuid": "vw", "valid_at": "2026-01-01T00:00:00Z"}]
    seen = []

    def ask(prompt, text):
        seen.append(text)
        if '"queries"' in prompt:
            return '{"queries": ["who runs payroll?", ""]}'
        if "several notes" in prompt:
            return '{"query": "what do we know of Vaultwarden?", "answer": "LXC 104, NAS", "notes": [1, 2]}'
        return '{"query": "where does it run?", "answer": "LXC 104"}'

    out = drafts.build(episodes, proposals, edges, mentions, ask, {"point": 5, "entity": 5, "temporal": 5, "ood": 2}, ("person",))
    assert [d["id"] for d in out] == [f"d{i:03d}" for i in range(1, len(out) + 1)]
    assert all(not d["validated"] for d in out)
    assert not any("Claude Code session" in t for t in seen)   # a capture is never sent
    by = {d["class"]: d for d in out}
    assert sorted(d["answer_episodes"][0] for d in out if d["class"] == "point") == ["p1", "p2"]
    assert by["entity"]["answer_episodes"] == ["p1", "p2"]
    assert by["temporal"]["stale"] == ["old"] and by["temporal"]["answer_episodes"] == ["p1"]
    assert [d["query"] for d in out if d["class"] == "ood"] == ["who runs payroll?"]
    assert ev.check_gold(out) == []   # a draft has the shape the eval expects
