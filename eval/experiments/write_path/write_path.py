"""Offline write-path experiment for Phase 0 (#517): the gate prompt and the `replaces` proposal, on labelled data from the frozen
snapshot. Nothing is ingested and the brain is not changed.

Run from `api/`, on the instance where the snapshot was restored, with its MIMIRSYNTH_* environment and MIMIRSYNTH_EVAL_SNAPSHOT=1:

    cd api && .venv/bin/python ../eval/experiments/write_path/write_path.py gate --sheet ../eval/census/out/episodes.csv
    cd api && .venv/bin/python ../eval/experiments/write_path/write_path.py replaces --brain SLUG --gold ../eval/out/gold.jsonl
    cd api && .venv/bin/python ../eval/experiments/write_path/write_path.py report

Results go to `eval/out/write_path/`, which git ignores: they hold the brain's uuids and the engine's words about its notes. Only the
tables `report` prints (counts and rates) are posted in #491.
"""
from __future__ import annotations

import argparse
import contextlib
import functools
import importlib.util
import json
import re
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
EVAL = HERE.parents[1]
OUT = EVAL / "out" / "write_path"

KINDS = ("note", "dump", "event", "meta")            # the census's episode labels (#514)
ANSWERS = ("note", "event", "alert", "dump", "meta")  # what the gate answers: the census's "event or alert" split in two
ACCEPT = ("note", "event")                           # a self-contained note, and an event that records a change
REJECT = ("alert", "dump", "meta")                   # what the gate rejects or flags
# The labels a rejection is right for. A note labelled `event` may be an alert or an event that records a change, and the census
# labels cannot tell them apart, so those notes stay out of P1: they are reported on their own, for the ADR to decide.
WRONG = ("dump", "meta")
MAX_NOTE = 6000        # characters of the incoming note sent to the engine
MAX_CANDIDATE = 1500   # characters of each similar current note
MAX_FTS = 500          # characters of the note the text part of the similarity search reads
K = 8                  # similar current notes given to the `replaces` call
# Declared in #491 (P1): the gate's precision on "reject or flag", and the proposal's hit rate and false-proposal rate. A threshold
# is met only when the whole 95 % interval is on its side.
# The gate's precision is read weighted back to the brain: the census samples each stratum alike, so rare strata weigh as much as
# common ones in the sheet.
P1 = {"gate": ("precision_reject_w", ">=", 0.8), "hit": ("hit", ">=", 0.7), "false": ("false", "<=", 0.1)}


@functools.cache
def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run():
    return _load("eval_run", EVAL / "run.py")


def _census():
    return _load("census", EVAL / "census" / "census.py")


prompts = _load("write_path_prompts", HERE / "prompts.py")


def parse_json(text: str) -> dict | None:
    """The first JSON object in an engine's answer, which may come wrapped in a code fence, after reasoning with braces of its own,
    or followed by more words or objects."""
    dec = json.JSONDecoder()
    for m in re.finditer(r"\{", text or ""):
        try:
            v, _ = dec.raw_decode(text, m.start())
        except ValueError:
            continue
        if isinstance(v, dict):
            return v
    return None


def _uncell(v: str) -> str:
    """A sheet cell back to its text: the census writes a leading `'` before `=`, `+`, `-` or `@` so no spreadsheet reads a formula."""
    return v[1:] if v[:1] == "'" and v[1:2] in ("=", "+", "-", "@") else v


def _tokens(usage: dict | None) -> dict:
    """The call's tokens, as an OpenAI-compatible engine reports them under either pair of names."""
    u = usage or {}
    tin = u.get("prompt_tokens", u.get("input_tokens"))
    tout = u.get("completion_tokens", u.get("output_tokens"))
    return {"in": tin, "out": tout}


def wilson(k: float, n: float, z: float = 1.96) -> tuple[float | None, float | None]:
    """The 95 % Wilson interval of k successes in n. Unlike a percentile bootstrap, it does not shrink to a point when every item
    agrees: 5 of 5 gives about 0.57 – 1."""
    if not n:
        return None, None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
    return max(0.0, c - h), min(1.0, c + h)


# --- gate (pure) ---------------------------------------------------------------------------------------------------------------------

