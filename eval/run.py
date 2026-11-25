"""Retrieval eval for Phase 0 (#492): per-class metrics on the final context, at two budgets, with intervals, and a paired comparison
with a verdict fixed in advance.

It runs on the frozen Phase 0 snapshot, with the instance's MIMIRSYNTH_* environment, from `api/`:

    cd api && .venv/bin/python ../eval/run.py split   --gold ../eval/out/gold.jsonl
    cd api && .venv/bin/python ../eval/run.py run     --brain SLUG --gold ../eval/out/gold.jsonl --split holdout --budget plugin
    cd api && .venv/bin/python ../eval/run.py compare ../eval/out/a.json ../eval/out/b.json
    cd api && .venv/bin/python ../eval/run.py hookset --brain SLUG      # real prompts from the replay sample, to label

Everything it writes goes to `eval/out/` (ignored by git): the questions and the results hold the brain's own text.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"

CLASSES = ("point", "entity", "temporal", "ood", "volatile")
BUDGETS = {   # the recall parameters each budget runs with
    "2500": {"n_facts": 8, "n_chunks": 4, "max_chars": 2500},
    "plugin": {"n_facts": 6, "n_chunks": 3, "max_chars": 4000},   # what the agent plugins' per-prompt hook sends
}
HOOK_PARAMS = {"facts": 6, "chunks": 3}
# Declared in advance (#492): the co-primaries must fall by at least this much, relative to the baseline; the answer metrics may
# not lose more than NON_INFERIORITY points at the lower bound of their interval.
MIN_EFFECT = {"noise": -0.30, "stale_as_current": -0.50}
COPRIMARY = tuple(MIN_EFFECT)
ANSWER = ("top3", "coverage", "empty_ok", "hook_precision", "hook_silence")
NON_INFERIORITY = -3.0
BOOT = 2000
SEED = 492


# --- questions -----------------------------------------------------------------------------------------------------------------------

def load_jsonl(path: Path) -> list[dict]:
    rows = []
    for n, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        if line.strip():
            try:
                rows.append(json.loads(line))
            except ValueError as e:
                raise SystemExit(f"{path.name}:{n}: not JSON: {e}") from None
    return rows


def check_gold(rows: list[dict]) -> list[str]:
    """What is wrong with a gold set, one line per problem; empty when it is usable.

    A question: `id`, `class` (one of CLASSES), `query`, `answer_episodes` (the episode uuids that contain the answer; empty only out of
    domain), optional `answer_docs` (document ids), optional `stale` (for temporal ones: the uuids of the replaced facts, or of the
    episodes and documents that state the old value), `validated` (the maintainer read and accepted it)."""
    problems, seen = [], set()
    for i, q in enumerate(rows, 1):
        where = f"question {q.get('id') or '#' + str(i)}"
        if not q.get("id"):
            problems.append(f"{where}: no id")
        elif q["id"] in seen:
            problems.append(f"{where}: repeated id")
        seen.add(q.get("id"))
        if q.get("class") not in CLASSES:
            problems.append(f"{where}: class must be one of {', '.join(CLASSES)}")
        if not (q.get("query") or "").strip():
            problems.append(f"{where}: no query")
        answers = list(q.get("answer_episodes") or []) + list(q.get("answer_docs") or [])
        if q.get("class") == "ood" and answers:
            problems.append(f"{where}: an out-of-domain question has no answer")
        if q.get("class") not in ("ood", None) and not answers:
            problems.append(f"{where}: no answer_episodes")
        if q.get("class") == "entity" and len(q.get("answer_episodes") or []) < 2:
            problems.append(f"{where}: an entity question has its answer in several episodes")
    return problems


def label_hook(h: dict) -> str | None:
    """A hook prompt's label: an episode uuid (the note that should have been injected), `nothing`, or empty while unlabelled."""
    lab = (h.get("label") or "").strip()
    return None if not lab else lab


# --- split ---------------------------------------------------------------------------------------------------------------------------

