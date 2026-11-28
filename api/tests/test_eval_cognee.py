"""Cognee as an external baseline arm of the eval (#526), with a fake Cognee client: results mapped back to episodes, an unmapped
result counted as noise, the budget cut, the guards (snapshot and separate instance), the cost prompt, and the arm scored by
`run.py` like any other system."""
import importlib.util
import json
from collections import Counter
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
cg = _load("eval_cognee", EVAL / "adapters" / "cognee_arm.py")
ld = _load("eval_cognee_load", EVAL / "adapters" / "cognee_load.py")

E1 = {"uuid": "e1", "reference_time": "2026-01-05T10:00:00", "text": "2026-01-05\nThe backup server powers off at 23:00 every night."}
E2 = {"uuid": "e2", "reference_time": "2026-02-01T10:00:00", "text": "2026-02-01\nVaultwarden runs on LXC 104."}
DUP = {"uuid": "e3", "reference_time": "2026-03-01T10:00:00", "text": "2026-02-01\nVaultwarden runs on LXC 104."}
Q = {"id": "q1", "class": "point", "query": "when does the backup server power off", "answer_episodes": ["e1"], "validated": True}


class FakeCognee:
    """The client's methods, in memory: `results` per query, LLM calls per episode cognified, and errors to raise first."""

    def __init__(self, results=None, calls_per_episode=3, version="1.6.11", fail=()):
        self.results, self.cpe, self.version = results or {}, calls_per_episode, version
        self.added, self.cognified, self.searched, self.pending = [], [], [], []
        self.fail = list(fail)
        self.calls = 0 if calls_per_episode is not None else None

    def _maybe_fail(self, what):
        if self.fail and self.fail[0] == what:
            self.fail.pop(0)
            raise TimeoutError(f"{what} timed out")

    def add(self, episode):
        self._maybe_fail("add")
        self.added.append(episode["uuid"])
        self.pending.append(episode["uuid"])

    def cognify(self):
        self._maybe_fail("cognify")
        self.cognified.append(list(self.pending))
        if self.calls is not None:
            self.calls += self.cpe * len(self.pending)
        self.pending = []

    def search(self, query, top_k):
        self.searched.append((query, top_k))
        return self.results.get(query, [])[:top_k]

    def llm_calls(self):
        return self.calls

    def describe(self):
        return {"version": self.version, "search": "CHUNKS", "llm": {"LLM_MODEL": "m"}, "embedding": {"EMBEDDING_MODEL": "e"}}


def search_fn(results, ms=7):
    return lambda q, k: (results.get(q, [])[:k], ms)


def recall(results, episodes=(E1, E2)):
    fn, stats = cg.make_recall(search_fn(results), list(episodes), build_context)
    return fn, stats


# --- mapping and scoring -------------------------------------------------------------------------------------------------------------

def test_a_result_maps_back_to_its_episode_whitespace_aside_and_scores_as_a_match():
    fn, stats = recall({Q["query"]: [{"text": "The backup  server powers off\nat 23:00", "id": "c1", "score": 0.1}]})
    out = fn(Q["query"], n_facts=8, n_chunks=4, max_chars=2500)
    assert out["chunks"][0]["episode_uuid"] == "e1" and out["chunks"][0]["valid_at"] == E1["reference_time"]
    items = ev.context_items(out)
    assert [it["episodes"] for it in items] == [["e1"]]
    r = ev.score(Q, items, out["ms"]["total"], out["context"])
    assert r["m"]["top3"] == [1, 1] and r["ms"] == 7
    assert stats == Counter({"results": 1})


def test_an_unmapped_result_is_noise_never_a_match():
    fn, stats = recall({Q["query"]: [{"text": "The backup server powers off at 23:00 sharp, says an invented summary."}]})
    out = fn(Q["query"], n_facts=8, n_chunks=4, max_chars=2500)
    items = ev.context_items(out)
    assert items and items[0]["episodes"] == []
    r = ev.score(Q, items, None, out["context"])
    assert r["m"]["top3"] == [0, 1]
    assert r["m"]["noise"][0] == r["m"]["noise"][1] == len(out["context"]) > 0
    assert stats["unmapped"] == 1


