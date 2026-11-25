"""The Phase 0 retrieval eval (#492): gold-set checks, the split, scoring on the final context (also against the app's own
build_context), the bootstrap, the paired comparison and its verdict, and the question drafts, all on fixtures: no brain, no LLM."""
import importlib.util
import json
from pathlib import Path

import pytest

from mimirsynth.recall import build_context

EVAL = Path(__file__).resolve().parents[2] / "eval"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ev = _load("eval_run", EVAL / "run.py")
drafts = _load("eval_drafts", EVAL / "drafts.py")


def F(uuid, text, episodes, status="current", **kw):
    return {"uuid": uuid, "fact": text, "episodes": episodes, "status": status, "valid_at": "2026-01-01", "created_at": "2026-01-01",
            "invalid_at": "2026-02-01" if status == "invalidated" else None, **kw}


def C(cid, text, episode, superseded=None):
    return {"id": cid, "text": text, "episode_uuid": episode, "name": f"note {cid}", "valid_at": "2026-01-01",
            **({"superseded": superseded} if superseded else {})}


def out(facts=(), chunks=(), docs=(), max_chars=100000, ms=10):
    """A recall's output with its context written by the app's own build_context."""
    facts, chunks, docs = list(facts), list(chunks), list(docs)
    return {"facts": facts, "chunks": chunks, "documents": docs, "context": build_context(facts, chunks, max_chars, docs),
            "ms": {"total": ms}}


def D(doc, idx, text):
    return {"document_id": doc, "chunk_idx": idx, "text": text, "title": "Runbook", "heading_path": "", "page": None}


Q = {"id": "q1", "class": "point", "query": "where does X run", "answer_episodes": ["e1"], "validated": True}


# --- gold set and split ----------------------------------------------------------------------------------------------------------

def test_check_gold_names_every_problem():
    rows = [Q, dict(Q), {"id": "q2", "class": "nope", "query": ""},
            {"id": "q3", "class": "ood", "query": "x", "answer_episodes": ["e1"]},
            {"id": "q4", "class": "entity", "query": "x", "answer_episodes": ["e1", "e1"]},
            {"id": "q5", "class": "temporal", "query": "x"},
            {"id": "q6", "class": "point", "query": "x", "answer_episodes": "e1abc"},
            {"id": "q7", "class": "point", "query": "x", "answer_episodes": ["e1"], "validated": "false"}]
    p = ev.check_gold(rows)
    assert "question q1: repeated id" in p
    assert any("q2: class must be" in x for x in p) and any("q2: no query" in x for x in p)
    assert any("q3: an out-of-domain question has no answer" in x for x in p)
    assert any("q4: an entity question" in x for x in p)   # the same episode twice is one
    assert any("q5: no answer_episodes" in x for x in p)
    assert any("q6: answer_episodes must be a list" in x for x in p)
    assert any("q7: validated must be true or false" in x for x in p)
    assert ev.check_gold([Q]) == []
    assert ev.check_gold([{"id": ["q1"], "class": "ood", "query": "x"}, [1, 2]]) == ["question #1: no id", "line 2: not a question object"]


def test_split_is_even_per_class_fixed_and_only_adds():
    qs = [{"id": f"p{i}", "class": "point"} for i in range(10)] + [{"id": f"t{i}", "class": "temporal"} for i in range(7)]
    sp = ev.make_split(qs)
    assert len(sp["tune"]) + len(sp["holdout"]) == 17
    assert len([i for i in sp["holdout"] if i.startswith("p")]) == 5
    assert len([i for i in sp["holdout"] if i.startswith("t")]) in (3, 4)
    assert ev.make_split(qs) == sp   # the same seed, the same split
    more = qs + [{"id": "p10", "class": "point"}, {"id": "p11", "class": "point"}]
    sp2 = ev.make_split(more, old=sp)
    assert set(sp["tune"]) <= set(sp2["tune"]) and set(sp["holdout"]) <= set(sp2["holdout"])   # nothing moves
    assert len([i for i in sp2["holdout"] if i.startswith("p")]) == 6
    with pytest.raises(SystemExit, match="in no split"):
        ev.pick_split(more, sp, "holdout")
    assert {q["id"] for q in ev.pick_split(qs, sp, "holdout")} == set(sp["holdout"])


# --- what reached the context ---------------------------------------------------------------------------------------------------

def test_only_what_reached_the_context_counts_in_its_order():
    o = out([F("f2", "Y runs on node 2", ["e1"]), F("f1", "X runs on node 1", ["e9"])], [C(7, "a long fragment about X " * 20, "e1")],
            max_chars=150)   # the fragment does not fit
    assert [i["id"] for i in ev.context_items(o)] == ["f2", "f1"]


