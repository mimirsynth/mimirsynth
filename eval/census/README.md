# Corpus census (#514)

What the episodes and facts of a real brain actually are, measured before any v1 decision (#491, Phase 0). The script only reads.

## Where it runs

On the **frozen Phase 0 snapshot**, restored on an instance that is not production. It uses the same `MIMIRSYNTH_*` environment as
that instance, and runs from `api/` so that the app's settings and models load:

```bash
cd api
.venv/bin/python ../eval/census/census.py count  --brain SLUG    # census.md / census.json
.venv/bin/python ../eval/census/census.py sample --brain SLUG    # episodes.csv, facts.csv, keys.csv
# label the two sheets, then:
.venv/bin/python ../eval/census/census.py summarize              # labels.md
```

PostgreSQL is read in a `READ ONLY` transaction and the graph with `ro_query`, so the databases refuse any write. The script refuses
to run on anything but PostgreSQL: an unset `MIMIRSYNTH_DATABASE_URL` would otherwise open the development SQLite file.

## What the counts mean

- **Facts by state** follow the app (`db.fact_status`): `future` before their `valid_at`, `invalidated` from their `invalid_at` on,
  and `expired` when Graphiti expired them with no `invalid_at`.
- **Invalidations** are split three ways:
  - *through MimirSynth*: the fact's last change in the vocabulary history is an applied `fact.invalidate` (a correction, a claim, a
    contradiction resolved, or by hand); a later `fact.reactivate` takes it out;
  - *by Graphiti at creation*: expired within 15 minutes of being created, because the text dated it as past or it was older than a
    fact already there. That is history, not knowledge taken back;
  - *by Graphiti later*: the rest, invalidated by a newer fact. This is the number root cause 1 of #491 is about.
- **Cost** divides the `extraction` LLM calls by the proposals that reached extraction (ingested into an episode), since the day the
  counters start. Failed calls are shown apart.

## Output

Everything goes to `eval/census/out/`, which git ignores: the sheets and the keys hold the brain's own text. Only `census.md` and
`labels.md` (counts and percentages) are posted in #491.

| File | Holds | Share |
|---|---|---|
| `census.md`, `census.json` | counts and percentages | yes, in #491 |
| `episodes.csv`, `facts.csv` | the blind label sheets: text, dates and entity names only | no |
| `keys.csv` | each sheet row's episode or fact uuid and its stratum | no |
| `labels.md` | the share of each label per stratum | yes, in #491 |

## Strata

Each episode gets the stratum of the proposal that produced it (`stratum()` in the script):

| Stratum | How it is recognised |
|---|---|
| `person`, `agent` | `origin` of the proposal |
| `capture` | `origin=auto` and a source description `<agent> session` (plugin capture) |
| `auto` | `origin=auto` from anything else |
| `webhook` | a webhook's source description, or approved by a webhook |
| `document` | a document passage promoted to memory |
| `distil`, `forget-rewrite`, `machine` | written by the system: distil, forget, curator passes, verifier, topic-review gaps |
| `correction` | the replacement text of a correction |
| `no-proposal` | no proposal points to it: an adopted or imported graph |
| `unknown` | a proposal from before `origin` existed |

These strata come from metadata the client declares. The 100 labelled episodes are what defines "curated" in the end.

## Labelling

Open only `episodes.csv` and `facts.csv`; leave `keys.csv` closed until both are done. The rows are shuffled and the strata mixed.
The sheets leave out the episode's title, which names the system writer in several strata («Curador: …», «Corrección: …»).

- **Episodes**: `note` (a self-contained note), `dump` (a session dump), `event` (an event or alert), `meta` (a note about the
  memory itself).
- **Facts**: `true` (true and useful), `trivial` (trivial or a fragment), `stale` (no longer true), `wrong`.

Write the label in the `label` column, in any case. The sheets are UTF-8 with a BOM and open in a spreadsheet; `summarize` reads
them back saved as CSV with `,`, `;` or tab. A cell that would start with `=`, `+`, `-` or `@` starts with `'`, so it is never read
as a formula.

**The blinding is partial.** Some texts say where they came from: a session capture starts with "`<agent>` session in «project»",
and a promoted document passage names its source. Label what the text is, not where it seems to come from.

## Reading `labels.md`

Every stratum gets about the same number of rows, so a small stratum is measured as well as a large one. Two consequences:

- **The weighted row** gives each stratum its size in the brain. That is the brain's overall share; an unweighted total would not
  be.
- **Each row has a margin** (95 % Wilson interval at 50 %). With 10 strata, a stratum has about 10 rows and a share can be off by
  about ±28 points, so compare strata that differ by more than that, or label more rows (`sample --episodes 200`).

## Real prompts

`recall_logs` drops every log nobody rated after 48 hours and its query text after 30 days, so turning on `recall_query_text` does
not collect prompts. The replay sample (`recall_samples`, Ask → Recall quality, or `PUT /api/brains/{slug}/replay/settings`) keeps
each recall's query with secrets masked, its parameters and how it came. The census counts a sample made over HTTP with the hook's
parameters (`facts=6`, `chunks=3`) as the hook's.
