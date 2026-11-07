**English** · [Español](Curador)

# Curator

The **curator** goes over a brain's graph once a day and turns what it finds into **proposals in quarantine**, each with its evidence. It changes nothing on its own: a curator decides each proposal in [[Proposals]], one at a time, and every change is in the vocabulary history and can be undone. It is in [[Content quality]] → **Curator**.

## What it looks for
For now, **clear contradictions** in the relations marked functional (a single value at a time, see [[Contradictions]]): a subject with two current values where one has a strictly newer validity date, every date is a validity date, and the relation does not look multi-valued. The proposal keeps the newest value and invalidates the others, as of the newest one's date. It leaves out:
- groups a curator marked «not a contradiction»;
- unclear groups, which stay in Content quality → Contradictions for a person;
- facts that already have a pending proposal.

And, once an administrator ticks it (it is off by default), **repeated facts**: current facts between the same two entities that say the same thing. That means the same text, or very close embeddings with the same numbers and identifiers, as [[Memory health]] counts redundancy: «PostgreSQL 14» and «PostgreSQL 16» are a change, not a repeat. The proposal keeps the newest one and invalidates the others. Up to 3,000 candidate facts are read per run, the most recent first.

Each pass has its own checkbox and its own precision. Noise and outdated facts come next ([#300](https://github.com/mimirsynth/mimirsynth/issues/300)).

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