def test_a_text_quoted_in_another_line_is_not_its_item():
    new = F("fnew", "X runs on node 2", ["e2"], replaces="X runs on node 1")
    old = F("fold", "X runs on node 1", ["e1"], status="invalidated")
    tight = out([new, old], max_chars=90)   # the old fact's own line is cut; its text is still quoted in [sustituye a «…»]
    assert "X runs on node 1" in tight["context"]
    assert [i["id"] for i in ev.context_items(tight)] == ["fnew"]
    roomy = out([new, old])
    assert [(i["id"], i["current"]) for i in ev.context_items(roomy)] == [("fnew", True), ("fold", False)]


def test_duplicated_texts_need_one_line_each_and_a_fact_inside_a_fragment_is_not_the_fact():
    a, b = F("a", "X runs on node 1", ["e1"]), F("b", "X runs on node 1", ["e2"])
    cut = out([a], [C(1, "Notes: X runs on node 1 since May", "e3")])
    cut["facts"] = [a, b]   # b was returned but its line was never written
    assert [i["id"] for i in ev.context_items(cut)] == ["a", "1"]
    lone = out(chunks=[C(1, "Notes: Z runs on node 3", "e3")])
    lone["facts"] = [F("z", "Z runs on node 3", ["e3"])]   # only quoted inside the fragment
    assert [i["id"] for i in ev.context_items(lone)] == ["1"]


def test_a_fact_only_takes_a_line_of_its_own_section():
    cur = F("cur", "X runs on node 1", ["e2"], replaces="a very long replaced fact text " * 4)
    old = F("old", "X runs on node 1", ["e1"], status="invalidated")
    o = out([cur, old], max_chars=150)   # the long current line is cut, the old section still fits
    assert "invalidado" in o["context"] and "sustituye" not in o["context"]
    assert [(i["id"], i["current"]) for i in ev.context_items(o)] == [("old", False)]


def test_documents_match_by_their_marker():
    o = out(docs=[D(12, 0, "restart the service"), D(12, 1, "then check the logs")])
    assert [(i["kind"], i["id"]) for i in ev.context_items(o)] == [("doc", "12"), ("doc", "12")]
    q = {"id": "q5", "class": "point", "query": "x", "answer_docs": ["12"]}
    assert ev.score(q, ev.context_items(o))["m"]["top3"] == [1, 1]


def test_no_two_items_share_a_character():
    """A `###` heading inside a passage is not a fragment's header, and a `> ` line is part of an entry only when it is the warning."""
    t = "Deploy with the blue-green script."
    o = out(docs=[D(7, 0, "# Runbook\n### Deploy\n" + t)])
    o["chunks"] = [C(1, t, "e1")]   # returned, but its own entry is not in the context
    items = ev.context_items(o)
    assert [(i["kind"], i["id"]) for i in items] == [("doc", "7")]
    q = {"id": "q", "class": "point", "query": "x", "answer_docs": ["7"], "answer_episodes": ["e1"]}
    r = ev.score(q, items, context=o["context"])
    assert 0 <= r["m"]["noise"][0] <= r["m"]["noise"][1] and r["unparsed_chars"] >= 0
    padded = out(chunks=[C(1, "note: X on node 1", "e1")])
    padded["context"] += "\n> a summary a variant might add " * 10
    ctx = padded["context"]
    items = ev.context_items(padded)
    assert items[0]["chars"] == ctx.index("\n> a summary") + 1 - ctx.index("### ")   # header and text, with the break: no padding
    r = ev.score(Q, items, context=ctx)
    assert r["m"]["noise"] == [len(ctx) - items[0]["chars"], len(ctx)]   # the padding is noise, not answer


# --- scoring --------------------------------------------------------------------------------------------------------------------

def test_top3_noise_and_latency():
    o = out([F("a", "aaaa", ["x"]), F("b", "bbbb", ["x"]), F("c", "cccc", ["x"]), F("d", "dddddddd", ["e1"])])
    r = ev.score(Q, ev.context_items(o), 42, o["context"])
    assert r["m"]["top3"] == [0, 1]   # the answer is fourth
    answer = o["context"].split("\n")[-1]   # its whole line, date included
    assert answer.startswith("- dddddddd (")
    total = len(o["context"])
    assert r["m"]["noise"] == [total - len(answer), total] and r["ms"] == 42
    assert r["unparsed_chars"] == len("## Hechos vigentes\n")   # the section header: noise, taken by no item
    one = out([F("d", "dddddddd", ["e1"])])
    assert ev.score(Q, ev.context_items(one), context=one["context"])["m"] == {"noise": [19, len(one["context"])], "top3": [1, 1]}