def test_a_text_loaded_for_two_episodes_maps_to_both():
    q = {**Q, "query": "where does vaultwarden run", "answer_episodes": ["e3"]}
    fn, stats = recall({q["query"]: [{"text": "Vaultwarden runs on LXC 104."}]}, (E1, E2, DUP))
    out = fn(q["query"], n_facts=8, n_chunks=4, max_chars=2500)
    items = ev.context_items(out)
    assert items[0]["episodes"] == ["e2", "e3"] and out["chunks"][0]["episode_uuid"] is None
    assert ev.score(q, items, None, out["context"])["m"]["top3"] == [1, 1]
    assert stats["duplicates"] == 1 and stats["unmapped"] == 0


def test_a_chunk_found_in_different_episodes_is_noise_not_a_match_for_all_of_them():
    eps = [{"uuid": f"e{i}", "reference_time": None, "text": f"Note {i} about something else.\nGracias."} for i in range(30)]
    q = {**Q, "query": "x", "answer_episodes": ["e17"]}
    fn, stats = cg.make_recall(lambda q_, k: ([{"text": "Gracias."}], 1), eps, build_context)
    out = fn("x", n_facts=8, n_chunks=4, max_chars=2500)
    items = ev.context_items(out)
    assert items[0]["episodes"] == [] and ev.score(q, items, None, out["context"])["m"]["top3"] == [0, 1]
    assert stats["ambiguous"] == 1 and stats["unmapped"] == 1


def test_results_wrapped_per_dataset_or_not_text_are_flattened():
    raw = [{"dataset_name": "d", "search_result": [{"text": "a", "id": 5}, "plain string"]}, {"text": "b", "score": 0.3}, 42, None]
    assert cg.results_of(raw) == [{"text": "a", "id": "5"}, {"text": "plain string"}, {"text": "b", "score": 0.3}, {"text": "42"}]


def test_a_dataset_cognee_could_not_search_fails_the_question_instead_of_scoring_empty(env):
    with pytest.raises(RuntimeError, match="boom"):
        cg.results_of([{"dataset_name": "d", "search_result": [], "error": "boom"}])
    mp = _loaded(env)
    g = _gold(env, [Q])
    res = env / "res.jsonl"

    class Broken(FakeCognee):
        def search(self, query, top_k):
            return [{"dataset_name": "d", "search_result": [], "error": "no searchable memory"}]

    assert cg.main(["search", "--brain", "b", "--gold", str(g), "--map", str(mp), "--out", str(res)], client=Broken()) == 1
    row = json.loads(res.read_text(encoding="utf-8").splitlines()[0])
    assert "no searchable memory" in row["error"] and row["raw"][0]["error"] == "no searchable memory"
    assert ev.main(["run", "--brain", "b", "--gold", str(g), "--split", "all", "--system", "cognee", "--cognee-map", str(mp),
                    "--cognee-results", str(res), "--out", str(env / "r.json")]) == 1
    assert json.loads((env / "r.json").read_text(encoding="utf-8"))["records"][0]["error"].startswith("RuntimeError")


def test_the_stored_raw_output_is_what_gets_scored(env):
    mp = _loaded(env)
    g = _gold(env, [Q])
    res = env / "res.jsonl"
    wrapped = [{"dataset_name": "d", "dataset_id": "x", "search_result": [{"text": "Vaultwarden runs on LXC 104.", "id": 1}]}]
    fake = FakeCognee({Q["query"]: wrapped})
    fake.search = lambda q, k: wrapped
    cg.main(["search", "--brain", "b", "--gold", str(g), "--map", str(mp), "--out", str(res)], client=fake)
    row = json.loads(res.read_text(encoding="utf-8").splitlines()[0])
    assert row["raw"] == wrapped and row["results"] == [{"text": "Vaultwarden runs on LXC 104.", "id": "1"}]
    fn, _ = cg.make_recall(cg.from_results(res), [E1, E2], build_context)
    assert fn(Q["query"], n_facts=6, n_chunks=3, max_chars=4000)["chunks"][0]["episode_uuid"] == "e2"


# --- the budget ----------------------------------------------------------------------------------------------------------------------

