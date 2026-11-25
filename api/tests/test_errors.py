"""The error analysis of Phase 0 (#515): the mechanical classes of each miss and each noisy item, the sheet, and the summary per
class, question class and component. All on fixtures: the recall's output is written by the app's own build_context; no brain."""
import importlib.util
import json
from pathlib import Path

import pytest

from mimirsynth.recall import build_context

ER = Path(__file__).resolve().parents[2] / "eval" / "errors" / "errors.py"
spec = importlib.util.spec_from_file_location("eval_errors", ER)
er = importlib.util.module_from_spec(spec)
spec.loader.exec_module(er)

PARAMS = {"n_facts": 2, "n_chunks": 1, "max_chars": 100000}


def F(uuid, text, episodes, status="current", similarity=0.6, **kw):
    return {"uuid": uuid, "fact": text, "episodes": episodes, "status": status, "valid_at": "2026-01-01", "created_at": "2026-01-01",
            "invalid_at": "2026-02-01" if status == "invalidated" else None, "similarity": similarity, **kw}


def C(cid, text, episode, similarity=0.5):
    return {"id": cid, "text": text, "episode_uuid": episode, "name": f"note {cid}", "valid_at": "2026-01-01", "similarity": similarity}


def R(qid, cls, facts=(), chunks=(), shown=None, answer=("e1",), cands=None, snapshot=None, **kw):
    """A question's record as `candidates` writes it. `shown`: the facts and chunks the context holds (default: all returned)."""
    facts, chunks = list(facts), list(chunks)
    sf, sc = shown if shown is not None else (facts, chunks)
    out = {"facts": facts, "chunks": chunks, "documents": [], "min_similarity": 0.3,
           "context": build_context(list(sf), list(sc), 100000, [])}
    rec = {"id": qid, "class": cls, "query": "where does X run", "answer_episodes": list(answer), "params": PARAMS, "out": out,
           "candidates": cands or {"facts": [], "chunks": []},
           "snapshot": snapshot or {e: {"in": True, "facts": True} for e in answer}, **kw}
    return rec


def only(rows, unit):
    return [r for r in rows if r["unit"] == unit]


def test_a_hit_in_the_first_three_gives_no_miss_and_the_rest_is_noise():
    rows = er.classify(R("q1", "point", [F("f1", "X runs on node 1", ["e1"]), F("f2", "Y is blue", ["e9"])]))
    assert only(rows, "miss") == []
    (n,) = only(rows, "noise")
    assert n["suggested"] == n["class"] == 9 and n["what"] == "fact" and n["why"].startswith("similarity 0.600")


def test_an_answer_after_the_first_three_is_ranked_below_the_cut():
    facts = [F(f"f{i}", f"noise {i}", ["e9"]) for i in range(3)] + [F("fa", "X runs on node 1", ["e1"])]
    (m,) = only(er.classify(R("q1", "point", facts)), "miss")
    assert (m["suggested"], m["class"]) == (5, 5) and "item 4" in m["why"]


def test_returned_but_cut_out_of_the_context_is_the_budget():
    fa = F("fa", "X runs on node 1", ["e1"])
    (m,) = only(er.classify(R("q1", "point", [fa], shown=([], []))), "miss")
    assert (m["suggested"], m["class"]) == (8, 8)


def test_a_candidate_below_the_cut_or_the_threshold_says_which():
    cands = {"facts": [{"uuid": f"x{i}", "episodes": ["e9"], "similarity": 0.5} for i in range(6)]
             + [{"uuid": "fa", "episodes": ["e1"], "similarity": 0.45}],
             "chunks": [{"id": 3, "episode_uuid": "e1", "similarity": 0.1}]}
    (m,) = only(er.classify(R("q1", "point", [F("f9", "noise", ["e9"])], cands=cands)), "miss")
    assert (m["suggested"], m["class"]) == (5, 5)
    assert "facts rank 7, the recall returns 2" in m["why"] and "chunks rank 1, similarity 0.100 under the threshold 0.3" in m["why"]


def test_in_no_top_50_is_not_among_the_candidates_unless_the_snapshot_lacks_it():
    (m,) = only(er.classify(R("q1", "point")), "miss")
    assert (m["suggested"], m["class"], m["hint"]) == (4, 4, "")
    (m,) = only(er.classify(R("q1", "point", snapshot={"e1": {"in": True, "facts": False}})), "miss")
    assert (m["suggested"], m["class"]) == (4, 4) and m["hint"].endswith("3?")
    (m,) = only(er.classify(R("q1", "point", snapshot={"e1": {"in": False, "facts": False}})), "miss")
    assert (m["suggested"], m["class"]) == (1, "") and "does not hold" in m["hint"]   # left for a person