def test_a_fragment_takes_its_header_text_and_warning():
    warned = [{"fact": "X runs on node 1", "invalid_at": "2026-02-01"}]
    o = out([F("a", "X has 4 GB", ["x"])], [C(1, "note: X on node 1", "e1", superseded=warned)])
    items = ev.context_items(o)
    assert sum(i["chars"] for i in items) + len("## Hechos vigentes\n## Fragmentos de episodios\n") == len(o["context"])
    r = ev.score(Q, items, context=o["context"])
    frag = o["context"][o["context"].index("### "):]
    assert "Puede estar superado" in frag and r["m"]["noise"] == [len(o["context"]) - len(frag), len(o["context"])]
    en = build_context([], [C(1, "note: X on node 1", "e1", superseded=warned)], 100000, lang="en")
    item = ev.context_items({"chunks": [C(1, "note: X on node 1", "e1", superseded=warned)], "context": en})[0]
    assert "May be superseded" in en and item["chars"] == len(en) - en.index("### ")   # the English warning is part of it too


def test_entity_coverage_counts_distinct_answer_episodes():
    q = {"id": "q2", "class": "entity", "query": "all about X", "answer_episodes": ["e1", "e2", "e3", "e4"]}
    o = out([F("a", "X one", ["e1"]), F("b", "X two", ["e1", "e2"])], [C(1, "X three fragment", "e9")])
    r = ev.score(q, ev.context_items(o))
    assert r["m"]["coverage"] == [0.5, 1] and "top3" not in r["m"]


def test_stale_as_current_and_what_does_not_count():
    q = {"id": "q3", "class": "temporal", "query": "where does X run now", "answer_episodes": ["new"], "stale": ["fold", "eold"]}
    def stale(o):
        return ev.score(q, ev.context_items(o))["m"]["stale_as_current"]
    assert stale(out([F("fold", "X runs on node 1", ["eold"]), F("fnew", "X runs on node 2", ["new"])])) == [1, 1]
    assert stale(out([F("fold", "X runs on node 1", ["eold"], status="invalidated"), F("fnew", "X runs on node 2", ["new"])])) == [0, 1]
    warned = [{"fact": "X runs on node 1", "invalid_at": "2026-02-01"}]
    assert stale(out(chunks=[C(1, "note: X on node 1", "eold", superseded=warned)])) == [0, 1]
    assert stale(out(chunks=[C(1, "note: X on node 1", "eold")])) == [1, 1]
    assert stale(out([F("other", "X has 4 GB", ["eold"])])) == [0, 1]   # a current fact from the old episode is not the stale value


def test_empty_ok_and_silence_read_the_context_not_only_the_items():
    q = {"id": "q4", "class": "ood", "query": "the payroll system", "answer_episodes": []}
    card = "## Estado actual de «X»\n- runs_on: node 1 (desde 1 ene 2026)"
    assert ev.score(q, [], context="")["m"] == {"noise": [0, 0], "empty_ok": [1, 1]}
    s = ev.score(q, [], context=card)   # a state card alone is still something injected, and all of it is noise
    assert s["m"] == {"noise": [len(card), len(card)], "empty_ok": [0, 1]} and s["unparsed_chars"] == len(card)
    o = out([F("a", "unrelated", ["e1"])])
    r = ev.score(q, ev.context_items(o), context=o["context"])
    assert r["m"] == {"noise": [len(o["context"])] * 2, "empty_ok": [0, 1]}
    assert ev.score_hook({"id": "h", "label": "nothing"}, [], context=card)["m"] == {"hook_precision": [0, 1], "hook_silence": [0, 1]}


def test_hook_precision_and_silence():
    note = {"id": "h1", "query": "fix the build", "label": "e1"}
    nothing = {"id": "h2", "query": "thanks!", "label": "nothing"}
    hit = ev.score_hook(note, ev.context_items(out([F("a", "the build uses X", ["e1"])])))
    miss = ev.score_hook(note, ev.context_items(out([F("b", "other", ["e2"])])))
    recs = [hit, miss, ev.score_hook(note, []), ev.score_hook(nothing, []),
            ev.score_hook(nothing, ev.context_items(out([F("b", "other", ["e2"])])))]
    assert ev.aggregate(recs, "hook_precision") == pytest.approx(1 / 3)   # 3 injected, 1 with the note
    assert ev.aggregate(recs, "hook_silence") == 0.5
    assert ev.label_hook({"label": "  "}) is None