def gate_items(rows: list[dict]) -> tuple[list[dict], dict]:
    """The labelled episodes of the census sheet. Returns them and how many were left out, by reason."""
    items, skipped = [], {"unlabelled": 0, "unknown label": 0, "no text": 0}
    for r in rows:
        label = (r.get("label") or "").strip().lower()
        text = _uncell(r.get("text") or "").strip()
        if not label:
            skipped["unlabelled"] += 1
        elif label not in KINDS:
            skipped["unknown label"] += 1
        elif not text:
            skipped["no text"] += 1
        else:
            items.append({"id": r["id"], "label": label, "text": text})
    return items, skipped


def gate_metrics(label: str, kind: str) -> dict:
    """Each metric a (numerator, denominator) pair, so a set or a resample is the ratio of their sums.
    - `precision_reject`: of the notes the gate rejected or flagged, the share labelled `dump` or `meta` (the P1 metric, also
      weighted back to the brain). Notes labelled `event` are left out of it;
    - `recall_reject`: of the notes labelled `dump` or `meta`, the share the gate rejected or flagged;
    - `precision_<kind>` and `recall_<kind>` for `dump` and `meta`;
    - `accept_note`: of the self-contained notes, the share the gate let through;
    - `event_accept` and `event_reject`: of the notes labelled `event`, the share the gate let through and the share it rejected
      or flagged."""
    m: dict[str, list[int]] = {}
    for c in WRONG:
        if kind == c and label != "event":
            m[f"precision_{c}"] = [int(label == c), 1]
        if label == c:
            m[f"recall_{c}"] = [int(kind == c), 1]
    if kind in REJECT and label != "event":
        m["precision_reject"] = [int(label in WRONG), 1]
    if label in WRONG:
        m["recall_reject"] = [int(kind in REJECT), 1]
    if label == "note":
        m["accept_note"] = [int(kind in ACCEPT), 1]
    if label == "event":
        m["event_accept"] = [int(kind in ACCEPT), 1]
        m["event_reject"] = [int(kind in REJECT), 1]
    return m


def gate_weights(items: list[dict], keys: list[dict]) -> dict[str, dict]:
    """Each labelled note's stratum and weight: its stratum's size in the brain over the notes of that stratum in the set. The
    census samples each stratum alike, so without it a rare stratum weighs as much as a common one."""
    key = {k["id"]: k for k in keys if (k.get("kind") or "episode") == "episode"}
    missing = [it["id"] for it in items if it["id"] not in key]
    if missing:
        raise SystemExit(f"the census key has no row for {len(missing)} labelled notes ({', '.join(missing[:5])}): "
                         "is it the sheet's own key?")
    strata = {it["id"]: key[it["id"]].get("stratum") or "?" for it in items}
    per: dict[str, int] = defaultdict(int)
    for st in strata.values():
        per[st] += 1
    pop: dict[str, int] = {}
    for i, st in strata.items():
        try:
            pop[st] = int(str(key[i].get("population") or "").strip())
        except ValueError:
            pop[st] = 0
        if pop[st] <= 0:   # it would drop out of the weighted precision, and the report would not say so
            raise SystemExit(f"the census key gives stratum {st!r} no size (row {i}): it cannot be weighted back to the brain")
    return {i: {"stratum": st, "w": pop[st] / per[st]} for i, st in strata.items()}


def run_gate(items: list[dict], ask) -> list[dict]:
    """`ask(system, user, max_tokens) -> (text, usage)` is the instance's LLM engine (or a fake in the tests). A failed call or an
    answer with no kind is recorded with its error and left out of the metrics."""
    out = []
    for it in items:
        rec = {"id": it["id"], "label": it["label"], "truncated": len(it["text"]) > MAX_NOTE,
               **{k: it[k] for k in ("stratum", "w") if k in it}}
        try:
            text, usage = ask(prompts.GATE, it["text"][:MAX_NOTE], 200)
        except Exception as e:  # noqa: BLE001  (one failed call is recorded, the run goes on)
            out.append({**rec, "m": {}, "error": f"{type(e).__name__}: {e}"})
            continue
        ans = parse_json(text) or {}
        kind = str(ans.get("kind") or "").strip().lower()
        rec["tokens"] = _tokens(usage)
        if kind not in ANSWERS:
            out.append({**rec, "m": {}, "error": "the answer has no kind"})
            continue
        out.append({**rec, "kind": kind, "reason": str(ans.get("reason") or "")[:300], "m": gate_metrics(it["label"], kind)})
    return out