def test_entity_questions_spread_past_the_limit_and_the_missing_episodes_only():
    answer = ("e1", "e2", "e3", "e4")
    found = {"facts": [], "chunks": [{"id": i, "episode_uuid": e, "similarity": 0.6} for i, e in enumerate(answer)]}
    (m,) = only(er.classify(R("q2", "entity", [F("f1", "X has A", ["e1"])], answer=answer, cands=found)), "miss")
    assert (m["suggested"], m["class"]) == (7, 7) and m["why"].startswith("4 answer episodes for 3 items")
    # past the limit, but the missing ones are in no top 50: the limit is not why
    (m,) = only(er.classify(R("q2", "entity", [F("f1", "X has A", ["e1"])], answer=answer)), "miss")
    assert (m["suggested"], m["class"]) == (4, 4)
    # an entity question is never "after the first three": it is scored on coverage
    facts = [F(f"n{i}", f"noise {i}", ["e9"]) for i in range(3)] + [F("f1", "X has A", ["e1"]), F("f2", "X has B", ["e2"])]
    assert only(er.classify(R("q2", "entity", facts, answer=("e1", "e2"))), "miss") == []
    # within the limit: the stage of the episodes it missed, not of the one it found
    cands = {"facts": [{"uuid": "f1", "episodes": ["e1"], "similarity": 0.9}], "chunks": [{"id": 1, "episode_uuid": "e2", "similarity": 0.6}]}
    (m,) = only(er.classify(R("q2", "entity", [F("f1", "X has A", ["e1"])], answer=("e1", "e2"), cands=cands)), "miss")
    assert (m["suggested"], m["class"]) == (5, 5) and m["why"] == "chunks rank 1, the recall returns 1"


def test_out_of_domain_and_hook_silence_misses_are_noise():
    rec = R("q3", "ood", [F("f1", "Y is blue", ["e9"])], answer=())
    rows = er.classify(rec)
    assert [(r["unit"], r["class"]) for r in rows] == [("miss", 9), ("noise", 9)]
    assert er.classify(R("q3", "ood", answer=())) == []   # an empty context is right
    hook = R("h1", "hook", [F("f1", "Y is blue", ["e9"])], answer=(), label="nothing")
    assert [(r["unit"], r["what"], r["class"]) for r in er.classify(hook)] == [("miss", "hook_silence", 9), ("noise", "fact", 9)]


def test_a_hook_prompt_that_missed_its_note_is_staged_like_a_question():
    hook = R("h2", "hook", [F("f1", "Y is blue", ["e9"])], answer=(), label="e1", snapshot={"e1": {"in": True, "facts": True}})
    rows = er.classify(hook)
    assert [(r["unit"], r["what"], r["class"]) for r in rows] == [("miss", "hook_precision", 4), ("noise", "fact", 9)]
    hit = R("h3", "hook", [F("f1", "X runs on node 1", ["e1"])], answer=(), label="e1")
    assert er.classify(hit) == []
    empty = R("h4", "hook", answer=(), label="e1", snapshot={"e1": {"in": True, "facts": True}})
    assert [(r["what"], r["class"]) for r in er.classify(empty)] == [("hook_injected", 4)]


def test_stale_as_current_is_left_for_a_person_and_linked_noise_says_so():
    old = F("fo", "X runs on node 1", ["e0"])   # Graphiti did not invalidate it
    linked = F("fl", "Z moved", ["e8"], similarity=None, replaces="Z was here")
    rec = R("q4", "temporal", [F("fn", "X runs on node 2", ["e1"]), old, linked], stale=["fo"])
    rows = er.classify(rec)
    (s,) = only(rows, "stale")
    assert (s["suggested"], s["class"]) == ("", "") and "fact fo" in s["why"]   # nothing in the snapshot to go on
    noise = {r["why"].split(";")[0] for r in only(rows, "noise")}
    assert "came in through a link: replaces a fact in the result" in noise and "similarity 0.600" in noise


def test_stale_rows_get_a_hint_from_the_snapshot_and_no_class():
    def stale(info, snapshot):
        rec = R("q4", "temporal", [F("fn", "X runs on node 2", ["e1"]), F("fo", "X runs on node 1", ["e0"])], stale=["fo"],
                snapshot=snapshot)
        rec["stale_info"] = info
        (s,) = only(er.classify(rec), "stale")
        return s

    dated = {"e1": {"in": True, "facts": True, "valid_at": "2026-03-01"}}
    s = stale({"fo": {"invalid": True, "episodes": ["e0"]}, "e0": {"valid_at": "2026-01-01"}}, dated)
    assert (s["suggested"], s["class"]) == (6, "") and "invalidated or expired" in s["hint"]
    s = stale({"fo": {"invalid": False, "episodes": ["e0"]}, "e0": {"valid_at": "2026-01-01"}}, dated)
    assert (s["suggested"], s["class"]) == (6, "") and "dated after every stale episode" in s["hint"]
    s = stale({"fo": {"invalid": False, "episodes": ["e0"]}, "e0": {"valid_at": "2026-01-01"}},
              {"e1": {"in": False, "facts": False, "valid_at": ""}})
    assert (s["suggested"], s["class"]) == (2, "") and "only episodes with the answer are the stale ones" in s["hint"]
    s = stale({"fo": {"invalid": False, "episodes": ["e0"]}, "e0": {"valid_at": "2026-05-01"}}, dated)
    assert (s["suggested"], s["class"]) == ("", "")   # the answer is older than the stale note: a person reads it


