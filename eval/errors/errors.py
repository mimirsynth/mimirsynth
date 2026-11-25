"""Error analysis of 0.17 for Phase 0 (#515): every miss and every noisy item of the recall on `tune`, in exactly one class, so the
classes that dominate say which component to change, and which #513 variants are worth building.

Run from `api/`, on the instance where the snapshot was restored, with its MIMIRSYNTH_* environment and MIMIRSYNTH_EVAL_SNAPSHOT=1:

    cd api && .venv/bin/python ../eval/errors/errors.py candidates --brain SLUG --gold ../eval/out/gold.jsonl \\
        --hookset ../eval/out/hookset.jsonl --budget plugin
    cd api && .venv/bin/python ../eval/errors/errors.py sheet --candidates ../eval/out/errors/candidates-plugin-tune.jsonl
    # fill in the empty `class` cells of errors-plugin-tune.csv, and correct any suggestion that is wrong, then:
    cd api && .venv/bin/python ../eval/errors/errors.py summarize --sheet ../eval/out/errors/errors-plugin-tune.csv

Everything goes to `eval/out/errors/`, which git ignores: the candidates and the sheet hold the brain's own text. Only the tables
`summarize` prints (counts and percentages) are posted in #491.
"""
from __future__ import annotations

import argparse
import functools
import importlib.util
import json
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
EVAL = HERE.parent
OUT = EVAL / "out" / "errors"

TOP = 50   # candidates looked at per path, before the threshold and the cut
CLASSES = {
    1: "not in the corpus",
    2: "stored stale or wrong",
    3: "extraction lost it",
    4: "not among the candidates",
    5: "a candidate, ranked below the cut",
    6: "stale shown as current",
    7: "spread over more notes than the limit",
    8: "cut by the character budget",
    9: "noise",
}
COMPONENT = {1: "write path", 2: "write path", 3: "extraction", 4: "retrieval", 5: "ranking", 6: "invalidation", 7: "limit",
             8: "budget", 9: "ranking"}
MECHANICAL = (4, 5, 7, 8, 9)   # the classes the sheet fills in; the rest are read by hand
QCLASSES = ("point", "entity", "temporal", "volatile", "ood", "hook")
COLUMNS = ("row", "id", "qclass", "unit", "what", "suggested", "class", "why", "hint", "query", "answer")