def make_split(questions: list[dict], seed: int = SEED, old: dict | None = None) -> dict:
    """`tune` / `holdout` at 50 / 50 within each class, fixed by id. With `old`, its ids keep their side and only new ones are placed,
    each on the smaller side of its class."""
    old = old or {"tune": [], "holdout": []}
    side = {i: s for s in ("tune", "holdout") for i in old[s]}
    by_class: dict[str, list[str]] = defaultdict(list)
    for q in questions:
        by_class[q["class"]].append(q["id"])
    rng = random.Random(seed)
    out = {"tune": list(old["tune"]), "holdout": list(old["holdout"])}
    for cls in sorted(by_class):
        ids = sorted(by_class[cls])
        new = [i for i in ids if i not in side]
        rng.shuffle(new)
        count = {s: sum(1 for i in ids if side.get(i) == s) for s in ("tune", "holdout")}
        for i in new:
            s = "holdout" if count["holdout"] < count["tune"] else "tune" if count["tune"] < count["holdout"] else rng.choice(("tune", "holdout"))
            out[s].append(i)
            count[s] += 1
    return {"seed": seed, "tune": sorted(out["tune"]), "holdout": sorted(out["holdout"])}


def pick_split(questions: list[dict], split: dict | None, which: str) -> list[dict]:
    if which == "all":
        return questions
    if split is None:
        raise SystemExit("no split file: run `split` once first")
    missing = [q["id"] for q in questions if q["id"] not in split["tune"] and q["id"] not in split["holdout"]]
    if missing:
        raise SystemExit(f"{len(missing)} questions are in no split ({', '.join(missing[:5])}…): run `split --add`")
    keep = set(split[which])
    return [q for q in questions if q["id"] in keep]


# --- scoring (pure) ------------------------------------------------------------------------------------------------------------------

def context_items(out: dict) -> list[dict]:
    """The items of a recall that made it into its final `context`, in the order they appear there. An item the budget cut out is not
    in the context and does not count, for or against."""
    ctx = out.get("context") or ""
    items = []
    for f in out.get("facts") or []:
        items.append({"kind": "fact", "id": str(f.get("uuid") or ""), "episodes": [str(e) for e in f.get("episodes") or []],
                      "text": (f.get("fact") or "").strip(), "current": f.get("status") != "invalidated"})
    for c in out.get("chunks") or []:
        items.append({"kind": "chunk", "id": str(c.get("id") or ""), "episodes": [str(c["episode_uuid"])] if c.get("episode_uuid") else [],
                      "text": (c.get("text") or "").strip(), "current": not c.get("superseded")})
    for p in out.get("documents") or []:
        items.append({"kind": "doc", "id": str(p.get("document_id") or ""), "episodes": [], "text": (p.get("text") or "").strip(),
                      "current": not p.get("superseded")})
    placed = [(ctx.find(it["text"]), n, it) for n, it in enumerate(items) if it["text"]]
    return [it for pos, _, it in sorted(placed, key=lambda x: (x[0], x[1])) if pos >= 0]


def _relevant(it: dict, q: dict) -> bool:
    if it["kind"] == "doc":
        return it["id"] in {str(d) for d in q.get("answer_docs") or []}
    return bool(set(it["episodes"]) & {str(e) for e in q.get("answer_episodes") or []})


def _stale(it: dict, stale: set[str]) -> bool:
    """A replaced value shown as current: the replaced fact itself in the current section, or a fragment or passage that states it
    with no "may be superseded" warning. A current fact that only shares an episode with the old one is not stale."""
    if not it["current"]:
        return False
    return it["id"] in stale if it["kind"] in ("fact", "doc") else bool(set(it["episodes"]) & stale)


