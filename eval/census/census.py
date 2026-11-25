"""Corpus census of one brain (#514): what its episodes and facts actually are, before anything in v1 is decided.

Read-only. It runs against the frozen Phase 0 snapshot, never against production, with the same MIMIRSYNTH_* environment as the
instance that serves the snapshot, from the `api/` folder so that the app's settings and models load:

    cd api && .venv/bin/python ../eval/census/census.py count --brain SLUG
    cd api && .venv/bin/python ../eval/census/census.py sample --brain SLUG
    cd api && .venv/bin/python ../eval/census/census.py summarize

- `count` writes `census.json` and `census.md`: counts and percentages only, ready to paste in #491.
- `sample` writes two blind label sheets, `episodes.csv` and `facts.csv` (text only, strata hidden, both strata mixed and shuffled),
  and `keys.csv`, which maps each sheet row back to its episode or fact and its stratum. The person labelling opens only the sheets.
- `summarize` reads the labelled sheets with the keys and writes `labels.md`: the share of each label per stratum.

Everything is written to `eval/census/out/` (ignored by git): the sheets and the keys hold the brain's own text.

PostgreSQL is read in a READ ONLY transaction and the graph with `ro_query`, so the database refuses any write.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import random
import re
import statistics
import sys
from collections import Counter, defaultdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"

EPISODE_LABELS = ("note", "dump", "event", "meta")   # self-contained note | session dump | event | meta-note about the memory
FACT_LABELS = ("true", "trivial", "stale", "wrong")  # true and useful | trivial or fragment | stale | wrong
LENGTH_BANDS = ((200, "<200"), (500, "200-499"), (1500, "500-1499"), (3000, "1500-2999"))
HOOK_PARAMS = {"facts": 6, "chunks": 3}   # what the agent plugins' per-prompt hook sends (integrations/claude-code/plugin/scripts)


# --- classification (pure) ----------------------------------------------------------------------------------------------------------

def stratum(p: dict | None) -> str:
    """Where an episode came from, from the proposal that produced it. Without a proposal: an adopted or imported graph, or an
    episode written outside MimirSynth."""
    if p is None:
        return "no-proposal"
    cat = p.get("category") or ""
    desc = p.get("source_description") or ""
    origin = p.get("origin") or ""
    if cat == "curator.distil":
        return "distil"
    if cat == "forget.rewrite":
        return "forget-rewrite"
    if p.get("kind") == "correction":
        return "correction"
    if desc.startswith("documento ") and " · trozo " in desc:
        return "document"
    if desc.startswith("webhook «") or p.get("review_kind") == "webhook":
        return "webhook"
    if cat:   # curator passes, verifier, topic-review gaps: written by the system
        return "machine"
    if origin == "auto" and desc.endswith(" session"):
        return "capture"
    return origin if origin in ("person", "agent", "auto") else "unknown"


NO_PROPOSAL_TOP = 4   # an episode with no proposal is split by its most common sources: "source A" to "D", "other", "(none)"


def source_key(desc: str | None, source_map: list | None = None) -> str:
    """The origin an episode's source description stands for. With a source map, the label of the first pattern that matches, so
    the many spellings of one origin fold together; otherwise the text with quoted names and numbers taken out. Either way it is
    only written to the local legend (`sources.csv`), never to the counts that are posted."""
    desc = (desc or "").strip()
    if not desc:
        return "(none)"
    for rx, label in source_map or []:
        if rx.search(desc):
            return label
    d = re.sub(r"«[^»]*»", "«…»", desc)
    return " ".join(re.sub(r"\d+", "N", d).split())[:60]


def _strata_and_sources(episodes: list[dict], proposals: list[dict], source_map: list | None = None):
    by_ep: dict[str, list[dict]] = defaultdict(list)
    for p in proposals:
        if p.get("episode_uuid"):
            by_ep[p["episode_uuid"]].append(p)
    st, loose = {}, {}
    for e in episodes:
        st[e["uuid"]] = stratum(pick(by_ep.get(e["uuid"], [])))
        if st[e["uuid"]] == "no-proposal":
            loose[e["uuid"]] = source_key(e.get("source_description"), source_map)
    counts = Counter(loose.values())
    ranked = [k for k, _ in counts.most_common() if k != "(none)"]
    names = {k: f"source {chr(65 + i)}" for i, k in enumerate(ranked[:NO_PROPOSAL_TOP])}
    for u, k in loose.items():
        st[u] = "no-proposal: " + ("(none)" if k == "(none)" else names.get(k, "other"))
    legend = [{"stratum": "no-proposal: " + names.get(k, "other"), "source": k, "episodes": counts[k]} for k in ranked]
    return st, legend


def episode_strata(episodes: list[dict], proposals: list[dict], source_map: list | None = None) -> dict[str, str]:
    """Each episode's stratum. One with no proposal (an adopted or imported graph) gets a neutral sub-stratum from its own source
    description in the graph (`no-proposal: source A`), so the labels can tell which of them are curated without any name
    reaching the posted counts."""
    return _strata_and_sources(episodes, proposals, source_map)[0]


def source_legend(episodes: list[dict], proposals: list[dict], source_map: list | None = None) -> list[dict]:
    """What each neutral `no-proposal` sub-stratum stands for, with its episodes: for `sources.csv`, which stays on the machine."""
    return _strata_and_sources(episodes, proposals, source_map)[1]


def read_source_map(path: Path) -> list:
    """Lines of `regex<TAB>label`, first match wins; blank lines and lines starting with `#` are skipped."""
    out = []
    for n, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        rx, sep, label = line.partition("\t")
        if not sep or not label.strip():
            raise SystemExit(f"{path.name}:{n}: expected regex<TAB>label")
        try:
            out.append((re.compile(rx), label.strip()))
        except re.error as err:
            raise SystemExit(f"{path.name}:{n}: bad regex: {err}") from None
    return out


def approved_by(p: dict | None) -> str:
    """Who let the episode in. `direct`: a curator token or user wrote it and nobody reviewed it."""
    if p is None:
        return "no-proposal"
    return {"human": "person", "direct": "direct (nobody reviewed)", "decider": "decider", "auto": "category tier",
            "webhook": "webhook auto-approve"}.get(p.get("review_kind") or "", "unknown")


def length_band(n: int) -> str:
    for limit, name in LENGTH_BANDS:
        if n < limit:
            return name
    return ">=3000"


def pct(part: int, whole: int) -> float:
    return round(100 * part / whole, 1) if whole else 0.0


def percentile(xs: list[float], q: float) -> float:
    """Nearest-rank percentile; 0 for an empty list."""
    if not xs:
        return 0.0
    s = sorted(xs)
    return float(s[min(len(s), max(1, math.ceil(q / 100 * len(s)))) - 1])


def table(c: Counter, total: int) -> list[dict]:
    return [{"key": k, "n": n, "pct": pct(n, total)} for k, n in c.most_common()]


def pick(proposals: list[dict]) -> dict | None:
    """The proposal that produced an episode when several point to it: the memory one, then the oldest."""
    if not proposals:
        return None
    return min(proposals, key=lambda p: (p.get("kind") != "memory", str(p.get("created_at") or ""), p.get("id") or 0))


# --- census (pure) ------------------------------------------------------------------------------------------------------------------

def episode_census(episodes: list[dict], proposals: list[dict], source_map: list | None = None) -> dict:
    by_ep: dict[str, list[dict]] = defaultdict(list)
    for p in proposals:
        if p.get("episode_uuid"):
            by_ep[p["episode_uuid"]].append(p)
    n = len(episodes)
    st = episode_strata(episodes, proposals, source_map)
    strata, who, cats, dated, bands = Counter(st.values()), Counter(), Counter(), Counter(), Counter()
    for e in episodes:
        p = pick(by_ep.get(e["uuid"], []))
        who[approved_by(p)] += 1
        if p is not None and p.get("category"):
            cats[p["category"]] += 1
        dated["no proposal" if p is None else ("own date" if p.get("reference_time") else "ingest time")] += 1
        bands[length_band(len(e.get("content") or ""))] += 1
    in_graph = {e["uuid"] for e in episodes}
    ingested = [p for p in proposals if p.get("status") == "ingested"]
    gone = [p for p in ingested if p.get("episode_uuid") and p["episode_uuid"] not in in_graph]
    shared = sum(1 for ps in by_ep.values() if len(ps) > 1)
    return {
        "episodes": n,
        "by_stratum": table(strata, n),
        "approved_by": table(who, n),
        "by_category": table(cats, n)[:15],
        "date": table(dated, n),
        "length": table(bands, n),
        "proposals": {
            "total": len(proposals),
            "by_status": table(Counter(p.get("status") or "" for p in proposals), len(proposals)),
            "ingested": len(ingested),
            "ingested_episode_in_graph": len(ingested) - len(gone) - sum(1 for p in ingested if not p.get("episode_uuid")),
            "ingested_episode_deleted": len(gone),   # distil or forget deleted it: must not come back in a migration
            "ingested_without_episode": sum(1 for p in ingested if not p.get("episode_uuid")),   # claims only, actions only
            "purged": sum(1 for p in proposals if p.get("purged_at")),
            "episodes_with_several_proposals": shared,
        },
    }


def _ts(v) -> datetime | None:
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        d = v
    else:
        try:
            d = datetime.fromisoformat(str(v))
        except ValueError:
            return None
    return d if d.tzinfo else d.replace(tzinfo=UTC)


def _state(f: dict, now: datetime | None = None) -> str:
    """As the app's `db.fact_status`: `future` before its `valid_at`, `invalidated` from its `invalid_at` on; and `expired` for a fact
    Graphiti expired with no `invalid_at`."""
    now = now or datetime.now(UTC)
    v, i = _ts(f.get("valid_at")), _ts(f.get("invalid_at"))
    if v and v > now:
        return "future"
    if i and i <= now:
        return "invalidated"
    if f.get("expired_at"):
        return "expired"
    return "current"


BORN_INVALID_MINUTES = (1, 5, 15)   # the windows the split is reported at: during a bulk ingestion a newer fact can come minutes later


def born_invalid(f: dict, minutes: int = 15) -> bool:
    """Graphiti stores a fact that the text itself dates as past ("X ran on Y until 2023"), or that is older than one it already has,
    as expired at creation (graphiti_core edge_operations). That is history, not knowledge the memory later took back. It is told
    apart only by how soon after creation the fact expired, and a newer fact ingested within the window looks the same, so the split
    is reported at several windows."""
    c, e = _ts(f.get("created_at")), _ts(f.get("expired_at"))
    return bool(c and e and abs(e - c) <= timedelta(minutes=minutes))


def fact_census(edges: list[dict], episode_ids: list[str], manual: set[str], now: datetime | None = None,
                strata: dict[str, str] | None = None) -> dict:
    """`manual`: the uuids of facts whose last change through MimirSynth was an invalidation (vocab_ops `fact.invalidate`: a
    correction, a claim, a contradiction resolved, or by hand). Every other invalidated fact was invalidated by Graphiti: either at
    creation (`born_invalid`) or later, by a newer fact. `strata`: each episode's stratum, to count the facts that episodes of more
    than one stratum back."""
    n = len(edges)
    st = {id(f): _state(f, now) for f in edges}
    states = Counter(st.values())
    per_ep = Counter()
    for f in edges:
        for ep in set(f.get("episodes") or []):
            per_ep[ep] += 1
    counts = [per_ep.get(e, 0) for e in episode_ids]
    texts = Counter(" ".join((f.get("fact") or "").lower().split()) for f in edges if st[id(f)] == "current")
    dup_groups = {t: k for t, k in texts.items() if t and k > 1}
    inval = [f for f in edges if st[id(f)] in ("invalidated", "expired")]
    by_hand = [f for f in inval if f.get("uuid") in manual]
    auto = [f for f in inval if f.get("uuid") not in manual]
    windows = []
    for m in BORN_INVALID_MINUTES:
        born = sum(1 for f in auto if born_invalid(f, m))
        windows.append({"minutes": m, "born_invalid": born, "later": len(auto) - born, "later_pct": pct(len(auto) - born, len(inval))})
    strata = strata or {}
    mixed = [f for f in edges if len({strata[e] for e in f.get("episodes") or [] if e in strata}) > 1]
    return {
        "facts": n,
        "by_state": table(states, n),
        "per_episode": {"median": statistics.median(counts) if counts else 0, "p90": percentile(counts, 90),
                        "episodes_without_facts": sum(1 for c in counts if c == 0)},
        "identical_current": {"groups": len(dup_groups), "facts": sum(dup_groups.values()),
                              "extra": sum(k - 1 for k in dup_groups.values())},
        "invalidations": {"total": len(inval), "through_mimirsynth": len(by_hand), "graphiti": len(auto), "by_window": windows},
        "without_episode": sum(1 for f in edges if not f.get("episodes")),
        "mixed_strata": {"facts": len(mixed), "current": sum(1 for f in mixed if st[id(f)] == "current")},
    }


def _hook_like(params: dict | None) -> bool:
    params = params or {}
    return all(params.get(k) == v for k, v in HOOK_PARAMS.items())


def prompt_census(logs: list[dict], samples: list[dict]) -> dict:
    """Real queries available. `recall_logs` drops every log nobody rated after 48 h and its text after 30 days (ratings.py), so it
    cannot collect prompts; the replay sample (`recall_samples`, replay.py) can. A sample made with the hook's parameters is counted
    as the hook's."""
    days = sorted(str(s.get("created_at"))[:10] for s in samples if s.get("created_at"))
    return {
        "recall_logs": len(logs),
        "recall_logs_with_text": sum(1 for r in logs if r.get("query_text")),
        "recall_samples": len(samples),
        "samples_by_via": table(Counter(s.get("via") or "" for s in samples), len(samples)),
        "samples_hook_like": sum(1 for s in samples if s.get("via") == "http" and _hook_like(s.get("params"))),
        "samples_from": days[0] if days else None,
        "samples_to": days[-1] if days else None,
    }