def test_errors_and_unparsed_contexts_are_their_own_rows():
    assert er.classify({"id": "q5", "class": "point", "error": "EmbeddingDown: x"})[0]["unit"] == "error"
    rec = R("q6", "point", [F("f1", "X runs on node 1", ["e1"])])
    rec["out"]["context"] = "a context in another format"
    assert er.classify(rec)[0]["why"].startswith("unparsed context")


def test_summary_shares_per_class_and_component_and_leaves_out_the_unclassified():
    rows = [{"id": "q1", "qclass": "point", "unit": "miss", "class": "4", "why": ""},
            {"id": "q2", "qclass": "point", "unit": "miss", "class": "5", "why": ""},
            {"id": "q3", "qclass": "temporal", "unit": "stale", "class": "6", "why": ""},
            {"id": "q4", "qclass": "temporal", "unit": "stale", "class": "", "why": ""},
            {"id": "q5", "qclass": "point", "unit": "miss", "class": "12", "why": ""},
            {"id": "q6", "qclass": "point", "unit": "error", "class": "", "why": "x"},
            {"id": "q1", "qclass": "point", "unit": "noise", "what": "fact", "class": "9", "why": "came in through a link: x"},
            {"id": "q1", "qclass": "point", "unit": "noise", "what": "chunk", "class": "9", "why": "similarity 0.4"}]
    s = er.summarize(rows)
    assert s["by_qclass"] == {"point": {4: 1, 5: 1}, "temporal": {6: 1}} and s["all"] == {4: 1, 5: 1, 6: 1}
    assert s["unclassified"] == {"temporal": 1, "point": 1} and s["errors"] == 1
    assert s["noise"] == {"fact · through a link": 1, "chunk · above the threshold": 1}
    md = er.summary_markdown(s)
    assert "| point | 2 | 0 | 0 | 0 | 50 | 50 |" in md
    assert "| 6 | stale shown as current | invalidation | 1 | 33 |" in md
    assert "| fact · through a link | 1 |" in md and "2 rows with no class yet" in md and "1 recalls that failed or could not be read" in md


def test_end_to_end_with_a_fake_snapshot(tmp_path, capsys):
    gold = [{"id": "q1", "class": "point", "query": "where does X run", "answer_episodes": ["e1"], "validated": True},
            {"id": "q2", "class": "ood", "query": "what is the moon", "validated": True},
            {"id": "q3", "class": "point", "query": "draft", "answer_episodes": ["e1"], "validated": False}]
    (tmp_path / "gold.jsonl").write_text("".join(json.dumps(q) + "\n" for q in gold), encoding="utf-8")
    (tmp_path / "hook.jsonl").write_text(json.dumps({"id": "h1", "query": "hi", "label": "nothing"}) + "\n", encoding="utf-8")
    seen = {}

    def gather(slug, items, params):
        seen["ids"], seen["params"] = [i["id"] for i in items], params
        return [R(i["id"], i.get("class") or "hook", [F("f1", "Y is blue", ["e9"])], answer=i.get("answer_episodes") or (),
                  label=i.get("label")) for i in items]

    cand = tmp_path / "c.jsonl"
    assert er.main(["candidates", "--brain", "b", "--gold", str(tmp_path / "gold.jsonl"), "--hookset", str(tmp_path / "hook.jsonl"),
                    "--split", "all", "--out", str(cand)], gather_fn=gather) == 0
    assert seen["ids"] == ["q1", "q2", "h1"] and seen["params"]["n_facts"] == 6
    cand = cand.rename(tmp_path / "candidates-plugin-all.jsonl")
    assert er.main(["sheet", "--candidates", str(cand)]) == 0
    sheet = tmp_path / "errors-plugin-all.csv"   # the name follows the candidates file
    assert sheet.exists()
    with pytest.raises(SystemExit, match="may hold your classes"):
        er.main(["sheet", "--candidates", str(cand)])
    assert er.main(["summarize", "--sheet", str(sheet)]) == 0
    text = capsys.readouterr().out
    assert "## Error analysis of 0.17 (#515)" in text and "| fact · above the threshold | 3 |" in text


def test_only_the_restored_instance_gathers(tmp_path, monkeypatch):
    monkeypatch.delenv("MIMIRSYNTH_EVAL_SNAPSHOT", raising=False)
    (tmp_path / "gold.jsonl").write_text(json.dumps({"id": "q1", "class": "ood", "query": "x", "validated": True}) + "\n",
                                         encoding="utf-8")
    with pytest.raises(SystemExit, match="MIMIRSYNTH_EVAL_SNAPSHOT=1"):
        er.main(["candidates", "--brain", "b", "--gold", str(tmp_path / "gold.jsonl"), "--split", "all"])
