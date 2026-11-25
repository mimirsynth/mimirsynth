"""Draft eval questions from a snapshot (#492), for the maintainer to validate or edit.

It runs from `api/` with the instance's environment and MIMIRSYNTH_EVAL_SNAPSHOT=1, on the frozen snapshot only:

    cd api && .venv/bin/python ../eval/drafts.py --brain SLUG

- From the episodes of the chosen census strata (`person`, `agent` and `capture` by default) it asks the instance's default LLM engine
  for point, entity and temporal questions, and for out-of-domain ones from the names of those episodes' entities. Only text from
  episodes of those strata is sent to the engine.
- From the replay sample it takes real prompts as they were asked (secrets already masked), without sending them anywhere: the
  maintainer gives each its class and answer.

Every draft carries `drafted_from` (the stratum of its source episodes, `entities`, or `replay sample`), so the bias of where the
questions came from can be measured later. It writes `eval/out/drafts.jsonl` (ignored by git) and refuses to overwrite it, since the
maintainer edits it. It does not change the brain, but the engine's calls are counted in the snapshot's `ai_usage`.
"""
from __future__ import annotations

import argparse
import functools
import importlib.util
import json
import random
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
EPISODE_CHARS = 3000   # what of each episode the engine reads
SAME_TIME = 60         # seconds, as recall._SAME_TIME: Graphiti gives the fact it invalidates the `valid_at` of the one replacing it
OOD_BATCH = 10         # out-of-domain questions per call, so the answer is never cut

PROMPTS = {   # all but `point` go through str.format, so their JSON braces are doubled
    "point": ("Here is a note from a team's memory. Write one question a member of the team might ask whose answer is in this note, "
              "in the note's language, without quoting it word for word. Answer with JSON only: "
              '{"query": "...", "answer": "the answer, in one line"}.'),
    "entity": ("Here are several notes from a team's memory that all mention «{entity}». Write one question about «{entity}» whose "
               "full answer needs at least two of these notes, in their language. Answer with JSON only: "
               '{{"query": "...", "answer": "the answer, in one line", "notes": [the numbers of the notes the answer needs]}}.'),
    "temporal": ("In a team's memory, «{old}» was true until {when}, and then «{new}» replaced it. Write one question, in the facts' "
                 "language, that asks what is true now or what was true before the change, the way a team member would ask it. "
                 'Answer with JSON only: {{"query": "...", "answer": "the answer, in one line"}}.'),
    "ood": ("A team's memory is about these subjects: {subjects}. Write {n} questions a team member might ask that sound like they "
            "belong to this memory but are about other systems, people or topics, so the right answer is that the memory has nothing. "
            'One per line, in the subjects\' language. Answer with JSON only: {{"queries": ["...", "..."]}}.'),
}