# --- replaces (pure) -----------------------------------------------------------------------------------------------------------------

def _current(f: dict) -> bool:
    return not f.get("invalid_at") and not f.get("expired_at")


def replace_pairs(gold: list[dict], episodes: dict[str, dict], edges: dict[str, dict]) -> tuple[list[dict], dict]:
    """(new note, the old notes it replaces) for each temporal question of the gold set (#492).
    - The old notes: the episodes in its `stale`, and the episodes of the facts in its `stale`, less the answer episodes.
    - The new note: the answer episode that brought the change, the earliest one written after every old note; when none is, the
      most recent answer episode. It needs a date: without one, the notes written after it cannot be told apart.
    - Only the old notes dated no later than the new note stay: an undated or later one could never be among its candidates, and
      would count as a miss the prompt is not to blame for. A pair with none left is left out.
    - `partial`, for each old note: some of its facts other than the replaced ones (the `stale` facts) are still current, so the new
      note replaces only part of it.
    - Two questions about the same change give one pair.
    Returns the pairs and how many temporal questions were left out, by reason."""
    pairs, seen = [], set()
    skipped = {"new note not in the snapshot": 0, "no old note": 0, "new note has no date": 0,
               "no old note before the new one": 0, "repeated pair": 0}
    ts = _census()._ts
    for q in gold:
        if q.get("class") != "temporal":
            continue
        new_eps = [e for e in q.get("answer_episodes") or [] if e in episodes]
        if not new_eps:
            skipped["new note not in the snapshot"] += 1
            continue
        stale = set(q.get("stale") or [])
        old = {s for s in stale if s in episodes} | {e for s in stale if s in edges for e in edges[s].get("episodes") or []
                                                    if e in episodes}
        old -= set(new_eps)
        if not old:
            skipped["no old note"] += 1
            continue
        dated = sorted((t, e) for e in new_eps if (t := ts(episodes[e].get("valid_at"))))
        if not dated:
            skipped["new note has no date"] += 1
            continue
        last_old = max((t for o in old if (t := ts(episodes[o].get("valid_at")))), default=None)
        after = [e for t, e in dated if last_old is None or t > last_old]
        new = after[0] if after else dated[-1][1]
        when = ts(episodes[new].get("valid_at"))
        old = {o for o in old if (t := ts(episodes[o].get("valid_at"))) and t <= when}   # what the search could have shown
        if not old:
            skipped["no old note before the new one"] += 1
            continue
        key = (new, tuple(sorted(old)))
        if key in seen:
            skipped["repeated pair"] += 1
            continue
        seen.add(key)
        facts_of = {o: [f for u, f in edges.items() if u not in stale and o in (f.get("episodes") or [])] for o in old}
        pairs.append({"id": q["id"], "new": new, "old": sorted(old),
                      "partial": {o: any(_current(f) for f in facts_of[o]) for o in sorted(old)}})
    return pairs, skipped


def candidates(pair: dict, episodes: dict[str, dict], hits: list[str], k: int = K) -> list[str]:
    """The current notes a `replaces` call is given: the similarity search's episodes in rank order, once each, without the new note
    and without any note written after it (it did not exist yet when the new note came in)."""
    ts = _census()._ts
    when = ts(episodes[pair["new"]].get("valid_at"))
    out: list[str] = []
    for e in hits:
        if e in out or e == pair["new"] or e not in episodes:
            continue
        t = ts(episodes[e].get("valid_at"))
        if t is None or t > when:   # written after the new note, or undated: it cannot be placed before it
            continue
        out.append(e)
        if len(out) == k:
            break
    return out


def replaces_message(new: dict, cands: list[dict]) -> str:
    lines = [f"New note ({str(new.get('valid_at') or '')[:10]}):", (new.get("content") or "")[:MAX_NOTE], "", "Current notes:"]
    for i, c in enumerate(cands, 1):
        lines += [f"[{i}] ({str(c.get('valid_at') or '')[:10]})", (c.get("content") or "")[:MAX_CANDIDATE], ""]
    return "\n".join(lines)


def proposals(ans: dict | None, n: int) -> list[dict]:
    """The proposals in an answer: numbers in range, each once."""
    out, seen = [], set()
    for p in (ans or {}).get("replaces") or []:
        if not isinstance(p, dict):
            continue
        try:
            i = int(p.get("n"))
        except (TypeError, ValueError):
            continue
        if 1 <= i <= n and i not in seen:
            seen.add(i)
            out.append({"n": i, "partial": p.get("partial") is True, "what": str(p.get("what") or "")[:300]})
    return out


