**English** · [Español](Trabajos)

# Jobs

The **job queue**: everything the application does **in the background** for the active brain. It is used to see whether something is slow, failing or waiting, and to retry or cancel. Anyone with access to the brain (reader or above) can see it.

## What a job is
Any task that takes long enough not to be done in the request itself. The **Type** filter uses these names:

| Type | What it does | Launched by |
|---|---|---|
| **Ingestion into the graph** | The LLM extracts entities and facts from an approved proposal | Approving a proposal |
| **Index document** | Chunks a document and computes its embeddings | Uploading or reindexing a document, or a scan that finds changes |
| **Sync source** | Scans a folder or syncs a wiki | A person, or the source's scheduled rescan |
| **Type corrector** | Analyses entities whose type is missing or does not fit the ontology | A brain administrator, from Vocabulary ([[Type corrector]]) |
| **Find duplicate documents** | Checks the documents already indexed and takes the repeated ones out of the index; nothing is deleted at the source | A brain administrator, with **Find duplicates** in [[Knowledge]] |
| **Reference queries** | Runs the brain's reference queries, or simulates them with other similarity thresholds | A curator, from Ask; also on its own before and after an embedding model change |
| **Find contradictions between facts** | Daily check of the single-valued relations; raises an alert if it finds possible contradictions | The system, in brains that have marked some relation as single-valued |

The **embedding model change** (*Embedding model change (shadow fill)* and *(swap)*) also runs as jobs, but it covers every brain at once: its progress, Cancel, Retry and Discard are in Administration → Embeddings, not on this screen ([[AI providers]]).

## The list
Each job shows its **type**, **title**, **state**, **progress** (done / total, with a bar), who launched it (or "system" if automatic) and the dates.

| State | Meaning |
|---|---|
| Queued | Waiting its turn |
| Running | Executing, with its progress |
| Finished | Ended well |
| Failed | Ended with an error (the reason is visible) |
| Cancelled | You stopped it |

Filters: **State** (with counters), **Type** and a search by title. Each column can be sorted and filtered.

## Grouped rescans
Scheduled folder rescans repeat endlessly and almost never find anything. To avoid filling the list with noise, **consecutive, identical** runs that ended well and were launched by the system are **folded into a single row**: "Scheduled folder scan · 20 consecutive runs with no issues", with the date range. Press **Show N** to expand them and **Hide** to fold them. Failed jobs, retries and anything launched by a person are **always shown separately**.

## A job's detail
Opening it shows a panel with:
- Creation, start and end dates, and **duration**.
- Who launched it and, if it is a retry, of which.
- The **parameters** it was launched with.
- The step-by-step **log** with the time of each line.
- The **error** if it failed.

## Actions
- **Cancel:** stops a queued or running job (it stops at the next safe point).
- **Retry:** launches a new job with the same parameters. It appears as "retry of #N".

You need the **curator** role (or higher) in the brain to cancel or retry.

## Retention
To avoid filling the database:
- Finished scheduled rescans **with no issues** are deleted after **7 days**.
- The rest of finished, failed and cancelled jobs are kept for **60 days**.
Purging runs on start and every hour. Both periods are changed in [[Recall and ingestion]].

## If something gets stuck
- A job "Running" for a long time is usually waiting on the LLM (provider rate limit): it retries by itself several times before failing. Check [[AI providers]].
- If the service restarts with jobs half-done, on start they are marked **failed ("interrupted by a service restart")** and the resumable ones (indexing a document, syncing a source and the embedding shadow fill) are relaunched automatically; the others you can retry by hand.
- A failed job raises an alert in the bell and, if configured, in the notification channels.
- Many failures in a row with the same error: look at the job's log and at [[Troubleshooting]].
