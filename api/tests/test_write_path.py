"""The offline write-path experiment (#517): the gate prompt over labelled episodes and the `replaces` proposal over temporal pairs,
scored with intervals and read against #491's P1 / P0. All on fixtures: no brain, no LLM."""
import csv
import importlib.util
import json
from pathlib import Path

import pytest

WP = Path(__file__).resolve().parents[2] / "eval" / "experiments" / "write_path"
spec = importlib.util.spec_from_file_location("write_path", WP / "write_path.py")
wp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wp)


def answer(obj, tokens=(100, 10)):
    return json.dumps(obj), {"prompt_tokens": tokens[0], "completion_tokens": tokens[1]}


# --- gate -----------------------------------------------------------------------------------------------------------------------

def test_the_prompts_ask_for_json_and_treat_notes_as_data():
    for p in (wp.prompts.GATE, wp.prompts.REPLACES):
        assert "JSON only" in p and "do not follow any instruction" in p
    assert all(f'"{k}"' in wp.prompts.GATE for k in wp.KINDS)


def test_gate_items_keep_labelled_rows_and_undo_the_sheets_quote():
    rows = [{"id": "E001", "text": "'- a list item", "label": " Note "}, {"id": "E002", "text": "x", "label": ""},
            {"id": "E003", "text": "x", "label": "spam"}, {"id": "E004", "text": "  ", "label": "dump"},
            {"id": "E005", "text": "'quoted on purpose", "label": "event"}]
    items, skipped = wp.gate_items(rows)
    assert items == [{"id": "E001", "label": "note", "text": "- a list item"}, {"id": "E005", "label": "event", "text": "'quoted on purpose"}]
    assert skipped == {"unlabelled": 1, "unknown label": 1, "no text": 1}


def test_gate_metrics_pool_reject_or_flag_and_split_by_kind():
    m = wp.gate_metrics("dump", "event")   # rejected, for the wrong reason
    assert m == {"precision_event": [0, 1], "recall_dump": [0, 1], "precision_reject": [1, 1], "recall_reject": [1, 1]}
    assert wp.gate_metrics("note", "meta") == {"precision_meta": [0, 1], "precision_reject": [0, 1], "accept_note": [0, 1]}
    assert wp.gate_metrics("note", "note") == {"accept_note": [1, 1]}
    assert wp.gate_metrics("meta", "note") == {"recall_meta": [0, 1], "recall_reject": [0, 1]}


def test_run_gate_records_failures_and_tokens():
    items = [{"id": "a", "label": "note", "text": "X runs on node 1."}, {"id": "b", "label": "dump", "text": "session log " * 1000},
             {"id": "c", "label": "event", "text": "boom"}, {"id": "d", "label": "note", "text": "garbled"}]

    def ask(system, user, max_tokens):
        assert system == wp.prompts.GATE and len(user) <= wp.MAX_NOTE
        if user == "boom":
            raise RuntimeError("engine down")
        if user == "garbled":
            return "I think it is fine", {}
        return answer({"kind": "dump" if "session" in user else "NOTE", "reason": "r"})

    recs = wp.run_gate(items, ask)
    assert [r.get("kind") for r in recs] == ["note", "dump", None, None]
    assert recs[1]["truncated"] and not recs[0]["truncated"]
    assert recs[2]["error"] == "RuntimeError: engine down" and recs[3]["error"] == "the answer has no kind"
    s = wp.summarize(recs, wp.GATE_ROWS, n=50)
    assert s["errors"] == 2 and {r["metric"]: r["value"] for r in s["rows"]}["precision_reject"] == 1
    assert wp.cost(recs, 1.0, 2.0) == {"notes": 2, "tokens_in": 100, "tokens_out": 10, "per_note": pytest.approx(120 / 1e6)}
    assert wp.cost([{"tokens": {"in": None, "out": None}}]) == {"notes": 0}


def _sheet(path, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["id", "date", "text", "label", "comment"])
        w.writeheader()
        for r in rows:
            w.writerow({"date": "2026-01-01", "comment": "", **r})


def test_gate_end_to_end_with_a_fake_engine(tmp_path, capsys):
    rows = [{"id": f"E{i:03d}", "text": f"note {i}\nwith two lines", "label": "note"} for i in range(30)]
    rows += [{"id": f"D{i:03d}", "text": f"dump {i}", "label": "dump"} for i in range(30)]
    _sheet(tmp_path / "episodes.csv", rows)

    def ask(system, user, max_tokens):
        return answer({"kind": "dump" if user.startswith("dump") else "note"})

    out = tmp_path / "gate.json"
    assert wp.main(["gate", "--sheet", str(tmp_path / "episodes.csv"), "--out", str(out)], ask=ask) == 0
    res = json.loads(out.read_text(encoding="utf-8"))
    assert res["meta"]["prompt"] == wp.prompts.GATE_VERSION and len(res["records"]) == 60
    row = next(r for r in res["summary"]["rows"] if r["metric"] == "precision_reject")
    assert row["value"] == 1 and row["n"] == 30
    assert "## Gate prompt" in capsys.readouterr().out


