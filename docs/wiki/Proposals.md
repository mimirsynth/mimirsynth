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
3. **Review.** A curator opens the proposal and **approves** or **rejects** it. **+ Note** (or <kbd>N</kbd>) opens an optional note, and **What deciding does** unfolds what each button will do; what must be read before approving (a correction invalidates a fact, flagged secrets get masked) is always shown. After deciding, a notice says what happened and offers **Undo**. In **To review** it appears just above the note and the buttons of the next proposal, so nothing on the screen moves; elsewhere it appears above the list. A screen reader announces each step once (decided, entering the graph, the result), not the countdown. After an undo, the proposal opens again in the queue and the focus goes back to it:
   - **An approval waits 10 seconds** before ingestion, and can be undone in that time: the proposal goes back to *Pending* and nothing reaches the graph. Afterwards the notice follows the ingestion until it ends and says how many entities and facts were created (or that none was extracted). What is already in the graph is corrected by invalidating its facts, like the rest of the memory. Approvals by the decider and by webhooks do not wait.
   - **A rejection can be undone or reopened** at any time, unless its text was purged by the retention period.
4. **Ingestion.** An approved proposal is sent to the LLM, which extracts entities and facts and adds them to the graph (invalidating those it contradicts). It becomes *Ingested*. If it fails, it stays *Failed* and can be **retried**.

> The decider knows what the brain is about from its **description**: write one when creating or editing the brain (Administration → Brains, see [[Brains and members]]).

## The screen
It has two tabs:
- **To review** (curators; it opens by default) is the queue of what waits for a decision.
- **My proposals** has the form to propose and what you have sent, in every state.

A **contributor** only has the second one.

### To review
On the left, the **queue** of pending proposals; on the right, the open proposal with its detail and the **Reject** and **Approve** buttons always in view. On a narrow screen you see one at a time, with **Back to the queue**; on a phone the decision stays fixed at the bottom of the screen, within reach, and the shortcut hint is hidden on touch screens.

- **Ordered by risk and age:** corrections first, then the ones with a secret to review, then the ones the brain already knows (marked **Possible duplicate** when a current fact says nearly the same, or **Possibly outdated** when they resemble a fact that stopped being true), then those with a low declared confidence (below 0.6) and, inside each group, the oldest first. Each entry says who sent it and how long it has been waiting.
- **Keyboard shortcuts:** <kbd>J</kbd>/<kbd>K</kbd> go to the next or the previous one, <kbd>A</kbd> approves, <kbd>R</kbd> rejects, <kbd>X</kbd> marks it for a batch decision, <kbd>N</kbd> opens the note and <kbd>Z</kbd> undoes the last decision while the notice still offers it. They do nothing while you type in the note. After a decision the next one opens. On a narrow screen <kbd>A</kbd> and <kbd>R</kbd> act only while the proposal is open, never on one you have not seen. On a proposal with a secret to review, <kbd>A</kbd> opens the **Mask and approve** confirmation.
- **In batches:** check several (or **Select all**) and use **Approve the selected ones** or **Reject the selected ones**. A confirmation lists them by number and title, says how many of the selected ones it decides («Approve 2 of 3?») and takes a common note. Corrections, proposals with a secret to review and the ones the brain already knows **are not approved in a batch**: they stay selected, to decide one at a time. Only what you see in the queue goes into the batch.
- The **Show** selector switches between **Pending** and **Decided**, the history: approved, ingested, rejected and failed ones, in a table with filters. The **Kind** selector (*All*, *Add*, *Correct*) filters both views.

When corrections are waiting, a notice says how many, because each one invalidates a fact and only a person decides it. **Show only the pending corrections** filters the queue.

### The tables
**Decided** and **My proposals** show **#** (the proposal number), **Kind**, **Title**, **Author**, **Confidence**, **State**, **Submitted** and **Decided**: who decided it (a curator, the decider, a webhook, or its author on submission) and when. The kind is a marker with an icon and a word, **Adds** or **Corrects**, and a correction's marker is filled, so it stands out without relying on colour. You can filter by title and by author (**All authors**), sort by title, author, confidence, submission or decision date, and move through the pages with the pager below. Filters and sort order apply to **every proposal**, not only to the rows on screen, so old proposals are always reachable.

> A **reader** neither sees proposals nor can create them. A **contributor** sees only their own; a **curator** or higher sees all.

