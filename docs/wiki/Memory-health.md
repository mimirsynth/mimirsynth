**English** · [Español](Salud-de-la-memoria)

# Memory health

A memory that only accumulates becomes a log of everything that was ever said, not of what is true now. **Memory health** is a handful of numbers per brain, measured **once a day** and kept as a time series, that say whether the memory is getting better or worse: a release, a new embedding model or a change of threshold that degrades the recall shows here before an agent answers with a stale fact.

## Where to see it
- In the [[Overview]], under **Memory health**, for **curators and above**: the last measurement and, under each number, the one of a week before. **Measure now** measures again; that day's numbers are replaced when it finishes.
- In the API: `GET /api/brains/{slug}/health?days=90` (the runs of the last days, the oldest first, and the last finished one) and `POST /api/brains/{slug}/health/run`.
- In Prometheus, one gauge per number and brain (see [[Metrics]]), to chart it over time or alert on it.

## The numbers
| Number | What it is | Better |
|---|---|---|
| **Coverage** | Share of the expected texts of the brain's [[Reference queries]] that the recall finds, counted as a run counts them. Empty without reference queries that expect something. | Higher |
| **Results with something outdated** | Share of the reference queries whose recall brings something marked as possibly outdated: a current fact past its relation's shelf life, or an episode fragment or a document passage that states something no longer true. A fact no longer true that the recall shows as history does not count: it is labelled as such. | Lower |
| **Noise** | Mean items (facts, fragments and passages) the recall returns for a vague or off-topic question: a built-in set (a greeting, a single word, «ok, go on with what we were doing», in English and Spanish) plus the reference queries that expect nothing. The share that returned nothing and the size of the context are in the API. | 0 |
| **Redundancy** | Share of current facts that repeat another current fact **between the same two entities**: the same text, or very close embeddings (cosine 0.93 or more) **with the same numbers and identifiers**. «The wiki uses PostgreSQL 14» and «… 16» are a change, not a repeat. With more than 3,000 candidate facts, it is estimated on the most recent ones and says so. | Lower |
| **Open contradictions** | Possible contradictions in the functional relations, as [[Contradictions]] counts them. Empty if no relation is functional. | Lower |
| **Facts to review** | Current facts past their relation's shelf life, as [[Content quality]] → To review counts them. Empty if no relation has a shelf life. | Lower |

## How it is measured
- **Once a day** per brain, shortly after midnight UTC. The day is the measurement's key in the database: a restart never measures twice and never skips a day; a measurement cut by a restart is started again.
- It runs as a job ([[Jobs]], «Measure the memory health»), one brain at a time.
- Coverage, staleness and noise come from **recalls**, one embedding each (the reference queries plus eight vague questions). They are not logged for the recall ratings. A brain that has reached its [[AI consumption]] budget is not probed that day; the other numbers are still measured.
- Each number is measured on its own: one that fails is left empty and named under the numbers, and the rest is kept.
- Nothing is written to the graph.
- Measurements are kept for 400 days.

## Reading it
- **Coverage drops** after an update or a model change: run the [[Reference queries]] to see which expected texts stopped coming, and simulate a threshold.
- **Outdated results grow**: review [[Content quality]] → To review and the contradictions; facts that stopped being true are better invalidated (or corrected) than left current.
- **Noise above 0**: the recall's minimum similarity may be too low for your embedding model ([[Recall and ingestion]]).
- **Redundancy grows**: agents are writing the same lesson in different words; see [[Writing good memory]].