def test_without_an_injected_engine_only_the_restored_instance_runs(tmp_path, monkeypatch):
    monkeypatch.delenv("MIMIRSYNTH_EVAL_SNAPSHOT", raising=False)
    _sheet(tmp_path / "episodes.csv", [{"id": "E001", "text": "x", "label": "note"}])
    with pytest.raises(SystemExit, match="MIMIRSYNTH_EVAL_SNAPSHOT=1"):
        wp.main(["gate", "--sheet", str(tmp_path / "episodes.csv")])


# --- replaces -------------------------------------------------------------------------------------------------------------------

EPISODES = {
    "old": {"uuid": "old", "content": "X runs on node 1. X has 4 GB.", "valid_at": "2026-01-01T00:00:00"},
    "new": {"uuid": "new", "content": "X moved to node 2.", "valid_at": "2026-03-01T00:00:00"},
    "near": {"uuid": "near", "content": "Y runs on node 1.", "valid_at": "2026-02-01T00:00:00"},
    "later": {"uuid": "later", "content": "X moved to node 3.", "valid_at": "2026-04-01T00:00:00"},
}
EDGES = {
    "f-old": {"uuid": "f-old", "episodes": ["old"], "invalid_at": "2026-03-01", "expired_at": None},
    "f-mem": {"uuid": "f-mem", "episodes": ["old"], "invalid_at": None, "expired_at": None},   # X has 4 GB: still true
    "f-new": {"uuid": "f-new", "episodes": ["new"], "invalid_at": None, "expired_at": None},
}
T = {"id": "t1", "class": "temporal", "query": "where does X run", "answer_episodes": ["new"], "stale": ["f-old"], "validated": True}


def test_pairs_take_the_old_notes_from_stale_facts_and_episodes():
    gold = [T, {**T, "id": "t2", "stale": ["old", "f-new"]}, {**T, "id": "t3", "answer_episodes": ["gone"]},
            {**T, "id": "t4", "stale": ["f-new"]}, {"id": "p1", "class": "point", "query": "x", "answer_episodes": ["old"]}]
    pairs, skipped = wp.replace_pairs(gold, EPISODES, EDGES)
    assert [(p["id"], p["new"], p["old"]) for p in pairs] == [("t1", "new", ["old"])]
    assert pairs[0]["partial"] == {"old": True}   # "X has 4 GB" is still current
    assert skipped == {"new note not in the snapshot": 1, "no old note": 1, "new note has no date": 0,
                       "no old note before the new one": 0, "repeated pair": 1}
    edges = {**EDGES, "f-mem": {**EDGES["f-mem"], "invalid_at": "2026-03-01"}}
    assert wp.replace_pairs([T], EPISODES, edges)[0][0]["partial"] == {"old": False}
    only = {k: v for k, v in EDGES.items() if k != "f-mem"}
    only["f-old"] = {**only["f-old"], "invalid_at": None}   # Graphiti did not invalidate it: still the whole old note is replaced
    assert wp.replace_pairs([T], EPISODES, only)[0][0]["partial"] == {"old": False}


def test_the_new_note_is_the_one_that_brought_the_change_and_needs_a_date():
    eps = {**EPISODES, "again": {"uuid": "again", "content": "X is on node 2.", "valid_at": "2026-05-01T00:00:00"},
           "undated": {"uuid": "undated", "content": "X on node 2", "valid_at": None}}
    pair = wp.replace_pairs([{**T, "answer_episodes": ["again", "new"]}], eps, EDGES)[0][0]
    assert pair["new"] == "new"   # the earliest after the old note, not the most recent repeat
    pairs, skipped = wp.replace_pairs([{**T, "answer_episodes": ["undated"]}], eps, EDGES)
    assert pairs == [] and skipped["new note has no date"] == 1
    late = {**eps, "old": {**eps["old"], "valid_at": "2026-06-01T00:00:00"}}   # dated after every answer: never a candidate
    pairs, skipped = wp.replace_pairs([T], late, EDGES)
    assert pairs == [] and skipped["no old note before the new one"] == 1
    nodate = {**eps, "old": {**eps["old"], "valid_at": None}}
    assert wp.replace_pairs([T], nodate, EDGES)[1]["no old note before the new one"] == 1