def test_hook_rows_keep_only_the_hooks_calls_and_merge_keeps_labels():
    like = _load("census_mod", EVAL / "census" / "census.py")._hook_like
    samples = [{"id": 1, "via": "http", "params": {"facts": 6, "chunks": 3, "max_chars": 4000}, "query": "a"},
               {"id": 2, "via": "mcp", "params": {"facts": 6, "chunks": 3}, "query": "b"},
               {"id": 3, "via": "http", "params": {"facts": 8}, "query": "c"}]
    rows = ev.hook_rows(samples, like)
    assert [r["id"] for r in rows] == ["h1"]
    old = [{"id": "h1", "query": "a", "label": "e7"}]
    merged = ev.merge_labels([*rows, {"id": "h9", "query": "z", "label": ""}], old)
    assert merged == [old[0], {"id": "h9", "query": "z", "label": ""}]


def test_noise_weighs_characters_and_rates_weigh_questions():
    recs = [{"class": "point", "m": {"noise": [0, 100], "top3": [1, 1]}}, {"class": "point", "m": {"noise": [10, 10], "top3": [0, 1]}}]
    assert ev.aggregate(recs, "noise") == pytest.approx(10 / 110)
    assert ev.aggregate(recs, "top3") == 0.5
    assert ev.aggregate(recs, "coverage") is None


# --- intervals and comparison ---------------------------------------------------------------------------------------------------

def _recs(top3, noise_num, cls="point"):
    return [{"id": f"q{i}", "class": cls, "ms": 10 + i, "items": 1, "m": {"top3": [t, 1], "noise": [n, 100]}}
            for i, (t, n) in enumerate(zip(top3, noise_num, strict=True))]


def _temporal(stale, noise=10):
    return [{"id": f"t{i}", "class": "temporal", "ms": 1, "items": 1, "m": {"top3": [1, 1], "noise": [noise, 100], "stale_as_current": [s, 1]}}
            for i, s in enumerate(stale)]


def _run(recs, budget="2500"):
    return {"meta": {"budget": budget, "split": "holdout"}, "summary": ev.summarize(recs, n=50), "records": recs}


def test_bootstrap_is_seeded_and_brackets_the_value():
    recs = _recs([1, 0] * 20, [30] * 40)
    s = ev.summarize(recs, n=500)
    row = next(r for r in s["rows"] if r["scope"] == "point" and r["metric"] == "top3")
    assert row["value"] == 0.5 and row["lo"] < 0.5 < row["hi"]
    assert ev.summarize(recs, n=500) == s
    assert s["latency_ms"] == {"p50": 29, "p95": 47}   # nearest rank over 10…49
    assert ev.summarize([]) == {"rows": [], "errors": 0, "unparsed_chars": 0, "context_chars": 0,
                                "latency_ms": {"p50": None, "p95": None}}


def test_verdict_yes_when_noise_falls_enough_and_answers_hold():
    a = _run(_recs([1] * 40, [40] * 40) + _temporal([1, 0] * 10))
    b = _run(_recs([1] * 40, [20] * 40) + _temporal([1, 0] * 10))   # noise −50 %, the same answers
    c = ev.compare(a, b, n=300)
    noise = next(r for r in c["rows"] if r["scope"] == "all" and r["metric"] == "noise")
    assert noise["rel"] < -0.30 and noise["diff_hi"] < 0
    assert c["verdict"]["yes"] and c["verdict"]["improved"] == ["noise"]
    assert c["counts"] == {"a": 60, "b": 60, "paired": 60, "failed_a": 0, "failed_b": 0}


def test_verdict_yes_on_stale_alone_and_no_when_the_other_co_primary_rises():
    a = _run(_recs([1] * 20, [30] * 20) + _temporal([1] * 20))
    b = _run(_recs([1] * 20, [30] * 20) + _temporal([1, 0, 0, 0] * 5))   # stale-as-current −75 %, noise the same
    c = ev.compare(a, b, n=300)
    assert c["verdict"]["yes"] and c["verdict"]["improved"] == ["stale_as_current"]
    noisier = _run(_recs([1] * 20, [60] * 20) + _temporal([1, 0, 0, 0] * 5, noise=60))
    c2 = ev.compare(a, noisier, n=300)
    assert not c2["verdict"]["yes"] and "noise: worse" in c2["verdict"]["reasons"]