@functools.cache
def _run():
    spec = importlib.util.spec_from_file_location("eval_run", HERE / "run.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _census():
    return _run()._census()


def parse_json(text: str) -> dict | None:
    """The first JSON object in an engine's answer, which may come wrapped in a code fence or with words around it."""
    m = re.search(r"\{.*\}", text or "", re.DOTALL)
    if not m:
        return None
    try:
        v = json.loads(m.group(0))
    except ValueError:
        return None
    return v if isinstance(v, dict) else None


def _ts(v) -> datetime | None:
    return _census()._ts(v)   # a naive date is UTC, so it compares with an aware one


def temporal_pairs(edges: list[dict]) -> list[dict]:
    """(old, new): `new` is the current fact on the same source entity that took effect when `old` stopped being true, which is what
    Graphiti records when a newer fact invalidates an older one. Among several, the same relation first, then the closest in time."""
    by_source: dict[str, list[dict]] = defaultdict(list)
    for f in edges:
        if not f.get("invalid_at") and not f.get("expired_at") and f.get("episodes"):
            by_source[f.get("source_uuid") or ""].append(f)
    pairs = []
    for old in edges:
        end = _ts(old.get("invalid_at"))
        if not end or not old.get("episodes"):
            continue
        cands = []
        for new in by_source.get(old.get("source_uuid") or "", []):
            start = _ts(new.get("valid_at"))
            if new is not old and start and abs((start - end).total_seconds()) <= SAME_TIME:
                cands.append((new.get("name") != old.get("name"), abs((start - end).total_seconds()), new))
        if cands:
            pairs.append({"old": old, "new": min(cands, key=lambda c: (c[0], c[1]))[2]})
    return pairs


def entity_groups(mentions: list[dict], allowed: set[str], low: int = 2, high: int = 5) -> list[dict]:
    """Entities mentioned by several allowed episodes: the material of an entity question. `mentions`: {entity, name, episodes}."""
    out = []
    for m in mentions:
        eps = sorted({e for e in m.get("episodes") or [] if e in allowed})
        if len(eps) >= low:
            out.append({"entity": m["entity"], "name": m["name"], "episodes": eps[:high]})
    return out


def draft(cls: str, material: dict, ask, n_ood: int = 0) -> list[dict]:
    """The drafts for one piece of material; empty when the engine's answer is unusable. `ask(prompt, text, max_tokens) -> str`."""
    if cls == "point":
        e = material["episode"]
        v = parse_json(ask(PROMPTS["point"], e["content"][:EPISODE_CHARS], 400))
        return [{"class": "point", "query": v["query"], "answer_episodes": [e["uuid"]], "draft_answer": v.get("answer", "")}] \
            if v and v.get("query") else []
    if cls == "entity":
        eps = material["episodes"]
        text = "\n\n".join(f"Note {i}:\n{e['content'][:EPISODE_CHARS]}" for i, e in enumerate(eps, 1))
        v = parse_json(ask(PROMPTS["entity"].format(entity=material["name"]), text, 500))
        if not v or not v.get("query"):
            return []
        picked = sorted({eps[i - 1]["uuid"] for i in v.get("notes") or [] if isinstance(i, int) and 1 <= i <= len(eps)})
        return [{"class": "entity", "query": v["query"], "answer_episodes": picked if len(picked) >= 2 else [e["uuid"] for e in eps],
                 "draft_answer": v.get("answer", "")}]
    if cls == "temporal":
        old, new = material["old"], material["new"]
        v = parse_json(ask(PROMPTS["temporal"].format(old=old["fact"], new=new["fact"], when=str(old["invalid_at"])[:10]), "", 400))
        # Graphiti invalidated the old fact, so it can only show as current through a fragment of its episodes: those go in `stale`
        stale = [old["uuid"], *sorted(set(old["episodes"]) - set(new["episodes"]))]
        return [{"class": "temporal", "query": v["query"], "answer_episodes": sorted(set(new["episodes"])), "stale": stale,
                 "draft_answer": v.get("answer", "")}] if v and v.get("query") else []
    if cls == "ood":
        out, seen = [], set()
        subjects = material["subjects"]
        for batch in range(0, n_ood, OOD_BATCH):
            n = min(OOD_BATCH, n_ood - len(out))
            if n <= 0:
                break
            shown = subjects[batch % len(subjects):] + subjects[:batch % len(subjects)]   # a different lead each batch
            prompt = PROMPTS["ood"].format(subjects=", ".join(shown), n=n)
            if out:
                prompt += " Not these, already written: " + " | ".join(q["query"] for q in out)
            try:
                v = parse_json(ask(prompt, "", 60 * n + 100 + 20 * len(out)))
            except Exception:  # noqa: BLE001  (a failed batch keeps what the earlier ones gave)
                break
            for q in (v or {}).get("queries") or []:
                key = " ".join(str(q).lower().split())
                if isinstance(q, str) and key and key not in seen and len(out) < n_ood:
                    seen.add(key)
                    out.append({"class": "ood", "query": q.strip(), "answer_episodes": [], "draft_answer": "nothing"})
        return out
    raise ValueError(cls)


def _from(st: dict[str, str], episodes) -> str:
    return "+".join(sorted({st.get(e, "?") for e in episodes}))


def build(episodes, proposals, edges, mentions, ask, counts: dict[str, int], strata: tuple[str, ...], samples=(), seed: int = 492):
    """All the drafts, numbered d001…, and how many pieces of material gave nothing. Only text from episodes of `strata` reaches
    `ask`: the out-of-domain subjects are names of entities those episodes mention, and a temporal pair needs both facts to come
    only from them."""
    census = _census()
    st = census.episode_strata(episodes, proposals)
    allowed = {u for u, s in st.items() if s in strata or any(s.startswith(x + ":") for x in strata)}
    by_uuid = {e["uuid"]: e for e in episodes}
    rng = random.Random(seed)
    out: list[dict] = []
    failed = Counter()

    def add(cls, material, n=0):
        try:
            got = draft(cls, material, ask, n)
        except Exception:  # noqa: BLE001  (an engine error leaves this piece out; the rest go on)
            got = []
        if not got:
            failed[cls] += 1
        return got

    singles = [e for e in episodes if e["uuid"] in allowed and (e.get("content") or "").strip()]
    for e in rng.sample(singles, min(counts.get("point", 0), len(singles))):
        out += [{**d, "drafted_from": st[e["uuid"]]} for d in add("point", {"episode": e})]
    groups = entity_groups(mentions, allowed)
    for g in rng.sample(groups, min(counts.get("entity", 0), len(groups))):
        eps = [by_uuid[u] for u in g["episodes"] if u in by_uuid]
        out += [{**d, "drafted_from": _from(st, d["answer_episodes"])} for d in add("entity", {"name": g["name"], "episodes": eps})]
    pairs = [p for p in temporal_pairs(edges) if set(p["old"]["episodes"]) <= allowed and set(p["new"]["episodes"]) <= allowed]
    for p in rng.sample(pairs, min(counts.get("temporal", 0), len(pairs))):
        out += [{**d, "drafted_from": _from(st, p["new"]["episodes"])} for d in add("temporal", p)]
    if counts.get("ood"):
        mine = [m for m in mentions if set(m.get("episodes") or []) & allowed]
        subjects = [m["name"] for m in sorted(mine, key=lambda m: -len(set(m.get("episodes") or []) & allowed))[:30]]
        if subjects:
            out += [{**d, "drafted_from": "entities"} for d in add("ood", {"subjects": subjects}, counts["ood"])]
    # Real prompts, never sent to the engine: class and answer by hand. The hook's own prompts are left out: they are the hook set
    # (`run.py hookset`), split on their own, and the same prompt on both sides would leak across the split.
    asked = set()
    for s in samples:
        key = " ".join((s.get("query") or "").lower().split())
        if len(asked) >= counts.get("samples", 0) or not key or key in asked or (s.get("via") == "http" and census._hook_like(s.get("params"))):
            continue
        asked.add(key)
        out.append({"class": "", "query": s["query"], "answer_episodes": [], "draft_answer": "", "drafted_from": "replay sample",
                    "sample": s["id"]})
    drafts = [{"id": f"d{i:03d}", **d, "validated": False} for i, d in enumerate(out, 1)]
    return drafts, dict(failed)


def _read(slug: str, n_samples: int):
    _run().snapshot_guard()
    sys.path.insert(0, str(HERE.parent / "api"))
    from mimirsynth import models
    from mimirsynth.db import graph, rows
    from mimirsynth.llm import resolve
    from mimirsynth.store import _factory
    from mimirsynth.summary_review import ask as llm_ask
    with _factory()() as db:
        b = db.query(models.Brain).filter(models.Brain.slug == slug).one_or_none()
        if b is None:
            raise SystemExit(f"no brain with slug {slug!r}")
        P, S = models.Proposal, models.RecallSample
        proposals = [{"id": p.id, "status": p.status, "kind": p.kind, "origin": p.origin, "review_kind": p.review_kind,
                      "category": p.category, "source_description": p.source_description, "episode_uuid": p.episode_uuid,
                      "created_at": p.created_at} for p in db.query(P).filter(P.brain_id == b.id)]
        samples = [{"id": s.id, "query": s.query, "via": s.via, "params": s.params} for s in
                   db.query(S).filter(S.brain_id == b.id).order_by(S.id.desc())] if n_samples else []
        eng = resolve(db)
        gname = b.graph_name
    if not eng:
        raise SystemExit("this instance has no LLM engine")
    g = graph(gname)
    episodes = rows(g.ro_query("MATCH (e:Episodic) RETURN e.uuid AS uuid, e.content AS content, "
                               "e.source_description AS source_description"))
    edges = rows(g.ro_query("MATCH (a:Entity)-[r:RELATES_TO]->(:Entity) RETURN r.uuid AS uuid, r.name AS name, r.fact AS fact, "
                            "r.episodes AS episodes, r.valid_at AS valid_at, r.invalid_at AS invalid_at, r.expired_at AS expired_at, "
                            "a.uuid AS source_uuid"))
    mentions = rows(g.ro_query("MATCH (e:Episodic)-[:MENTIONS]->(n:Entity) RETURN n.uuid AS entity, n.name AS name, "
                               "collect(e.uuid) AS episodes"))

    def ask(prompt: str, text: str, max_tokens: int) -> str:
        msgs = [{"role": "system", "content": prompt}, {"role": "user", "content": text or "(no further text)"}]
        return llm_ask(eng, msgs, max_tokens=max_tokens)

    return episodes, proposals, edges, mentions, samples, ask


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--brain", required=True)
    ap.add_argument("--point", type=int, default=60)
    ap.add_argument("--entity", type=int, default=60)
    ap.add_argument("--temporal", type=int, default=60)
    ap.add_argument("--ood", type=int, default=45)
    ap.add_argument("--samples", type=int, default=40, help="real prompts from the replay sample, the most recent first")
    ap.add_argument("--strata", default="person,agent,capture", help="the census strata whose episodes the engine may read")
    ap.add_argument("--out", type=Path, default=OUT / "drafts.jsonl")
    ap.add_argument("--force", action="store_true", help="overwrite an existing drafts file")
    a = ap.parse_args(argv)
    if a.out.exists() and not a.force:
        raise SystemExit(f"{a.out} already exists and may hold your edits: move it, or use --force")
    episodes, proposals, edges, mentions, samples, ask = _read(a.brain, a.samples)
    counts = {"point": a.point, "entity": a.entity, "temporal": a.temporal, "ood": a.ood, "samples": a.samples}
    strata = tuple(s.strip() for s in a.strata.split(",") if s.strip())
    with _run().counted():
        drafts, failed = build(episodes, proposals, edges, mentions, ask, counts, strata, samples)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text("".join(json.dumps(d, ensure_ascii=False) + "\n" for d in drafts), encoding="utf-8")
    by = Counter(d["class"] or "to classify" for d in drafts)
    print(f"{len(drafts)} drafts ({', '.join(f'{k} {v}' for k, v in sorted(by.items()))}) → {a.out}")
    if failed:
        print(f"no usable answer from the engine for: {', '.join(f'{k} {v}' for k, v in sorted(failed.items()))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