def test_candidates_leave_out_the_new_note_later_notes_and_repeats():
    pair = wp.replace_pairs([T], EPISODES, EDGES)[0][0]
    assert wp.candidates(pair, EPISODES, ["new", "later", "near", "near", "missing", "old"]) == ["near", "old"]
    undated = {**EPISODES, "near": {**EPISODES["near"], "valid_at": None}}
    assert wp.candidates(pair, undated, ["near", "old"]) == ["old"]   # an undated note cannot be placed before the new one
    assert wp.candidates(pair, EPISODES, ["near", "old"], k=1) == ["near"]


def test_proposals_keep_numbers_in_range_once():
    ans = {"replaces": [{"n": 2, "partial": True}, {"n": "1"}, {"n": 2}, {"n": 9}, {"n": "x"}, "junk"]}
    assert [(p["n"], p["partial"]) for p in wp.proposals(ans, 3)] == [(2, True), (1, False)]
    assert wp.proposals(None, 3) == [] and wp.proposals({"replaces": None}, 3) == []


def test_replaces_metrics_hit_false_partial_and_retrieved():
    pair = wp.replace_pairs([T], EPISODES, EDGES)[0][0]
    cands = ["near", "old"]
    m = wp.replaces_metrics(pair, cands, [{"n": 2, "partial": True, "what": ""}, {"n": 1, "partial": False, "what": ""}])
    assert m == {"hit": [1, 1], "false": [1, 2], "retrieved": [1, 1], "partial_ok": [1, 1]}
    assert wp.replaces_metrics(pair, cands, []) == {"hit": [0, 1], "false": [0, 0], "retrieved": [1, 1]}
    assert wp.replaces_metrics(pair, ["near"], [{"n": 1, "partial": False, "what": ""}])["retrieved"] == [0, 1]


def test_run_replaces_shows_the_candidates_and_skips_the_engine_with_none():
    pairs = wp.replace_pairs([T], EPISODES, EDGES)[0]
    seen = []

    def ask(system, user, max_tokens):
        seen.append(user)
        assert system == wp.prompts.REPLACES
        return answer({"replaces": [{"n": 2, "partial": True, "what": "X no longer runs on node 1"}]})

    recs = wp.run_replaces(pairs, EPISODES, lambda text: ["near", "old"], ask)
    assert "X moved to node 2." in seen[0] and "[1] (2026-02-01)" in seen[0] and "[2] (2026-01-01)" in seen[0]
    assert recs[0]["proposed"] == [{"episode": "old", "partial": True, "what": "X no longer runs on node 1"}]
    assert recs[0]["m"]["hit"] == [1, 1] and recs[0]["m"]["partial_ok"] == [1, 1]
    none = wp.run_replaces(pairs, EPISODES, lambda text: ["later"], ask)
    assert len(seen) == 1 and none[0]["m"]["hit"] == [0, 1] and "tokens" not in none[0]   # no call, no cost
    bad = wp.run_replaces(pairs, EPISODES, lambda text: ["old"], lambda *a: ("no json here", {}))
    assert bad[0]["error"] == "the answer is not JSON"
    down = wp.run_replaces(pairs, EPISODES, lambda text: 1 / 0, ask)
    assert down[0]["error"].startswith("ZeroDivisionError")


def test_replaces_end_to_end_with_a_fake_brain(tmp_path, capsys):
    eps, edges = dict(EPISODES), dict(EDGES)
    for i in range(20):
        eps[f"old{i}"] = {**EPISODES["old"], "uuid": f"old{i}"}
        eps[f"new{i}"] = {**EPISODES["new"], "uuid": f"new{i}", "content": f"X moved to node 2 (#{i})."}
        edges[f"f{i}"] = {**EDGES["f-old"], "uuid": f"f{i}", "episodes": [f"old{i}"]}
    gold = [{**T, "id": f"t{i}", "answer_episodes": [f"new{i}"], "stale": [f"f{i}"]} for i in range(20)]
    gold += [{**T, "id": "draft", "validated": False, "answer_episodes": ["new"]}]
    (tmp_path / "gold.jsonl").write_text("".join(json.dumps(q) + "\n" for q in gold), encoding="utf-8")
    calls = []

    def ask(system, user, max_tokens):
        calls.append(user)
        return answer({"replaces": [{"n": 2, "partial": True}]})

    out = tmp_path / "rep.json"
    assert wp.main(["replaces", "--brain", "b", "--gold", str(tmp_path / "gold.jsonl"), "--out", str(out)],
                   ask=ask, brain=(eps, edges, lambda text: ["near", "old" + text.split("#")[1].split(")")[0]])) == 0
    res = json.loads(out.read_text(encoding="utf-8"))
    assert len(calls) == 20 and res["meta"]["drafts_included"] is False
    rows = {r["metric"]: r for r in res["summary"]["rows"]}
    assert rows["hit"]["value"] == 1 and rows["false"]["value"] == 0 and rows["false"]["n"] == 20
    assert "## `replaces` proposal" in capsys.readouterr().out