def score(q: dict, items: list[dict], ms: float | None = None) -> dict:
    """One question's record. Each metric is a (numerator, denominator) pair, so a class or a resample is the ratio of their sums:
    `noise` weighs every character the same, the rates weigh every question the same."""
    rel = [_relevant(it, q) for it in items]
    chars = sum(len(it["text"]) for it in items)
    m: dict[str, list[float]] = {"noise": [sum(len(it["text"]) for it, r in zip(items, rel, strict=True) if not r), chars]}
    cls = q["class"]
    if cls in ("point", "temporal", "volatile"):
        m["top3"] = [int(any(rel[:3])), 1]
    if cls == "entity":
        want = {str(e) for e in q["answer_episodes"]}
        got = {e for it in items for e in it["episodes"] if e in want}
        m["coverage"] = [len(got) / len(want), 1]
    if cls == "temporal" and q.get("stale"):
        m["stale_as_current"] = [int(any(_stale(it, {str(s) for s in q["stale"]}) for it in items)), 1]
    if cls == "ood":
        m["empty_ok"] = [int(not items), 1]
    return {"id": q["id"], "class": cls, "items": len(items), "ms": ms, "m": m}


def score_hook(h: dict, items: list[dict], ms: float | None = None) -> dict:
    """A real prompt: was anything injected, and was it the labelled note. `hook_precision`: of the injected contexts, the share that
    holds the note. `hook_silence`: of the prompts labelled `nothing`, the share with nothing injected."""
    note = label_hook(h)
    injected = int(bool(items))
    m: dict[str, list[float]] = {}
    if injected:
        m["hook_precision"] = [int(note not in (None, "nothing") and any(note in it["episodes"] for it in items)), 1]
    if note == "nothing":
        m["hook_silence"] = [1 - injected, 1]
    return {"id": h["id"], "class": "hook", "items": len(items), "ms": ms, "m": m}


def aggregate(records: list[dict], metric: str) -> float | None:
    num = den = 0.0
    for r in records:
        if metric in r["m"]:
            num += r["m"][metric][0]
            den += r["m"][metric][1]
    return num / den if den else None


def percentile(xs: list[float], q: float) -> float | None:
    if not xs:
        return None
    s = sorted(xs)
    return s[min(len(s), max(1, math.ceil(q / 100 * len(s)))) - 1]


METRICS_BY_CLASS = {"point": ("top3",), "volatile": ("top3",), "entity": ("coverage",), "temporal": ("top3", "stale_as_current"),
                    "ood": ("empty_ok",), "hook": ("hook_precision", "hook_silence")}


def _rows(records: list[dict]) -> list[tuple[str, str, list[dict]]]:
    """(scope, metric, records) for every metric reported: per class, and noise over each class and over all the questions."""
    out = []
    by: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        by[r["class"]].append(r)
    for cls in [*CLASSES, "hook"]:
        rs = by.get(cls) or []
        for metric in METRICS_BY_CLASS[cls]:
            if any(metric in r["m"] for r in rs):
                out.append((cls, metric, rs))
        if cls != "hook" and any(r["m"]["noise"][1] for r in rs):
            out.append((cls, "noise", rs))
    questions = [r for r in records if r["class"] != "hook"]
    if any(r["m"]["noise"][1] for r in questions):
        out.append(("all", "noise", questions))
    return out


def bootstrap(records: list[dict], fn, n: int = BOOT, seed: int = SEED) -> tuple[float | None, float | None]:
    """95 % percentile interval of `fn` over resamples of the records."""
    rng = random.Random(seed)
    vals = [v for _ in range(n) if (v := fn([records[rng.randrange(len(records))] for _ in records])) is not None]
    return (percentile(vals, 2.5), percentile(vals, 97.5)) if vals else (None, None)


def summarize(records: list[dict], n: int = BOOT) -> dict:
    rows = []
    for scope, metric, rs in _rows(records):
        lo, hi = bootstrap(rs, lambda x, m=metric: aggregate(x, m), n)
        rows.append({"scope": scope, "metric": metric, "n": sum(1 for r in rs if metric in r["m"]), "value": aggregate(rs, metric),
                     "lo": lo, "hi": hi})
    ms = [r["ms"] for r in records if r["ms"] is not None]
    return {"rows": rows, "latency_ms": {"p50": percentile(ms, 50), "p95": percentile(ms, 95)}}


