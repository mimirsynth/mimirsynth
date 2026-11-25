"""Draft eval questions from a snapshot's episodes with an LLM (#492), for the maintainer to validate or edit.

Read-only on the snapshot; it runs from `api/` with the instance's environment and uses the instance's default LLM engine, so the
episodes it drafts from are sent to that engine:

    cd api && .venv/bin/python ../eval/drafts.py --brain SLUG

It writes `eval/out/drafts.jsonl` (ignored by git). Each draft has `validated: false`; the maintainer reads it, fixes the query, the
answer episodes and the stale list if needed, sets `validated: true` and copies it to the gold set. Volatile-data questions are not
drafted: they are the three probes, written by hand.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import random
import re
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
EPISODE_CHARS = 3000   # what of each episode the engine reads
SAME_TIME = 60         # seconds: Graphiti gives the fact it invalidates, as `invalid_at`, the `valid_at` of the fact that replaces it

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


def _census():
    spec = importlib.util.spec_from_file_location("census", HERE / "census" / "census.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


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
    if not v:
        return None
    try:
        d = v if isinstance(v, datetime) else datetime.fromisoformat(str(v))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=UTC)   # a naive date is UTC, so it compares with an aware one


def temporal_pairs(edges: list[dict]) -> list[dict]:
    """(old, new) where `new` is a current fact on the same source entity that took effect when `old` stopped being true: what
    Graphiti records when a newer fact invalidates an older one."""
    current = [f for f in edges if not f.get("invalid_at") and not f.get("expired_at")]
    by_source: dict[str, list[dict]] = defaultdict(list)
    for f in current:
        by_source[f.get("source_uuid") or ""].append(f)
    pairs = []
    for old in edges:
        end = _ts(old.get("invalid_at"))
        if not end or not old.get("episodes"):
            continue
        for new in by_source.get(old.get("source_uuid") or "", []):
            start = _ts(new.get("valid_at"))
            if new is not old and start and new.get("episodes") and abs((start - end).total_seconds()) <= SAME_TIME:
                pairs.append({"old": old, "new": new})
                break
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
    """The drafts for one piece of material; empty when the engine's answer is unusable. `ask(prompt, text) -> str`."""
    if cls == "point":
        e = material["episode"]
        v = parse_json(ask(PROMPTS["point"], e["content"][:EPISODE_CHARS]))
        return [{"class": "point", "query": v["query"], "answer_episodes": [e["uuid"]], "draft_answer": v.get("answer", "")}] \
            if v and v.get("query") else []
    if cls == "entity":
        eps = material["episodes"]
        text = "\n\n".join(f"Note {i}:\n{e['content'][:EPISODE_CHARS]}" for i, e in enumerate(eps, 1))
        v = parse_json(ask(PROMPTS["entity"].format(entity=material["name"]), text))
        if not v or not v.get("query"):
            return []
        picked = [eps[i - 1]["uuid"] for i in v.get("notes") or [] if isinstance(i, int) and 1 <= i <= len(eps)]
        return [{"class": "entity", "query": v["query"], "answer_episodes": picked if len(picked) >= 2 else [e["uuid"] for e in eps],
                 "draft_answer": v.get("answer", "")}]
    if cls == "temporal":
        old, new = material["old"], material["new"]
        v = parse_json(ask(PROMPTS["temporal"].format(old=old["fact"], new=new["fact"], when=str(old["invalid_at"])[:10]), ""))
        return [{"class": "temporal", "query": v["query"], "answer_episodes": list(new["episodes"]), "stale": [old["uuid"]],
                 "draft_answer": v.get("answer", "")}] if v and v.get("query") else []
    if cls == "ood":
        v = parse_json(ask(PROMPTS["ood"].format(subjects=", ".join(material["subjects"]), n=n_ood), ""))
        return [{"class": "ood", "query": q, "answer_episodes": [], "draft_answer": "nothing"}
                for q in (v or {}).get("queries") or [] if isinstance(q, str) and q.strip()]
    raise ValueError(cls)