def test_cognee_gets_as_many_results_as_the_recall_may_show_and_the_same_characters():
    seen = []
    long = "word " * 2000
    ep = {"uuid": "e9", "reference_time": None, "text": long}

    def fn_search(q, k):
        seen.append(k)
        return [{"text": long[:3000]}, {"text": "Vaultwarden runs on LXC 104."}], 3

    fn, stats = cg.make_recall(fn_search, [ep, E2], build_context)
    out = fn("x", n_facts=6, n_chunks=3, max_chars=2500)
    assert seen == [9]
    assert len(out["context"]) <= 2500
    assert len(out["chunks"]) == 1 and stats["cut"] == 1   # the long one is cut to what is left; nothing is added after it
    piece = out["chunks"][0]["text"]
    assert len(piece) >= cg.MIN_PIECE and not piece.endswith(" wo") and piece in long
    assert ev.context_items(out)[0]["episodes"] == ["e9"]   # a cut chunk still maps to its episode


def test_what_does_not_fit_is_left_out_and_a_tiny_remainder_is_not_kept():
    first = "A" * 2400   # leaves ~50 characters: the next result does not fit whole, and less than MIN_PIECE of it would
    eps = [{"uuid": "a", "reference_time": None, "text": first}, E1]
    fn, stats = cg.make_recall(lambda q, k: ([{"text": first}, {"text": "The backup server powers off at 23:00 every night."}], 1),
                               eps, build_context)
    out = fn("x", n_facts=8, n_chunks=4, max_chars=2500)
    assert [c["episode_uuid"] for c in out["chunks"]] == ["a"] and stats["cut"] == 0
    assert "backup" not in out["context"]


def test_a_repeated_text_does_not_count_as_fitting_twice_and_the_next_one_is_still_cut_in():
    big = "B " * 1100
    eps = [{"uuid": "a", "reference_time": None, "text": big}, {"uuid": "b", "reference_time": None, "text": "C " * 2000}]
    fn, stats = cg.make_recall(lambda q, k: ([{"text": big}, {"text": big}, {"text": "C " * 1500}], 1), eps, build_context)
    out = fn("x", n_facts=6, n_chunks=3, max_chars=4000)
    # the repeat does not fit whole (its text being in the context already is not fitting): it is the one cut to what is left
    assert [c["episode_uuid"] for c in out["chunks"]] == ["a", "a"] and stats["cut"] == 1
    assert len(out["chunks"][1]["text"]) < len(big.strip()) and 3800 < len(out["context"]) <= 4000
    assert len(ev.context_items(out)) == 2


def test_nothing_returned_is_an_empty_context():
    fn, _ = recall({})
    out = fn("payroll", n_facts=8, n_chunks=4, max_chars=2500)
    assert out["context"] == "" and ev.score({"id": "o", "class": "ood", "query": "payroll"}, [], None, "")["m"]["empty_ok"] == [1, 1]


# --- guards --------------------------------------------------------------------------------------------------------------------------

def test_the_separate_instance_needs_its_own_folder_and_no_database_server(tmp_path):
    with pytest.raises(SystemExit, match="MIMIRSYNTH_EVAL_COGNEE_ROOT"):
        cg.instance_guard({})
    with pytest.raises(SystemExit, match="VECTOR_DB_URL"):
        cg.instance_guard({"MIMIRSYNTH_EVAL_COGNEE_ROOT": str(tmp_path), "VECTOR_DB_URL": "postgresql://prod"})
    assert cg.instance_guard({"MIMIRSYNTH_EVAL_COGNEE_ROOT": str(tmp_path)}) == tmp_path.resolve()


def test_cognee_s_own_env_file_cannot_point_it_back_at_production(tmp_path):
    """Importing Cognee loads a .env over the environment: it is pointed at an empty file under the root, and a COGNEE_ENV_FILE
    already set is refused."""
    with pytest.raises(SystemExit, match="unset COGNEE_ENV_FILE"):
        cg.prepare_env(tmp_path, {"COGNEE_ENV_FILE": "/home/me/.env"})
    env = {}
    cg.prepare_env(tmp_path / "inst", env)
    assert Path(env["COGNEE_ENV_FILE"]).read_text(encoding="utf-8") == ""
    assert env["SYSTEM_ROOT_DIRECTORY"].startswith(str(tmp_path / "inst"))


