# Error analysis of 0.17 (#515)

Every miss and every noisy item of 0.17's recall on `tune` goes into exactly one of nine classes. The classes that dominate show
which component to change, and which #513 variants are worth building (#491, Phase 0). It reuses the eval (#492): the gold set,
the hook set, the split, the budgets, and the scoring on the final context.

Run it like the eval: from `api/`, on the instance where the snapshot was restored, with its `MIMIRSYNTH_*` environment and
`MIMIRSYNTH_EVAL_SNAPSHOT=1`. The recall's embedding calls are counted for the instance (brain 0) under `eval`, as in the eval.
Everything goes to `eval/out/errors/`, which git ignores, because the candidates and the sheet hold the brain's own text.

```bash
.venv/bin/python ../eval/errors/errors.py candidates --brain SLUG --gold ../eval/out/gold.jsonl \
    --hookset ../eval/out/hookset.jsonl --budget plugin                  # candidates-plugin-tune.jsonl
.venv/bin/python ../eval/errors/errors.py sheet --candidates ../eval/out/errors/candidates-plugin-tune.jsonl   # errors-plugin-tune.csv
# classify by hand the rows whose `class` is empty, and correct any filled-in class that is wrong, then:
.venv/bin/python ../eval/errors/errors.py summarize --sheet ../eval/out/errors/errors-plugin-tune.csv
```

## 1. Candidates

For each validated question of the split (`tune` by default) and each labelled hook prompt, `candidates` records:
- **the recall at the budget's parameters**: what 0.17 returns and its final context, as `run` calls it;
- **the top 50 of each path, before the threshold and the cut**:
  - facts by cosine, as 0.17 searches them (`search_facts`);
  - episode chunks by the hybrid search (`index.search`), with the recall's recency weight and common terms;
- **for each answer episode**: whether the snapshot holds it, its date, and whether any fact comes from it;
- **for each `stale` uuid**: whether the fact is invalidated or expired in the snapshot, and the dates of the stale episodes.

Only the brain's own graph and index are searched. What other brains lend is in the recall, but not among the candidates. So when
the recall reads lent brains, a row suggested 1 or 4 says so in its hint: an answer that only a lent brain holds would look missing.
Document passages are not searched either.

## 2. The sheet

`sheet` writes one row per unit, and refuses to overwrite a sheet that may already hold your classes.

| `unit` | One row per | |
|---|---|---|
| `miss` | question whose answer metric missed: `top3`, `coverage`, `empty_ok`, or a hook prompt without its note or with something injected when it should be silent | the class of where the answer got furthest |
| `stale` | temporal question with `stale_as_current` | left for a person: 6 if Graphiti failed to invalidate the fact, 2 if only the stale version is stored |
| `noise` | item in the final context that is not from the answer | always 9, with its similarity, or the link it came in through |
| `error` | recall that failed, or context that could not be read | left out of the summary, and counted |

**Filled in by the sheet** (`suggested` and `class`). The rules go from the furthest stage back. For an entity question they apply
to the answer episodes it missed.

| Where the answer got furthest | Class |
|---|---|
| in the final context, after the first three (point, temporal and volatile questions; an entity question is scored on coverage) | 5 |
| returned by the recall, then cut out of the context by the character budget | 8 |
| among the top 50 of a path, below the number the recall returns or below its threshold (`why` says which) | 5 |
| in no top 50 | 4 |
| an entity question with more answer episodes than `n_facts + n_chunks`, whose missing ones are among the top 50 (when they are in none, it stays 4) | 7 |
| an out-of-domain question, or a hook prompt labelled `nothing`, with something injected | 9 |

**Left for a person** (`class` empty). The `suggested` and `hint` columns help.
- An answer episode the snapshot does not hold is suggested 1, unless another note holds the answer.
- An answer episode no fact comes from is hinted 3, when the chunks did not find it either.
- Class 2 is read from the episodes.
- Every `stale` row. Its suggestion comes from the snapshot:
  - **6**: a stale fact shown as current is invalidated or expired there, or an answer episode it holds is dated after every stale
    episode, so the new value was there to invalidate the old one;
  - **2**: the snapshot holds no answer episode other than the stale ones;
  - none, when neither is clear.

Correct any filled-in class you disagree with. Each row keeps exactly one class.

## 3. Summary

`summarize` prints what is posted in #491:
- the share of each class per question class, over the `miss` and `stale` rows;
- each class with the component that would fix it:

| Class | | Component |
|--:|---|---|
| 1 | not in the corpus | write path |
| 2 | stored stale or wrong | write path |
| 3 | extraction lost it | extraction |
| 4 | not among the candidates | retrieval |
| 5 | a candidate, ranked below the cut | ranking |
| 6 | stale shown as current | invalidation |
| 7 | spread over more notes than the limit | limit |
| 8 | cut by the character budget | budget |
| 9 | noise | ranking |

- the noise items by kind, and by how they came in: above the threshold, or through a link (a fact that replaces one in the result,
  or an old fact a fragment states, which skip the threshold);
- how many rows have no class yet, and how many recalls failed.
