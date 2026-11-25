# Offline write path (#517)

Two candidate write-path prompts, measured on labelled data from the frozen Phase 0 snapshot, for the P1 / P0 row of the decision
table in #491. Nothing is ingested and the brain does not change. The code is throwaway: it measures the prompts, it is not how v1
will call them.

| File | |
|---|---|
| `prompts.py` | the two prompts, each with a version that every result records |
| `write_path.py` | the runner: `gate`, `replaces` and `report` |

Run it from `api/`, on the instance where the snapshot was restored, with its `MIMIRSYNTH_*` environment and
`MIMIRSYNTH_EVAL_SNAPSHOT=1`. Results go to `eval/out/write_path/`, which git ignores: they hold the brain's uuids and what the
engine said about its notes. Only the tables that `report` prints are posted in #491. The engine's calls are made at temperature
0. They and the embedding calls are counted in the snapshot's `ai_usage` for the instance (brain 0), under the purpose `eval`, and
the counters are written before the command exits. They are not counted for the brain: its monthly AI budget would include them,
and reaching it sends an alert through the channels the snapshot copied from production.

## Gate prompt

```bash
.venv/bin/python ../eval/experiments/write_path/write_path.py gate --sheet ../eval/census/out/episodes.csv
```

One call per note, over the episodes the census labelled blind (#514): `note`, `dump`, `event` or `meta`. The engine reads the text
of the sheet, as the person labelling read it, and gives one of the same four kinds. A `note` is accepted; the other three are
rejected or flagged.

| Metric | Definition |
|---|---|
| `precision_reject` | of the notes the gate rejected or flagged, the share that are not self-contained notes. **The P1 metric** |
| `recall_reject` | of the notes that are not self-contained, the share the gate rejected or flagged |
| `precision_<kind>`, `recall_<kind>` | the same for `dump`, `event` and `meta` one by one |
| `accept_note` | of the self-contained notes, the share the gate let through |

Unlabelled rows and labels outside the four kinds are left out and counted. A failed call or an answer with no kind is recorded
with its error and left out of the metrics.

## `replaces` proposal

```bash
.venv/bin/python ../eval/experiments/write_path/write_path.py replaces --brain SLUG --gold ../eval/out/gold.jsonl
```

For every validated temporal question of the gold set (#492), the pair of notes it records:
- **the old notes** are the episodes in its `stale`, and the episodes of the facts in its `stale`, less its answer episodes;
- **the new note** is the answer episode that brought the change: the earliest one written after every old note, or the most
  recent answer episode when none is.

Left out, and counted:
- a question whose new note has no date;
- the old notes that are undated or dated after the new note, since the search could never show them; a question with none left
  is left out;
- a second question about the same pair.

For the new note, the app's own embedding and episode index give the most similar notes of the brain. The new note itself and the
notes written after it (or with no date) are left out, since they did not exist yet when it came in. Other answer episodes stay:
an older note that agrees with the new one is a fair distractor. The first `--k` (8) go to one call, which proposes which of them
the new note replaces, and whether only partly. With no candidate left, no call is made.

| Metric | Definition |
|---|---|
| `hit` | a true old note was proposed. **P1** |
| `false` | of the notes proposed, the share that are not a true old note. **P1**. An upper bound: a proposed note may be another one the new note really replaces, which the gold set does not record. The proposals are in the result file, to read |
| `partial_ok` | of the true old notes proposed, the share whose "only partly" matches the snapshot. An old note is replaced only partly when some of its facts, other than the `stale` ones, are still current |
| `retrieved` | a true old note was among the candidates at all. It tells a search miss from an engine miss |

`--split holdout` runs only the holdout questions of `eval/out/split.json`. Run that if the prompt is changed after looking at
results. `--include-drafts` adds the questions not yet validated.

## Cost and report

`--price-in` and `--price-out` (per million tokens) add the price per note to the tokens per note that both commands report. The
cost is over the notes for which a call was made, and the `replaces` cost leaves out the embedding call, which is cheap and local.

```bash
.venv/bin/python ../eval/experiments/write_path/write_path.py report
```

`report` prints both tables, each rate with a 95 % interval: the wider of the bootstrap over the notes (2,000 resamples, fixed
seed, as in #492) and the Wilson interval of the pooled count. The bootstrap alone shrinks to a point when every note agrees, and
would read 5 of 5 as certain. Then it reads #491's row:
- **P1:** `precision_reject` ≥ 0.8, `hit` ≥ 0.7 and `false` ≤ 0.1, each with its whole interval on its side;
- **P0:** anything else. An interval that crosses its threshold counts as not met. The report names the weaker part: the gate, the
  proposal or both. That part stays a suggestion in the inbox, or is dropped.

## Not covered

- Notes that replace nothing. Every pair here is a note that does replace something, so `false` measures proposals beside a true
  one, not proposals for a note that should get none.
- The gate on facts. It reads the episode labels only, not the fact labels of the census.
- The brain's own mix of kinds. The census labels about the same number of episodes per stratum, so `precision_reject` is the
  precision on that sample, not weighted back to the brain. Precision depends on how common each kind is.