def test_export_and_load_refuse_to_start_without_the_snapshot_flag(tmp_path, monkeypatch):
    monkeypatch.delenv("MIMIRSYNTH_EVAL_SNAPSHOT", raising=False)
    calls = []
    with pytest.raises(SystemExit, match="MIMIRSYNTH_EVAL_SNAPSHOT=1"):
        ld.main(["export", "--brain", "b", "--out", str(tmp_path / "m.json")], snapshot=lambda s: calls.append(s))
    with pytest.raises(SystemExit, match="MIMIRSYNTH_EVAL_SNAPSHOT=1"):
        ld.main(["load", "--brain", "b", "--map", str(tmp_path / "m.json")], client=FakeCognee())
    assert calls == []


# --- export and load -----------------------------------------------------------------------------------------------------------------

def _snapshot(n=25):
    eps = [{"uuid": f"u{i:02d}", "content": f"note {i}", "valid_at": f"2026-01-{i + 1:02d}T09:00:00"} for i in range(n)]
    eps.append({"uuid": "empty", "content": "  ", "valid_at": None})
    return lambda slug: ({"slug": slug}, {"episodes": list(reversed(eps))})


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("MIMIRSYNTH_EVAL_SNAPSHOT", "1")
    monkeypatch.setenv("MIMIRSYNTH_EVAL_COGNEE_ROOT", str(tmp_path / "cognee"))
    for k in cg.REMOTE_ENV:
        monkeypatch.delenv(k, raising=False)
    return tmp_path


def test_export_writes_the_episodes_oldest_first_with_their_date_and_leaves_out_the_clean_drop(env):
    out = env / "m.json"
    assert ld.main(["export", "--brain", "b", "--out", str(out)], snapshot=_snapshot(3)) == 0
    m = json.loads(out.read_text(encoding="utf-8"))
    assert [e["uuid"] for e in m["episodes"]] == ["u00", "u01", "u02"]   # the empty episode is left out
    assert m["episodes"][0]["text"] == "2026-01-01\nnote 0" and m["corpus"] == "full" and m["loaded"] == []
    cur = env / "curated.json"
    cur.write_text(json.dumps({"brain": "b", "rule": {}, "cells": [], "drop": ["u01"]}), encoding="utf-8")
    ld.main(["export", "--brain", "b", "--corpus", "clean", "--curated", str(cur), "--out", str(env / "c.json")],
            snapshot=_snapshot(3))
    c = json.loads((env / "c.json").read_text(encoding="utf-8"))
    assert [e["uuid"] for e in c["episodes"]] == ["u00", "u02"] and c["left_out"] == 1 and c["dataset"].endswith("-clean")


def test_load_runs_a_trial_prints_the_cost_and_stops_without_yes(env, capsys):
    path = env / "m.json"
    ld.main(["export", "--brain", "b", "--out", str(path)], snapshot=_snapshot(25))
    fake = FakeCognee(calls_per_episode=4)
    assert ld.main(["load", "--brain", "b", "--map", str(path)], client=fake) == 2
    assert fake.added == [f"u{i:02d}" for i in range(10)] and len(fake.cognified) == 1
    said = capsys.readouterr().out
    assert "15 episodes left, about 4 LLM calls each: about 60 LLM calls" in said and "--yes" in said
    m = json.loads(path.read_text(encoding="utf-8"))
    assert len(m["loaded"]) == 10 and m["llm_calls_per_episode"] == 4 and m["cognee"]["version"] == "1.6.11"

    assert ld.main(["load", "--brain", "b", "--map", str(path), "--yes", "--batch", "6"], client=fake) == 0
    assert fake.added[10:] == [f"u{i:02d}" for i in range(10, 25)]   # resumed, not reloaded
    assert [len(b) for b in fake.cognified] == [10, 6, 6, 3]            # serial batches, each cognified before the next
    assert len(json.loads(path.read_text(encoding="utf-8"))["loaded"]) == 25


