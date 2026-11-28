"""Cognee as an external baseline arm of the eval (#526): the same questions, the same budgets and the same scoring as 0.17, on a
separate Cognee instance loaded with the snapshot's episodes (`cognee_load.py`).

Cognee and the app do not share a virtual environment (their dependencies pin different versions), so the arm runs in two steps:

    # in Cognee's own venv (eval/adapters/requirements-cognee.txt), with MIMIRSYNTH_EVAL_COGNEE_ROOT set
    python ../eval/adapters/cognee.py search --brain SLUG --gold ../eval/out/gold.jsonl --hookset ../eval/out/hookset.jsonl
    # in the app's venv: score those results like any other system
    .venv/bin/python ../eval/run.py run --system cognee --brain SLUG --gold ../eval/out/gold.jsonl ... --label cognee

`search` asks Cognee for the chunks of every question at each budget and writes them, untouched, to `eval/out/cognee/`. `run.py`
then builds the final context with the app's own `build_context` within the budget, maps each chunk back to the episode it comes
from, and scores it. A chunk that cannot be mapped to an episode counts as noise, never as a match.
"""
from __future__ import annotations

import argparse
import asyncio
import functools
import importlib.util
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
EVAL = HERE.parent
OUT = EVAL / "out" / "cognee"

ROOT_ENV = "MIMIRSYNTH_EVAL_COGNEE_ROOT"
# Cognee's settings that point it at a database server instead of its own embedded stores under the root: any of them set could
# mean production (our Cognee keeps its vectors in PostgreSQL), so the arm refuses to start.
REMOTE_ENV = ("DB_HOST", "DB_PROVIDER", "VECTOR_DB_URL", "VECTOR_DB_PROVIDER", "GRAPH_DATABASE_URL", "GRAPH_DATABASE_PROVIDER")
MIN_PIECE = 200   # a chunk cut to fit the budget keeps at least this many characters, or it is left out


