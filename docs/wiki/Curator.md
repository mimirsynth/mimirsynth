**English** · [Español](Curador)

# Curator

The **curator** goes over a brain's graph once a day and turns what it finds into **proposals in quarantine**, each with its evidence. It changes nothing on its own: a curator decides each proposal in [[Proposals]], one at a time, and every change is in the vocabulary history and can be undone. It is in [[Content quality]] → **Curator**.

## What it looks for
For now, **clear contradictions** in the relations marked functional (a single value at a time, see [[Contradictions]]): a subject with two current values where one has a strictly newer validity date, every date is a validity date, and the relation does not look multi-valued. The proposal keeps the newest value and invalidates the others, as of the newest one's date. It leaves out:
- groups a curator marked «not a contradiction»;
- unclear groups, which stay in Content quality → Contradictions for a person;
- facts that already have a pending proposal.

And, once an administrator ticks it (it is off by default), **repeated facts**: current facts between the same two entities that say the same thing. That means the same text, or very close embeddings with the same numbers and identifiers, as [[Memory health]] counts redundancy: «PostgreSQL 14» and «PostgreSQL 16» are a change, not a repeat. The proposal keeps the newest one and invalidates the others. Up to 3,000 candidate facts are read per run, the most recent first.

And, also off by default, **facts past their shelf life**: the current facts that Content quality → To review lists (relations with a shelf life, not confirmed in time), the longest overdue first. Each one becomes a proposal to invalidate it. Rejecting the proposal, or confirming the fact in To review, keeps it.

And, also off by default, **noise**: current facts that say nothing useful, by four deliberately conservative rules.
- One end is a placeholder, not a thing of the world («it», «esto», «something»…).
- One end is the memory itself («the graph», «la memoria», «episode», «fact»…). Names that can be real things, such as «node» (Node.js), «memory» (RAM) or «edge», do not count.
- A generic relation (`RELATES_TO`, `MENTIONS`…) whose text adds nothing beyond its two entities.
- A change told as an event («X was moved to Y») when another current fact between the same entities already states the result. If it is the only trace of the change, it is kept.

And, also off by default, **facts never recalled**: current facts that no recall brought in the last 180 days (`archive_days`, adjustable through the API), learned before that, never confirmed by a person or a probe. Approving one **archives** it: it stays in the graph untouched, but the recall leaves it out unless asked (`archived: true` in `POST /recall` or the MCP `recall`). The **Archived** list in this tab restores any of them with one click. Every logged recall notes when its facts came back, and this pass only proposes once the brain has been tracked for the whole period; before that, every old fact would look unused.

Each pass has its own checkbox and its own precision, which says how far to trust it.

## It stops if coverage falls
Before proposing anything, the curator looks at [[Memory health]]. If the reference queries' coverage fell more than *Memory health: notify when coverage falls* since the previous measurement, and some of its proposals were approved in between, it proposes nothing that day. The run ends **stopped**, with the numbers, and the **curator.stopped** notification says so.

## Turning it on
It is **off by default**. A brain administrator ticks **Turn on the curator in this brain**. From then on it runs once a day (the day is the run's key: a restart never runs it twice), and **Run now** runs it at once. **See what it would propose** shows it without creating anything.

## A sample before a batch
If a run would propose **more than 5 changes** at once (the batch, adjustable through the API), it proposes nothing. Instead it waits with a sample of what it would change and what it keeps. When a service is decommissioned, dozens of facts can go at once, and only a person tells «still useful» from «now stale». **Create the proposals** creates them all, and each one is still decided on its own; **Discard** drops the run.

## Deciding its proposals
Its proposals have no text, only claims: subject, relation, the value kept and the fact each one replaces (see [[Proposals]] → Structured claims). Like a correction, they are decided one at a time: neither the decider nor a batch approval approves them. Approving one invalidates the old fact once the 10-second undo grace has passed, without an LLM. Rejecting one leaves everything as it was.

## Precision
The tab says how many of its proposals curators approved and rejected so far. That is the measure for trusting it more later ([#299](https://github.com/mimirsynth/mimirsynth/issues/299)).

## API
`GET/PUT /api/brains/{slug}/curator/settings` (`enabled`, `passes`, `batch`; changing them needs a brain administrator), `POST …/curator/preview`, `POST …/curator/run`, `GET …/curator/runs`, `POST …/curator/runs/{id}/confirm` and `…/discard`.