def test_load_retries_and_needs_the_calls_per_episode_when_they_cannot_be_counted(env):
    path = env / "m.json"
    ld.main(["export", "--brain", "b", "--out", str(path)], snapshot=_snapshot(12))
    slept = []
    fake = FakeCognee(calls_per_episode=None, fail=("add", "cognify"))
    with pytest.raises(SystemExit, match="--calls-per-episode"):
        ld.main(["load", "--brain", "b", "--map", str(path)], client=fake, sleep=slept.append)
    assert slept == [5, 5] and len(fake.added) == 10   # each failure retried once, after a wait
    assert ld.main(["load", "--brain", "b", "--map", str(path), "--calls-per-episode", "2", "--yes"], client=fake,
                   sleep=slept.append) == 0
    assert len(json.loads(path.read_text(encoding="utf-8"))["loaded"]) == 12

    down = FakeCognee(fail=("cognify",) * 3)
    ld.main(["export", "--brain", "b", "--out", str(env / "n.json")], snapshot=_snapshot(3))
    with pytest.raises(SystemExit, match=r"cognify failed \(attempts: 3\)"):
        ld.main(["load", "--brain", "b", "--map", str(env / "n.json"), "--retries", "2"], client=down, sleep=lambda s: None)
    assert json.loads((env / "n.json").read_text(encoding="utf-8"))["loaded"] == []


def test_a_brain_loaded_with_another_cognee_version_is_not_mixed(env):
    path = env / "m.json"
    ld.main(["export", "--brain", "b", "--out", str(path)], snapshot=_snapshot(12))
    ld.main(["load", "--brain", "b", "--map", str(path)], client=FakeCognee())
    with pytest.raises(SystemExit, match="loaded with 1.6.11"):
        ld.main(["load", "--brain", "b", "--map", str(path), "--yes"], client=FakeCognee(version="1.7.0"))
    with pytest.raises(SystemExit, match="already has episodes loaded"):
        ld.main(["export", "--brain", "b", "--out", str(path)], snapshot=_snapshot(12))


# --- search and run.py ---------------------------------------------------------------------------------------------------------------

def _loaded(env, episodes=(E1, E2), corpus="full"):
    m = {"brain": "b", "corpus": corpus, "dataset": "d", "lang": "en", "episodes": list(episodes),
         "loaded": [e["uuid"] for e in episodes], "cognee": FakeCognee().describe()}
    cg.write_map(env / "m.json", m)
    return env / "m.json"


def _gold(env, rows):
    g = env / "gold.jsonl"
    g.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return g


def test_search_stores_every_question_at_each_budget_and_run_scores_it_as_cognee(env):
    mp = _loaded(env)
    ood = {"id": "o1", "class": "ood", "query": "payroll", "answer_episodes": [], "validated": True}
    g = _gold(env, [Q, ood])
    fake = FakeCognee({Q["query"]: [{"text": "The backup server powers off at 23:00 every night.", "id": "c1"},
                                    {"text": "made-up text"}]})
    res = env / "res.jsonl"
    assert cg.main(["search", "--brain", "b", "--gold", str(g), "--map", str(mp), "--out", str(res)], client=fake) == 0
    assert sorted(fake.searched) == sorted([(Q["query"], 9), ("payroll", 9), (Q["query"], 12), ("payroll", 12)])

    out = env / "r.json"
    assert ev.main(["run", "--brain", "b", "--gold", str(g), "--split", "all", "--budget", "plugin", "--system", "cognee",
                    "--cognee-map", str(mp), "--cognee-results", str(res), "--out", str(out), "--label", "cognee"]) == 0
    r = json.loads(out.read_text(encoding="utf-8"))
    assert r["meta"]["system"] == "cognee" and r["meta"]["cognee"]["version"] == "1.6.11" and r["meta"]["lang"] == "en"
    assert r["meta"]["results"] == {"results": 2, "unmapped": 1}
    rows = {(x["scope"], x["metric"]): x["value"] for x in r["summary"]["rows"]}
    assert rows[("point", "top3")] == 1 and rows[("ood", "empty_ok")] == 1 and 0 < rows[("all", "noise")] < 1


def test_run_refuses_another_corpus_or_an_unfinished_load_and_records_a_missing_question(env):
    mp = _loaded(env)
    g = _gold(env, [Q])
    res = env / "res.jsonl"
    res.write_text("", encoding="utf-8")
    base = ["run", "--brain", "b", "--gold", str(g), "--split", "all", "--system", "cognee", "--cognee-map", str(mp),
            "--cognee-results", str(res), "--out", str(env / "r.json")]
    with pytest.raises(SystemExit, match="--corpus full"):
        ev.main([*base, "--corpus", "clean"])
    assert ev.main(base) == 1   # the only question has no stored result: its recall fails and is recorded
    r = json.loads((env / "r.json").read_text(encoding="utf-8"))
    assert r["records"][0]["error"].startswith("LookupError")
    m = json.loads(mp.read_text(encoding="utf-8"))
    cg.write_map(mp, {**m, "loaded": ["e1"]})
    with pytest.raises(SystemExit, match="1 of the 2 episodes"):
        ev.main(base)


