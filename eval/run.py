"""Retrieval eval for Phase 0 (#492): per-class metrics on the final context, at two budgets, with intervals, and a paired comparison
with a verdict fixed in advance.

It runs on the frozen Phase 0 snapshot, never on production, with the instance's MIMIRSYNTH_* environment and
MIMIRSYNTH_EVAL_SNAPSHOT=1 (set only on the restored instance), from `api/`:

    cd api && .venv/bin/python ../eval/run.py hookset --brain SLUG      # real prompts from the replay sample, to label
    cd api && .venv/bin/python ../eval/run.py split   --gold ../eval/out/gold.jsonl --hookset ../eval/out/hookset.jsonl
    cd api && .venv/bin/python ../eval/run.py run     --brain SLUG --gold ../eval/out/gold.jsonl --split holdout --budget plugin
    cd api && .venv/bin/python ../eval/run.py compare ../eval/out/a.json ../eval/out/b.json

Its own output goes to `eval/out/` (ignored by git): the questions and the results hold the brain's own text. It does not change the
brain, but it is not read-only: the app's recall counts its embedding calls in the snapshot's `ai_usage`, as any recall does.
"""
from __future__ import annotations

import argparse
import contextlib
import functools
import importlib.util
import json
import math
import random
import re
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"

CLASSES = ("point", "entity", "temporal", "ood", "volatile")
BUDGETS = {   # the recall parameters each budget runs with
    "2500": {"n_facts": 8, "n_chunks": 4, "max_chars": 2500},
    # What the agent plugins' per-prompt hook sends. The hook also cuts what it injects at 9,500 characters
    # (integrations/claude-code/plugin/scripts/hook.py), which a max_chars of 4,000 never reaches: raising max_chars past it would
    # measure text the agent never sees.
    "plugin": {"n_facts": 6, "n_chunks": 3, "max_chars": 4000},
}
# Declared in advance (#492): the co-primaries must fall by at least this much, relative to the baseline; the answer metrics may
# not lose more than NON_INFERIORITY points at the lower bound of their interval.
MIN_EFFECT = {"noise": -0.30, "stale_as_current": -0.50}
COPRIMARY = tuple(MIN_EFFECT)
ANSWER = ("top3", "coverage", "empty_ok", "hook_precision", "hook_silence")
NON_INFERIORITY = -3.0
BOOT = 2000
SEED = 492