# --- comparison (pure) ---------------------------------------------------------------------------------------------------------------

def compare(a: dict, b: dict, n: int = BOOT, seed: int = SEED) -> dict:
    """B against A on the questions both ran, paired: every resample draws the same questions for both. Differences are B − A; for
    the co-primaries also relative to A."""
    for k in ("budget", "split"):
        if a["meta"].get(k) != b["meta"].get(k):
            raise SystemExit(f"the two runs differ in {k}: {a['meta'].get(k)} against {b['meta'].get(k)}")
    rb = {(r["class"], r["id"]): r for r in b["records"]}
    pairs = [(r, rb[(r["class"], r["id"])]) for r in a["records"] if (r["class"], r["id"]) in rb]
    if not pairs:
        raise SystemExit("the two runs share no question")
    rng = random.Random(seed)
    draws = [[rng.randrange(len(pairs)) for _ in pairs] for _ in range(n)]
    rows = []
    for scope, metric, _ in _rows([p[0] for p in pairs]):
        sel = [i for i, (x, _) in enumerate(pairs) if (scope == "all" and x["class"] != "hook") or x["class"] == scope]
        xa = [pairs[i][0] for i in sel]
        xb = [pairs[i][1] for i in sel]
        va, vb = aggregate(xa, metric), aggregate(xb, metric)
        if va is None or vb is None:
            continue
        diffs, rels = [], []
        pos = {i: k for k, i in enumerate(sel)}
        for d in draws:
            pick = [pos[i] for i in d if i in pos]
            if not pick:
                continue
            sa, sb = aggregate([xa[k] for k in pick], metric), aggregate([xb[k] for k in pick], metric)
            if sa is None or sb is None:
                continue
            diffs.append(sb - sa)
            if sa:
                rels.append((sb - sa) / sa)
        rows.append({"scope": scope, "metric": metric, "n": len(sel), "a": va, "b": vb, "diff": vb - va,
                     "diff_lo": percentile(diffs, 2.5), "diff_hi": percentile(diffs, 97.5),
                     "rel": (vb - va) / va if va else None, "rel_lo": percentile(rels, 2.5), "rel_hi": percentile(rels, 97.5)})
    return {"rows": rows, "verdict": verdict(rows), "latency_ms": {"a": a["summary"]["latency_ms"], "b": b["summary"]["latency_ms"]}}


def verdict(rows: list[dict]) -> dict:
    """The rule written before measuring (#492). Yes only when:
    - at least one co-primary (noise, stale-as-current; over all the questions) falls by its minimum relative effect, and its
      interval is wholly below zero;
    - no co-primary rises (its interval wholly above zero);
    - every answer metric's lower bound loses at most NON_INFERIORITY points.
    Anything else, a tie included, is a no."""
    def get(scope, metric):
        return next((r for r in rows if r["scope"] == scope and r["metric"] == metric), None)

    reasons, improved = [], []
    for metric in COPRIMARY:
        r = get("all" if metric == "noise" else "temporal", metric)
        if r is None:
            reasons.append(f"{metric}: not measured")
            continue
        if r["diff_lo"] is not None and r["diff_lo"] > 0:
            reasons.append(f"{metric}: worse")
        elif r["rel"] is not None and r["rel"] <= MIN_EFFECT[metric] and r["diff_hi"] is not None and r["diff_hi"] < 0:
            improved.append(metric)
        else:
            reasons.append(f"{metric}: below the minimum effect ({MIN_EFFECT[metric]:+.0%}) or not significant")
    inferior = [f"{r['scope']} {r['metric']}" for r in rows
                if r["metric"] in ANSWER and r["diff_lo"] is not None and 100 * r["diff_lo"] < NON_INFERIORITY]
    if inferior:
        reasons.append("worse answers: " + ", ".join(inferior))
    yes = bool(improved) and not inferior and not any(x.endswith("worse") for x in reasons)
    return {"yes": yes, "improved": improved, "reasons": reasons}