def cost_estimate(usage: list[dict], ingested_at: list, arms: dict[str, int]) -> dict:
    """LLM calls and tokens per ingested note, from the `extraction` counters (ai_usage) over the days they cover, and what each arm of
    #516 would cost to re-ingest. `ingested_at`: only the proposals that reached extraction (ingested into an episode). Failed calls
    (`errors_*`) are counted apart; embedding calls are left out: they are cheap and local."""
    llm = [u for u in usage if u.get("kind") == "llm" and u.get("purpose") == "extraction"]
    if not llm:
        return {"available": False}
    first = min(_day(u["day"]) for u in llm)
    notes = sum(1 for t in ingested_at if t and _day(t) >= first)
    calls = sum(u.get("calls") or 0 for u in llm)
    failed = sum((u.get("errors_429") or 0) + (u.get("errors_5xx") or 0) + (u.get("errors_other") or 0) for u in llm)
    tokens = sum((u.get("prompt_tokens") or 0) + (u.get("completion_tokens") or 0) for u in llm)
    per_call = calls / notes if notes else None
    per_tok = tokens / notes if notes else None
    return {"available": True, "since": first.isoformat(), "notes": notes, "llm_calls": calls, "failed_calls": failed,
            "tokens": tokens, "calls_per_note": None if per_call is None else round(per_call, 1),
            "tokens_per_note": None if per_tok is None else round(per_tok),
            "arms": {k: {"episodes": v, "llm_calls": None if per_call is None else round(v * per_call),
                         "tokens": None if per_tok is None else round(v * per_tok)} for k, v in arms.items()}}