def replaces_metrics(pair: dict, cands: list[str], props: list[dict]) -> dict:
    """- `hit`: the true old note was proposed (any of them, when there are several);
    - `false`: of the notes proposed, the share that are not a true old note (an upper bound: one may be another note the new one
      really replaces, which the gold set does not record);
    - `partial_ok`: of the true old notes proposed, the share whose "replaces only part of it" matches the snapshot;
    - `retrieved`: a true old note was among the candidates at all, to tell a search miss from an engine miss."""
    old = set(pair["old"])
    chosen = {cands[p["n"] - 1]: p for p in props}
    hits = [e for e in chosen if e in old]
    m = {"hit": [int(bool(hits)), 1], "false": [sum(1 for e in chosen if e not in old), len(chosen)],
         "retrieved": [int(bool(old & set(cands))), 1]}
    if hits:
        m["partial_ok"] = [sum(1 for e in hits if chosen[e]["partial"] == pair["partial"][e]), len(hits)]
    return m


def run_replaces(pairs: list[dict], episodes: dict[str, dict], search, ask, k: int = K) -> list[dict]:
    """`search(text) -> [episode uuid, …]` is the similarity search over the brain's notes, best first; `ask` as in `run_gate`. With
    no candidate the engine is not called: nothing can be proposed."""
    out = []
    for pair in pairs:
        rec = {"id": pair["id"], "new": pair["new"], "old": pair["old"]}
        try:
            cands = candidates(pair, episodes, search(episodes[pair["new"]].get("content") or ""), k)
            if not cands:   # no call: it is left out of the cost per note
                out.append({**rec, "candidates": [], "proposed": [], "m": replaces_metrics(pair, [], [])})
                continue
            text, usage = ask(prompts.REPLACES, replaces_message(episodes[pair["new"]], [episodes[c] for c in cands]), 400)
        except Exception as e:  # noqa: BLE001  (one failed call is recorded, the run goes on)
            out.append({**rec, "m": {}, "error": f"{type(e).__name__}: {e}"})
            continue
        ans = parse_json(text)
        if ans is None:
            out.append({**rec, "candidates": cands, "m": {}, "tokens": _tokens(usage), "error": "the answer is not JSON"})
            continue
        props = proposals(ans, len(cands))
        out.append({**rec, "candidates": cands, "tokens": _tokens(usage),
                    "proposed": [{"episode": cands[p["n"] - 1], "partial": p["partial"], "what": p["what"]} for p in props],
                    "m": replaces_metrics(pair, cands, props)})
    return out


# --- summary (pure) ------------------------------------------------------------------------------------------------------------------

GATE_ROWS = ("precision_reject", "recall_reject", *(f"{w}_{c}" for c in WRONG for w in ("precision", "recall")), "accept_note",
             "event_accept", "event_reject")
GATE_WEIGHTED = ("precision_reject",)
REPLACES_ROWS = ("hit", "false", "partial_ok", "retrieved")


def _weighted(records: list[dict], metric: str) -> float | None:
    num = sum(r["w"] * r["m"][metric][0] for r in records if metric in r["m"])
    den = sum(r["w"] * r["m"][metric][1] for r in records if metric in r["m"])
    return num / den if den else None