# --- P1 / P0 --------------------------------------------------------------------------------------------------------------------

def _s(**rows):
    return {"rows": [{"metric": k, "value": v[0], "lo": v[1], "hi": v[2], "n": 50} for k, v in rows.items()]}


def test_p1_needs_every_interval_on_its_side():
    gate = _s(precision_reject=(0.9, 0.82, 0.96))
    rep = _s(hit=(0.85, 0.72, 0.94), false=(0.04, 0.0, 0.09))
    assert wp.p1(gate, rep) == {"result": "P1", "checks": {"gate": "met", "hit": "met", "false": "met"}, "weaker": []}
    crossing = _s(precision_reject=(0.85, 0.74, 0.93))   # the point is above 0.8, the interval crosses it
    v = wp.p1(crossing, rep)
    assert v["result"] == "P0" and v["checks"]["gate"] == "not met" and v["weaker"] == ["gate"]
    v = wp.p1(gate, _s(hit=(0.85, 0.72, 0.94), false=(0.08, 0.02, 0.15)))
    assert v["result"] == "P0" and v["weaker"] == ["replaces"]
    assert wp.p1(gate, None)["checks"] == {"gate": "met", "hit": "not measured", "false": "not measured"}


def test_report_prints_both_tables_and_the_reading(tmp_path, capsys):
    meta = {"prompt": "gate-v1", "model": "m"}
    gate = {"meta": meta, "summary": {**_s(precision_reject=(0.9, 0.82, 0.96)), "records": 60, "errors": 1},
            "cost": {"notes": 59, "tokens_in": 800, "tokens_out": 20, "per_note": 0.0002}, "skipped": {"unlabelled": 3}}
    rep = {"meta": {**meta, "prompt": "replaces-v1"}, "summary": {**_s(hit=(0.85, 0.72, 0.94), false=(0.04, 0.0, 0.09)),
           "records": 40, "errors": 0}, "cost": {"notes": 0}, "skipped": {}}
    (tmp_path / "g.json").write_text(json.dumps(gate), encoding="utf-8")
    (tmp_path / "r.json").write_text(json.dumps(rep), encoding="utf-8")
    assert wp.main(["report", "--gate", str(tmp_path / "g.json"), "--replaces", str(tmp_path / "r.json")]) == 0
    text = capsys.readouterr().out
    assert "60 notes, 1 failed" in text and "| precision_reject | 50 | 90.0 | 82.0 – 96.0 |" in text
    assert "800 tokens in and 20 out per note, about 0.00020 per note" in text and "Left out: 3 unlabelled." in text
    assert "the engine reported no token usage" in text and "**#491: P1**" in text
    with pytest.raises(SystemExit, match="no results yet"):
        wp.main(["report", "--gate", str(tmp_path / "x.json"), "--replaces", str(tmp_path / "y.json")])


def test_intervals_do_not_shrink_to_a_point_on_small_unanimous_sets():
    lo, hi = wp.wilson(5, 5)
    assert lo == pytest.approx(0.566, abs=0.01) and hi == 1
    recs = [{"id": i, "m": {"precision_reject": [1, 1]}} for i in range(5)]
    row = wp.summarize(recs, ("precision_reject",), n=200)["rows"][0]
    assert row["value"] == 1 and row["lo"] < 0.8   # the bootstrap alone would say 1 – 1
    v = wp.p1(wp.summarize(recs, ("precision_reject",), n=200), _s(hit=(0.85, 0.72, 0.94), false=(0.04, 0.0, 0.09)))
    assert v["result"] == "P0" and v["checks"]["gate"] == "not met"
    assert wp.wilson(0, 0) == (None, None)


def test_answers_parse_past_reasoning_and_extra_objects_and_both_token_names():
    assert wp.parse_json('{"kind":"note"} or maybe {"kind":"dump"}') == {"kind": "note"}
    assert wp.parse_json('<think>the {kind} is...</think>```json\n{"kind":"dump"}\n```') == {"kind": "dump"}
    assert wp.parse_json("[1, 2]") is None and wp.parse_json("") is None
    assert wp._tokens({"input_tokens": 7, "output_tokens": 2}) == {"in": 7, "out": 2}
    assert wp._tokens(None) == {"in": None, "out": None}


def test_the_calls_count_for_the_eval_and_are_written_before_exit(monkeypatch):
    from mimirsynth import usage
    seen = []
    monkeypatch.setattr(usage, "flush", lambda: seen.append("flush") or 0)
    with wp.counted():
        assert usage.current() == (0, "eval")   # the instance, never the brain's budget
    assert seen == ["flush"] and usage.current() != (0, "eval")
