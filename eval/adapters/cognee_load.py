"""Loads the snapshot's episodes into a separate Cognee instance (#526), never production, in two steps:

    # in the app's venv, on the instance where the snapshot was restored (MIMIRSYNTH_EVAL_SNAPSHOT=1)
    cd api && .venv/bin/python ../eval/adapters/cognee_load.py export --brain SLUG [--corpus clean]
    # in Cognee's own venv, with MIMIRSYNTH_EVAL_SNAPSHOT=1 and MIMIRSYNTH_EVAL_COGNEE_ROOT set
    python ../eval/adapters/cognee_load.py load --brain SLUG            # a trial of 10 episodes, then the cost estimate
    python ../eval/adapters/cognee_load.py load --brain SLUG --yes      # the rest, serially, with retries

`export` writes each episode's uuid, reference time and text to `eval/out/cognee/<brain>.json` (ignored by git: it is the brain's
own text). `load` adds them to Cognee one by one, the reference time on the first line of the text and the uuid as a node set, and
runs `cognify` after each batch, one at a time. The episodes loaded are written to the same file after each batch, so a run that
stops resumes where it was.
"""
from __future__ import annotations

import argparse
import functools
import importlib.util
import math
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
EVAL = HERE.parent


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@functools.cache
def _cognee():
    return _load("eval_cognee", HERE / "cognee.py")


def snapshot_guard() -> None:
    if os.environ.get("MIMIRSYNTH_EVAL_SNAPSHOT") != "1":
        raise SystemExit("set MIMIRSYNTH_EVAL_SNAPSHOT=1, only on the instance where the Phase 0 snapshot was restored")


# --- export (the app's venv) ---------------------------------------------------------------------------------------------------------

def episode_rows(episodes: list[dict], drop: set[str]) -> list[dict]:
    """The episodes to load, oldest first, each with its reference time on the first line of its text: Cognee has no reference
    time of its own, and that is how a reader sees when a note was written. Episodes with no text are left out."""
    rows = []
    for e in episodes:
        content = (e.get("content") or "").strip()
        if e["uuid"] in drop or not content:
            continue
        ref = str(e.get("valid_at") or "")
        rows.append({"uuid": e["uuid"], "reference_time": ref or None, "text": f"{ref[:10]}\n{content}" if ref else content})
    return sorted(rows, key=lambda r: (r["reference_time"] or "", r["uuid"]))


def export(brain: str, corpus: str, curated: Path, out: Path, snapshot=None) -> dict:
    snapshot_guard()
    if out.exists() and _cognee().read_map(out, brain).get("loaded"):
        raise SystemExit(f"{out} already has episodes loaded into Cognee: export to another --out, or delete it together with the "
                         "Cognee instance")
    run = _cognee()._run()
    lang = "es"
    if snapshot is None:
        run.snapshot_guard()
        snapshot = run._census().read_snapshot
        from mimirsynth import appsettings
        lang = appsettings.get("default_language") or "es"   # the language 0.17's arm writes its context in (run.recall_on)
    drop: set[str] = set()
    if corpus == "clean":
        drop = set(run._clean().load(curated, brain)["drop"])
    _, data = snapshot(brain)
    rows = episode_rows(data["episodes"], drop)
    m = {"brain": brain, "corpus": corpus, "dataset": f"mimirsynth-eval-{brain}-{corpus}", "lang": lang, "episodes": rows,
         "loaded": [], "left_out": len(drop)}
    _cognee().write_map(out, m)
    print(f"{len(rows)} episodes of {brain} ({corpus} corpus, {len(drop)} left out) → {out}")
    return m


# --- load (Cognee's venv) ------------------------------------------------------------------------------------------------------------