def summarize(records: list[dict], metrics: tuple[str, ...], n: int | None = None, weighted: tuple[str, ...] = ()) -> dict:
    """Each metric over the records that ran, with a 95 % interval: the wider of the bootstrap over the records (as in #492) and the
    Wilson interval of the pooled count. The bootstrap alone shrinks to a point when every item agrees, and would read 5 of 5 as
    certain.

    Each metric in `weighted` also gets a row `<metric>_w`, weighted back to the brain by the records' `w`, when every record has
    one: the bootstrap of the weighted ratio and the Wilson interval at the effective sample size (Kish), the wider of the two. It
    is an approximation: it treats the strata's sizes as fixed.

    With the gate's records, `confusion` counts each label against each answer."""
    run = _run()
    ok = [r for r in records if not r.get("error")]
    rows = []

    def add(name, metric, rs, value, fn, k, nn):
        blo, bhi = run.bootstrap(rs, fn, n or run.BOOT)
        wlo, whi = wilson(k, nn)
        rows.append({"metric": name, "n": sum(r["m"][metric][1] for r in rs), "value": value,
                     "lo": min(x for x in (blo, wlo) if x is not None), "hi": max(x for x in (bhi, whi) if x is not None)})

    for metric in metrics:
        rs = [r for r in ok if metric in r["m"]]
        den = sum(r["m"][metric][1] for r in rs)
        if not den:
            continue
        num = sum(r["m"][metric][0] for r in rs)
        add(metric, metric, rs, num / den, lambda x, m=metric: run.aggregate(x, m), num, den)
        if metric in weighted and all("w" in r for r in rs):
            v = _weighted(rs, metric)
            ws = [r["w"] * r["m"][metric][1] for r in rs]
            if v is None or not any(ws):
                continue
            neff = sum(ws) ** 2 / sum(w * w for w in ws)
            add(f"{metric}_w", metric, rs, v, lambda x, m=metric: _weighted(x, m), v * neff, neff)
    out = {"rows": rows, "records": len(records), "errors": len(records) - len(ok)}
    confusion: dict[str, dict[str, int]] = {}
    for r in ok:
        if r.get("kind") and r.get("label"):
            row = confusion.setdefault(r["label"], {})
            row[r["kind"]] = row.get(r["kind"], 0) + 1
    if confusion:
        out["confusion"] = confusion
    return out


def cost(records: list[dict], price_in: float | None = None, price_out: float | None = None) -> dict:
    """Tokens per call, over the notes whose call the engine answered with its usage; and their price, given per million tokens.
    A note for which no call was made (no candidate for `replaces`) is not in it."""
    used = [r["tokens"] for r in records if (r.get("tokens") or {}).get("in") is not None]
    if not used:
        return {"notes": 0}
    tin = sum(t["in"] or 0 for t in used) / len(used)
    tout = sum(t["out"] or 0 for t in used) / len(used)
    out = {"notes": len(used), "tokens_in": round(tin), "tokens_out": round(tout)}
    if price_in is not None and price_out is not None:
        out["per_note"] = (tin * price_in + tout * price_out) / 1e6
    return out


def p1(gate: dict | None, replaces: dict | None) -> dict:
    """#491's P1 / P0, as written: P1 when the gate's precision on "reject or flag" is ≥ 0.8 and the proposal's hit rate is ≥ 0.7
    with ≤ 0.1 false proposals, each with its whole interval on its side. Anything else is P0, and the parts that failed are the
    weaker ones: they stay a suggestion in the inbox, or are dropped."""
    def row(s, metric):
        return next((r for r in (s or {}).get("rows", []) if r["metric"] == metric), None)

    failed, checks = [], {}
    for name, (metric, op, at) in P1.items():
        r = row(gate if name == "gate" else replaces, metric)
        if r is None or r["lo"] is None:
            checks[name] = "not measured"
            failed.append(name)
            continue
        ok = r["lo"] >= at if op == ">=" else r["hi"] <= at
        checks[name] = "met" if ok else "not met"
        if not ok:
            failed.append(name)
    weaker = sorted({"gate" if f == "gate" else "replaces" for f in failed})
    return {"result": "P1" if not failed else "P0", "checks": checks, "weaker": weaker}


def _pct(v) -> str:
    return "–" if v is None else f"{100 * v:.1f}"


def report_markdown(gate: dict | None, replaces: dict | None) -> str:
    lines = []
    for title, res in (("Gate prompt", gate), ("`replaces` proposal", replaces)):
        if not res:
            continue
        m, s = res["meta"], res["summary"]
        lines += [f"## {title} · {m['prompt']} · {m['model']} · {s['records']} notes" + (f", {s['errors']} failed" if s["errors"] else ""),
                  "", "| metric | n | value % | 95 % interval |", "|---|--:|--:|--:|"]
        lines += [f"| {r['metric']} | {r['n']} | {_pct(r['value'])} | {_pct(r['lo'])} – {_pct(r['hi'])} |" for r in s["rows"]]
        if s.get("confusion"):
            lines += ["", "| label · answer | " + " | ".join(ANSWERS) + " |", "|---|" + "--:|" * len(ANSWERS)]
            lines += [f"| {lab} | " + " | ".join(str(s["confusion"].get(lab, {}).get(k, 0)) for k in ANSWERS) + " |"
                      for lab in KINDS if lab in s["confusion"]]
        c = res["cost"]
        if c.get("notes"):
            price = f", about {c['per_note']:.5f} per note" if "per_note" in c else ""
            lines += ["", f"Cost: {c['tokens_in']} tokens in and {c['tokens_out']} out per note{price} (over {c['notes']} notes)."]
        else:
            lines += ["", "Cost: the engine reported no token usage."]
        if res.get("skipped") and any(res["skipped"].values()):
            lines.append("Left out: " + ", ".join(f"{v} {k}" for k, v in res["skipped"].items() if v) + ".")
        lines.append("")
    v = p1(gate and gate["summary"], replaces and replaces["summary"])
    lines += [f"**#491: {v['result']}** (" + ", ".join(f"{k} {x}" for k, x in v["checks"].items()) + ")"]
    if v["weaker"]:
        lines.append(f"Below the P1 values: {', '.join(v['weaker'])}.")
    return "\n".join(lines + [""])