def _day(v) -> date:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    return date.fromisoformat(str(v)[:10])


CURATED = ("person", "agent")   # the candidates for the clean corpus of #516, until the episode labels define "curated"


def census(episodes, proposals, edges, manual, logs, samples, usage, now: datetime | None = None,
           source_map: list | None = None) -> dict:
    ep = episode_census(episodes, proposals, source_map)
    strata = {r["key"]: r["n"] for r in ep["by_stratum"]}
    curated = sum(strata.get(s, 0) for s in CURATED)
    loose = sum(n for s, n in strata.items() if s.startswith("no-proposal"))
    arms = {"all episodes": len(episodes), "person + agent": curated, "person + agent + no proposal": curated + loose}
    extracted = [p.get("ingested_at") for p in proposals if p.get("status") == "ingested" and p.get("episode_uuid")]
    st = episode_strata(episodes, proposals, source_map)
    return {"episodes": ep, "facts": fact_census(edges, [e["uuid"] for e in episodes], manual, now, st),
            "prompts": prompt_census(logs, samples), "cost": cost_estimate(usage, extracted, arms)}


def manual_invalidations(ops: list[dict]) -> set[str]:
    """The facts whose last change through MimirSynth was an applied invalidation. A reactivation is its own `fact.reactivate` op and
    does not mark the earlier invalidation as reverted, so only the latest op of each fact counts."""
    last: dict[str, dict] = {}
    for o in sorted(ops, key=lambda o: o.get("id") or 0):
        u = (o.get("detail") or {}).get("uuid")
        if u and o.get("status") == "applied":
            last[u] = o
    return {u for u, o in last.items() if o.get("kind") == "fact.invalidate"}


