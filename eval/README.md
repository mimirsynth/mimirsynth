# Retrieval eval (#492)

How well the recall serves a brain, measured on its final context: per question class, at two budgets, with intervals, and B
against A with a verdict written before measuring (#491, Phase 0). `census/` holds the corpus census (#514).

Everything runs on the **frozen Phase 0 snapshot**, restored on an instance that is not production, from `api/` with that instance's
`MIMIRSYNTH_*` environment and `MIMIRSYNTH_EVAL_SNAPSHOT=1`. Set that variable only on the restored instance: `run`, `hookset` and
`drafts.py` refuse to touch a brain without it, since production is PostgreSQL too. Everything it writes goes to `eval/out/`, which
git ignores: questions, prompts and results hold the brain's own text.

Nothing here changes the brain, but it is not read-only either:
- the recall's embedding calls and the drafts' LLM calls are counted in the snapshot's `ai_usage`, as on any instance;
- reading a federation grant stamps its last use;
- both refuse to run on anything but PostgreSQL;
- run it with the instance's notifications off, so a budget warning goes nowhere.

## 1. Questions

The gold set is a JSONL file, one question per line, kept in `eval/out/` (never in the repository):

```json
{"id": "q001", "class": "temporal", "query": "¿dónde corre ahora X?", "answer_episodes": ["<uuid>"], "stale": ["<uuid>"], "validated": true}
```

| Field | |
|---|---|
| `class` | `point`, `entity` (the answer is spread over several notes), `temporal`, `ood` (out of domain: the answer is nothing), `volatile` (the three probes) |
| `answer_episodes` | the uuids of the episodes that contain the answer: an `entity` question needs at least two distinct ones, `ood` none |
| `answer_docs` | optional: document ids, when the answer is in a document |
| `stale` | `temporal` only: what must not appear as current. A fact uuid counts only when Graphiti failed to invalidate that fact, since an invalidated fact always shows as no longer true. An episode or document uuid counts when a fragment or passage from it shows with no warning |
| `validated` | `true` or `false`: the maintainer read the question and accepts it. `run` leaves out the rest unless given `--include-drafts` |
| `drafted_from` | where the draft came from: the census stratum of its episodes, `entities` or `replay sample`. Kept to measure the bias later |

`check_gold` refuses a set with any of these:
- a missing or repeated id;
- an unknown class;
- an id list that is not a list of strings;
- a `validated` that is not a boolean;
- an entity question with fewer than two distinct episodes.

**Drafts.** `drafts.py` writes drafts to `eval/out/drafts.jsonl`. It refuses to overwrite that file, since you edit it.

```bash
.venv/bin/python ../eval/drafts.py --brain SLUG
```

- **From episodes, through the instance's default LLM engine.** The episodes come from the census strata in `--strata`: by default
  `person`, `agent` and `capture`, so the gold set does not lean towards the clean arm of #516. Only text from episodes of those
  strata reaches the engine.
  - `point`: one episode.
  - `entity`: two to five episodes that mention the same entity.
  - `temporal`: a fact Graphiti invalidated and the fact that replaced it, both from those strata. `stale` gets the old fact and the
    episodes only the old fact came from.
  - `ood`: questions that sound like the brain but are not about it, drafted from the names of the entities those episodes mention,
    ten per call. Each call is told the ones already written, and repeats are dropped. A failed call keeps what the earlier ones
    gave.
- **From real prompts.** The replay sample's most recent queries (`--samples`, 40 by default), as they were asked. They are never
  sent to the engine, and they come with an empty `class` and no answer for you to fill in. A prompt asked twice is drafted once.
  The hook's own prompts are left out, since they are the hook set (below), split on their own.

Every draft has `validated: false`, a `draft_answer` and its `drafted_from`. To accept a draft:
1. Read it.
2. Fix its class, query, `answer_episodes` and `stale`.
3. Set `validated: true`.
4. Copy it to the gold set.

The script reports at the end how many pieces of material the engine gave nothing usable for. Volatile questions are not drafted.

## 2. Real prompts (hook set)

```bash
.venv/bin/python ../eval/run.py hookset --brain SLUG     # eval/out/hookset.jsonl
```

This writes the replay sample's prompts that came through the agents' hook: over HTTP, with `facts=6` and `chunks=3`.
- Put in `label` the uuid of the episode that should have been injected, or `nothing`.
- Unlabelled prompts are skipped.
- Running the command again adds the new prompts and keeps every label already written.

## 3. Split

```bash
.venv/bin/python ../eval/run.py split --gold ../eval/out/gold.jsonl --hookset ../eval/out/hookset.jsonl          # eval/out/split.json
.venv/bin/python ../eval/run.py split --gold ../eval/out/gold.jsonl --hookset ../eval/out/hookset.jsonl --add    # new ones only
```

- The split is `tune` / `holdout` at 50 / 50 within each class, fixed by id. The hook prompts are split the same way, separately.
- It refuses to be redone. With `--add`, everything already placed keeps its side, and new questions and prompts go to the smaller
  side of their class.
- `run` stops if a question or a labelled prompt is in neither side.

## 4. Run

```bash
.venv/bin/python ../eval/run.py run --brain SLUG --gold ../eval/out/gold.jsonl --hookset ../eval/out/hookset.jsonl \
    --split holdout --budget plugin --label baseline-0.17
```

| Budget | Facts | Fragments | Characters |
|---|--:|--:|--:|
| `2500` | 8 | 4 | 2,500 |
| `plugin` | 6 | 3 | 4,000 (the hook's real parameters) |

It calls the app's `recall()` in process, the way the hook's HTTP call makes it: with what other brains lend this one (federation),
in the instance's default language and with its default document passages. All three are recorded in the result's `meta`. It prints the table
and writes `eval/out/run-<label>-<budget>-<split>.json`. A recall that fails is recorded with its error and left out of the metrics,
and the run goes on. If every recall fails, the command exits with 1.

**What is scored.** Only the items that made it into the final `context`, in the order they appear there.
- Each item is matched by its own line: a fact by its `- <fact> (` line, and a fragment or passage by its text right under its
  `###` header.
- A text that is only quoted in another line (`[sustituye a «…»]`, a warning) does not count, and an item the budget cut out counts
  neither for nor against.
- `empty_ok` and hook silence look at the context itself, so a state card alone counts as something injected.
- `noise` is over the whole context. An item from the answer takes its whole entry: a fact's line, or a fragment's or passage's
  header, text and "may be superseded" lines (any other `> ` line is not part of it). No two items share a character: a `###`
  heading or a `- … (` line inside a passage's text is not taken as another item. Every other character is noise, whether it was parsed or not: section headers, state cards, items
  outside the answer, and any text in a format the parser does not know. So a variant that writes its context another way cannot
  look cleaner for it.
- Each record keeps `unparsed_chars`, the characters no item took, and the summary prints their total against the context's.
- If the recall returned items and none of them is found in a context that has text, the record is an error, `unparsed context`. It
  leaves the metrics and the pairing instead of scoring as an empty answer. This also happens if state cards take the whole budget.

| Metric | Classes | Definition |
|---|---|---|
| `top3` | point, temporal, volatile | an item from an answer episode (or answer document) is among the first three |
| `coverage` | entity | share of the answer episodes that some item comes from |
| `stale_as_current` | temporal | something in `stale` is shown as current (see `stale` above) |
| `empty_ok` | ood | the context is empty |
| `noise` | every class, and all together | share of the context's characters that are not part of an item from the answer: summed over the questions, over the sum of their context lengths |
| `hook_precision` | hook | of the prompts where something was injected, the share that injected the labelled note |
| `hook_silence` | hook | of the prompts labelled `nothing`, the share where nothing was injected |

Latency p50 and p95 come from the recall's own `ms.total`. Every rate has a 95 % bootstrap interval over the questions (2,000
resamples, fixed seed).

## 5. Compare

```bash
.venv/bin/python ../eval/run.py compare ../eval/out/run-a.json ../eval/out/run-b.json
```

- **Paired:** each resample draws the same questions for A and B, over the questions that ran without error in both. The counts are
  printed.
- **Refuses** two runs that differ in budget, split or whether drafts were included.
- **The table** gives B − A in points with its interval, and the change relative to A. A metric that A measured and B could not,
  such as hook precision when B injects nothing, stays in the table without a value.

**The verdict, written before measuring:**

- **Yes** needs all four:
  - at least one co-primary improves:
    - `noise` over all questions falls 30 % or more relative to A, or
    - `stale_as_current` on the temporal questions falls 50 % or more,

    and the interval of that change is wholly below zero;
  - neither co-primary rises (its interval is not wholly above zero);
  - every answer metric that A measured (`top3`, `coverage`, `empty_ok`, `hook_precision`, `hook_silence`) is measured in B too, and
    loses 3 points or fewer at the lower bound of its interval;
  - B fails on no more of the questions both runs have than A does. A failed recall or an unparsed context leaves the pairing, and
    B must not be judged only on the questions it got through.
- **Anything else, a tie included, is no.** A co-primary at 0 in A cannot fall. The command exits with 1 on a no.

How "improves" is read: the point estimate of the relative change reaches the minimum effect (−30 % or −50 %), and the interval of
the difference B − A is wholly below zero. The interval does not have to be wholly past the minimum effect: with about 50 questions
per class that would rarely be reached. Agreed in the review of #522.
