"""A virtual clean corpus for Phase 0 (#516, step 1): which episodes are curated, extrapolated from the census labels (#514), and a
filter that leaves the others out of 0.17's recall at query time. No LLM, no rebuild, and nothing in the app changes: the filter
replaces three of the recall's functions inside the eval's process, for the length of a block.

Run from `api/`, on the instance where the snapshot was restored, with its MIMIRSYNTH_* environment and MIMIRSYNTH_EVAL_SNAPSHOT=1:

    cd api && .venv/bin/python ../eval/clean/clean.py curated --brain SLUG      # eval/out/clean/curated.json
    cd api && .venv/bin/python ../eval/run.py run --brain SLUG ... --corpus clean --label clean-0.17

`curated.json` holds the brain's episode uuids, so it goes to `eval/out/`, which git ignores. Its table (cells, counts and shares)
is what is posted in #491.
"""
from __future__ import annotations

import argparse
import contextlib
import functools
import importlib.util
import json
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
EVAL = HERE.parent
OUT = EVAL / "out" / "clean"

CLEAN_LABELS = ("note", "event")   # what a curated memory holds: a self-contained note, or a dated record of a change (#517)
MIN_CLEAN = 0.8                    # a cell is curated when at least this share of its labelled episodes is clean
MIN_LABELLED = 5                   # with fewer labelled episodes, a cell is not decided: it is kept, and the table says so
OVERFETCH = 4                      # how many more candidates the filtered searches ask for, so the cut is not left short