# --- markdown ------------------------------------------------------------------------------------------------------------------------

def _pct(v) -> str:
    return "–" if v is None else f"{100 * v:.1f}"


def summary_markdown(meta: dict, s: dict) -> str:
    lines = [f"## Eval · budget {meta['budget']} · split {meta['split']} · {meta['questions']} questions"
             + (f", {meta['hook']} hook prompts" if meta.get("hook") else ""), "",
             "| class | metric | n | value % | 95 % interval |", "|---|---|--:|--:|--:|"]
    lines += [f"| {r['scope']} | {r['metric']} | {r['n']} | {_pct(r['value'])} | {_pct(r['lo'])} – {_pct(r['hi'])} |" for r in s["rows"]]
    lat = s["latency_ms"]
    lines += ["", f"Latency: p50 {lat['p50']} ms, p95 {lat['p95']} ms" if lat["p50"] is not None else "Latency: not measured", ""]
    return "\n".join(lines)


def compare_markdown(c: dict) -> str:
    lines = ["| class | metric | n | A % | B % | B − A (points) | 95 % interval | relative |", "|---|---|--:|--:|--:|--:|--:|--:|"]
    for r in c["rows"]:
        rel = "–" if r["rel"] is None else f"{100 * r['rel']:+.0f} %"
        lines.append(f"| {r['scope']} | {r['metric']} | {r['n']} | {_pct(r['a'])} | {_pct(r['b'])} | {100 * r['diff']:+.1f} | "
                     f"{_pct(r['diff_lo'])} – {_pct(r['diff_hi'])} | {rel} |")
    v = c["verdict"]
    lines += ["", f"**Verdict: {'yes' if v['yes'] else 'no'}**" + (f" (improved: {', '.join(v['improved'])})" if v["improved"] else "")]
    lines += [f"- {x}" for x in v["reasons"]]
    la, lb = c["latency_ms"]["a"], c["latency_ms"]["b"]
    lines += ["", f"Latency p50 / p95: A {la['p50']} / {la['p95']} ms, B {lb['p50']} / {lb['p95']} ms", ""]
    return "\n".join(lines)


# --- running against the snapshot ------------------------------------------------------------------------------------------------------

def run(questions: list[dict], hooks: list[dict], recall_fn, budget: str) -> list[dict]:
    """`recall_fn(query, **params) -> dict` is the app's recall on the snapshot (or a fake in the tests)."""
    params = BUDGETS[budget]
    records = []
    for q in questions:
        out = recall_fn(q["query"], **params)
        records.append(score(q, context_items(out), (out.get("ms") or {}).get("total")))
    for h in hooks:
        if label_hook(h) is None:
            continue
        out = recall_fn(h["query"], **params)
        records.append(score_hook(h, context_items(out), (out.get("ms") or {}).get("total")))
    return records


def _app():
    sys.path.insert(0, str(HERE.parent / "api"))
    from mimirsynth import models, recall
    from mimirsynth.store import _factory
    return models, recall, _factory


def recall_on(slug: str):
    models, recall, factory = _app()
    with factory()() as db:
        b = db.query(models.Brain).filter(models.Brain.slug == slug).one_or_none()
        if b is None:
            raise SystemExit(f"no brain with slug {slug!r}")
        bid, gname = b.id, b.graph_name
    return lambda query, **p: recall.recall(bid, gname, query, **p)


