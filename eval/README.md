# Retrieval eval (#492)

How well the recall serves a brain, measured on its final context: per question class, at two budgets, with intervals, and B
against A with a verdict written before measuring (#491, Phase 0). `census/` holds the corpus census (#514).

Everything runs on the **frozen Phase 0 snapshot**, restored on an instance that is not production, from `api/` with that instance's
`MIMIRSYNTH_*` environment. Everything it writes goes to `eval/out/`, which git ignores: questions, prompts and results hold the
brain's own text.

## 1. Questions

The gold set is a JSONL file, one question per line, kept in `eval/out/` (never in the repository):

```json
{"id": "q001", "class": "temporal", "query": "¿dónde corre ahora X?", "answer_episodes": ["<uuid>"], "stale": ["<fact uuid>"], "validated": true}
```

| Field | |
|---|---|
| `class` | `point`, `entity` (the answer is spread over several notes), `temporal`, `ood` (out of domain: the answer is nothing), `volatile` (the three probes) |
| `answer_episodes` | the uuids of the episodes that contain the answer: an `entity` question needs at least two, `ood` none |
| `answer_docs` | optional: document ids, when the answer is in a document |
| `stale` | `temporal` only: what must not appear as current, meaning the replaced fact's uuid, or the episode or document that states the old value |
| `validated` | the maintainer read it and accepts it; `run` leaves the rest out unless `--include-drafts` |

`check_gold` refuses a set with a missing id, a repeated id, an unknown class, an entity question with one episode, and so on.

**Drafts.** `drafts.py` writes about 225 drafts to `eval/out/drafts.jsonl`, from the episodes of the curated strata of the census
(`person`, `agent`; `--strata` changes them):

```bash
.venv/bin/python ../eval/drafts.py --brain SLUG
```

- `point`: one episode;
- `entity`: two to five episodes that mention the same entity;
- `temporal`: a fact Graphiti invalidated and the fact that replaced it, with the old one in `stale`;
- `ood`: questions that sound like the brain but are not about it.

The drafts use the instance's default LLM engine, so those episodes are sent to it. Every draft comes with `validated: false` and a
`draft_answer`. Read each one, fix the query, `answer_episodes` and `stale`, set `validated: true`, and copy it to the gold set.
Volatile questions are not drafted.

Drafting only from curated episodes favours the clean arm of #516. To compensate, also draft from captures
(`--strata person,agent,capture`) and use the real prompts below.

## 2. Real prompts (hook set)

```bash
.venv/bin/python ../eval/run.py hookset --brain SLUG     # eval/out/hookset.jsonl
```

This writes the replay sample's prompts that came through the agents' hook: over HTTP, with `facts=6` and `chunks=3`. Put in `label`
the uuid of the episode that should have been injected, or `nothing`. Unlabelled prompts are skipped.

## 3. Split

```bash
.venv/bin/python ../eval/run.py split --gold ../eval/out/gold.jsonl          # eval/out/split.json
.venv/bin/python ../eval/run.py split --gold ../eval/out/gold.jsonl --add    # place new questions only
```

The split is `tune` / `holdout` at 50 / 50 within each class, fixed by id. It refuses to be redone. With `--add`, the questions already
placed keep their side, and new ones go to the smaller side of their class. `run` stops if a question is in neither side.

## 4. Run

```bash
.venv/bin/python ../eval/run.py run --brain SLUG --gold ../eval/out/gold.jsonl --hookset ../eval/out/hookset.jsonl \
    --split holdout --budget plugin --label baseline-0.17
```

| Budget | Facts | Fragments | Characters |
|---|--:|--:|--:|
| `2500` | 8 | 4 | 2,500 |
| `plugin` | 6 | 3 | 4,000 (the hook's real parameters) |

It calls the app's `recall()` in process, prints the table and writes `eval/out/run-<label>-<budget>-<split>.json`.

**What is scored.** Only the items that made it into the final `context`, in the order they appear there. An item the budget cut
out counts neither for nor against.

| Metric | Classes | Definition |
|---|---|---|
| `top3` | point, temporal, volatile | an item from an answer episode (or answer document) is among the first three |
| `coverage` | entity | share of the answer episodes that some item comes from |
| `stale_as_current` | temporal | something in `stale` is shown as current: the replaced fact in the current section, or a fragment or passage from a stale episode with no «Puede estar superado» warning. A current fact that only shares an episode with the old one does not count |
| `empty_ok` | ood | nothing was returned |
| `noise` | every class, and all together | share of the characters that come from items outside the answer, the sum of characters over the sum of characters |
| `hook_precision` | hook | of the prompts where something was injected, the share that injected the labelled note |
| `hook_silence` | hook | of the prompts labelled `nothing`, the share where nothing was injected |

Also reported: latency p50 and p95 from the recall's own `ms.total`. Every rate comes with a 95 % bootstrap interval over the
questions (2,000 resamples, fixed seed).

## 5. Compare

```bash
.venv/bin/python ../eval/run.py compare ../eval/out/run-a.json ../eval/out/run-b.json
```

The comparison is paired: each resample draws the same questions for A and B. It refuses two runs with a different budget or split.
The table gives B − A in points with its interval, and the change relative to A.

**The verdict, written before measuring:**

- **Yes** needs all three:
  - at least one co-primary improves:
    - `noise` over all questions falls 30 % or more relative to A, or
    - `stale_as_current` on the temporal questions falls 50 % or more,

    and the interval of that change is wholly below zero;
  - neither co-primary rises (its interval is not wholly above zero);
  - every answer metric (`top3`, `coverage`, `empty_ok`, `hook_precision`, `hook_silence`) loses 3 points or fewer at the lower bound
    of its interval.
- **Anything else, a tie included, is no.** The command exits with 1 on a no.
