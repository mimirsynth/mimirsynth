**English** · [Español](Propuestas)

# Proposals

The **contribution quarantine**. It is the only way new memory enters the graph: what a contributor (or an agent with a contributor token) sends **is not incorporated until someone approves it**. That way an agent that makes a mistake, or a doubtful text, does not pollute the memory.

## Flow
```
Submitted ──► (optional decider) ──► Pending ──► Approved ──► Ingested
                                        │              │
                                        └► Rejected    └► Failed ──► (retry)
```
1. **Submit.** A contributor ends up *Pending*. A curator (or higher) ends up *Approved* directly ("approved on submission"), unless the secret detector flagged something (see below).
2. **Decider (optional).** If a decider model is configured, it evaluates the proposal against the **brain's scope**: its description and the entity and relation types of its [[Ontology]]. Without either, it only checks that the proposal is factual. It answers two questions (is it factual? what action does it recommend?) and, if both exceed the **confidence threshold**, it approves the proposal by itself. If not, it leaves it for a curator. **It never rejects on its own**: what does not fit goes to a curator.
3. **Review.** A curator opens the proposal and **approves** or **rejects** it (with an optional note).
4. **Ingestion.** An approved proposal is sent to the LLM, which extracts entities and facts and adds them to the graph (invalidating those it contradicts). It becomes *Ingested*. If it fails, it stays *Failed* and can be **retried**.

> The decider knows what the brain is about from its **description**: write one when creating or editing the brain (Administration → Brains, see [[Brains and members]]).

## The list
At the top, the **State** selector with a counter per state: *All*, *Pending*, *Approved*, *Rejected*, *Failed*, *Ingested*. It opens on *Pending* when there are pending proposals, and on *All* otherwise. Next to it, the **Kind** selector: *All*, *Add* (proposals that add knowledge) and *Correct* ([corrections](#corrections), which invalidate a fact). The state counters follow the chosen kind.

When corrections are waiting, a notice above the list says how many, because each one invalidates a fact and only a person decides it. **Show only the pending corrections** sets both selectors at once.

The table shows **#** (the proposal number), **Kind**, **Title**, **Author**, **Confidence**, **State** and **Submitted**. The kind is a marker with an icon and a word, **Adds** or **Corrects**, and a correction's marker is filled, so it stands out without relying on colour; the detail repeats it next to the number. You can filter by title and by author (**All authors**), sort by title, author, confidence or date, and move through the pages with the pager below. Filters and sort order apply to **every proposal**, not only to the rows on screen, so old proposals are always reachable.

> A **reader** neither sees proposals nor can create them. A **contributor** sees only their own; a **curator** or higher sees all.

## Creating a proposal
The form above the list, with:
- **Title:** short and descriptive ("Database migration to PostgreSQL 17").
- **Content:** *what happened or what needs remembering, with exact dates and names*.
- **Confidence (0–1, optional):** how much you trust that data. It is shown to the reviewer.

The button is **Propose** for a contributor and **Add** for a curator (it is approved on submission). Writing tips: [[Writing good memory]].

## Corrections
A **correction** is a proposal that does not add memory: it asks to **invalidate one fact** that is no longer true. Agents send it with the MCP tool `correct` or `POST /proposals/corrections`, pointing to the fact by its uuid (the one `facts_about`, `timeline` and `whats_new` give), with the reason and, optionally, the text that replaces it and the date it stopped being true.
- Its title starts with "Correction:" and its detail shows the **fact to invalidate** (subject → relation → target, since when it was current and its uuid), the **reason** and **what replaces it**.
- The decider **never** approves a correction, and over MCP it always waits for a person, even with a curator token. Through the REST API, a curator who sends one applies it at once.
- On approval the fact is **invalidated, never deleted**, as of the correction date; the step **Fact invalidated** shows it. If there is a replacement, it is ingested like any memory, with that date. The invalidation also goes to the vocabulary history, like those made from [[Facts]] or [[Contradictions]].
- If the fact stopped being current while the correction waited, approving it gives an error and the correction stays pending: reject it.
- **Reactivate the fact** in the correction puts the fact back as it was. An ingested replacement is left as it is.

## Secrets in proposals
Before a proposal is stored (from the interface, the API or the `remember` tool over MCP), its title and content go through the **secret detector**: cloud and AI provider keys, tokens, private keys, JWTs, `Authorization` headers, passwords in URLs… Some findings are **certain**; a random-looking value assigned to `password`, `secret` or `token` is only **possible**. What happens depends on the brain's policy (Administration → Brain access → **Secrets**):

| Policy | Certain secrets | Possible secrets |
|---|---|---|
| **Mask** (default) | Replaced with `[secret removed: type]` before storing | Flagged, left untouched |
| **Block** | The proposal is **rejected** with an error that names the type of secret | Flagged, left untouched |
| **Only warn** | Flagged, left untouched | Flagged, left untouched |

- **A flagged proposal always waits for a curator**, even when a curator sent it, and the decider does not approve it on its own.
- **With Mask, a curator's proposal is stored already masked and approved at once:** nothing is left for anyone to review, because the value never reached the memory.
- **The author is told when submitting:** the form says which types of secret were masked or flagged, the `POST /proposals` response carries the same text in `secrets_notice`, and the `remember` result adds it, so an agent knows its text was altered.
- Afterwards, the list marks those proposals (**Secret masked** or **Secret to review**, also the ones approved at once) and the detail shows **Secrets detected**: what was masked and what was flagged for review. The value itself is never shown, stored in the audit log or sent in notifications.
- Keep secrets in a password manager and store in memory only **where** they are.

## A proposal's detail
When you open it you see a **timeline**:
- **Submitted:** who and when, and the declared confidence.
- **Review:** whether it was approved on submission, approved by a curator (with their note) or decided by the decider. If it was the decider, it shows which model, the threshold, its two answers with their confidence and the verdict (**Approved automatically** or **Referred to a curator**). If the decider was unavailable, the error is shown.
- **Ingestion into the graph:** the id of the created episode, the date, and a **report**: how many entities and facts were created, how many entities ended up *untyped*, which types fell outside the ontology, which entities were merged into their primary, which were not merged because the match was ambiguous, and how many relations were normalised by an alias.

## Curator actions
- **Approve / Reject** (with an optional note).
- **Ingest now** or **Retry ingestion** when an approved one has not been ingested or failed.
- **Reactivate the fact** in an applied correction.

## Notices you may see
- **"No LLM engine configured":** approved proposals are not ingested and stay in "Approved". An administrator must configure it in [[AI providers]].
- **"No decider":** all contributors' proposals wait for a curator.
- **Ingestion failed:** see the reason in the detail and in [[Jobs]]. The most common errors are a provider rate limit or a model that does not return valid JSON ("reasoning" models sometimes need a proxy that disables *thinking*).

## From an agent
Agents create proposals through the REST API or the `remember` tool of the MCP server, and corrections with the `correct` tool: [[Connect agents]]. From a document, the **Promote to memory** button in [[Knowledge]] creates a proposal with the passage and its provenance.