def test_verdict_no_on_a_small_effect_worse_answers_a_tie_or_a_zero_baseline():
    a = _run(_recs([1] * 40, [40] * 40))
    assert not ev.compare(a, _run(_recs([1] * 40, [36] * 40)), n=300)["verdict"]["yes"]   # −10 %: below the minimum
    worse = ev.compare(a, _run(_recs([1, 0] * 20, [10] * 40)), n=300)   # far less noise, half the answers
    assert not worse["verdict"]["yes"] and any("worse answers" in x for x in worse["verdict"]["reasons"])
    tie = ev.compare(a, a, n=300)
    assert not tie["verdict"]["yes"] and "stale_as_current: not measured" in tie["verdict"]["reasons"]
    zero = _run(_recs([1] * 10, [0] * 10))   # no noise in A: it cannot fall
    z = ev.compare(zero, zero, n=100)
    assert next(r for r in z["rows"] if r["metric"] == "noise" and r["scope"] == "all")["rel"] is None
    assert not z["verdict"]["yes"]


def test_a_metric_b_cannot_measure_counts_against_b():
    hooks_a = [{"id": f"h{i}", "class": "hook", "ms": 1, "items": 1, "m": {"hook_precision": [1, 1]}} for i in range(10)]
    hooks_b = [{"id": f"h{i}", "class": "hook", "ms": 1, "items": 0, "m": {}} for i in range(10)]   # B injects nothing
    a = _run(_recs([1] * 20, [40] * 20) + hooks_a)
    b = _run(_recs([1] * 20, [10] * 20) + hooks_b)
    c = ev.compare(a, b, n=200)
    row = next(r for r in c["rows"] if r["metric"] == "hook_precision")
    assert row["b"] is None and row["diff"] is None
    assert not c["verdict"]["yes"] and any("hook_precision (not measured in B)" in x for x in c["verdict"]["reasons"])
    assert "| hook | hook_precision |" in ev.compare_markdown(c)


def test_b_failing_on_more_questions_is_a_no():
    a = _run(_recs([1] * 40, [40] * 40))
    recs = _recs([1] * 40, [20] * 40)   # noise −50 %, but B fails on five questions A ran
    for r in recs[:5]:
        r["m"], r["error"] = {}, "unparsed context: …"
    c = ev.compare(a, _run(recs), n=300)
    assert c["counts"]["failed_b"] == 5 and c["counts"]["paired"] == 35
    assert not c["verdict"]["yes"] and "B failed on 5 more of the shared questions than A" in c["verdict"]["reasons"]
    assert "B on 5" in ev.compare_markdown(c)


def test_compare_refuses_runs_that_are_not_comparable():
    a = _run(_recs([1], [1]))
    with pytest.raises(SystemExit, match="differ in budget"):
        ev.compare(a, _run(_recs([1], [1]), budget="plugin"))
    b = _run(_recs([1], [1]))
    b["meta"]["drafts_included"] = True
    with pytest.raises(SystemExit, match="differ in drafts_included"):
        ev.compare(a, b)


# --- the command, end to end with a fake recall ---------------------------------------------------------------------------------

def _files(tmp_path, gold, hooks=()):
    (tmp_path / "gold.jsonl").write_text("".join(json.dumps(q) + "\n" for q in gold), encoding="utf-8")
    (tmp_path / "hook.jsonl").write_text("".join(json.dumps(h) + "\n" for h in hooks), encoding="utf-8")
    return str(tmp_path / "gold.jsonl"), str(tmp_path / "hook.jsonl"), str(tmp_path / "split.json")


def test_run_scores_validated_questions_at_the_plugin_budget(tmp_path):
    gold = [Q, {**Q, "id": "q2", "validated": False}, {"id": "o1", "class": "ood", "query": "payroll", "answer_episodes": [], "validated": True}]
    g, h, sp = _files(tmp_path, gold, [{"id": "h1", "query": "fix", "label": "e1"}, {"id": "h2", "query": "todo", "label": ""}])
    calls = []

    def fake(query, **p):
        calls.append((query, p))
        return out([F("a", "X runs on node 1", ["e1"])]) if query != "payroll" else out()

    assert ev.main(["split", "--gold", g, "--hookset", h, "--out", sp]) == 0
    with pytest.raises(SystemExit, match="fixed once"):
        ev.main(["split", "--gold", g, "--out", sp])
    assert ev.main(["run", "--brain", "b", "--gold", g, "--hookset", h, "--split", "all", "--budget", "plugin",
                    "--out", str(tmp_path / "r.json")], recall_fn=fake) == 0
    res = json.loads((tmp_path / "r.json").read_text(encoding="utf-8"))
    assert {p["max_chars"] for _, p in calls} == {4000} and {p["n_facts"] for _, p in calls} == {6}
    assert [r["id"] for r in res["records"]] == ["q1", "o1", "h1"]   # the draft and the unlabelled prompt are left out
    assert res["meta"]["questions"] == 2 and res["meta"]["hook"] == 1
    rows = {(r["scope"], r["metric"]): r["value"] for r in res["summary"]["rows"]}
    assert rows[("point", "top3")] == 1 and rows[("ood", "empty_ok")] == 1 and rows[("hook", "hook_precision")] == 1


