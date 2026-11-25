"""The virtual clean corpus of Phase 0 (#516, step 1): which cells are curated, from the census labels, and the filter that leaves
the others out of 0.17's recall in the eval's process only. All on fixtures: no brain."""
import csv
import importlib.util
import json
from collections import Counter
from pathlib import Path

import pytest

from mimirsynth import recall

EVAL = Path(__file__).resolve().parents[2] / "eval"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cl = _load("eval_clean_t", EVAL / "clean" / "clean.py")
ev = _load("eval_run_t", EVAL / "run.py")


def P(ep, origin, review="human", desc=""):
    return {"id": hash(ep) % 10000, "status": "approved", "kind": "memory", "origin": origin, "review_kind": review, "category": "",
            "source_description": desc, "episode_uuid": ep, "created_at": "2026-01-01"}


# --- curated cells ---------------------------------------------------------------------------------------------------------------

def test_a_cell_is_its_stratum_and_who_let_it_in():
    eps = [{"uuid": "a"}, {"uuid": "b"}, {"uuid": "c"}]
    cell = cl.cells(eps, [P("a", "person"), P("b", "person", "direct"), P("c", "auto", "auto", "claude session")])
    assert cell["a"] == ("person", "person") and cell["b"] == ("person", "direct (nobody reviewed)")
    assert cell["c"] == ("capture", "category tier")


def test_curated_cells_never_guess_and_show_their_interval():
    cell_of = {f"p{i}": ("person", "person") for i in range(20)} | {f"c{i}": ("capture", "category tier") for i in range(30)} \
        | {f"w{i}": ("webhook", "webhook auto-approve") for i in range(9)} | {f"x{i}": ("agent", "decider") for i in range(4)}
    labelled = {f"p{i}": "note" for i in range(4)} | {"p4": "event"}                      # 5 of 5 clean
    labelled |= {f"c{i}": "dump" for i in range(4)} | {"c4": "note", "c5": "meta"}         # 1 of 6
    labelled |= {"w0": "note", "w1": "note"}                                              # 2: too few to decide
    rows = {r["stratum"]: r for r in cl.curated_table(cell_of, labelled)}
    assert rows["person"]["curated"] is True and rows["person"]["lo"] < 0.6   # 5 of 5 is not certainty
    assert rows["capture"]["curated"] is False and rows["capture"]["share"] == pytest.approx(1 / 6)
    assert rows["webhook"]["curated"] is None and rows["agent"]["curated"] is None and rows["agent"]["labelled"] == 0
    drop = cl.dropped(cell_of, list(rows.values()))
    assert drop == {f"c{i}" for i in range(30)}   # only the cell decided as not curated
    cur = {"rule": {"clean_labels": ["note", "event"], "min_clean": 0.8, "min_labelled": 5}, "cells": list(rows.values()),
           "drop": sorted(drop)}
    md = cl.table_markdown(cur)
    assert "| capture | category tier | 30 | 6 | 17 |" in md and "| **no** |" in md
    assert "too few labels: kept" in md and "no labels: kept" in md and "2 cells (13 episodes) have too few" in md
    assert "Left out: 30 of 63 episodes." in md


def test_labels_go_through_the_key_and_a_different_source_map_stops():
    cell_of = {"u1": ("person", "person"), "u2": ("capture", "category tier")}
    sheet = [{"id": "E001", "label": "Note"}, {"id": "E002", "label": "dump"}, {"id": "E003", "label": ""},
             {"id": "E004", "label": "spam"}, {"id": "E005", "label": "note"}, {"id": "E006", "label": "note"}]
    keys = [{"id": "E001", "kind": "episode", "uuid": "u1", "stratum": "person"},
            {"id": "E002", "kind": "episode", "uuid": "u2", "stratum": "capture"},
            {"id": "E006", "kind": "episode", "uuid": "gone", "stratum": "person"},
            {"id": "E005", "kind": "fact", "uuid": "f1", "stratum": "person"}]
    lab, skipped = cl.labels(sheet, keys, cell_of)
    assert lab == {"u1": "note", "u2": "dump"}
    assert skipped == {"unlabelled": 1, "unknown label": 1, "no key": 1, "not in the snapshot": 1}
    with pytest.raises(SystemExit, match="--source-map"):
        cl.labels(sheet, [{**keys[0], "stratum": "no-proposal: source A"}], cell_of)


# --- the filter ------------------------------------------------------------------------------------------------------------------

def test_a_fact_leaves_only_when_every_episode_it_comes_from_is_left_out():
    drop = {"bad1", "bad2"}
    assert not cl._keep({"episodes": ["bad1", "bad2"]}, drop)
    assert cl._keep({"episodes": ["bad1", "good"]}, drop)   # mixed: it stays
    assert not cl._keep({"episode_uuid": "bad1"}, drop) and cl._keep({"episode_uuid": "good"}, drop)
    assert cl._keep({"episodes": []}, drop) and cl._keep({"document_id": 3}, drop)