## Creating a proposal
In **My proposals**, the form (it can be folded away), with:
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
Before a proposal is stored (from the interface, the API or the `remember` tool over MCP), its title and content go through the **secret detector**: cloud and AI provider keys, tokens, private keys, JWTs, `Authorization` headers, passwords in URLs… Some findings are **certain**; a random-looking value assigned to `password`, `secret` or `token` is only **possible**. What happens depends on the brain's policy (Administration → Brain → **Secrets**):

| Policy | Certain secrets | Possible secrets |
|---|---|---|
| **Mask** (default) | Replaced with `[secret removed: type]` before storing | Flagged, left untouched |
| **Block** | The proposal is **rejected** with an error that names the type of secret | Flagged, left untouched |
| **Only warn** | Flagged, left untouched | Flagged, left untouched |

- **A flagged proposal always waits for a curator**, even when a curator sent it, and the decider does not approve it on its own.
- **It is never approved as written.** Its **Approve** button becomes **Mask and approve**. A confirmation names the types of secret; then every flagged value in the title and the text is replaced with `[secret removed: type]` and the proposal is approved. The original value is not kept, not even if you undo the approval. The audit log records which types were masked (`proposal.secrets_masked`), never the values. Over the API it is `POST /proposals/{id}/mask-and-approve`; `POST /proposals/{id}/approve` answers 409 for such a proposal.
- **With Mask, a curator's proposal is stored already masked and approved at once:** nothing is left for anyone to review, because the value never reached the memory.
- **The author is told when submitting:** the form says which types of secret were masked or flagged, the `POST /proposals` response carries the same text in `secrets_notice`, and the `remember` result adds it, so an agent knows its text was altered.
- Afterwards, the list marks those proposals (**Secret masked** or **Secret to review**, also the ones approved at once) and the detail shows **Secrets detected**: what was masked and what was flagged for review. The value itself is never shown, stored in the audit log or sent in notifications.
- Keep secrets in a password manager and store in memory only **where** they are.

## A proposal's detail
When you open it you see a **timeline**:
- **Submitted:** who and when, the declared confidence and the **source** (where the author says it comes from, and the format it arrived in).
- **What the brain already knows** (on pending proposals that add knowledge): the facts closest to the proposal's text, with their entities linked and their dates, to see whether it repeats or contradicts something. A first line says what to look at: **Possible duplicate** when the brain already says nearly the same, a warning when it resembles something that stopped being true, or only related facts. Each fact is marked **Nearly the same** (most of its words are already in the proposal, or the embeddings are almost identical) or **Very similar**, the closest first; a fact that is no longer true is struck through. The three closest are shown, the rest behind **Show N more**. A contradiction cannot be told from the text alone: the closest facts are there to check it. When nothing is similar it says so: it would be new knowledge. The brain checks this in the background as soon as a proposal arrives (when there is an extraction engine), and again whenever its detail is opened, so the queue can rank and mark it. Approving a possible duplicate, or something that resembles a fact no longer true, asks for a confirmation that quotes that fact, with the button and with <kbd>A</kbd>. This lookup does not count towards recall quality.
- **Review:** whether it was approved on submission, approved by a curator (with their note) or decided by the decider. If it was the decider, it shows which model, the threshold, its two answers with their confidence and the verdict (**Approved automatically** or **Referred to a curator**). If the decider was unavailable, the error is shown.
- **Ingestion into the graph:** the id of the created episode, the date, and a **report**: how many entities and facts were created, how many entities ended up *untyped*, which types fell outside the ontology, which entities were merged into their primary, which were not merged because the match was ambiguous, and how many relations were normalised by an alias.

## Curator actions
- **Approve / Reject** (with an optional note).
- **Reopen** a rejected one, or **Undo the approval** of an approved one whose ingestion has not started yet.
- **Ingest now** or **Retry ingestion** when an approved one has not been ingested or failed.
- **Reactivate the fact** in an applied correction.

## Notices you may see
- **"No LLM engine configured":** approved proposals are not ingested and stay in "Approved". An administrator must configure it in [[AI providers]].
- **"No decider":** all contributors' proposals wait for a curator.
- **Ingestion failed:** see the reason in the detail and in [[Jobs]]. The most common errors are a provider rate limit or a model that does not return valid JSON ("reasoning" models sometimes need a proxy that disables *thinking*).

## From an agent
Agents create proposals through the REST API or the `remember` tool of the MCP server, and corrections with the `correct` tool: [[Connect agents]]. From a document, the **Promote to memory** button in [[Knowledge]] creates a proposal with the passage and its provenance.