def test_a_context_in_an_unknown_format_does_not_look_cleaner():
    """A variant of #513 or #516 may write its context another way. What the parser cannot read is noise, and a context with items
    none of which was found is an error that leaves the pairing, never an empty answer."""
    qs = [{**Q, "id": f"q{i}"} for i in range(20)]

    def v017(query, **p):
        return out([F("a", "X runs on node 1", ["e1"]), F("b", "Y is unrelated", ["e9"])])

    def other(query, **p):   # the same facts, written with no `- fact (` lines
        return {**v017(query), "context": "<<facts>>\n* X runs on node 1 — 2026\n* Y is unrelated — 2026"}

    def bare(query, **p):    # only a context, in a format of its own
        return {"context": "EPISODE e1: X runs on node 1, and much else besides. " * 3, "ms": {"total": 5}}

    a = ev.run(qs, [], v017, "2500")
    b = ev.run(qs, [], other, "2500")
    assert all(r["error"].startswith("unparsed context") and r["m"] == {} for r in b)
    with pytest.raises(SystemExit, match="share no question"):
        ev.compare(_run(a), _run(b))
    c = ev.run(qs, [], bare, "2500")
    assert all(r["m"]["noise"][0] == r["m"]["noise"][1] == r["chars"] == r["unparsed_chars"] for r in c)
    vs = ev.compare(_run(a), _run(c), n=200)
    noise = next(r for r in vs["rows"] if r["scope"] == "all" and r["metric"] == "noise")
    assert noise["diff"] > 0 and not vs["verdict"]["yes"] and "noise" not in vs["verdict"]["improved"]
    s = ev.summarize(c, n=50)
    assert s["unparsed_chars"] == s["context_chars"] > 0
    assert "Unparsed:" in ev.summary_markdown({"budget": "2500", "split": "all", "questions": 20}, s)


def test_only_the_restored_instance_runs_against_a_brain(tmp_path, monkeypatch):
    monkeypatch.delenv("MIMIRSYNTH_EVAL_SNAPSHOT", raising=False)
    with pytest.raises(SystemExit, match="MIMIRSYNTH_EVAL_SNAPSHOT=1"):
        ev.main(["hookset", "--brain", "b", "--out", str(tmp_path / "h.jsonl")])
    g, _, _ = _files(tmp_path, [Q])
    with pytest.raises(SystemExit, match="MIMIRSYNTH_EVAL_SNAPSHOT=1"):
        ev.main(["run", "--brain", "b", "--gold", g, "--split", "all"])
    with pytest.raises(SystemExit, match="MIMIRSYNTH_EVAL_SNAPSHOT=1"):
        drafts._read("b", 0)


def test_the_hook_prompts_are_split_too_and_add_only_places_new_ones(tmp_path):
    gold = [{**Q, "id": f"q{i}"} for i in range(4)]
    hooks = [{"id": f"h{i}", "query": f"p{i}", "label": "e1"} for i in range(4)]
    g, h, sp = _files(tmp_path, gold, hooks)
    assert ev.main(["split", "--gold", g, "--hookset", h, "--out", sp]) == 0
    first = json.loads(Path(sp).read_text(encoding="utf-8"))
    assert len(first["hook"]["holdout"]) == 2
    seen = []
    ev.main(["run", "--brain", "b", "--gold", g, "--hookset", h, "--split", "holdout", "--split-file", sp,
             "--out", str(tmp_path / "r.json")], recall_fn=lambda q, **p: seen.append(q) or out())
    assert sorted(x for x in seen if x.startswith("p")) == sorted(f"p{x[1:]}" for x in first["hook"]["holdout"])
    g2, h2, _ = _files(tmp_path, [*gold, {**Q, "id": "q9"}], [*hooks, {"id": "h9", "query": "p9", "label": "e1"}])
    assert ev.main(["split", "--gold", g2, "--hookset", h2, "--out", sp, "--add"]) == 0
    second = json.loads(Path(sp).read_text(encoding="utf-8"))
    assert set(first["tune"]) <= set(second["tune"]) and set(first["hook"]["holdout"]) <= set(second["hook"]["holdout"])
    assert "q9" in second["tune"] + second["holdout"] and "h9" in second["hook"]["tune"] + second["hook"]["holdout"]