def test_the_cut_is_made_after_filtering(monkeypatch):
    asked = {}

    def facts(graph_name, qvec, limit, amap=None):
        asked["facts"] = limit
        return [{"uuid": f"f{i}", "episodes": ["bad" if i < 3 else f"e{i}"]} for i in range(limit)]

    def chunks(brain_id, qvec, query, n, min_sim, common=False):
        asked["chunks"] = n
        return [{"id": i, "episode_uuid": "bad" if i < 3 else f"e{i}"} for i in range(n)]

    monkeypatch.setattr(recall, "search_facts", facts)
    monkeypatch.setattr(recall, "search_chunks", chunks)
    with cl.corpus({"bad"}) as stats:
        got = recall.search_facts("g", [0.1], 3)
        got_c = recall.search_chunks(1, [0.1], "q", 3, 0.3)
    assert [f["uuid"] for f in got] == ["f3", "f4", "f5"] and asked["facts"] == 3 * cl.OVERFETCH
    assert [c["id"] for c in got_c] == [3, 4, 5] and asked["chunks"] == 3 * cl.OVERFETCH
    assert stats == Counter({"facts": 3, "chunks": 3})


def test_with_nothing_left_out_the_searches_are_the_same_even_with_repeated_texts(monkeypatch):
    rows = [{"uuid": f"f{i}", "fact": f"fact {i // 2}", "episodes": [f"e{i}"]} for i in range(40)]   # each text twice

    def facts(graph_name, qvec, limit, amap=None):   # as the real one: LIMIT first, then repeated texts out
        seen, out = set(), []
        for f in rows[:limit]:
            if f["fact"] not in seen:
                seen.add(f["fact"])
                out.append(f)
        return out

    monkeypatch.setattr(recall, "search_facts", facts)
    full = recall.search_facts("g", [0.1], 6)
    with cl.corpus(set()):
        assert recall.search_facts("g", [0.1], 6) == full
    with cl.corpus({"e0", "e1"}) as stats:   # both copies of "fact 0" left out: one more text comes in, no more than full had
        got = recall.search_facts("g", [0.1], 6)
    assert [f["fact"] for f in got] == ["fact 1", "fact 2", "fact 3"] and len(got) == len(full)
    assert stats["facts"] == 1   # of what the full recall would have used


def test_what_stopped_being_true_leaves_no_trace_of_a_left_out_episode(monkeypatch):
    old = {"uuid": "o", "fact": "X ran on node 1", "episodes": ["e1"]}          # stated by a kept fragment
    old_bad = {"uuid": "ob", "fact": "Y ran on node 1", "episodes": ["bad"]}
    new_bad = {"uuid": "nb", "fact": "X runs on node 9", "episodes": ["bad"]}   # replaces it, only from a left-out episode
    new_mixed = {"uuid": "nm", "fact": "X runs on node 2", "episodes": ["bad", "e2"]}
    monkeypatch.setattr(recall, "superseded", lambda *a, **k: ([old, old_bad], {"o": [new_bad, new_mixed], "ob": [new_bad]}))
    with cl.corpus({"bad"}) as stats:
        found, repl = recall.superseded("g", {"e1"}, [])
    assert found == [old] and repl == {"o": [new_mixed]}
    assert stats == Counter({"superseding facts": 2, "superseded facts": 1})


def test_the_patch_does_not_outlive_the_block_even_on_error():
    real = (recall.search_facts, recall.search_chunks, recall.superseded, recall.build_context)
    with pytest.raises(RuntimeError):
        with cl.corpus({"x"}):
            assert recall.search_facts is not real[0] and recall.superseded is not real[2] and recall.build_context is not real[3]
            raise RuntimeError("boom")
    assert (recall.search_facts, recall.search_chunks, recall.superseded, recall.build_context) == real


def test_linked_facts_leave_the_context_and_state_cards_are_counted():
    good = {"uuid": "g", "fact": "X runs on node 2", "episodes": ["e1"], "status": "current", "valid_at": "2026-01-01"}
    linked = {"uuid": "l", "fact": "X runs on node 1", "episodes": ["bad"], "status": "current", "valid_at": "2026-01-01",
              "replaces": "X ran on node 0", "similarity": None}
    full = recall.build_context([good, linked], [], 10000)
    with cl.corpus({"bad"}) as stats:
        ctx = recall.build_context([good, linked], [], 10000)
    assert "X runs on node 1" in full and "X runs on node 1" not in ctx and "X runs on node 2" in ctx
    assert stats["linked facts"] == 1
    out = cl.filtered(lambda q, **p: {"facts": [good, linked], "chunks": [{"id": 1, "episode_uuid": "bad"}], "context": ""}, {"bad"})("q")
    assert [f["uuid"] for f in out["facts"]] == ["g"] and out["chunks"] == []