# --- blind samples (pure) -----------------------------------------------------------------------------------------------------------

def allocate(sizes: dict[str, int], n: int) -> dict[str, int]:
    """`n` places split as evenly as the strata allow: a small stratum gives all it has and the rest goes to the others."""
    out = {k: 0 for k in sizes}
    left = n
    open_ = sorted((k for k, v in sizes.items() if v > 0), key=lambda k: sizes[k])
    while left > 0 and open_:
        share = max(1, left // len(open_))
        for k in list(open_):
            take = min(share, sizes[k] - out[k], left)
            out[k] += take
            left -= take
            if out[k] >= sizes[k]:
                open_.remove(k)
            if left == 0:
                break
    return out


def stratified(items: list[dict], key, n: int, rng: random.Random) -> list[dict]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for it in items:
        groups[key(it)].append(it)
    plan = allocate({k: len(v) for k, v in groups.items()}, n)
    chosen = []
    for k in sorted(groups):
        chosen += rng.sample(groups[k], plan[k])
    return chosen


def _cell(v: str) -> str:
    """A text cell a spreadsheet will not read as a formula: webhook payloads are external input, and a markdown bullet starts
    with "-"."""
    return "'" + v if v[:1] in ("=", "+", "-", "@") else v


def blind_sheets(episodes, proposals, edges, n_eps: int, n_facts: int, seed: int, now: datetime | None = None,
                 source_map: list | None = None):
    """The two sheets and the key. The sheets show only text, dates and entity names, shuffled, with neutral ids (E001, F001); not
    the episode's title, which names the system writer in several strata («Curador: …», «Corrección: …»). The key also records each
    stratum's size, so the overall share can be weighted back to the brain."""
    rng = random.Random(seed)
    st = episode_strata(episodes, proposals, source_map)
    eps = stratified(episodes, lambda e: st[e["uuid"]], n_eps, rng)
    current = [f for f in edges if f.get("episodes") and _state(f, now) == "current"]
    fact_st = lambda f: st.get(f["episodes"][0], "no-proposal")   # its first episode's; `mixed` says when others differ
    mixed = lambda f: len({st[e] for e in f["episodes"] if e in st}) > 1
    facts = stratified(current, fact_st, n_facts, rng)
    ep_pop, fact_pop = Counter(st[e["uuid"]] for e in episodes), Counter(fact_st(f) for f in current)
    rng.shuffle(eps)
    rng.shuffle(facts)
    ep_rows, fact_rows, keys = [], [], []
    for i, e in enumerate(eps, 1):
        sid = f"E{i:03d}"
        ep_rows.append({"id": sid, "date": str(e.get("valid_at") or "")[:10], "text": _cell(e.get("content") or ""),
                        "label": "", "comment": ""})
        keys.append({"id": sid, "kind": "episode", "uuid": e["uuid"], "stratum": st[e["uuid"]], "population": ep_pop[st[e["uuid"]]],
                     "mixed": ""})
    for i, f in enumerate(facts, 1):
        sid = f"F{i:03d}"
        fact_rows.append({"id": sid, "fact": _cell(f.get("fact") or ""), "source": _cell(f.get("source") or ""),
                          "target": _cell(f.get("target") or ""), "valid_from": str(f.get("valid_at") or "")[:10],
                          "label": "", "comment": ""})
        keys.append({"id": sid, "kind": "fact", "uuid": f["uuid"], "stratum": fact_st(f), "population": fact_pop[fact_st(f)],
                     "mixed": "true" if mixed(f) else ""})
    return ep_rows, fact_rows, keys


def margin(n: int) -> float:
    """Half-width of the 95 % Wilson interval at p = 0.5, in points: the widest a share measured on `n` rows can be off."""
    if not n:
        return 100.0
    z = 1.96
    return round(100 * z * math.sqrt(0.25 / n + z * z / (4 * n * n)) / (1 + z * z / n), 1)


def summarize_labels(rows: list[dict], keys: list[dict], allowed: tuple[str, ...], skip_mixed: bool = False) -> dict:
    """Share of each label per stratum, with its margin. The overall row weights each stratum by its size in the brain (the sample
    gives every stratum the same number of rows, so an unweighted total would misstate the brain). Rows with no label, or a label
    outside `allowed`, are counted apart and left out; with `skip_mixed`, so are the facts backed by episodes of several strata."""
    key = {k["id"]: k for k in keys}
    per: dict[str, Counter] = defaultdict(Counter)
    pop: dict[str, int] = {}
    unlabelled, unknown, skipped = 0, 0, 0
    for r in rows:
        if skip_mixed and key.get(r["id"], {}).get("mixed") == "true":
            skipped += 1
            continue
        lab = (r.get("label") or "").strip().lower()
        if not lab:
            unlabelled += 1
            continue
        if lab not in allowed:
            unknown += 1
            continue
        k = key.get(r["id"], {})
        s = k.get("stratum", "?")
        per[s][lab] += 1
        pop[s] = int(k.get("population") or 0)
    out = {s: {"n": sum(c.values()), "margin": margin(sum(c.values())),
               **{lab: pct(c[lab], sum(c.values())) for lab in allowed}} for s, c in per.items()}
    total = sum(pop.values())
    if out and total:
        out["(brain, weighted)"] = {"n": sum(r["n"] for r in out.values()), "margin": None,
                                    **{lab: round(sum(out[s][lab] * pop[s] for s in pop) / total, 1) for lab in allowed}}
    return {"by_stratum": out, "unlabelled": unlabelled, "unknown_label": unknown, "mixed_skipped": skipped}


# --- markdown -----------------------------------------------------------------------------------------------------------------------

def _md_table(rows: list[dict], head: str) -> list[str]:
    out = [f"| {head} | n | % |", "|---|--:|--:|"]
    out += [f"| {r['key'] or '(empty)'} | {r['n']} | {r['pct']} |" for r in rows]
    return out + [""]


def to_markdown(c: dict) -> str:
    e, f, p, k = c["episodes"], c["facts"], c["prompts"], c["cost"]
    lines = [f"## Corpus census · {e['episodes']} episodes, {f['facts']} facts", "", "### Episodes by stratum", ""]
    lines += _md_table(e["by_stratum"], "stratum")
    lines += ["### Who let them in", ""] + _md_table(e["approved_by"], "approved by")
    lines += ["### Date the episode carries", ""] + _md_table(e["date"], "date")
    lines += ["### Length (characters)", ""] + _md_table(e["length"], "band")
    if e["by_category"]:
        lines += ["### Category (top 15)", ""] + _md_table(e["by_category"], "category")
    pr = e["proposals"]
    lines += ["### Proposals", "",
              f"- total {pr['total']}, ingested {pr['ingested']}",
              f"- ingested and still backed by an episode: {pr['ingested_episode_in_graph']}",
              f"- ingested but their episode was deleted (distil, forget): **{pr['ingested_episode_deleted']}**",
              f"- ingested with no episode (claims or actions only): {pr['ingested_without_episode']}",
              f"- purged texts: {pr['purged']}; episodes with several proposals: {pr['episodes_with_several_proposals']}", ""]
    lines += ["### Facts", ""] + _md_table(f["by_state"], "state")
    pe, ic, iv = f["per_episode"], f["identical_current"], f["invalidations"]
    lines += [f"- facts per episode: median {pe['median']}, p90 {pe['p90']}; episodes with no fact: {pe['episodes_without_facts']}",
              f"- identical current texts: {ic['groups']} groups, {ic['extra']} extra copies",
              f"- facts with no source episode: {f['without_episode']}",
              (f"- facts backed by episodes of more than one stratum: {f['mixed_strata']['facts']} "
               f"({f['mixed_strata']['current']} current)"), "",
              (f"Invalidated or expired: {iv['total']}; through MimirSynth (correction, claim, by hand): {iv['through_mimirsynth']}; "
               f"by Graphiti: {iv['graphiti']}. Graphiti's are split by how soon after creation the fact expired: within the window "
               "it is taken as dated as past at creation, after it as invalidated later by a newer fact. A newer fact ingested within "
               "the window (a bulk import) is counted as at creation, and one dated as past that took longer to resolve as later: read the "
               "rows together, not one of them."), "",
              "| window | at creation | later, by a newer fact | later % |", "|--:|--:|--:|--:|"]
    lines += [f"| {w['minutes']} min | {w['born_invalid']} | **{w['later']}** | {w['later_pct']} |" for w in iv["by_window"]] + [""]
    lines += ["### Real prompts available", "",
              f"- recall_logs: {p['recall_logs']} ({p['recall_logs_with_text']} with text)",
              f"- recall_samples: {p['recall_samples']}, hook-like: {p['samples_hook_like']}"
              + (f", from {p['samples_from']} to {p['samples_to']}" if p["samples_from"] else ""), ""]
    if k.get("available"):
        lines += ["### Cost of re-ingesting (extraction counters since " + k["since"] + ")", "",
                  (f"- {k['notes']} notes ingested, {k['llm_calls']} LLM calls, {k['tokens']} tokens: "
                   f"**{k['calls_per_note']} calls** and {k['tokens_per_note']} tokens per note"), "",
                  "| arm | episodes | LLM calls | tokens |", "|---|--:|--:|--:|"]
        lines += [f"| {a} | {v['episodes']} | {v['llm_calls']} | {v['tokens']} |" for a, v in k["arms"].items()] + [""]
    else:
        lines += ["### Cost of re-ingesting", "", "- no extraction counters in `ai_usage`", ""]
    return "\n".join(lines)


def labels_markdown(name: str, s: dict, allowed: tuple[str, ...]) -> str:
    lines = [f"### {name}", "", "| stratum | n | ± (95 %) | " + " | ".join(f"{a} %" for a in allowed) + " |",
             "|---|--:|--:|" + "--:|" * len(allowed)]
    for st in sorted(s["by_stratum"], key=lambda x: (x.startswith("("), x)):
        r = s["by_stratum"][st]
        m = "" if r["margin"] is None else str(r["margin"])
        lines.append(f"| {st} | {r['n']} | {m} | " + " | ".join(str(r[a]) for a in allowed) + " |")
    return "\n".join(lines + ["", ("± is the widest a share in that row can be off (95 % Wilson interval at 50 %). The weighted row "
                              "gives each stratum its size in the brain."),
                              (f"Unlabelled: {s['unlabelled']}; unknown label: {s['unknown_label']}"
                               + (f"; left out as backed by several strata: {s['mixed_skipped']}" if s["mixed_skipped"] else "")),
                              ""])


# --- reading the snapshot (read-only) -----------------------------------------------------------------------------------------------

def _app():
    """The app's modules, loaded from api/ with the instance's environment."""
    sys.path.insert(0, str(HERE.parents[1] / "api"))
    from mimirsynth import models
    from mimirsynth.db import graph, rows
    from mimirsynth.store import engine
    return models, graph, rows, engine


def _rows(conn, table, *cols, where=None) -> list[dict]:
    from sqlalchemy import select
    q = select(*[table.c[c] for c in cols])
    if where is not None:
        q = q.where(where)
    return [dict(r._mapping) for r in conn.execute(q)]


def read_snapshot(slug: str, allow_sqlite: bool = False) -> tuple[dict, dict]:
    """`allow_sqlite`: only for the tests. A snapshot is always PostgreSQL; an unset MIMIRSYNTH_DATABASE_URL would otherwise open (and
    create) the development SQLite file and fail later with a misleading "no brain"."""
    models, graph, rows, engine = _app()
    from sqlalchemy import text
    eng = engine()
    if eng.dialect.name != "postgresql" and not allow_sqlite:
        raise SystemExit(f"the snapshot must be PostgreSQL (MIMIRSYNTH_DATABASE_URL); this is {eng.dialect.name}")
    with eng.connect() as conn:
        if eng.dialect.name == "postgresql":
            conn.execute(text("SET TRANSACTION READ ONLY"))
        b = models.Brain.__table__
        brain = _rows(conn, b, "id", "slug", "graph_name", where=b.c.slug == slug)
        if not brain:
            raise SystemExit(f"no brain with slug {slug!r}")
        brain = brain[0]
        bid = brain["id"]
        P = models.Proposal.__table__
        proposals = _rows(conn, P, "id", "status", "kind", "origin", "review_kind", "category", "source_description",
                          "reference_time", "episode_uuid", "purged_at", "created_at", "ingested_at", where=P.c.brain_id == bid)
        V = models.VocabOp.__table__
        ops = _rows(conn, V, "id", "kind", "status", "detail",
                    where=(V.c.brain_id == bid) & V.c.kind.in_(("fact.invalidate", "fact.reactivate")))
        L, S, U = models.RecallLog.__table__, models.RecallSample.__table__, models.AiUsage.__table__
        logs = _rows(conn, L, "id", "query_text", where=L.c.brain_id == bid)
        samples = _rows(conn, S, "via", "params", "created_at", where=S.c.brain_id == bid)
        usage = _rows(conn, U, "day", "kind", "purpose", "calls", "errors_429", "errors_5xx", "errors_other", "prompt_tokens",
                      "completion_tokens", where=U.c.brain_id == bid)
        conn.rollback()
    manual = manual_invalidations(ops)
    g = graph(brain["graph_name"])
    episodes = rows(g.ro_query("MATCH (e:Episodic) RETURN e.uuid AS uuid, e.content AS content, e.valid_at AS valid_at, "
                               "e.source_description AS source_description"))
    edges = rows(g.ro_query("MATCH (a:Entity)-[r:RELATES_TO]->(b:Entity) RETURN r.uuid AS uuid, r.fact AS fact, r.episodes AS episodes, "
                            "r.valid_at AS valid_at, r.invalid_at AS invalid_at, r.expired_at AS expired_at, "
                            "r.created_at AS created_at, a.name AS source, b.name AS target"))
    data = {"episodes": episodes, "proposals": proposals, "edges": edges, "manual": manual, "logs": logs, "samples": samples,
            "usage": usage}
    return brain, data


# --- files --------------------------------------------------------------------------------------------------------------------------

def _write_csv(path: Path, rows: list[dict]) -> None:
    """UTF-8 with a BOM, so a spreadsheet opens the accents and «» right."""
    if not rows:
        path.write_text("", encoding="utf-8-sig")
        return
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def _read_csv(path: Path, need: tuple[str, ...] = ("id",)) -> list[dict]:
    """A sheet as a spreadsheet may have saved it back: with or without a BOM, and with `,` `;` or tab between fields. Fails loudly
    when a column it needs is missing, rather than counting every row as unlabelled."""
    if not path.exists() or not path.stat().st_size:
        return []
    raw = path.read_bytes()
    try:
        data = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        data = raw.decode("cp1252")
    try:
        dialect = csv.Sniffer().sniff(data.split("\n", 1)[0], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    rows = list(csv.DictReader(data.splitlines(keepends=True), dialect=dialect))
    cols = set(rows[0]) if rows else set()
    missing = [c for c in need if rows and c not in cols]
    if missing:
        raise SystemExit(f"{path.name}: no column {', '.join(missing)} (found {', '.join(sorted(cols))})")
    return rows


def _json_default(v):
    return v.isoformat() if isinstance(v, (date, datetime)) else str(v)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("count", "sample"):
        s = sub.add_parser(name)
        s.add_argument("--brain", required=True, help="the brain's slug")
        s.add_argument("--out", type=Path, default=OUT)
        s.add_argument("--source-map", type=Path, help="lines of regex<TAB>label that fold the spellings of one source together")
    s = sub.choices["sample"]
    s.add_argument("--episodes", type=int, default=100)
    s.add_argument("--facts", type=int, default=100)
    s.add_argument("--seed", type=int, default=514)
    s = sub.add_parser("summarize")
    s.add_argument("--out", type=Path, default=OUT)
    s.add_argument("--skip-mixed", action="store_true", help="leave out the facts backed by episodes of several strata")
    a = ap.parse_args(argv)
    a.out.mkdir(parents=True, exist_ok=True)

    if a.cmd == "summarize":
        keys = _read_csv(a.out / "keys.csv", ("id", "stratum", "population"))
        eps = summarize_labels(_read_csv(a.out / "episodes.csv", ("id", "label")), keys, EPISODE_LABELS)
        facts = summarize_labels(_read_csv(a.out / "facts.csv", ("id", "label")), keys, FACT_LABELS, a.skip_mixed)
        md = "## Blind labels by stratum\n\n" + labels_markdown("Episodes", eps, EPISODE_LABELS) + "\n" + \
             labels_markdown("Facts (by the stratum of their source episode)", facts, FACT_LABELS)
        (a.out / "labels.md").write_text(md, encoding="utf-8")
        print(md)
        return 0

    smap = read_source_map(a.source_map) if a.source_map else None
    _, d = read_snapshot(a.brain, allow_sqlite=os.environ.get("MIMIRSYNTH_CENSUS_ALLOW_SQLITE") == "1")
    _write_csv(a.out / "sources.csv", source_legend(d["episodes"], d["proposals"], smap))   # names: stays on this machine
    if a.cmd == "count":
        c = census(d["episodes"], d["proposals"], d["edges"], d["manual"], d["logs"], d["samples"], d["usage"], source_map=smap)
        (a.out / "census.json").write_text(json.dumps(c, indent=2, default=_json_default), encoding="utf-8")
        md = to_markdown(c)
        (a.out / "census.md").write_text(md, encoding="utf-8")
        print(md)
        return 0
    eps, facts, keys = blind_sheets(d["episodes"], d["proposals"], d["edges"], a.episodes, a.facts, a.seed, source_map=smap)
    _write_csv(a.out / "episodes.csv", eps)
    _write_csv(a.out / "facts.csv", facts)
    _write_csv(a.out / "keys.csv", keys)
    print(f"{len(eps)} episodes and {len(facts)} facts written to {a.out}. Label `episodes.csv` with {'/'.join(EPISODE_LABELS)} and "
          f"`facts.csv` with {'/'.join(FACT_LABELS)}; do not open keys.csv until both are labelled.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