def test_search_refuses_another_cognee_version_than_the_load(env):
    mp = _loaded(env)
    g = _gold(env, [Q])
    with pytest.raises(SystemExit, match="loaded with 1.6.11"):
        cg.main(["search", "--brain", "b", "--gold", str(g), "--map", str(mp)], client=FakeCognee(version="1.7.0"))


# --- the scripts as the README runs them ---------------------------------------------------------------------------------------------

STUB = r'''
import json, os
from pathlib import Path

class SearchType:
    CHUNKS = "CHUNKS"

def _path():
    return Path(os.environ["SYSTEM_ROOT_DIRECTORY"]) / "stub-store.json"

def _read():
    return json.loads(_path().read_text()) if _path().exists() else {"added": [], "cognified": 0}

def _write(d):
    _path().parent.mkdir(parents=True, exist_ok=True)
    _path().write_text(json.dumps(d))

async def add(data, dataset_name=None, node_set=None, **kw):
    d = _read(); d["added"].append({"text": str(data), "node_set": node_set}); _write(d)

async def cognify(datasets=None, **kw):
    d = _read(); d["cognified"] += 1; _write(d)

async def search(query_text, query_type=None, datasets=None, top_k=15, **kw):
    hits = [{"text": a["text"].split(chr(10), 1)[-1], "id": i} for i, a in enumerate(_read()["added"])]
    return [{"dataset_name": datasets[0], "search_result": hits[:top_k]}]
'''


def test_the_scripts_run_by_path_reach_the_real_cognee_package_not_the_adapter(env):
    """Run as `python eval/adapters/<script>.py`, the script's folder comes first on sys.path: an adapter named like the package
    would be imported instead of Cognee. A stand-in `cognee` package on PYTHONPATH must be the one reached."""
    import os
    import subprocess
    import sys
    stub = env / "stub"
    (stub / "cognee").mkdir(parents=True)
    (stub / "cognee" / "__init__.py").write_text(STUB, encoding="utf-8")
    (stub / "cognee-1.6.11.dist-info").mkdir()
    (stub / "cognee-1.6.11.dist-info" / "METADATA").write_text("Metadata-Version: 2.1\nName: cognee\nVersion: 1.6.11\n",
                                                                encoding="utf-8")
    mp = env / "m.json"
    cg.write_map(mp, {"brain": "b", "corpus": "full", "dataset": "d", "lang": "es", "episodes": [E1, E2], "loaded": []})
    g = _gold(env, [Q])
    e = {k: v for k, v in os.environ.items() if k not in (*cg.REMOTE_ENV, "COGNEE_ENV_FILE")}
    e.update(PYTHONPATH=str(stub), PYTHONUTF8="1")

    def script(name, *args):
        return subprocess.run([sys.executable, str(EVAL / "adapters" / name), *args], env=e, capture_output=True, text=True, check=False,
                              timeout=120)

    r = script("cognee_load.py", "load", "--brain", "b", "--map", str(mp), "--calls-per-episode", "2")
    assert r.returncode == 0, r.stderr
    m = json.loads(mp.read_text(encoding="utf-8"))
    assert m["loaded"] == ["e1", "e2"] and m["cognee"]["version"] == "1.6.11"
    store = json.loads((env / "cognee" / "system" / "stub-store.json").read_text())
    assert [a["node_set"] for a in store["added"]] == [["episode:e1"], ["episode:e2"]] and store["cognified"] == 1

    res = env / "res.jsonl"
    r = script("cognee_arm.py", "search", "--brain", "b", "--gold", str(g), "--map", str(mp), "--out", str(res))
    assert r.returncode == 0, r.stderr
    rows = [json.loads(x) for x in res.read_text(encoding="utf-8").splitlines()]
    assert all("error" not in x for x in rows) and rows[0]["results"][0]["text"].startswith("The backup server")