def test_with_nothing_left_out_the_recall_is_the_same():
    facts = [{"uuid": f"f{i}", "fact": f"fact {i}", "episodes": [f"e{i}"], "status": "current", "valid_at": "2026-01-01"}
             for i in range(5)]
    assert cl.answers_left_out([{"answer_episodes": ["e1"]}, {"answer_episodes": []}], set()) == 0
    full = recall.build_context(facts, [], 10000)
    with cl.corpus(set()):
        assert recall.build_context(facts, [], 10000) == full


# --- run.py --corpus ------------------------------------------------------------------------------------------------------------

Q = [{"id": "q1", "class": "point", "query": "where does X run", "answer_episodes": ["e1"], "validated": True},
     {"id": "q2", "class": "point", "query": "where does Y run", "answer_episodes": ["bad"], "validated": True}]


def _gold(tmp_path):
    g = tmp_path / "gold.jsonl"
    g.write_text("".join(json.dumps(q) + "\n" for q in Q), encoding="utf-8")
    return str(g)


def test_run_without_the_flag_replaces_nothing_and_writes_the_same_result(tmp_path):
    seen = []

    def recall_fn(query, **p):
        seen.append(recall.search_facts.__module__)
        facts = [{"uuid": "f1", "fact": "X runs on node 1", "episodes": ["e1"], "status": "current", "valid_at": "2026-01-01"},
                 {"uuid": "f2", "fact": "Y runs on node 3", "episodes": ["bad"], "status": "current", "valid_at": "2026-01-01"}]
        return {"facts": facts, "chunks": [], "documents": [], "context": recall.build_context(facts, [], 10000), "ms": {"total": 1}}

    outs = []
    for i, extra in enumerate(([], ["--corpus", "full"])):
        out = tmp_path / f"r{i}.json"
        ev.main(["run", "--brain", "b", "--gold", _gold(tmp_path), "--split", "all", "--out", str(out), *extra], recall_fn=recall_fn)
        res = json.loads(out.read_text(encoding="utf-8"))
        outs.append((res["records"], res["summary"]))
        assert res["meta"]["corpus"] == "full" and "curated" not in res["meta"]
    assert outs[0] == outs[1] and set(seen) == {"mimirsynth.recall"}


def test_run_on_the_clean_corpus_filters_and_says_what_it_left_out(tmp_path, capsys):
    cur = {"brain": "b", "rule": {"clean_labels": ["note", "event"], "min_clean": 0.8, "min_labelled": 5, "source_map": None},
           "cells": [{"stratum": "capture", "review": "category tier", "episodes": 1, "labelled": 5, "clean": 0, "share": 0.0,
                      "lo": 0.0, "hi": 0.43, "curated": False}], "skipped": {}, "drop": ["bad"]}
    (tmp_path / "curated.json").write_text(json.dumps(cur), encoding="utf-8")
    patched = []

    def recall_fn(query, **p):   # what recall() does: search, then build the context, through the module's own names
        patched.append(recall.search_facts.__module__ != "mimirsynth.recall")
        facts = [{"uuid": "f1", "fact": "X runs on node 1", "episodes": ["e1"], "status": "current", "valid_at": "2026-01-01"},
                 {"uuid": "f2", "fact": "Y runs on node 3", "episodes": ["bad"], "status": "current", "valid_at": "2026-01-01"}]
        return {"facts": facts, "chunks": [], "documents": [], "context": recall.build_context(facts, [], 10000), "ms": {"total": 1}}

    out = tmp_path / "r.json"
    ev.main(["run", "--brain", "b", "--gold", _gold(tmp_path), "--split", "all", "--out", str(out), "--corpus", "clean",
             "--curated", str(tmp_path / "curated.json")], recall_fn=recall_fn)
    res = json.loads(out.read_text(encoding="utf-8"))
    assert all(patched) and recall.search_facts.__module__ == "mimirsynth.recall"
    c = res["meta"]["curated"]
    assert res["meta"]["corpus"] == "clean" and c["left_out_episodes"] == 1 and c["questions_with_every_answer_left_out"] == 1
    assert c["latency"] == "not comparable with a full run"
    assert c["items_left_out"] == {"linked facts": 2}   # this fake recall builds its context with everything it found
    rec = {r["id"]: r for r in res["records"]}
    assert rec["q1"]["m"]["top3"] == [1, 1] and rec["q2"]["m"]["top3"] == [0, 1]
    text = capsys.readouterr().out
    assert "Curated cells (#516)" in text and "| capture | category tier |" in text and "every answer episode is left out: 1" in text
    with pytest.raises(SystemExit, match="made for brain 'b', not 'other'"):
        ev.main(["run", "--brain", "other", "--gold", _gold(tmp_path), "--split", "all", "--corpus", "clean",
                 "--curated", str(tmp_path / "curated.json")], recall_fn=recall_fn)
    with pytest.raises(SystemExit, match="run `clean.py curated` first"):
        ev.main(["run", "--brain", "b", "--gold", _gold(tmp_path), "--split", "all", "--corpus", "clean",
                 "--curated", str(tmp_path / "none.json")], recall_fn=recall_fn)