@functools.cache
def _run():
    spec = importlib.util.spec_from_file_location("eval_run", EVAL / "run.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --- which episodes are curated (pure) ----------------------------------------------------------------------------------------------

def cells(episodes: list[dict], proposals: list[dict], source_map: list | None = None) -> dict[str, tuple[str, str]]:
    """Each episode's cell: its census stratum (where it came from) and who let it in (`approved_by`: a person, nobody, the
    decider, a category tier, a webhook's auto-approval)."""
    census = _run()._census()
    st = census.episode_strata(episodes, proposals, source_map)
    by_ep: dict[str, list[dict]] = defaultdict(list)
    for p in proposals:
        if p.get("episode_uuid"):
            by_ep[p["episode_uuid"]].append(p)
    return {e["uuid"]: (st[e["uuid"]], census.approved_by(census.pick(by_ep.get(e["uuid"], [])))) for e in episodes}


def labels(sheet: list[dict], keys: list[dict], cell_of: dict[str, tuple[str, str]]) -> tuple[dict[str, str], dict]:
    """Each labelled episode's label, by uuid, through the census key. Stops when the key's stratum for an episode is not the one
    computed here: the census was sampled with another source map, and the cells would not match the labels."""
    census = _run()._census()
    key = {k["id"]: k for k in keys if (k.get("kind") or "episode") == "episode"}
    out, skipped = {}, {"unlabelled": 0, "unknown label": 0, "no key": 0, "not in the snapshot": 0}
    for r in sheet:
        lab = (r.get("label") or "").strip().lower()
        k = key.get(r.get("id"))
        if not lab:
            skipped["unlabelled"] += 1
        elif lab not in census.EPISODE_LABELS:
            skipped["unknown label"] += 1
        elif k is None:
            skipped["no key"] += 1
        elif k["uuid"] not in cell_of:
            skipped["not in the snapshot"] += 1
        else:
            if cell_of[k["uuid"]][0] != k.get("stratum"):
                raise SystemExit(f"{r['id']}: the census key says stratum {k.get('stratum')!r}, this snapshot gives "
                                 f"{cell_of[k['uuid']][0]!r}: run `curated` with the --source-map the census sample used")
            out[k["uuid"]] = lab
    return out, skipped


def curated_table(cell_of: dict[str, tuple[str, str]], labelled: dict[str, str], min_clean: float = MIN_CLEAN,
                  clean_labels: tuple[str, ...] = CLEAN_LABELS, min_labelled: int = MIN_LABELLED) -> list[dict]:
    """One row per cell: its episodes, how many are labelled, the share of them that is clean with its 95 % Wilson interval, and
    whether the cell is curated. A cell with fewer than `min_labelled` labelled episodes is `None`: it is never guessed, and its
    episodes are not filtered."""
    size = Counter(cell_of.values())
    lab: dict[tuple[str, str], Counter] = defaultdict(Counter)
    for u, label in labelled.items():
        lab[cell_of[u]][label] += 1
    rows = []
    for c in sorted(size, key=lambda c: (-size[c], c)):
        n = sum(lab[c].values())
        clean = sum(lab[c][x] for x in clean_labels)
        share = clean / n if n else None
        lo, hi = _wilson(clean, n)
        rows.append({"stratum": c[0], "review": c[1], "episodes": size[c], "labelled": n, "clean": clean, "share": share,
                     "lo": lo, "hi": hi, "curated": None if n < max(1, min_labelled) else share >= min_clean})
    return rows


def _wilson(k: int, n: int, z: float = 1.96) -> tuple[float | None, float | None]:
    if not n:
        return None, None
    p, d = k / n, 1 + z * z / n
    c, h = (p + z * z / (2 * n)) / d, z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
    return max(0.0, c - h), min(1.0, c + h)


def dropped(cell_of: dict[str, tuple[str, str]], table: list[dict]) -> set[str]:
    """The episodes of the cells that are not curated. A cell with no labels keeps its episodes."""
    out_cells = {(r["stratum"], r["review"]) for r in table if r["curated"] is False}
    return {u for u, c in cell_of.items() if c in out_cells}


def table_markdown(cur: dict) -> str:
    rule = cur["rule"]
    lines = [f"Curated cells (#516): clean labels {', '.join(rule['clean_labels'])}; a cell is curated at ≥ {100 * rule['min_clean']:.0f} %"
             f" of its labelled episodes clean, with at least {rule['min_labelled']} labelled.", "",
             "| stratum | approved by | episodes | labelled | clean % | 95 % interval | curated |", "|---|---|--:|--:|--:|--:|---|"]
    for r in cur["cells"]:
        share = "–" if r["share"] is None else f"{100 * r['share']:.0f}"
        ci = "–" if r.get("lo") is None else f"{100 * r['lo']:.0f} – {100 * r['hi']:.0f}"
        verdict = {True: "yes", False: "**no**"}.get(r["curated"]) or ("no labels: kept" if not r["labelled"] else "too few labels: kept")
        lines.append(f"| {r['stratum']} | {r['review']} | {r['episodes']} | {r['labelled']} | {share} | {ci} | {verdict} |")
    total = sum(r["episodes"] for r in cur["cells"])
    lines += ["", f"Left out: {len(cur['drop'])} of {total} episodes."]
    unlabelled = [r for r in cur["cells"] if r["curated"] is None]
    if unlabelled:
        lines.append(f"**Warning:** {len(unlabelled)} cells ({sum(r['episodes'] for r in unlabelled)} episodes) have too few labelled "
                     "episodes to decide and are kept as they are. Label more of them to decide.")
    return "\n".join(lines + [""])


# --- the filter ----------------------------------------------------------------------------------------------------------------------

def _keep(item: dict, drop: set[str]) -> bool:
    """An item stays unless every episode it comes from is left out. One with no episode (a lent brain's, a document's) stays."""
    eps = [str(item["episode_uuid"])] if item.get("episode_uuid") else [str(e) for e in item.get("episodes") or []]
    return not eps or not all(e in drop for e in eps)


@contextlib.contextmanager
def corpus(drop: set[str], stats: Counter | None = None):
    """0.17's recall without the episodes in `drop`, in this process, for the length of the block:
    - `search_facts` and `search_chunks` ask for OVERFETCH times as many, leave out the facts and chunks that come only from those
      episodes, and cut to what was asked, so the recall's own cut is not left short;
    - `build_context` also leaves them out of what the recall adds through links (a fact that replaces one in the result, an old
      fact a fragment states), which no search returned.
    The state cards are not filtered: they describe the current graph. `stats` counts what was left out at each step, and the
    characters the state cards take (`state card chars`), since they weigh in the noise."""
    from mimirsynth import recall
    names = ("search_facts", "search_chunks", "build_context")
    real = {n: getattr(recall, n) for n in names}
    stats = stats if stats is not None else Counter()

    def keep(items: list[dict], what: str) -> list[dict]:
        kept = [x for x in items if _keep(x, drop)]
        if len(kept) < len(items):
            stats[what] += len(items) - len(kept)
        return kept

    def search_facts(graph_name, qvec, limit, amap=None):
        return keep(real["search_facts"](graph_name, qvec, limit * OVERFETCH, amap), "facts")[:limit]

    def search_chunks(brain_id, qvec, query, n, min_sim, common=False):
        if n <= 0:
            return real["search_chunks"](brain_id, qvec, query, n, min_sim, common)
        return keep(real["search_chunks"](brain_id, qvec, query, n * OVERFETCH, min_sim, common), "chunks")[:n]

    def build_context(facts, chunks, max_chars, passages=None, lang="es", cards=None):
        if cards:
            stats["state card chars"] += len(real["build_context"]([], [], max_chars, None, lang, cards))
        return real["build_context"](keep(list(facts), "linked facts"), keep(list(chunks), "linked chunks"), max_chars, passages,
                                     lang, cards)

    for n, f in (("search_facts", search_facts), ("search_chunks", search_chunks), ("build_context", build_context)):
        setattr(recall, n, f)
    try:
        yield stats
    finally:
        for n in names:
            setattr(recall, n, real[n])


def filtered(recall_fn, drop: set[str]):
    """The recall's output without the left-out items it still lists, so what is scored matches its context."""
    def fn(query, **p):
        out = recall_fn(query, **p)
        return {**out, "facts": [f for f in out.get("facts") or [] if _keep(f, drop)],
                "chunks": [c for c in out.get("chunks") or [] if _keep(c, drop)]}
    return fn


def answers_left_out(questions: list[dict], drop: set[str]) -> int:
    """Questions whose every answer episode is left out: on the clean corpus they cannot be answered from the graph."""
    return sum(1 for q in questions if q.get("answer_episodes") and all(e in drop for e in q["answer_episodes"]))


def load(path: Path) -> dict:
    if not path.exists():
        raise SystemExit(f"{path}: run `clean.py curated` first")
    cur = json.loads(path.read_text(encoding="utf-8"))
    if not {"rule", "cells", "drop"} <= set(cur):
        raise SystemExit(f"{path}: not a curated file")
    return cur


# --- command -------------------------------------------------------------------------------------------------------------------------

def main(argv: list[str] | None = None, snapshot=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("curated", help="which cells of the brain are curated, from the census labels")
    c.add_argument("--brain", required=True)
    c.add_argument("--sheet", type=Path, default=EVAL / "census" / "out" / "episodes.csv")
    c.add_argument("--keys", type=Path, default=EVAL / "census" / "out" / "keys.csv")
    c.add_argument("--source-map", type=Path, help="the same one the census sample used")
    c.add_argument("--min-clean", type=float, default=MIN_CLEAN)
    c.add_argument("--min-labelled", type=int, default=MIN_LABELLED)
    c.add_argument("--clean-labels", default=",".join(CLEAN_LABELS))
    c.add_argument("--out", type=Path, default=OUT / "curated.json")
    a = ap.parse_args(argv)
    census = _run()._census()
    clean_labels = tuple(x.strip() for x in a.clean_labels.split(",") if x.strip())
    if not clean_labels or set(clean_labels) - set(census.EPISODE_LABELS):
        raise SystemExit(f"--clean-labels must be among {', '.join(census.EPISODE_LABELS)}")
    sheet = census._read_csv(a.sheet, ("id", "label"))
    keys = census._read_csv(a.keys, ("id", "uuid", "stratum"))
    if not sheet or not keys:
        raise SystemExit("the census sheet and its key are needed (label episodes.csv first)")
    if snapshot is None:
        _run().snapshot_guard()
        _, data = census.read_snapshot(a.brain)
        episodes, proposals = data["episodes"], data["proposals"]
    else:
        episodes, proposals = snapshot
    cell_of = cells(episodes, proposals, census.read_source_map(a.source_map) if a.source_map else None)
    labelled, skipped = labels(sheet, keys, cell_of)
    if not labelled:
        raise SystemExit("no labelled episode of the sheet is in this snapshot")
    table = curated_table(cell_of, labelled, a.min_clean, clean_labels, a.min_labelled)
    cur = {"rule": {"clean_labels": list(clean_labels), "min_clean": a.min_clean, "min_labelled": a.min_labelled, "source_map": a.source_map.name if a.source_map else None},
           "cells": table, "skipped": skipped, "drop": sorted(dropped(cell_of, table))}
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(cur, indent=1), encoding="utf-8")
    print(table_markdown(cur))
    if any(skipped.values()):
        print("Labels not used: " + ", ".join(f"{v} {k}" for k, v in skipped.items() if v) + ".")
    print(f"→ {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