def with_retries(fn, retries: int, sleep, what: str):
    for attempt in range(retries + 1):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001  (the gateway's limits and timeouts are retried; the last error stops the load)
            if attempt == retries:
                raise SystemExit(f"{what} failed {retries + 1} times, the last with {type(e).__name__}: {e}. What was loaded is "
                                 "saved: run `load` again to resume") from None
            wait = 2 ** attempt * 5
            print(f"{what}: {type(e).__name__}: {e}; retrying in {wait} s", file=sys.stderr)
            sleep(wait)


def load_batch(client, batch: list[dict], retries: int, sleep) -> None:
    for e in batch:
        with_retries(lambda e=e: client.add(e), retries, sleep, f"add {e['uuid']}")
    with_retries(client.cognify, retries, sleep, "cognify")


def load(m: dict, path: Path, client, *, trial: int, per_episode: float | None, batch: int, retries: int, yes: bool,
         sleep=time.sleep) -> int:
    """Serial: one batch at a time, each added and cognified before the next, with retries. Without `yes`, it stops after the trial
    with the estimated LLM calls for the rest."""
    cg = _cognee()
    have = client.describe()
    m["cognee"] = m.get("cognee") or have
    cg.check_same(have, m["cognee"])
    done = set(m.get("loaded") or [])
    todo = [e for e in m["episodes"] if e["uuid"] not in done]

    def save(b: list[dict]) -> None:
        m["loaded"] = [*(m.get("loaded") or []), *(e["uuid"] for e in b)]
        cg.write_map(path, m)

    if not done and todo:   # the trial: its cost per episode estimates the rest
        first = todo[:trial]
        before = client.llm_calls()
        print(f"trial: {len(first)} episodes")
        load_batch(client, first, retries, sleep)
        after = client.llm_calls()
        if before is not None and after is not None and after > before:
            m["llm_calls_per_episode"] = (after - before) / len(first)
        save(first)
        todo = todo[len(first):]
    cpe = per_episode if per_episode is not None else m.get("llm_calls_per_episode")
    if todo and cpe is None:
        raise SystemExit("the LLM calls of the trial could not be counted: read them on the gateway and give --calls-per-episode")
    if todo:
        print(f"{len(todo)} episodes left, about {cpe:g} LLM calls each: about {math.ceil(len(todo) * cpe)} LLM calls in all "
              f"(plus their embeddings), in batches of {batch}, one at a time")
        if not yes:
            print("Nothing more was loaded. Run it again with --yes to load the rest.")
            return 2
    for i in range(0, len(todo), batch):
        b = todo[i:i + batch]
        load_batch(client, b, retries, sleep)
        save(b)
        print(f"{len(m['loaded'])} of {len(m['episodes'])} episodes loaded")
    cg.write_map(path, m)
    print(f"Done: {len(m['loaded'])} episodes in the dataset {m['dataset']} (Cognee {m['cognee'].get('version')}).")
    return 0


def main(argv: list[str] | None = None, client=None, snapshot=None, sleep=time.sleep) -> int:
    cg = _cognee()
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export", help="the snapshot's episodes to a file (in the app's venv)")
    e.add_argument("--brain", required=True)
    e.add_argument("--corpus", choices=("full", "clean"), default="full",
                   help="clean: leave out the episodes of the cells that are not curated (#516)")
    e.add_argument("--curated", type=Path, default=EVAL / "out" / "clean" / "curated.json", help="from `clean/clean.py curated`")
    e.add_argument("--out", type=Path, help="default: eval/out/cognee/<brain>.json")
    ld = sub.add_parser("load", help="load the exported episodes into the separate Cognee instance (in Cognee's venv)")
    ld.add_argument("--brain", required=True)
    ld.add_argument("--map", type=Path, help="default: eval/out/cognee/<brain>.json")
    ld.add_argument("--trial", type=int, default=10, help="episodes loaded first to measure the cost (default 10)")
    ld.add_argument("--calls-per-episode", type=float, help="when the trial's LLM calls cannot be counted: read on the gateway")
    ld.add_argument("--batch", type=int, default=10, help="episodes added before each cognify (default 10)")
    ld.add_argument("--retries", type=int, default=3)
    ld.add_argument("--yes", action="store_true", help="load the rest after the cost estimate")
    a = ap.parse_args(argv)

    if a.cmd == "export":
        export(a.brain, a.corpus, a.curated, a.out or cg.map_path(a.brain), snapshot)
        return 0
    snapshot_guard()
    if a.trial < 1 or a.batch < 1 or a.retries < 0:
        raise SystemExit("--trial and --batch must be at least 1, and --retries at least 0")
    path = a.map or cg.map_path(a.brain)
    m = cg.read_map(path, a.brain)
    root = cg.instance_guard()
    if client is None:
        client = cg.CogneeClient(root, m["dataset"])
    return load(m, path, client, trial=a.trial, per_episode=a.calls_per_episode, batch=a.batch, retries=a.retries, yes=a.yes,
                sleep=sleep)


if __name__ == "__main__":
    sys.exit(main())