def hook_samples(slug: str) -> list[dict]:
    """The replay sample's prompts that came through the hook (over HTTP, with its parameters), as a sheet to label."""
    models, _, factory = _app()
    with factory()() as db:
        b = db.query(models.Brain).filter(models.Brain.slug == slug).one_or_none()
        if b is None:
            raise SystemExit(f"no brain with slug {slug!r}")
        S = models.RecallSample
        rows = db.query(S).filter(S.brain_id == b.id, S.via == "http").order_by(S.id).all()
        return [{"id": f"h{s.id}", "query": s.query, "label": "", "masked": s.masked} for s in rows
                if all((s.params or {}).get(k) == v for k, v in HOOK_PARAMS.items())]


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def main(argv: list[str] | None = None, recall_fn=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("split", help="fix the tune / holdout split once")
    s.add_argument("--gold", type=Path, required=True)
    s.add_argument("--out", type=Path, default=OUT / "split.json")
    s.add_argument("--add", action="store_true", help="place only the questions that are in no side yet")
    r = sub.add_parser("run", help="run the questions and score them")
    r.add_argument("--brain", required=True)
    r.add_argument("--gold", type=Path, required=True)
    r.add_argument("--hookset", type=Path, help="the labelled real prompts (from `hookset`)")
    r.add_argument("--split", choices=("tune", "holdout", "all"), default="tune")
    r.add_argument("--split-file", type=Path, default=OUT / "split.json")
    r.add_argument("--budget", choices=tuple(BUDGETS), default="2500")
    r.add_argument("--include-drafts", action="store_true", help="also the questions the maintainer has not validated")
    r.add_argument("--label", default="", help="a name for this system, kept in the result")
    r.add_argument("--out", type=Path)
    c = sub.add_parser("compare", help="B against A, with the verdict")
    c.add_argument("a", type=Path)
    c.add_argument("b", type=Path)
    h = sub.add_parser("hookset", help="the hook's real prompts from the replay sample, to label")
    h.add_argument("--brain", required=True)
    h.add_argument("--out", type=Path, default=OUT / "hookset.jsonl")
    a = ap.parse_args(argv)

    if a.cmd == "compare":
        res = compare(json.loads(a.a.read_text(encoding="utf-8")), json.loads(a.b.read_text(encoding="utf-8")))
        print(compare_markdown(res))
        return 0 if res["verdict"]["yes"] else 1
    if a.cmd == "hookset":
        rows = hook_samples(a.brain)
        a.out.parent.mkdir(parents=True, exist_ok=True)
        _write_jsonl(a.out, rows)
        print(f"{len(rows)} hook prompts written to {a.out}. Put in `label` the uuid of the episode that should have been injected, "
              "or `nothing`.")
        return 0

    gold = load_jsonl(a.gold)
    problems = check_gold(gold)
    if problems:
        raise SystemExit("the gold set has problems:\n" + "\n".join(f"- {p}" for p in problems))
    if a.cmd == "split":
        old = json.loads(a.out.read_text(encoding="utf-8")) if a.out.exists() else None
        if old and not a.add:
            raise SystemExit(f"{a.out} already exists: the split is fixed once. Use --add to place new questions only")
        sp = make_split(gold, old=old)
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(sp, indent=1), encoding="utf-8")
        print(f"tune {len(sp['tune'])}, holdout {len(sp['holdout'])} → {a.out}")
        return 0

    split = json.loads(a.split_file.read_text(encoding="utf-8")) if a.split_file.exists() else None
    questions = pick_split(gold, split, a.split)
    drafts = [q for q in questions if not q.get("validated")]
    if drafts and not a.include_drafts:
        print(f"{len(drafts)} questions not validated yet are left out (--include-drafts to run them)", file=sys.stderr)
        questions = [q for q in questions if q.get("validated")]
    hooks = load_jsonl(a.hookset) if a.hookset else []
    fn = recall_fn or recall_on(a.brain)
    records = run(questions, hooks, fn, a.budget)
    meta = {"brain": a.brain, "budget": a.budget, "params": BUDGETS[a.budget], "split": a.split, "label": a.label,
            "questions": sum(1 for x in records if x["class"] != "hook"), "hook": sum(1 for x in records if x["class"] == "hook"),
            "drafts_included": bool(drafts and a.include_drafts), "when": datetime.now(UTC).isoformat(timespec="seconds")}
    s = summarize(records)
    out = a.out or OUT / f"run-{a.label or 'x'}-{a.budget}-{a.split}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"meta": meta, "summary": s, "records": records}, indent=1), encoding="utf-8")
    print(summary_markdown(meta, s))
    print(f"→ {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