@functools.cache
def _run():
    spec = importlib.util.spec_from_file_location("eval_run", EVAL / "run.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def map_path(brain: str) -> Path:
    return OUT / f"{brain}.json"


def results_path(brain: str) -> Path:
    return OUT / f"results-{brain}.jsonl"


def read_map(path: Path, brain: str) -> dict:
    """The episodes `cognee_load.py export` wrote for this brain, with what the load added (the episodes loaded, Cognee's version,
    LLM and embedding)."""
    if not path.exists():
        raise SystemExit(f"{path}: run `cognee_load.py export` first")
    m = json.loads(path.read_text(encoding="utf-8"))
    if not {"brain", "corpus", "dataset", "episodes"} <= set(m):
        raise SystemExit(f"{path}: not a Cognee episode map")
    if m["brain"] != brain:
        raise SystemExit(f"{path} was made for brain {m['brain']!r}, not {brain!r}")
    return m


def write_map(path: Path, m: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


# --- a separate instance -------------------------------------------------------------------------------------------------------------

def instance_guard(env=None) -> Path:
    """The folder of the separate Cognee instance. Never production: the arm needs MIMIRSYNTH_EVAL_COGNEE_ROOT, and refuses any setting
    that would send Cognee to a database server."""
    env = os.environ if env is None else env
    root = (env.get(ROOT_ENV) or "").strip()
    if not root:
        raise SystemExit(f"set {ROOT_ENV} to an empty folder for a separate Cognee instance (never production's)")
    remote = [k for k in REMOTE_ENV if (env.get(k) or "").strip()]
    if remote:
        raise SystemExit(f"{', '.join(remote)} would point Cognee at a database server: unset them, so the separate instance keeps "
                         f"its embedded stores under {ROOT_ENV}")
    return Path(root).resolve()


class CogneeClient:
    """The few Cognee calls the arm makes, on the instance under `root`, in one event loop. The tests use a fake with the same
    methods. Only `add`, `cognify` and `search` with `CHUNKS` are used: `CHUNKS` returns the stored text, with no LLM in between."""

    def __init__(self, root: Path, dataset: str):
        os.environ["SYSTEM_ROOT_DIRECTORY"] = str(root / "system")
        os.environ["DATA_ROOT_DIRECTORY"] = str(root / "data")
        import cognee
        for name, sub in (("system_root_directory", "system"), ("data_root_directory", "data")):
            set_dir = getattr(getattr(cognee, "config", None), name, None)
            if callable(set_dir):
                set_dir(str(root / sub))
        self._cognee, self.dataset = cognee, dataset
        self._loop = asyncio.new_event_loop()
        self._calls = self._count_llm_calls()

    def _count_llm_calls(self) -> Counter | None:
        """LLM calls (not embeddings) seen through litellm, which Cognee calls them through. None when litellm cannot be hooked:
        the load then needs --calls-per-episode."""
        try:
            import litellm
            from litellm.integrations.custom_logger import CustomLogger
        except ImportError:
            return None
        calls: Counter = Counter()

        def seen(kwargs) -> None:
            if "embedding" not in str(kwargs.get("call_type") or ""):
                calls["llm"] += 1

        class _Count(CustomLogger):
            def log_success_event(self, kwargs, *a):
                seen(kwargs)

            def log_failure_event(self, kwargs, *a):
                seen(kwargs)

            async def async_log_success_event(self, kwargs, *a):
                seen(kwargs)

            async def async_log_failure_event(self, kwargs, *a):
                seen(kwargs)

        litellm.callbacks = [*(litellm.callbacks or []), _Count()]
        return calls

    def _do(self, coro):
        return self._loop.run_until_complete(coro)

    def add(self, episode: dict) -> None:
        self._do(self._cognee.add(episode["text"], dataset_name=self.dataset, node_set=[f"episode:{episode['uuid']}"]))

    def cognify(self) -> None:
        self._do(self._cognee.cognify(datasets=[self.dataset]))

    def search(self, query: str, top_k: int):
        from cognee import SearchType
        return self._do(self._cognee.search(query_text=query, query_type=SearchType.CHUNKS, datasets=[self.dataset], top_k=top_k))

    def llm_calls(self) -> int | None:
        return None if self._calls is None else self._calls["llm"]

    def describe(self) -> dict:
        from importlib.metadata import version
        env = os.environ
        return {"version": version("cognee"), "search": "CHUNKS", "steps": "add + cognify (no improve)",
                "llm": {k: env.get(k) for k in ("LLM_PROVIDER", "LLM_MODEL", "LLM_ENDPOINT")},
                "embedding": {k: env.get(k) for k in ("EMBEDDING_PROVIDER", "EMBEDDING_MODEL", "EMBEDDING_DIMENSIONS",
                                                      "EMBEDDING_ENDPOINT")}}


# --- results back to episodes (pure) -------------------------------------------------------------------------------------------------

def norm(text: str) -> str:
    return " ".join((text or "").split())


class EpisodeIndex:
    """Finds the episodes a Cognee chunk comes from. A chunk is a piece of the text loaded for one episode, so it is found inside
    that text, whitespace aside. Cognee's own ids are not used: they are hashes of its internals, and the text is what was loaded."""

    def __init__(self, episodes: list[dict]):
        self._eps = [(e["uuid"], norm(e["text"])) for e in episodes]
        self._ref = {e["uuid"]: e.get("reference_time") for e in episodes}

    def find(self, text: str) -> list[str]:
        n = norm(text)
        return [u for u, t in self._eps if n in t] if n else []

    def reference_time(self, uuid: str):
        return self._ref.get(uuid)


def results_of(raw) -> list[dict]:
    """Cognee's search output as a flat list of results with a `text`. It may come wrapped per dataset (`search_result`); anything
    that is not a dict with text is kept as its string, so it still takes room in the context and counts as noise."""
    if raw is None:
        return []
    if isinstance(raw, list):
        return [r for x in raw for r in results_of(x)]
    if isinstance(raw, dict):
        if "search_result" in raw:
            return results_of(raw["search_result"])
        if isinstance(raw.get("text"), str):
            return [{"text": raw["text"], **({"id": str(raw["id"])} if raw.get("id") is not None else {}),
                     **({"score": raw["score"]} if isinstance(raw.get("score"), (int, float)) else {})}]
    return [{"text": raw if isinstance(raw, str) else json.dumps(raw, ensure_ascii=False, default=str)}]


def to_chunks(results: list[dict], index: EpisodeIndex, stats: Counter) -> list[dict]:
    """The results as the app's fragments, in Cognee's order, each with the episodes it maps to (none: noise; several: the same text
    was loaded for more than one episode)."""
    chunks = []
    for i, r in enumerate(results):
        text = (r.get("text") or "").strip()
        if not text:
            stats["empty"] += 1
            continue
        eps = index.find(text)
        stats["results"] += 1
        if not eps:
            stats["unmapped"] += 1
        elif len(eps) > 1:
            stats["ambiguous"] += 1
        one = eps[0] if len(eps) == 1 else None
        chunks.append({"id": r.get("id") or f"cognee-{i}", "text": text, "name": "Cognee", "episode_uuid": one, "episodes": eps,
                       "valid_at": index.reference_time(one) if one else None})
    return chunks


def fit(chunks: list[dict], max_chars: int, build, stats: Counter) -> list[dict]:
    """The chunks that fit the budget in `build`'s context. Cognee's chunks are longer than 0.17's 900-character fragments, so the
    first one that does not fit whole is cut, at a space, to what is left (at least MIN_PIECE characters), instead of leaving the
    budget unused; nothing after it is added. The cut text is still inside its episode, so it maps the same."""
    kept: list[dict] = []
    for c in chunks:
        if c["text"] in build(kept + [c], max_chars):
            kept.append(c)
            continue
        lo, hi = 0, len(c["text"])
        while lo < hi:   # the longest prefix that still fits
            mid = (lo + hi + 1) // 2
            if c["text"][:mid].strip() in build(kept + [{**c, "text": c["text"][:mid]}], max_chars):
                lo = mid
            else:
                hi = mid - 1
        piece = c["text"][:lo]
        if lo < len(c["text"]) and " " in piece:
            piece = piece.rsplit(" ", 1)[0]
        piece = piece.strip()
        if len(piece) >= MIN_PIECE:
            kept.append({**c, "text": piece})
            stats["cut"] += 1
        break
    return kept


def make_recall(search_fn, episodes: list[dict], build_context, lang: str = "es", stats: Counter | None = None):
    """`recall_fn(query, **params)` for `run.py`, over `search_fn(query, top_k) -> (raw results, ms)`. Cognee gets as many results
    as the app's recall may show (facts plus fragments) and the same character budget, through the app's `build_context`."""
    index = EpisodeIndex(episodes)
    stats = stats if stats is not None else Counter()

    def build(chunks, max_chars):
        return build_context([], chunks, max_chars, None, lang)

    def recall_fn(query: str, n_facts: int = 0, n_chunks: int = 0, max_chars: int = 2500, **_):
        raw, ms = search_fn(query, n_facts + n_chunks)
        chunks = fit(to_chunks(results_of(raw), index, stats), max_chars, build, stats)
        return {"facts": [], "chunks": chunks, "documents": [], "context": build(chunks, max_chars), "ms": {"total": ms}}

    return recall_fn, stats


# --- the stored search results -------------------------------------------------------------------------------------------------------

def from_results(path: Path):
    """`search_fn` over the file `search` wrote. A question it has no answer for, or whose search failed, fails its recall, and
    `run.py` records the error."""
    if not path.exists():
        raise SystemExit(f"{path}: run `cognee.py search` first, in Cognee's venv")
    got = {}
    for row in _run().load_jsonl(path):
        got[(row["query"], row["top_k"])] = row

    def search_fn(query: str, top_k: int):
        row = got.get((query, top_k))
        if row is None:
            raise LookupError(f"no Cognee result for this question at top_k {top_k}: run `cognee.py search` again")
        if row.get("error"):
            raise RuntimeError(f"Cognee's search failed: {row['error']}")
        return row["results"], row.get("ms")

    return search_fn


def queries(gold: list[dict], hooks: list[dict]) -> list[str]:
    seen, out = set(), []
    for q in [*gold, *hooks]:
        if q.get("query") and q["query"] not in seen:
            seen.add(q["query"])
            out.append(q["query"])
    return out


def search_all(client, qs: list[str], budgets: list[str], clock=time.perf_counter) -> list[dict]:
    """Every question at the top_k of each budget, in order. A failed search is kept with its error, and the rest go on."""
    rows = []
    for top_k in sorted({p["n_facts"] + p["n_chunks"] for b, p in _run().BUDGETS.items() if b in budgets}):
        for q in qs:
            t0 = clock()
            try:
                res = results_of(client.search(q, top_k))
            except Exception as e:  # noqa: BLE001  (one failed search is recorded, the rest go on)
                rows.append({"query": q, "top_k": top_k, "error": f"{type(e).__name__}: {e}"})
                continue
            rows.append({"query": q, "top_k": top_k, "ms": round(1000 * (clock() - t0), 1), "results": res})
    return rows


def main(argv: list[str] | None = None, client=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search", help="ask Cognee for every question's chunks, at each budget")
    s.add_argument("--brain", required=True)
    s.add_argument("--gold", type=Path, required=True)
    s.add_argument("--hookset", type=Path)
    s.add_argument("--budget", nargs="+", choices=tuple(_run().BUDGETS), default=list(_run().BUDGETS))
    s.add_argument("--map", type=Path, help="default: eval/out/cognee/<brain>.json")
    s.add_argument("--out", type=Path, help="default: eval/out/cognee/results-<brain>.jsonl")
    a = ap.parse_args(argv)

    m = read_map(a.map or map_path(a.brain), a.brain)
    if not m.get("cognee"):
        raise SystemExit("this brain was never loaded into Cognee: run `cognee_load.py load` first")
    root = instance_guard()
    if client is None:
        client = CogneeClient(root, m["dataset"])
    have = client.describe().get("version")
    if have != m["cognee"].get("version"):
        raise SystemExit(f"Cognee {have} is installed, but the brain was loaded with {m['cognee'].get('version')}")
    run = _run()
    qs = queries(run.load_jsonl(a.gold), run.load_jsonl(a.hookset) if a.hookset else [])
    rows = search_all(client, qs, a.budget)
    out = a.out or results_path(a.brain)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    failed = sum(1 for r in rows if r.get("error"))
    print(f"{len(rows)} searches ({len(qs)} questions), {failed} failed → {out}")
    return 1 if rows and failed == len(rows) else 0


if __name__ == "__main__":
    sys.exit(main())