def build(episodes, proposals, edges, mentions, ask, counts: dict[str, int], strata: tuple[str, ...], seed: int = 492) -> list[dict]:
    """All the drafts, numbered d001…, from the episodes of the given strata (`person`, `agent` by default: the curated candidates)."""
    census = _census()
    st = census.episode_strata(episodes, proposals)
    allowed = {u for u, s in st.items() if s in strata or any(s.startswith(x + ":") for x in strata)}
    by_uuid = {e["uuid"]: e for e in episodes}
    rng = random.Random(seed)
    out: list[dict] = []
    singles = [e for e in episodes if e["uuid"] in allowed and (e.get("content") or "").strip()]
    for e in rng.sample(singles, min(counts.get("point", 0), len(singles))):
        out += draft("point", {"episode": e}, ask)
    groups = entity_groups(mentions, allowed)
    for g in rng.sample(groups, min(counts.get("entity", 0), len(groups))):
        out += draft("entity", {"name": g["name"], "episodes": [by_uuid[u] for u in g["episodes"] if u in by_uuid]}, ask)
    pairs = [p for p in temporal_pairs(edges) if set(p["new"]["episodes"]) & allowed]
    for p in rng.sample(pairs, min(counts.get("temporal", 0), len(pairs))):
        out += draft("temporal", p, ask)
    if counts.get("ood"):
        subjects = [m["name"] for m in sorted(mentions, key=lambda m: -len(m.get("episodes") or []))[:30]]
        out += draft("ood", {"subjects": subjects}, ask, counts["ood"])
    return [{"id": f"d{i:03d}", **d, "validated": False, "source": "llm draft"} for i, d in enumerate(out, 1)]


def _read(slug: str):
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
        P = models.Proposal
        proposals = [{"id": p.id, "status": p.status, "kind": p.kind, "origin": p.origin, "review_kind": p.review_kind,
                      "category": p.category, "source_description": p.source_description, "episode_uuid": p.episode_uuid,
                      "created_at": p.created_at} for p in db.query(P).filter(P.brain_id == b.id)]
        eng = resolve(db)
        gname = b.graph_name
    if not eng:
        raise SystemExit("this instance has no LLM engine")
    g = graph(gname)
    episodes = rows(g.ro_query("MATCH (e:Episodic) RETURN e.uuid AS uuid, e.content AS content, "
                               "e.source_description AS source_description"))
    edges = rows(g.ro_query("MATCH (a:Entity)-[r:RELATES_TO]->(:Entity) RETURN r.uuid AS uuid, r.fact AS fact, r.episodes AS episodes, "
                            "r.valid_at AS valid_at, r.invalid_at AS invalid_at, r.expired_at AS expired_at, a.uuid AS source_uuid"))
    mentions = rows(g.ro_query("MATCH (e:Episodic)-[:MENTIONS]->(n:Entity) RETURN n.uuid AS entity, n.name AS name, "
                               "collect(e.uuid) AS episodes"))

    def ask(prompt: str, text: str) -> str:
        msgs = [{"role": "system", "content": prompt}, {"role": "user", "content": text or "(no further text)"}]
        return llm_ask(eng, msgs, max_tokens=600)

    return episodes, proposals, edges, mentions, ask


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--brain", required=True)
    ap.add_argument("--point", type=int, default=60)
    ap.add_argument("--entity", type=int, default=60)
    ap.add_argument("--temporal", type=int, default=60)
    ap.add_argument("--ood", type=int, default=45)
    ap.add_argument("--strata", default="person,agent", help="the strata of the episodes to draft from (census strata)")
    ap.add_argument("--out", type=Path, default=OUT / "drafts.jsonl")
    a = ap.parse_args(argv)
    episodes, proposals, edges, mentions, ask = _read(a.brain)
    counts = {"point": a.point, "entity": a.entity, "temporal": a.temporal, "ood": a.ood}
    drafts = build(episodes, proposals, edges, mentions, ask, counts, tuple(s.strip() for s in a.strata.split(",") if s.strip()))
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text("".join(json.dumps(d, ensure_ascii=False) + "\n" for d in drafts), encoding="utf-8")
    by = defaultdict(int)
    for d in drafts:
        by[d["class"]] += 1
    print(f"{len(drafts)} drafts ({', '.join(f'{k} {v}' for k, v in sorted(by.items()))}) → {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