@functools.cache
def _census():
    spec = importlib.util.spec_from_file_location("census", HERE / "census" / "census.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@functools.cache
def _clean():
    spec = importlib.util.spec_from_file_location("eval_clean", HERE / "clean" / "clean.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


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


def _ids(v) -> list[str] | None:
    """A list of non-empty strings, or None when it is not one."""
    if v is None:
        return []
    if not isinstance(v, list) or not all(isinstance(x, str) and x.strip() for x in v):
        return None
    return v


def check_gold(rows: list[dict]) -> list[str]:
    """What is wrong with a gold set, one line per problem; empty when it is usable.

    A question: `id`, `class` (one of CLASSES), `query`, `answer_episodes` (the episode uuids that contain the answer; empty only out of
    domain), optional `answer_docs` (document ids), optional `stale` (for temporal ones: what must not show as current), and
    `validated` (true or false: the maintainer read and accepted it)."""
    problems, seen = [], set()
    for i, q in enumerate(rows, 1):
        if not isinstance(q, dict):
            problems.append(f"line {i}: not a question object")
            continue
        good_id = isinstance(q.get("id"), str) and bool(q["id"].strip())
        where = f"question {q['id'] if good_id else '#' + str(i)}"
        if not good_id:
            problems.append(f"{where}: no id")
        elif q["id"] in seen:
            problems.append(f"{where}: repeated id")
        else:
            seen.add(q["id"])
        if q.get("class") not in CLASSES:
            problems.append(f"{where}: class must be one of {', '.join(CLASSES)}")
        if not isinstance(q.get("query"), str) or not q["query"].strip():
            problems.append(f"{where}: no query")
        lists = {k: _ids(q.get(k)) for k in ("answer_episodes", "answer_docs", "stale")}
        for k, v in lists.items():
            if v is None:
                problems.append(f"{where}: {k} must be a list of ids")
        if "validated" in q and not isinstance(q["validated"], bool):
            problems.append(f"{where}: validated must be true or false")
        eps, docs = set(lists["answer_episodes"] or []), set(lists["answer_docs"] or [])
        if q.get("class") == "ood" and (eps or docs):
            problems.append(f"{where}: an out-of-domain question has no answer")
        if q.get("class") in CLASSES and q.get("class") != "ood" and not (eps or docs):
            problems.append(f"{where}: no answer_episodes")
        if q.get("class") == "entity" and len(eps) < 2:
            problems.append(f"{where}: an entity question has its answer in at least two distinct episodes")
    return problems


def label_hook(h: dict) -> str | None:
    """A hook prompt's label: an episode uuid (the note that should have been injected), `nothing`, or None while unlabelled."""
    lab = (h.get("label") or "").strip()
    return lab or None


# --- split ---------------------------------------------------------------------------------------------------------------------------

def make_split(items: list[dict], seed: int = SEED, old: dict | None = None) -> dict:
    """`tune` / `holdout` at 50 / 50 within each class, fixed by id. With `old`, its ids keep their side and only new ones are placed,
    each on the smaller side of its class."""
    old = old or {"tune": [], "holdout": []}
    side = {i: s for s in ("tune", "holdout") for i in old.get(s, [])}
    by_class: dict[str, list[str]] = defaultdict(list)
    for q in items:
        by_class[q.get("class") or "hook"].append(q["id"])
    rng = random.Random(seed)
    out = {"tune": list(old.get("tune", [])), "holdout": list(old.get("holdout", []))}
    for cls in sorted(by_class):
        ids = sorted(by_class[cls])
        new = [i for i in ids if i not in side]
        rng.shuffle(new)
        count = {s: sum(1 for i in ids if side.get(i) == s) for s in ("tune", "holdout")}
        for i in new:
            if count["holdout"] != count["tune"]:
                s = "holdout" if count["holdout"] < count["tune"] else "tune"
            else:
                s = rng.choice(("tune", "holdout"))
            out[s].append(i)
            count[s] += 1
    return {"tune": sorted(out["tune"]), "holdout": sorted(out["holdout"])}


def pick_split(items: list[dict], split: dict | None, which: str, what: str = "questions") -> list[dict]:
    if which == "all" or not items:
        return items
    if split is None:
        raise SystemExit("no split file: run `split` once first")
    part = split if what == "questions" else split.get("hook") or {"tune": [], "holdout": []}
    missing = [q["id"] for q in items if q["id"] not in part["tune"] and q["id"] not in part["holdout"]]
    if missing:
        raise SystemExit(f"{len(missing)} {what} are in no split ({', '.join(missing[:5])}…): run `split --add`")
    keep = set(part[which])
    return [q for q in items if q["id"] in keep]


# --- scoring (pure) ------------------------------------------------------------------------------------------------------------------

# The line build_context writes under a fragment or a passage that may be superseded (api/mimirsynth/recall.py, _superseded_note),
# in each language the app speaks (web/src/i18n/en.server.json). Any other `> ` line under an entry is not part of it.
WARNINGS = ("\n> Puede estar superado: ", "\n> May be superseded: ")


def context_items(out: dict) -> list[dict]:
    """The items of a recall that made it into its final `context`, in the order they appear there. An item counts only by its own
    line, as `build_context` writes it: a fact by a line `- <fact> (`, a fragment or a passage by its text right under a `###` header
    (a passage's header carries its `[doc N, … M]`). A text quoted inside another line (`[sustituye a «…»]`, a "may be superseded"
    warning) does not count, and two items with the same text need two lines.

    Each item carries `chars`, the characters of the context it takes: a fact's whole line, a fragment's or a passage's header, text
    and "may be superseded" lines, each with its line break. No two items share a character, so their `chars` never add up to more
    than the context: passages are placed first (their header is the most specific), then fragments, then facts, and a match that
    would overlap one already placed (a `###` heading or a `- … (` line inside a passage's text, say) is not taken."""
    ctx = out.get("context") or ""
    lines = ctx.split("\n")
    starts, pos = [], 0
    for ln in lines:
        starts.append(pos)
        pos += len(ln) + 1
    taken: list[tuple[int, int]] = []
    found: list[tuple[int, dict]] = []

    def with_break(end: int) -> int:
        return end + 1 if ctx[end:end + 1] == "\n" else end

    def free(start: int, end: int) -> bool:
        return all(end <= s or start >= e for s, e in taken)

    def place(start: int, end: int, it: dict) -> None:
        taken.append((start, end))
        found.append((start, {**it, "chars": end - start}))

    def under_header(text: str, header_ok) -> tuple[int, int] | None:
        """(start, end) of a free entry whose header passes `header_ok` and whose text follows it, with its warning lines."""
        for i in range(len(lines) - 1):
            if not lines[i].startswith("### ") or not header_ok(lines[i]) or not ctx.startswith(text, starts[i + 1]):
                continue
            end = starts[i + 1] + len(text)
            while any(ctx.startswith(w, end) for w in WARNINGS):
                nxt = ctx.find("\n", end + 1)
                end = len(ctx) if nxt < 0 else nxt
            end = with_break(end)
            if free(starts[i], end):
                return starts[i], end
        return None

    for d in out.get("documents") or []:
        text = (d.get("text") or "").strip()
        doc, idx = d.get("document_id"), d.get("chunk_idx")
        marker = re.compile(rf"\[doc {re.escape(str(doc))}, \S+ {re.escape(str(idx))}\]$")
        span = under_header(text, lambda h, m=marker: bool(m.search(h))) if text else None
        if span is not None:
            place(*span, {"kind": "doc", "id": str(doc or ""), "episodes": [], "text": text, "current": not d.get("superseded")})
    for c in out.get("chunks") or []:
        text = (c.get("text") or "").strip()
        span = under_header(text, lambda h: not re.search(r"\[doc \d+, \S+ \d+\]$", h)) if text else None
        if span is not None:
            place(*span, {"kind": "chunk", "id": str(c.get("id") or ""), "text": text, "current": not c.get("superseded"),
                          "episodes": [str(c["episode_uuid"])] if c.get("episode_uuid") else []})

    def own_section(ln: str, prefix: str, current: bool) -> bool:
        # an old fact's line reads `- <fact> (<since> → <until>)`; a current one's parenthesis has no arrow
        return ln.startswith(prefix) and ("→" not in ln[len(prefix):].split(")", 1)[0]) == current

    for f in out.get("facts") or []:
        text = (f.get("fact") or "").strip()
        current = f.get("status") != "invalidated"
        for i, ln in enumerate(lines):
            end = with_break(starts[i] + len(ln))
            if text and own_section(ln, f"- {text} (", current) and free(starts[i], end):
                place(starts[i], end, {"kind": "fact", "id": str(f.get("uuid") or ""), "text": text, "current": current,
                                       "episodes": [str(e) for e in f.get("episodes") or []]})
                break
    return [it for _, it in sorted(found, key=lambda x: x[0])]


def _relevant(it: dict, q: dict) -> bool:
    if it["kind"] == "doc":
        return it["id"] in set(q.get("answer_docs") or [])
    return bool(set(it["episodes"]) & set(q.get("answer_episodes") or []))


def _stale(it: dict, stale: set[str]) -> bool:
    """A replaced value shown as current: the replaced fact in the current section (Graphiti did not invalidate it), or a fragment
    or passage from a stale episode or document with no "may be superseded" warning. A current fact that only shares an episode
    with the old one is not stale."""
    if not it["current"]:
        return False
    return it["id"] in stale if it["kind"] in ("fact", "doc") else bool(set(it["episodes"]) & stale)


def _context(items: list[dict], context: str | None) -> tuple[int, bool, int]:
    """(characters of the final context, whether it has any text, characters no item takes). Without `context`, the items alone."""
    taken = sum(it["chars"] for it in items)
    if context is None:
        return taken, bool(items), 0
    return len(context), bool(context.strip()), max(0, len(context) - taken)


def score(q: dict, items: list[dict], ms: float | None = None, context: str | None = None) -> dict:
    """One question's record. Each metric is a (numerator, denominator) pair, so a class or a resample is the ratio of their sums:
    `noise` weighs every character the same, the rates weigh every question the same.

    `noise` is over the whole final `context`: every character that is not part of an item from the answer is noise, whether it was
    parsed or not (section headers, state cards, a format the parser does not know). `unparsed_chars` is the part no item took.
    `empty_ok` reads the context itself, so a state card alone counts as something injected."""
    total, has_context, unparsed = _context(items, context)
    rel = [_relevant(it, q) for it in items]
    m: dict[str, list[float]] = {"noise": [total - sum(it["chars"] for it, r in zip(items, rel, strict=True) if r), total]}
    cls = q["class"]
    if cls in ("point", "temporal", "volatile"):
        m["top3"] = [int(any(rel[:3])), 1]
    if cls == "entity":
        want = set(q["answer_episodes"])
        got = {e for it in items for e in it["episodes"] if e in want}
        m["coverage"] = [len(got) / len(want), 1]
    if cls == "temporal" and q.get("stale"):
        m["stale_as_current"] = [int(any(_stale(it, set(q["stale"])) for it in items)), 1]
    if cls == "ood":
        m["empty_ok"] = [int(not has_context), 1]
    return {"id": q["id"], "class": cls, "items": len(items), "ms": ms, "m": m, "chars": total, "unparsed_chars": unparsed}


def score_hook(h: dict, items: list[dict], ms: float | None = None, context: str | None = None) -> dict:
    """A real prompt: was anything injected (the hook injects any non-empty context), and was it the labelled note.
    `hook_precision`: of the injected contexts, the share that holds the note. `hook_silence`: of the prompts labelled `nothing`, the
    share with nothing injected."""
    note = label_hook(h)
    total, has_context, unparsed = _context(items, context)
    injected = int(has_context)
    m: dict[str, list[float]] = {}
    if injected:
        m["hook_precision"] = [int(note not in (None, "nothing") and any(note in it["episodes"] for it in items)), 1]
    if note == "nothing":
        m["hook_silence"] = [1 - injected, 1]
    return {"id": h["id"], "class": "hook", "items": len(items), "ms": ms, "m": m, "chars": total, "unparsed_chars": unparsed}


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


def _has_noise(rs: list[dict]) -> bool:
    return any(r["m"].get("noise", [0, 0])[1] for r in rs)


def _rows(records: list[dict]) -> list[tuple[str, str, list[dict]]]:
    """(scope, metric, records) for every metric reported: per class, and noise over each class and over all the questions. A record
    whose recall failed is left out."""
    ok = [r for r in records if not r.get("error")]
    out = []
    by: dict[str, list[dict]] = defaultdict(list)
    for r in ok:
        by[r["class"]].append(r)
    for cls in [*CLASSES, "hook"]:
        rs = by.get(cls) or []
        for metric in METRICS_BY_CLASS[cls]:
            if any(metric in r["m"] for r in rs):
                out.append((cls, metric, rs))
        if cls != "hook" and _has_noise(rs):
            out.append((cls, "noise", rs))
    questions = [r for r in ok if r["class"] != "hook"]
    if _has_noise(questions):
        out.append(("all", "noise", questions))
    return out


def bootstrap(records: list[dict], fn, n: int = BOOT, seed: int = SEED) -> tuple[float | None, float | None]:
    """95 % percentile interval of `fn` over resamples of the records."""
    if not records:
        return None, None
    rng = random.Random(seed)
    vals = [v for _ in range(n) if (v := fn([records[rng.randrange(len(records))] for _ in records])) is not None]
    return (percentile(vals, 2.5), percentile(vals, 97.5)) if vals else (None, None)


def summarize(records: list[dict], n: int = BOOT) -> dict:
    rows = []
    for scope, metric, rs in _rows(records):
        lo, hi = bootstrap(rs, lambda x, m=metric: aggregate(x, m), n)
        rows.append({"scope": scope, "metric": metric, "n": sum(1 for r in rs if metric in r["m"]), "value": aggregate(rs, metric),
                     "lo": lo, "hi": hi})
    ok = [r for r in records if not r.get("error")]
    ms = [r["ms"] for r in ok if r.get("ms") is not None]
    questions = [r for r in ok if r["class"] != "hook"]   # the ones `noise` is measured on
    return {"rows": rows, "errors": sum(1 for r in records if r.get("error")),
            "unparsed_chars": sum(r.get("unparsed_chars") or 0 for r in questions),
            "context_chars": sum(r.get("chars") or 0 for r in questions),
            "latency_ms": {"p50": percentile(ms, 50), "p95": percentile(ms, 95)}}


# --- comparison (pure) ---------------------------------------------------------------------------------------------------------------

def compare(a: dict, b: dict, n: int = BOOT, seed: int = SEED) -> dict:
    """B against A on the questions both ran without error, paired: every resample draws the same questions for both. Differences are
    B − A, and relative to A. A metric A measured and B could not (nothing injected for any hook prompt, say) is kept, with no value,
    and the verdict counts it against B."""
    for k in ("budget", "split", "drafts_included"):
        if a["meta"].get(k) != b["meta"].get(k):
            raise SystemExit(f"the two runs differ in {k}: {a['meta'].get(k)} against {b['meta'].get(k)}")
    rb = {(r["class"], r["id"]): r for r in b["records"]}
    shared = [(r, rb[(r["class"], r["id"])]) for r in a["records"] if (r["class"], r["id"]) in rb]
    pairs = [(x, y) for x, y in shared if not x.get("error") and not y.get("error")]
    failed = {"a": sum(1 for x, _ in shared if x.get("error")), "b": sum(1 for _, y in shared if y.get("error"))}
    if not pairs:
        raise SystemExit("the two runs share no question that ran in both")
    rng = random.Random(seed)
    draws = [[rng.randrange(len(pairs)) for _ in pairs] for _ in range(n)]
    rows = []
    for scope, metric, _ in _rows([p[0] for p in pairs]):
        sel = [i for i, (x, _) in enumerate(pairs) if (scope == "all" and x["class"] != "hook") or x["class"] == scope]
        xa, xb = [pairs[i][0] for i in sel], [pairs[i][1] for i in sel]
        va, vb = aggregate(xa, metric), aggregate(xb, metric)
        if va is None:
            continue
        row = {"scope": scope, "metric": metric, "n": len(sel), "a": va, "b": vb, "diff": None, "diff_lo": None, "diff_hi": None,
               "rel": None, "rel_lo": None, "rel_hi": None}
        if vb is not None:
            pos = {i: k for k, i in enumerate(sel)}
            diffs, rels = [], []
            for d in draws:
                pick = [pos[i] for i in d if i in pos]
                sa = aggregate([xa[k] for k in pick], metric) if pick else None
                sb = aggregate([xb[k] for k in pick], metric) if pick else None
                if sa is None or sb is None:
                    continue
                diffs.append(sb - sa)
                if sa:
                    rels.append((sb - sa) / sa)
            row.update(diff=vb - va, diff_lo=percentile(diffs, 2.5), diff_hi=percentile(diffs, 97.5), rel=(vb - va) / va if va else None,
                       rel_lo=percentile(rels, 2.5), rel_hi=percentile(rels, 97.5))
        rows.append(row)
    counts = {"a": len(a["records"]), "b": len(b["records"]), "paired": len(pairs), "failed_a": failed["a"], "failed_b": failed["b"]}
    return {"rows": rows, "verdict": verdict(rows, failed["b"] - failed["a"]), "counts": counts,
            "latency_ms": {"a": a["summary"]["latency_ms"], "b": b["summary"]["latency_ms"]}}


def verdict(rows: list[dict], more_failed: int = 0) -> dict:
    """The rule written before measuring (#492). Yes only when:
    - at least one co-primary (noise over all the questions; stale-as-current on the temporal ones) falls by its minimum relative
      effect, and the interval of its difference is wholly below zero;
    - no co-primary rises (the interval wholly above zero);
    - every answer metric A measured is measured in B too, and its lower bound loses at most NON_INFERIORITY points;
    - B fails on no more of the shared questions than A (`more_failed`): a failed recall or an unparsed context leaves the pairing,
      and B must not be judged on the questions it happened to get through.
    Anything else, a tie included, is a no. A co-primary at 0 in A cannot fall, so it does not count for B."""
    def get(scope, metric):
        return next((r for r in rows if r["scope"] == scope and r["metric"] == metric), None)

    reasons, improved, worse = [], [], []
    for metric in COPRIMARY:
        r = get("all" if metric == "noise" else "temporal", metric)
        if r is None:
            reasons.append(f"{metric}: not measured")
        elif r["b"] is None:
            reasons.append(f"{metric}: not measured in B")
            worse.append(metric)
        elif r["diff_lo"] is not None and r["diff_lo"] > 0:
            reasons.append(f"{metric}: worse")
            worse.append(metric)
        elif r["rel"] is not None and r["rel"] <= MIN_EFFECT[metric] and r["diff_hi"] is not None and r["diff_hi"] < 0:
            improved.append(metric)
        else:
            reasons.append(f"{metric}: below the minimum effect ({MIN_EFFECT[metric]:+.0%}) or not significant")
    inferior = []
    for r in rows:
        if r["metric"] not in ANSWER:
            continue
        if r["b"] is None:
            inferior.append(f"{r['scope']} {r['metric']} (not measured in B)")
        elif r["diff_lo"] is not None and 100 * r["diff_lo"] < NON_INFERIORITY:
            inferior.append(f"{r['scope']} {r['metric']}")
    if inferior:
        reasons.append("worse answers: " + ", ".join(inferior))
    if more_failed > 0:
        reasons.append(f"B failed on {more_failed} more of the shared questions than A")
    return {"yes": bool(improved) and not worse and not inferior and more_failed <= 0, "improved": improved, "reasons": reasons}


# --- markdown ------------------------------------------------------------------------------------------------------------------------

def _pct(v) -> str:
    return "–" if v is None else f"{100 * v:.1f}"


def _pts(v) -> str:
    return "–" if v is None else f"{100 * v:+.1f}"


def summary_markdown(meta: dict, s: dict) -> str:
    lines = [f"## Eval · budget {meta['budget']} · split {meta['split']} · {meta['questions']} questions"
             + (f", {meta['hook']} hook prompts" if meta.get("hook") else ""), "",
             "| class | metric | n | value % | 95 % interval |", "|---|---|--:|--:|--:|"]
    lines += [f"| {r['scope']} | {r['metric']} | {r['n']} | {_pct(r['value'])} | {_pct(r['lo'])} – {_pct(r['hi'])} |" for r in s["rows"]]
    lat = s["latency_ms"]
    lines += ["", f"Latency: p50 {lat['p50']} ms, p95 {lat['p95']} ms" if lat["p50"] is not None else "Latency: not measured"]
    if s.get("context_chars"):
        lines.append(f"Unparsed: {s['unparsed_chars']} of the questions' {s['context_chars']} context characters "
                     f"({_pct(s['unparsed_chars'] / s['context_chars'])} %), counted as noise.")
    if s.get("errors"):
        lines.append(f"**{s['errors']} recalls failed** and are left out (see `error` in the records).")
    return "\n".join(lines + [""])


def compare_markdown(c: dict) -> str:
    k = c["counts"]
    lines = [(f"A {k['a']} records, B {k['b']}, compared on the {k['paired']} that ran in both. Of the shared ones, A failed on "
              f"{k['failed_a']} and B on {k['failed_b']}."), "",
             "| class | metric | n | A % | B % | B − A (points) | 95 % interval | relative |", "|---|---|--:|--:|--:|--:|--:|--:|"]
    for r in c["rows"]:
        rel = "–" if r["rel"] is None else f"{100 * r['rel']:+.0f} %"
        lines.append(f"| {r['scope']} | {r['metric']} | {r['n']} | {_pct(r['a'])} | {_pct(r['b'])} | {_pts(r['diff'])} | "
                     f"{_pts(r['diff_lo'])} – {_pts(r['diff_hi'])} | {rel} |")
    v = c["verdict"]
    lines += ["", f"**Verdict: {'yes' if v['yes'] else 'no'}**" + (f" (improved: {', '.join(v['improved'])})" if v["improved"] else "")]
    lines += [f"- {x}" for x in v["reasons"]]
    la, lb = c["latency_ms"]["a"], c["latency_ms"]["b"]
    lines += ["", f"Latency p50 / p95: A {la['p50']} / {la['p95']} ms, B {lb['p50']} / {lb['p95']} ms", ""]
    return "\n".join(lines)


# --- running against the snapshot ------------------------------------------------------------------------------------------------------

def _one(item: dict, recall_fn, params: dict, scorer) -> dict:
    """One recall, scored. A failed recall is recorded with its error. So is a context the parser cannot read: the recall returned
    items and none of them was found in a context that has text. Scoring it would read as empty (no answer, no noise), so it leaves
    the metrics and the pairing instead."""
    def failed(error: str, ms=None) -> dict:
        return {"id": item["id"], "class": item.get("class") or "hook", "items": 0, "ms": ms, "m": {}, "error": error}
    try:
        out = recall_fn(item["query"], **params)
    except Exception as e:  # noqa: BLE001  (one failed recall is recorded, the run goes on)
        return failed(f"{type(e).__name__}: {e}")
    ctx, ms, items = out.get("context") or "", (out.get("ms") or {}).get("total"), context_items(out)
    if ctx.strip() and not items and any(out.get(k) for k in ("facts", "chunks", "documents")):
        return failed("unparsed context: the recall returned items and none was found in its context", ms)
    return scorer(item, items, ms, ctx)


def run(questions: list[dict], hooks: list[dict], recall_fn, budget: str) -> list[dict]:
    """`recall_fn(query, **params) -> dict` is the app's recall on the snapshot (or a fake in the tests)."""
    params = BUDGETS[budget]
    records = [_one(q, recall_fn, params, score) for q in questions]
    return records + [_one(h, recall_fn, params, score_hook) for h in hooks if label_hook(h) is not None]


def _app():
    sys.path.insert(0, str(HERE.parent / "api"))
    from mimirsynth import models, recall
    from mimirsynth.federation import sources_for
    from mimirsynth.store import _factory
    return models, recall, sources_for, _factory


def snapshot_guard() -> None:
    """Only on the instance where the snapshot was restored, which says so with MIMIRSYNTH_EVAL_SNAPSHOT=1: production is PostgreSQL
    too, and the recall writes (a grant's last use, `ai_usage`). A snapshot is always PostgreSQL; an unset MIMIRSYNTH_DATABASE_URL
    would open (and create) the development SQLite file."""
    import os
    if os.environ.get("MIMIRSYNTH_EVAL_SNAPSHOT") != "1":
        raise SystemExit("set MIMIRSYNTH_EVAL_SNAPSHOT=1, only on the instance where the Phase 0 snapshot was restored")
    sys.path.insert(0, str(HERE.parent / "api"))
    from mimirsynth.store import engine
    name = engine().dialect.name
    if name != "postgresql" and os.environ.get("MIMIRSYNTH_CENSUS_ALLOW_SQLITE") != "1":
        raise SystemExit(f"the snapshot must be PostgreSQL (MIMIRSYNTH_DATABASE_URL); this is {name}")


@contextlib.contextmanager
def counted():
    """The AI calls inside (the recall's embeddings, the drafts' LLM calls) counted in `ai_usage` for the instance (brain 0) under
    the purpose `eval`, never for the brain: its monthly AI budget would count them, and reaching it sends an alert through the
    channels the snapshot copied from production. The recall opens its own scope for the brain, so `usage.scope` is replaced for
    the length of the block, in this process only. The counters are written before the block ends: the app writes them every few
    seconds, and would lose the last ones."""
    from mimirsynth import usage
    real = usage.scope
    usage.scope = lambda _brain, _purpose: real(0, "eval")
    try:
        with real(0, "eval"):
            yield
    finally:
        usage.scope = real
        usage.flush()


def recall_on(slug: str) -> tuple:
    """The app's recall on one brain, as the hook's HTTP call makes it: with what other brains lend it (federation; reading a grant
    stamps its last use), in the instance's default language and with its default number of document passages."""
    snapshot_guard()
    from mimirsynth import appsettings
    lang = appsettings.get("default_language") or "es"
    models, recall, sources_for, factory = _app()
    with factory()() as db:
        b = db.query(models.Brain).filter(models.Brain.slug == slug).one_or_none()
        if b is None:
            raise SystemExit(f"no brain with slug {slug!r}")
        bid, gname, src = b.id, b.graph_name, sources_for(db, b)
    extra = {"sources": src} if src else {}
    return (lambda query, **p: recall.recall(bid, gname, query, lang=lang, **p, **extra)), {
        "lang": lang, "docs": "instance default", "federated": [s.slug for s in src]}


def hook_samples(slug: str) -> list[dict]:
    """The replay sample's prompts that came through the hook (over HTTP, with its parameters), as a sheet to label."""
    snapshot_guard()
    census = _census()
    models, _, _, factory = _app()
    with factory()() as db:
        b = db.query(models.Brain).filter(models.Brain.slug == slug).one_or_none()
        if b is None:
            raise SystemExit(f"no brain with slug {slug!r}")
        S = models.RecallSample
        rows = db.query(S).filter(S.brain_id == b.id).order_by(S.id).all()
        return hook_rows([{"id": s.id, "via": s.via, "params": s.params, "query": s.query, "masked": s.masked} for s in rows],
                         census._hook_like)


def hook_rows(samples: list[dict], hook_like) -> list[dict]:
    return [{"id": f"h{s['id']}", "query": s["query"], "label": "", "masked": bool(s.get("masked"))} for s in samples
            if s.get("via") == "http" and hook_like(s.get("params"))]


def merge_labels(new: list[dict], old: list[dict]) -> list[dict]:
    """A re-export keeps every label already written: the old rows first, then the prompts that are new."""
    have = {h["id"] for h in old}
    return old + [h for h in new if h["id"] not in have]


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def main(argv: list[str] | None = None, recall_fn=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("split", help="fix the tune / holdout split once")
    s.add_argument("--gold", type=Path, required=True)
    s.add_argument("--hookset", type=Path, help="also split the hook prompts")
    s.add_argument("--out", type=Path, default=OUT / "split.json")
    s.add_argument("--add", action="store_true", help="place only the questions and prompts that are in no side yet")
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
    r.add_argument("--corpus", choices=("full", "clean"), default="full",
                   help="clean: leave out the episodes of the cells that are not curated (#516)")
    r.add_argument("--curated", type=Path, default=OUT / "clean" / "curated.json", help="from `clean/clean.py curated`")
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
        old = load_jsonl(a.out) if a.out.exists() else []
        rows = merge_labels(hook_samples(a.brain), old)
        a.out.parent.mkdir(parents=True, exist_ok=True)
        _write_jsonl(a.out, rows)
        print(f"{len(rows)} hook prompts ({len(rows) - len(old)} new) in {a.out}. Put in `label` the uuid of the episode that should "
              "have been injected, or `nothing`.")
        return 0

    gold = load_jsonl(a.gold)
    problems = check_gold(gold)
    if problems:
        raise SystemExit("the gold set has problems:\n" + "\n".join(f"- {p}" for p in problems))
    hooks = load_jsonl(a.hookset) if a.hookset else []
    if a.cmd == "split":
        old = json.loads(a.out.read_text(encoding="utf-8")) if a.out.exists() else None
        if old and not a.add:
            raise SystemExit(f"{a.out} already exists: the split is fixed once. Use --add to place new questions only")
        sp = {"seed": SEED, **make_split(gold, old=old)}
        sp["hook"] = make_split([{"id": x["id"], "class": "hook"} for x in hooks], old=(old or {}).get("hook"))
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(sp, indent=1), encoding="utf-8")
        print(f"tune {len(sp['tune'])}, holdout {len(sp['holdout'])}; hook prompts tune {len(sp['hook']['tune'])}, "
              f"holdout {len(sp['hook']['holdout'])} → {a.out}")
        return 0

    split = json.loads(a.split_file.read_text(encoding="utf-8")) if a.split_file.exists() else None
    questions = pick_split(gold, split, a.split)
    drafts = [q for q in questions if not q.get("validated")]
    if drafts and not a.include_drafts:
        print(f"{len(drafts)} questions not validated yet are left out (--include-drafts to run them)", file=sys.stderr)
        questions = [q for q in questions if q.get("validated")]
    hooks = pick_split([x for x in hooks if label_hook(x) is not None], split, a.split, "hook prompts")
    how: dict = {}
    clean, filter_ = None, contextlib.nullcontext()
    if a.corpus == "clean":   # #516: the curated episodes only; with `full` nothing in the recall is replaced
        clean = _clean()
        cur = clean.load(a.curated)
        drop = set(cur["drop"])
    if recall_fn is None:
        recall_fn, how = recall_on(a.brain)
    if clean:
        stats: Counter = Counter()
        filter_, recall_fn = clean.corpus(drop, stats), clean.filtered(recall_fn, drop)
    with counted() if how else contextlib.nullcontext(), filter_:
        records = run(questions, hooks, recall_fn, a.budget)
    meta = {"brain": a.brain, "budget": a.budget, "params": BUDGETS[a.budget], "split": a.split, "label": a.label, **how,
            "questions": sum(1 for x in records if x["class"] != "hook"), "hook": sum(1 for x in records if x["class"] == "hook"),
            "drafts_included": bool(drafts and a.include_drafts), "when": datetime.now(UTC).isoformat(timespec="seconds"),
            "corpus": a.corpus}
    if clean:
        meta["curated"] = {"rule": cur["rule"], "cells": cur["cells"], "left_out_episodes": len(drop),
                           "questions_with_every_answer_left_out": clean.answers_left_out(questions, drop),
                           "items_left_out": dict(stats)}
    s = summarize(records)
    out = a.out or OUT / f"run-{a.label or 'x'}-{a.budget}-{a.split}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"meta": meta, "summary": s, "records": records}, indent=1), encoding="utf-8")
    print(summary_markdown(meta, s))
    if clean:
        c = meta["curated"]
        print(clean.table_markdown({**cur, "drop": drop}))
        print(f"Questions whose every answer episode is left out: {c['questions_with_every_answer_left_out']}. Items left out: "
              + (", ".join(f"{v} {k}" for k, v in sorted(c["items_left_out"].items())) or "none") + ".")
    print(f"→ {out}")
    return 1 if records and s["errors"] == len(records) else 0


if __name__ == "__main__":
    raise SystemExit(main())