def test_a_failed_recall_is_recorded_and_the_run_goes_on(tmp_path):
    gold = [Q, {**Q, "id": "q2", "query": "boom"}]
    g, _, _ = _files(tmp_path, gold)

    def fake(query, **p):
        if query == "boom":
            raise RuntimeError("embedding engine down")
        return out([F("a", "X", ["e1"])])

    assert ev.main(["run", "--brain", "b", "--gold", g, "--split", "all", "--out", str(tmp_path / "r.json")], recall_fn=fake) == 0
    res = json.loads((tmp_path / "r.json").read_text(encoding="utf-8"))
    assert res["summary"]["errors"] == 1 and "embedding engine down" in res["records"][1]["error"]
    assert next(r for r in res["summary"]["rows"] if r["metric"] == "top3")["n"] == 1

    def down(query, **p):
        raise RuntimeError("embedding engine down")
    assert ev.main(["run", "--brain", "b", "--gold", g, "--split", "all", "--out", str(tmp_path / "r2.json")], recall_fn=down) == 1


def test_a_gold_set_with_problems_stops_the_run(tmp_path):
    g, _, _ = _files(tmp_path, [{"id": "x", "class": "entity", "query": "q", "answer_episodes": ["e1"]}])
    with pytest.raises(SystemExit, match="entity question"):
        ev.main(["run", "--brain", "b", "--gold", g, "--split", "all"], recall_fn=lambda q, **p: out())


# --- drafts ---------------------------------------------------------------------------------------------------------------------

def test_parse_json_and_the_prompts_survive_format():
    assert drafts.parse_json('Sure!\n```json\n{"query": "q?", "answer": "a"}\n```') == {"query": "q?", "answer": "a"}
    assert drafts.parse_json("no json here") is None and drafts.parse_json("[1, 2]") is None
    assert '{"query": "...", "answer"' in drafts.PROMPTS["temporal"].format(old="a", new="b", when="2026")
    assert '{"queries"' in drafts.PROMPTS["ood"].format(subjects="x", n=3)


def test_temporal_pairs_join_an_invalidated_fact_to_its_replacement():
    edges = [{"uuid": "old", "name": "RUNS_ON", "fact": "X on node 1", "episodes": ["e1"], "source_uuid": "x",
              "invalid_at": "2026-03-01T10:00:00Z"},
             {"uuid": "sib", "name": "HAS_RAM", "fact": "X has 8 GB", "episodes": ["e2"], "source_uuid": "x", "valid_at": "2026-03-01T10:00:00Z"},
             {"uuid": "new", "name": "RUNS_ON", "fact": "X on node 2", "episodes": ["e2"], "source_uuid": "x", "valid_at": "2026-03-01T10:00:30Z"},
             {"uuid": "far", "name": "RUNS_ON", "fact": "X on node 3", "episodes": ["e3"], "source_uuid": "x", "valid_at": "2026-05-01T00:00:00"},
             {"uuid": "y", "name": "RUNS_ON", "fact": "Y on node 2", "episodes": ["e4"], "source_uuid": "y", "valid_at": "2026-03-01T10:00:00Z"}]
    pairs = drafts.temporal_pairs(edges)
    assert [(p["old"]["uuid"], p["new"]["uuid"]) for p in pairs] == [("old", "new")]   # the same relation beats the closer sibling


EPISODES = [{"uuid": "p1", "content": "Vaultwarden runs on LXC 104"}, {"uuid": "p2", "content": "Vaultwarden backups go to NAS"},
            {"uuid": "c1", "content": "Claude Code session: SecretProject fixed a test"}]
PROPOSALS = [{"id": 1, "origin": "person", "episode_uuid": "p1"}, {"id": 2, "origin": "person", "episode_uuid": "p2"},
             {"id": 3, "origin": "auto", "source_description": "Claude Code session", "episode_uuid": "c1"}]
MENTIONS = [{"entity": "vw", "name": "Vaultwarden", "episodes": ["p1", "p2", "c1"]},
            {"entity": "sp", "name": "SecretProject", "episodes": ["c1"]}]