@functools.cache
def _run():
    spec = importlib.util.spec_from_file_location("eval_run", EVAL / "run.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --- classification (pure) ----------------------------------------------------------------------------------------------------------

def _eps_of(x: dict) -> set[str]:
    """The episodes an item of the recall's output, or a candidate, comes from."""
    if x.get("episode_uuid"):
        return {str(x["episode_uuid"])}
    return {str(e) for e in x.get("episodes") or []}


def _target(rec: dict) -> tuple[set[str], set[str]]:
    """(answer episodes, answer documents) of a question, or the labelled note of a hook prompt."""
    if rec["class"] == "hook":
        lab = (rec.get("label") or "").strip()
        return ({lab} if lab and lab != "nothing" else set()), set()
    return set(rec.get("answer_episodes") or []), set(rec.get("answer_docs") or [])


def _first(cands: list[dict], eps: set[str]) -> tuple[int, dict] | None:
    for i, c in enumerate(cands, 1):
        if _eps_of(c) & eps:
            return i, c
    return None


def stage(rec: dict, items: list[dict], eps: set[str], docs: set[str]) -> tuple[int | None, int | None, str, str]:
    """Where the answer got furthest, for the episodes (and documents) in `eps` and `docs` that the metric missed: (suggested class,
    class to prefill or None, why, hint). From the furthest stage back: returned by the recall but cut out of the context by the
    character budget (8); among the top 50 of a path, below its cut or its threshold (5); in no top 50 (4). An answer episode the
    snapshot does not hold is suggested 1, and left for a person to confirm."""
    out, params = rec.get("out") or {}, rec.get("params") or {}
    shown = {(it["kind"], it["id"]) for it in items}
    returned = [("fact", f) for f in out.get("facts") or []] + [("chunk", c) for c in out.get("chunks") or []]
    for kind, x in returned:
        if _eps_of(x) & eps and (kind, str(x.get("uuid") if kind == "fact" else x.get("id"))) not in shown:
            return 8, 8, f"a {kind} from it was returned and cut out of the context", ""
    for d in out.get("documents") or []:
        if str(d.get("document_id")) in docs and ("doc", str(d.get("document_id"))) not in shown:
            return 8, 8, "a passage from it was returned and cut out of the context", ""
    snap = rec.get("snapshot") or {}
    min_sim = out.get("min_similarity")
    found = []
    for path, n in (("facts", params.get("n_facts")), ("chunks", params.get("n_chunks"))):
        hit = _first((rec.get("candidates") or {}).get(path) or [], eps)
        if hit is None:
            continue
        rank, c = hit
        sim = c.get("similarity")
        if min_sim and sim is not None and sim < min_sim:
            found.append(f"{path} rank {rank}, similarity {sim:.3f} under the threshold {min_sim}")
        else:
            found.append(f"{path} rank {rank}" + (f", the recall returns {n}" if n else ""))
    if found:
        return 5, 5, "; ".join(found), ""
    missing = sorted(e for e in eps if not (snap.get(e) or {}).get("in", True))
    if eps and len(missing) == len(eps):
        return 1, None, "in no top 50", "the snapshot does not hold the answer episode: 1, unless another note holds the answer"
    hint = "no fact comes from the answer episode: 3?" if eps and all(not (snap.get(e) or {}).get("facts", True) for e in eps) else ""
    if docs and not eps:
        return 4, 4, "documents are not among the paths looked at", hint
    return 4, 4, f"in no top {TOP} of facts or chunks", hint


def stale_hint(rec: dict, shown: list[dict], eps: set[str]) -> tuple[int | None, str]:
    """A suggestion for a stale row, which a person still decides (#515):
    - 6, a wrong or missing invalidation: a stale fact shown as current is invalidated or expired in the snapshot, or an answer
      episode the snapshot holds is dated after every stale episode, so the new value was there to invalidate the old one;
    - 2, stored stale: no answer episode the snapshot holds is anything but a stale one, so only the old version is stored."""
    info, snap = rec.get("stale_info") or {}, rec.get("snapshot") or {}
    gone = [it["id"] for it in shown if it["kind"] == "fact" and (info.get(it["id"]) or {}).get("invalid")]
    if gone:
        return 6, f"6: the snapshot has {', '.join(gone)} invalidated or expired"
    facts = {k: v for k, v in info.items() if "invalid" in v}
    stale_eps = {s for s in rec.get("stale") or [] if s not in facts} | {e for f in facts.values() for e in f.get("episodes") or []}
    dates = [d for e in stale_eps if (d := (snap.get(e) or info.get(e) or {}).get("valid_at"))]
    held = [e for e in eps if (snap.get(e) or {}).get("in") and e not in stale_eps]
    later = [e for e in held if dates and (snap[e].get("valid_at") or "") > max(dates)]
    if later:
        return 6, f"6: answer episode {later[0]} is dated after every stale episode"
    if not held:
        return 2, "2: the only episodes with the answer are the stale ones"
    return None, "6 if Graphiti failed to invalidate it, 2 if only the stale version is stored"


def _linked(rec: dict, it: dict) -> str:
    """How an item came into the context: through a link, not its similarity (a fact that replaces one in the result, or an old
    fact a fragment states, both with no similarity), or by passing the threshold."""
    if it["kind"] != "fact":
        return ""
    f = next((x for x in (rec.get("out") or {}).get("facts") or [] if str(x.get("uuid")) == it["id"]), {})
    if f.get("similarity") is not None:
        return ""
    return "replaces a fact in the result" if f.get("replaces") else "an old fact a fragment states"


def _similarity(rec: dict, it: dict):
    out = rec.get("out") or {}
    pool = out.get("facts") if it["kind"] == "fact" else out.get("chunks") if it["kind"] == "chunk" else out.get("documents")
    key = "uuid" if it["kind"] == "fact" else "id" if it["kind"] == "chunk" else "document_id"
    x = next((x for x in pool or [] if str(x.get(key)) == it["id"]), {})
    return x.get("similarity")


def classify(rec: dict) -> list[dict]:
    """The sheet's rows for one question or hook prompt: one for its miss, if the metric missed; one if something stale showed as
    current; one per item in its context that is not from the answer (noise). Each row has exactly one suggested class."""
    ev = _run()
    base = {"id": rec["id"], "qclass": rec["class"], "query": rec.get("query") or "",
            "answer": " ".join(sorted(set(rec.get("answer_episodes") or []) | set(rec.get("answer_docs") or [])))
            or (rec.get("label") or "")}
    if rec.get("error"):
        return [{**base, "unit": "error", "what": "", "suggested": "", "class": "", "why": rec["error"], "hint": ""}]
    out, params = rec.get("out") or {}, rec.get("params") or {}
    ctx = out.get("context") or ""
    items = ev.context_items(out)
    if ctx.strip() and not items and any(out.get(k) for k in ("facts", "chunks", "documents")):
        return [{**base, "unit": "error", "what": "", "suggested": "", "class": "",
                 "why": "unparsed context: the recall returned items and none was found in its context", "hint": ""}]
    eps, docs = _target(rec)
    if rec["class"] == "hook":
        q = {"id": rec["id"], "label": rec.get("label")}
        m = ev.score_hook(q, items, None, ctx)["m"]
        relevant = lambda it: bool(eps & set(it["episodes"]))  # noqa: E731
    else:
        q = {k: rec.get(k) for k in ("id", "class", "answer_episodes", "answer_docs", "stale")}
        m = ev.score(q, items, None, ctx)["m"]
        relevant = lambda it: ev._relevant(it, q)  # noqa: E731
    rows = []

    def row(unit, what, suggested, prefill, why, hint=""):
        rows.append({**base, "unit": unit, "what": what, "suggested": suggested or "", "class": prefill or "", "why": why,
                     "hint": hint})

    cls = rec["class"]
    if cls in ("point", "temporal", "volatile") and m.get("top3", [1])[0] == 0:
        where = [i for i, it in enumerate(items, 1) if relevant(it)]
        if where:
            row("miss", "top3", 5, 5, f"in the context as item {where[0]}, after the first three")
        else:
            row("miss", "top3", *stage(rec, items, eps, docs))
    elif cls == "entity" and m.get("coverage", [1])[0] < 1:
        covered = {e for it in items for e in it["episodes"]}
        limit = (params.get("n_facts") or 0) + (params.get("n_chunks") or 0)
        sug, pre, why, hint = stage(rec, items, eps - covered, docs)
        if limit and len(eps) > limit and sug == 5:   # found among the candidates, but more notes than the recall returns
            sug, pre, why = 7, 7, f"{len(eps)} answer episodes for {limit} items; the missing ones: {why}"
        row("miss", "coverage", sug, pre, why, hint)
    elif cls == "ood" and m.get("empty_ok", [1])[0] == 0:
        row("miss", "empty_ok", 9, 9, f"{len(items)} items injected" if items else "only text outside any item (a state card)")
    elif cls == "hook":
        if "hook_silence" in m and m["hook_silence"][0] == 0:
            row("miss", "hook_silence", 9, 9, f"{len(items)} items injected" if items else "only text outside any item (a state card)")
        elif eps and not any(relevant(it) for it in items):
            row("miss", "hook_precision" if "hook_precision" in m else "hook_injected", *stage(rec, items, eps, set()))
    if m.get("stale_as_current", [0])[0] == 1:
        stale = set(rec.get("stale") or [])
        shown = [it for it in items if ev._stale(it, stale)]
        sug, hint = stale_hint(rec, shown, eps)
        row("stale", "stale_as_current", sug, "", "shown as current: " + ", ".join(f"{it['kind']} {it['id']}" for it in shown),
            hint)
    for it in items:
        if relevant(it):
            continue
        link = _linked(rec, it)
        sim = _similarity(rec, it)
        why = f"came in through a link: {link}" if link else (f"similarity {sim:.3f}" if isinstance(sim, (int, float)) else "")
        row("noise", it["kind"], 9, 9, why + f"; {it['chars']} characters")
    return rows


def sheet_rows(records: list[dict]) -> list[dict]:
    rows = [r for rec in records for r in classify(rec)]
    return [{"row": f"R{i:04d}", **{k: r.get(k, "") for k in COLUMNS if k != "row"}} for i, r in enumerate(rows, 1)]


# --- summary (pure) ------------------------------------------------------------------------------------------------------------------

def _class(v) -> int | None:
    try:
        c = int(str(v).strip())
    except ValueError:
        return None
    return c if c in CLASSES else None


def summarize(rows: list[dict]) -> dict:
    """The share of each class, per question class, over the misses and the stale rows; the noise rows by kind and by how they came
    in; and each class's component. Rows with no class, or a class outside 1-9, are counted apart."""
    per: dict[str, Counter] = defaultdict(Counter)
    noise: Counter = Counter()
    unclassified: Counter = Counter()
    errors = 0
    for r in rows:
        unit = (r.get("unit") or "").strip()
        if unit == "error":
            errors += 1
            continue
        c = _class(r.get("class"))
        if unit == "noise":
            how = "through a link" if "through a link" in (r.get("why") or "") else "above the threshold"
            noise[(r.get("what") or "?", how)] += 1
            continue
        if c is None:
            unclassified[r.get("qclass") or "?"] += 1
            continue
        per[r.get("qclass") or "?"][c] += 1
    total = Counter()
    for c in per.values():
        total.update(c)
    return {"by_qclass": {q: dict(c) for q, c in per.items()}, "all": dict(total), "noise": {f"{k} · {h}": v for (k, h), v in noise.items()},
            "unclassified": dict(unclassified), "errors": errors}


def _pct(part: int, whole: int) -> str:
    return f"{100 * part / whole:.0f}" if whole else "–"


def summary_markdown(s: dict, meta: str = "") -> str:
    lines = [f"## Error analysis of 0.17 (#515){' · ' + meta if meta else ''}", "",
             "Misses and stale rows, % of each question class's rows (n = rows):", "",
             "| question class | n | " + " | ".join(str(c) for c in CLASSES) + " |", "|---|--:|" + "--:|" * len(CLASSES)]
    order = [q for q in QCLASSES if q in s["by_qclass"]] + sorted(q for q in s["by_qclass"] if q not in QCLASSES)
    for q in order + (["all"] if s["all"] else []):
        c = s["all"] if q == "all" else s["by_qclass"][q]
        n = sum(c.values())
        lines.append(f"| {'**all**' if q == 'all' else q} | {n} | " + " | ".join(_pct(c.get(k, 0), n) for k in CLASSES) + " |")
    n = sum(s["all"].values())
    lines += ["", "| class | what | component | rows | % |", "|--:|---|---|--:|--:|"]
    lines += [f"| {k} | {v} | {COMPONENT[k]} | {s['all'].get(k, 0)} | {_pct(s['all'].get(k, 0), n)} |" for k, v in CLASSES.items()]
    if s["noise"]:
        lines += ["", "Noise items in the final context (class 9), by kind and by how they came in:", "", "| item | rows |", "|---|--:|"]
        lines += [f"| {k} | {v} |" for k, v in sorted(s["noise"].items())]
    left = []
    if s["unclassified"]:
        left.append(f"{sum(s['unclassified'].values())} rows with no class yet ("
                    + ", ".join(f"{q} {v}" for q, v in sorted(s["unclassified"].items())) + ")")
    if s["errors"]:
        left.append(f"{s['errors']} recalls that failed or could not be read")
    if left:
        lines += ["", "Left out: " + "; ".join(left) + "."]
    return "\n".join(lines + [""])


# --- the snapshot --------------------------------------------------------------------------------------------------------------------

def gather(slug: str, items: list[dict], params: dict, top: int = TOP) -> list[dict]:
    """For each question or hook prompt: the recall at the budget's parameters (what 0.17 returns and its final context), the top
    `top` candidates of each path before the threshold and the cut (facts by cosine, as 0.17 searches them; episode chunks by the
    hybrid search, with the recall's recency weight and common terms), and whether the snapshot holds each answer episode and any
    fact from it. Only the brain's own graph and index: what other brains lend is in the recall, not among the candidates."""
    ev = _run()
    recall_fn, how = ev.recall_on(slug)
    models, _, _, factory = ev._app()
    from mimirsynth import appsettings, index
    from mimirsynth.db import graph, rows
    from mimirsynth.embed import get_embedder
    from mimirsynth.recall import _common, recency_weight, search_facts
    from mimirsynth.vocab import alias_map
    with factory()() as db:
        b = db.query(models.Brain).filter(models.Brain.slug == slug).one()
        bid, gname = b.id, b.graph_name
        amap = alias_map(db, bid)
    g = graph(gname)
    held = {r["uuid"]: str(r["valid_at"] or "") for r in rows(g.ro_query("MATCH (e:Episodic) RETURN e.uuid AS uuid, "
                                                                        "e.valid_at AS valid_at"))}
    with_facts = {r["e"] for r in rows(g.ro_query("MATCH (:Entity)-[r:RELATES_TO]->(:Entity) UNWIND r.episodes AS e "
                                                  "RETURN DISTINCT e AS e"))}
    wanted = sorted({s for it in items for s in it.get("stale") or []})
    stale_facts = {r["uuid"]: {"invalid": bool(r["invalid_at"] or r["expired_at"]), "episodes": r["episodes"] or []}
                   for r in rows(g.ro_query("MATCH (:Entity)-[r:RELATES_TO]->(:Entity) WHERE r.uuid IN $ids RETURN r.uuid AS uuid, "
                                            "r.invalid_at AS invalid_at, r.expired_at AS expired_at, r.episodes AS episodes",
                                            {"ids": wanted}))} if wanted else {}
    common = _common(bid, "chunks", appsettings.get("recall_common_terms") == "yes")
    embedder = get_embedder()
    records = []
    with ev.counted():
        for it in items:
            rec = {k: it.get(k) for k in ("id", "class", "query", "answer_episodes", "answer_docs", "stale", "label")}
            rec["class"] = it.get("class") or "hook"
            rec["params"] = params
            eps, _ = _target(rec)
            rec["snapshot"] = {e: {"in": e in held, "facts": e in with_facts, "valid_at": held.get(e, "")} for e in sorted(eps)}
            if rec.get("stale"):   # what the stale rows' hints read: each stale fact's state, and the stale episodes' dates
                info = {s: stale_facts[s] for s in rec["stale"] if s in stale_facts}
                for e in {s for s in rec["stale"] if s not in info} | {e for f in info.values() for e in f["episodes"]}:
                    info.setdefault(e, {"valid_at": held.get(e, "")})
                rec["stale_info"] = info
            try:
                rec["out"] = recall_fn(it["query"], **params)
                qvec = embedder.embed([it["query"]])[0]
                facts = search_facts(gname, qvec, top, amap)
                chunks = index.search(bid, qvec, it["query"], k=top, pool=2 * top, recency=recency_weight(it["query"]), skip=common)
            except Exception as e:  # noqa: BLE001  (one failed question is recorded, the run goes on)
                rec["error"] = f"{type(e).__name__}: {e}"
                records.append(rec)
                continue
            rec["candidates"] = {
                "facts": [{"uuid": f.get("uuid"), "episodes": f.get("episodes") or [], "similarity": f.get("similarity")} for f in facts],
                "chunks": [{"id": c.get("id"), "episode_uuid": c.get("episode_uuid"), "similarity": c.get("similarity")} for c in chunks],
            }
            records.append(rec)
    for r in records:
        r["how"] = how
    return records


def main(argv: list[str] | None = None, gather_fn=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("candidates", help="run the recall and the top 50 of each path on the questions of a split")
    c.add_argument("--brain", required=True)
    c.add_argument("--gold", type=Path, required=True)
    c.add_argument("--hookset", type=Path)
    c.add_argument("--split", choices=("tune", "holdout", "all"), default="tune")
    c.add_argument("--split-file", type=Path, default=EVAL / "out" / "split.json")
    c.add_argument("--budget", choices=("2500", "plugin"), default="plugin")
    c.add_argument("--include-drafts", action="store_true")
    c.add_argument("--out", type=Path)
    s = sub.add_parser("sheet", help="the sheet to classify, with the mechanical classes filled in")
    s.add_argument("--candidates", type=Path, required=True)
    s.add_argument("--out", type=Path)
    s.add_argument("--force", action="store_true", help="overwrite a sheet that may hold your classes")
    m = sub.add_parser("summarize", help="the shares per class, ready for #491")
    m.add_argument("--sheet", type=Path, required=True)
    a = ap.parse_args(argv)
    ev = _run()

    if a.cmd == "summarize":
        rows = ev._census()._read_csv(a.sheet, ("id", "qclass", "unit", "class"))
        if not rows:
            raise SystemExit(f"{a.sheet}: no rows")
        print(summary_markdown(summarize(rows), a.sheet.stem.removeprefix("errors-")))
        return 0
    if a.cmd == "sheet":
        out = a.out or a.candidates.with_name(a.candidates.stem.replace("candidates", "errors") + ".csv")
        if out.exists() and not a.force:
            raise SystemExit(f"{out} already exists and may hold your classes: move it, or use --force")
        rows = sheet_rows(ev.load_jsonl(a.candidates))
        ev._census()._write_csv(out, [{k: ev._census()._cell(str(v)) for k, v in r.items()} for r in rows])
        todo = sum(1 for r in rows if r["unit"] != "error" and not r["class"])
        print(f"{len(rows)} rows ({todo} to classify by hand) → {out}")
        return 0

    gold = ev.load_jsonl(a.gold)
    problems = ev.check_gold(gold)
    if problems:
        raise SystemExit("the gold set has problems:\n" + "\n".join(f"- {p}" for p in problems))
    split = json.loads(a.split_file.read_text(encoding="utf-8")) if a.split_file.exists() else None
    questions = [q for q in ev.pick_split(gold, split, a.split) if q.get("validated") or a.include_drafts]
    hooks = ev.load_jsonl(a.hookset) if a.hookset else []
    hooks = ev.pick_split([h for h in hooks if ev.label_hook(h) is not None], split, a.split, "hook prompts")
    params = ev.BUDGETS[a.budget]
    records = (gather_fn or gather)(a.brain, questions + [{**h, "class": "hook"} for h in hooks], params)
    out = a.out or OUT / f"candidates-{a.budget}-{a.split}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(json.dumps(r, ensure_ascii=False, default=str) + "\n" for r in records), encoding="utf-8")
    failed = sum(1 for r in records if r.get("error"))
    print(f"{len(records)} questions and prompts ({failed} failed) → {out}")
    return 1 if records and failed == len(records) else 0


if __name__ == "__main__":
    raise SystemExit(main())
