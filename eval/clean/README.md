# Virtual clean corpus (#516, step 1)

Does clean content make 0.17's recall better? Step 1 of #516 answers this without an LLM and without rebuilding anything. At query
time, the recall leaves out the facts and chunks that come only from episodes that are not curated. Then the eval (#492) compares
the **full** corpus with the **virtually clean** one (#491, W1).

Run it like the eval: from `api/`, on the instance where the snapshot was restored, with its `MIMIRSYNTH_*` environment and
`MIMIRSYNTH_EVAL_SNAPSHOT=1`.

```bash
.venv/bin/python ../eval/clean/clean.py curated --brain SLUG                       # eval/out/clean/curated.json
.venv/bin/python ../eval/run.py run --brain SLUG --gold ../eval/out/gold.jsonl --hookset ../eval/out/hookset.jsonl \
    --split holdout --budget plugin --label full-0.17
.venv/bin/python ../eval/run.py run --brain SLUG --gold ../eval/out/gold.jsonl --hookset ../eval/out/hookset.jsonl \
    --split holdout --budget plugin --label clean-0.17 --corpus clean
.venv/bin/python ../eval/run.py compare ../eval/out/run-full-0.17-plugin-holdout.json ../eval/out/run-clean-0.17-plugin-holdout.json
```

R2 on the same clean corpus waits for #513. Step 2, the controlled rebuild, runs only if step 1 is ambiguous. Neither is here.

## 1. Which episodes are curated

The census labelled about 100 episodes blind (#514). `curated` extrapolates those labels to every episode of the brain, by
**cell**. A cell is the episode's census stratum (where it came from) combined with who let it in (`approved_by`: a person,
nobody, the decider, a category tier, a webhook's auto-approval).

| Rule | Default | Option |
|---|---|---|
| Clean labels | `note`, `event`: a self-contained note, or a dated record of a change (as the gate of #517 accepts) | `--clean-labels` |
| A cell is curated when its clean share is at least | 80 % | `--min-clean` |
| A cell is decided only with at least this many labelled episodes | 5 | `--min-labelled` |

- **A cell with fewer labels is never guessed.** Its episodes stay in the clean corpus, and the table marks it "too few labels" or
  "no labels" and warns about it. Label more of its episodes to decide it.
- **The table shows each cell's clean share with its 95 % Wilson interval,** so that 80 % from 4 of 5 is not read as certain.
- **The labels reach the episodes through the census key** (`keys.csv`). If the key gives an episode a different stratum than the
  one computed here, the census was sampled with another `--source-map`, and `curated` stops: pass the same one.

`curated.json` holds the rule, the table and the uuids of the episodes left out. It lives in `eval/out/`, which git ignores. Post
the table it prints in #491.

## 2. The filter

`run --corpus clean` (with `--curated`, by default `eval/out/clean/curated.json`) runs the same recall, with four of its
functions replaced in the eval's own process for the length of the run. Nothing in `api/` changes, and with `--corpus full` (the
default) nothing is replaced. The curated file records its brain, and `run` stops when it is given another one.

- **`search_facts` and `search_chunks`** ask for four times as many candidates, drop the facts and chunks that come only from
  episodes left out, and cut after that, so the recall's own cut is not left short. The facts are cut to as many as the unfiltered
  search gives: it removes repeated texts after its own limit, so with nothing left out both arms see exactly the same facts.
- **`superseded`** drops them from what stopped being true behind a fragment or a passage, and from what replaces it. So no "may
  be superseded" note, `replaces` mark or linked fact carries their text, and they take none of the places for linked facts.
- **`build_context`** also drops the facts that the recall adds through links and that no search returned.
- **A fact stays when any of its episodes is curated.** One with no episode (a document passage) stays too.
- **Lent graphs are not filtered.** `drop` holds only this brain's episodes. When the recall reads lent brains, the result names
  them (`meta.curated.not_filtered`) and `run` warns.
- **State cards are not filtered,** since they describe the current graph. Their characters are counted, because they weigh in the
  noise.
- **Latency is not comparable with a full run.** The filter runs the fact search twice and asks for four times as many chunks.
  The result says so (`meta.curated.latency`); compare the metrics, not the latency.
- **One known gap:** when a fact's text is repeated, the search keeps its first copy only. If that copy comes from an episode left
  out and a later one from a curated episode, the later copy is lost too.

The result's `meta.curated` records:
- the rule and the table;
- how many episodes were left out;
- how many questions had **every** answer episode left out;
- the items each step dropped, counted among what the unfiltered recall would have used (the first `n` of each search), not among
  the extra candidates.

Questions with every answer left out cannot be answered from the clean graph. Read the comparison with that count beside it.