EDGES = [{"uuid": "old", "name": "ON", "fact": "VW on LXC 9", "episodes": ["p1"], "source_uuid": "vw", "invalid_at": "2026-01-01T00:00:00Z"},
         {"uuid": "new", "name": "ON", "fact": "VW on LXC 104", "episodes": ["p2"], "source_uuid": "vw", "valid_at": "2026-01-01T00:00:00Z"},
         {"uuid": "cold", "name": "ON", "fact": "CAPTURE-ONLY old fact", "episodes": ["c1"], "source_uuid": "sp",
          "invalid_at": "2026-01-01T00:00:00Z"},
         {"uuid": "cnew", "name": "ON", "fact": "SecretProject now", "episodes": ["p1"], "source_uuid": "sp", "valid_at": "2026-01-01T00:00:00Z"}]


def _ask(sent):
    def ask(prompt, text, max_tokens):
        sent.append(prompt + "\n" + text)
        if '"queries"' in prompt:
            n = int(prompt.split("Write ")[1].split(" ")[0])
            return json.dumps({"queries": [f"ood {len(sent)}-{i}" for i in range(n)]})
        if "several notes" in prompt:
            return '{"query": "what do we know of Vaultwarden?", "answer": "LXC 104, NAS", "notes": [1, 2, 2]}'
        return '{"query": "where does it run?", "answer": "LXC 104"}'
    return ask


def test_build_sends_the_engine_only_the_chosen_strata():
    sent = []
    out_, failed = drafts.build(EPISODES, PROPOSALS, EDGES, MENTIONS, _ask(sent), {"point": 5, "entity": 5, "temporal": 5, "ood": 2},
                                ("person",))
    assert sent and not any("SecretProject" in s or "CAPTURE-ONLY" in s or "Claude Code session" in s for s in sent)
    assert [d["id"] for d in out_] == [f"d{i:03d}" for i in range(1, len(out_) + 1)] and failed == {}
    by = {d["class"]: d for d in out_}
    assert by["entity"]["answer_episodes"] == ["p1", "p2"] and by["entity"]["drafted_from"] == "person"
    assert by["temporal"]["stale"] == ["old", "p1"] and by["temporal"]["answer_episodes"] == ["p2"]   # the old fact's episode too
    assert by["ood"]["drafted_from"] == "entities"
    assert all(not d["validated"] for d in out_) and ev.check_gold(out_) == []


def test_build_drafts_from_captures_and_real_prompts_too_and_says_where_from():
    sent = []
    samples = [{"id": 41, "query": "how do I restart vaultwarden?", "via": "mcp"},
               {"id": 42, "query": "How do I restart  Vaultwarden?", "via": "answer"},   # the same prompt again
               {"id": 43, "query": "fix the failing test", "via": "http", "params": {"facts": 6, "chunks": 3}}]   # the hook's: hook set
    out_, _ = drafts.build(EPISODES, PROPOSALS, EDGES, MENTIONS, _ask(sent), {"point": 5, "ood": 25, "samples": 5},
                           ("person", "capture"), samples)
    froms = {d["drafted_from"] for d in out_ if d["class"] == "point"}
    assert froms == {"person", "capture"}
    assert sum(d["class"] == "ood" for d in out_) == 25 and sum('"queries"' in s for s in sent) == 3   # in batches of 10
    real = [d for d in out_ if d["drafted_from"] == "replay sample"]
    assert real == [{**real[0], "class": "", "query": "how do I restart vaultwarden?", "sample": 41}]
    assert not any("restart vaultwarden" in s for s in sent)   # a real prompt is never sent to the engine


def test_an_engine_error_leaves_that_piece_out_and_is_counted():
    def ask(prompt, text, max_tokens):
        raise RuntimeError("502")
    out_, failed = drafts.build(EPISODES, PROPOSALS, EDGES, MENTIONS, ask, {"point": 2}, ("person",))
    assert out_ == [] and failed == {"point": 2}


def test_out_of_domain_batches_keep_earlier_ones_name_them_and_drop_repeats():
    prompts, calls = [], {"n": 0}

    def ask(prompt, text, max_tokens):
        prompts.append(prompt)
        calls["n"] += 1
        if calls["n"] == 1:
            return json.dumps({"queries": [f"q{i}" for i in range(10)]})
        if calls["n"] == 2:
            return json.dumps({"queries": ["q1", "Q1 ", "new one"]})   # repeats of the first batch
        raise RuntimeError("timeout")
    got = drafts.draft("ood", {"subjects": ["a", "b", "c"]}, ask, 30)
    assert [d["query"] for d in got] == [f"q{i}" for i in range(10)] + ["new one"]   # the failed third batch keeps the rest
    assert "Not these, already written: q0 | q1" in prompts[1]
    assert prompts[0] != prompts[1].split(" Not these")[0]   # the subjects lead differently