# --- the snapshot --------------------------------------------------------------------------------------------------------------------

def engine_ask(eng: dict):
    """The instance's LLM engine, answering with its usage. The call is counted in `ai_usage`, as any call is."""
    import httpx

    from mimirsynth import usage

    def ask(system: str, user: str, max_tokens: int):
        body = {"model": eng["model"], "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                "temperature": 0, "max_tokens": max_tokens}
        r = httpx.post(f"{eng['base_url'].rstrip('/')}/chat/completions", json=body, timeout=120,
                       headers={"Authorization": f"Bearer {eng['api_key']}"} if eng.get("api_key") else {})
        usage.observe("llm", eng["model"], r)
        r.raise_for_status()
        j = r.json()
        return j["choices"][0]["message"].get("content") or "", j.get("usage")
    return ask


def _engine():
    _run().snapshot_guard()
    from mimirsynth.llm import resolve
    from mimirsynth.store import _factory
    with _factory()() as db:
        eng = resolve(db)
    if not eng:
        raise SystemExit("this instance has no LLM engine")
    return eng


def read_brain(slug: str, k: int = K):
    """The brain's id, notes and facts, and a similarity search over its notes: the app's own embedding and episode index. It asks
    for four fragments per candidate, since a note has several and the new note's own rank first."""
    eng = _engine()
    models, _, _, factory = _run()._app()
    from mimirsynth import index
    from mimirsynth.db import graph, rows
    from mimirsynth.embed import get_embedder
    if not index.enabled():   # every pair would have no candidate, and read as a miss of the prompt
        raise SystemExit("the episode index is off on this instance: the `replaces` candidates come from it")
    with factory()() as db:
        b = db.query(models.Brain).filter(models.Brain.slug == slug).one_or_none()
        if b is None:
            raise SystemExit(f"no brain with slug {slug!r}")
        bid, gname = b.id, b.graph_name
    g = graph(gname)
    episodes = {e["uuid"]: e for e in rows(g.ro_query("MATCH (e:Episodic) RETURN e.uuid AS uuid, e.content AS content, "
                                                       "e.valid_at AS valid_at"))}
    edges = {f["uuid"]: f for f in rows(g.ro_query("MATCH (:Entity)-[r:RELATES_TO]->(:Entity) RETURN r.uuid AS uuid, "
                                                    "r.episodes AS episodes, r.invalid_at AS invalid_at, r.expired_at AS expired_at"))}
    embedder = get_embedder()

    def search(text: str) -> list[str]:
        qvec = embedder.embed([text[:MAX_NOTE]])[0]
        return [h["episode_uuid"] for h in index.search(bid, qvec, text[:MAX_FTS], k=4 * k, pool=max(40, 8 * k), recency=0.0)
                if h.get("episode_uuid")]
    return eng, bid, episodes, edges, search


def counted():
    """The engine's and the embedder's calls, counted for the instance (brain 0) under `eval` and written before the command exits:
    the eval's own `counted()` (#492)."""
    return _run().counted()


def _result(meta: dict, records: list[dict], summary: dict, skipped: dict, price) -> dict:
    return {"meta": {**meta, "when": datetime.now(UTC).isoformat(timespec="seconds")}, "summary": summary,
            "cost": cost(records, *price), "skipped": skipped, "records": records}


def main(argv: list[str] | None = None, ask=None, brain=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("gate", help="the gate prompt over the census's labelled episodes")
    g.add_argument("--sheet", type=Path, default=EVAL / "census" / "out" / "episodes.csv")
    g.add_argument("--keys", type=Path, default=EVAL / "census" / "out" / "keys.csv",
                   help="that sheet's census key: each note's stratum and its stratum's size, to weight back to the brain")
    r = sub.add_parser("replaces", help="the `replaces` proposal over the gold set's temporal questions")
    r.add_argument("--brain", required=True)
    r.add_argument("--gold", type=Path, required=True)
    r.add_argument("--split", choices=("tune", "holdout", "all"), default="all")
    r.add_argument("--split-file", type=Path, default=EVAL / "out" / "split.json")
    r.add_argument("--include-drafts", action="store_true")
    r.add_argument("--k", type=int, default=K, help="similar current notes given to each call")
    for p in (g, r):
        p.add_argument("--price-in", type=float, help="the engine's price per million input tokens")
        p.add_argument("--price-out", type=float, help="the engine's price per million output tokens")
        p.add_argument("--out", type=Path)
    rep = sub.add_parser("report", help="both tables and #491's P1 / P0")
    rep.add_argument("--gate", type=Path, default=OUT / "gate.json")
    rep.add_argument("--replaces", type=Path, default=OUT / "replaces.json")
    a = ap.parse_args(argv)

    if a.cmd == "report":
        res = {k: json.loads(p.read_text(encoding="utf-8")) if p.exists() else None for k, p in (("gate", a.gate), ("replaces", a.replaces))}
        if not any(res.values()):
            raise SystemExit("no results yet: run `gate` and `replaces` first")
        print(report_markdown(res["gate"], res["replaces"]))
        return 0

    price = (a.price_in, a.price_out)
    if a.cmd == "gate":
        items, skipped = gate_items(_census()._read_csv(a.sheet, ("id", "text", "label")))
        if not items:
            raise SystemExit(f"{a.sheet}: no labelled episodes (label them with {'/'.join(KINDS)} first)")
        if ask is None:
            _run().snapshot_guard()   # before anything else: the engine is the instance's
        if not a.keys.exists():
            raise SystemExit(f"{a.keys}: the census key is needed to weight the precision back to the brain")
        w = gate_weights(items, _census()._read_csv(a.keys, ("id", "stratum", "population")))
        items = [{**it, **w[it["id"]]} for it in items]
        ctx = contextlib.nullcontext()
        if ask is None:
            eng = _engine()
            ask, model, ctx = engine_ask(eng), eng["model"], counted()
        else:
            model = "fake"
        with ctx:
            records = run_gate(items, ask)
        res = _result({"prompt": prompts.GATE_VERSION, "model": model, "sheet": a.sheet.name, "keys": a.keys.name}, records,
                      summarize(records, GATE_ROWS, weighted=GATE_WEIGHTED), skipped, price)
        out = a.out or OUT / "gate.json"
    else:
        run = _run()
        gold = run.load_jsonl(a.gold)
        problems = run.check_gold(gold)
        if problems:
            raise SystemExit("the gold set has problems:\n" + "\n".join(f"- {p}" for p in problems))
        split = json.loads(a.split_file.read_text(encoding="utf-8")) if a.split_file.exists() else None
        gold = [q for q in run.pick_split(gold, split, a.split) if q.get("validated") or a.include_drafts]
        ctx = contextlib.nullcontext()
        if brain is None:
            eng, _, episodes, edges, search = read_brain(a.brain, a.k)
            ask, model, ctx = engine_ask(eng), eng["model"], counted()
        else:
            episodes, edges, search = brain
            model = "fake"
        pairs, skipped = replace_pairs(gold, episodes, edges)
        if not pairs:
            raise SystemExit("no temporal question gives a pair of notes in this snapshot")
        with ctx:
            records = run_replaces(pairs, episodes, search, ask, a.k)
        res = _result({"prompt": prompts.REPLACES_VERSION, "model": model, "k": a.k, "split": a.split,
                       "drafts_included": a.include_drafts}, records, summarize(records, REPLACES_ROWS), skipped, price)
        out = a.out or OUT / "replaces.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    print(report_markdown(res if a.cmd == "gate" else None, res if a.cmd == "replaces" else None))
    print(f"→ {out}")
    return 1 if records and res["summary"]["errors"] == len(records) else 0


if __name__ == "__main__":
    raise SystemExit(main())