def test_a_clean_run_warns_that_lent_graphs_are_not_filtered(tmp_path, monkeypatch, capsys):
    cur = {"brain": "b", "rule": {"clean_labels": ["note"], "min_clean": 0.8, "min_labelled": 5, "source_map": None}, "cells": [],
           "drop": []}
    (tmp_path / "curated.json").write_text(json.dumps(cur), encoding="utf-8")
    fn = lambda query, **p: {"facts": [], "chunks": [], "documents": [], "context": "", "ms": {"total": 1}}  # noqa: E731
    monkeypatch.setattr(ev, "recall_on", lambda slug: (fn, {"federated": ["ops"]}))
    monkeypatch.setattr(ev, "counted", lambda: __import__("contextlib").nullcontext())
    out = tmp_path / "r.json"
    ev.main(["run", "--brain", "b", "--gold", _gold(tmp_path), "--split", "all", "--out", str(out), "--corpus", "clean",
             "--curated", str(tmp_path / "curated.json")])
    assert json.loads(out.read_text(encoding="utf-8"))["meta"]["curated"]["not_filtered"] == ["ops"]
    assert "lent to this brain, and nothing of theirs is left out" in capsys.readouterr().out


def _csv(path, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def test_curated_end_to_end_with_a_fake_snapshot(tmp_path, capsys):
    eps = [{"uuid": f"p{i}"} for i in range(6)] + [{"uuid": f"c{i}"} for i in range(6)]
    props = [P(f"p{i}", "person") for i in range(6)] + [P(f"c{i}", "auto", "auto", "claude session") for i in range(6)]
    sheet = [{"id": f"E{i:03d}", "label": "note" if i < 6 else "dump"} for i in range(12)]
    keys = [{"id": f"E{i:03d}", "kind": "episode", "uuid": (f"p{i}" if i < 6 else f"c{i - 6}"),
             "stratum": "person" if i < 6 else "capture", "population": 6} for i in range(12)]
    _csv(tmp_path / "episodes.csv", sheet)
    _csv(tmp_path / "keys.csv", keys)
    out = tmp_path / "curated.json"
    assert cl.main(["curated", "--brain", "b", "--sheet", str(tmp_path / "episodes.csv"), "--keys", str(tmp_path / "keys.csv"),
                    "--out", str(out)], snapshot=(eps, props)) == 0
    cur = json.loads(out.read_text(encoding="utf-8"))
    assert cur["drop"] == [f"c{i}" for i in range(6)] and cur["rule"]["min_labelled"] == 5 and cur["brain"] == "b"
    assert "| capture | category tier | 6 | 6 | 0 |" in capsys.readouterr().out
    for bad in ("80", "0"):
        with pytest.raises(SystemExit, match="--min-clean"):
            cl.main(["curated", "--brain", "b", "--sheet", str(tmp_path / "episodes.csv"), "--keys", str(tmp_path / "keys.csv"),
                     "--min-clean", bad], snapshot=(eps, props))
    with pytest.raises(SystemExit, match="--clean-labels"):
        cl.main(["curated", "--brain", "b", "--sheet", str(tmp_path / "episodes.csv"), "--keys", str(tmp_path / "keys.csv"),
                 "--clean-labels", "note,true"], snapshot=(eps, props))


def test_only_the_restored_instance_reads_the_brain(tmp_path, monkeypatch):
    monkeypatch.delenv("MIMIRSYNTH_EVAL_SNAPSHOT", raising=False)
    _csv(tmp_path / "episodes.csv", [{"id": "E001", "label": "note"}])
    _csv(tmp_path / "keys.csv", [{"id": "E001", "kind": "episode", "uuid": "u", "stratum": "person"}])
    with pytest.raises(SystemExit, match="MIMIRSYNTH_EVAL_SNAPSHOT=1"):
        cl.main(["curated", "--brain", "b", "--sheet", str(tmp_path / "episodes.csv"), "--keys", str(tmp_path / "keys.csv")])
