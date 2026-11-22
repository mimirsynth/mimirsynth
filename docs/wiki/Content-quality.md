**English** · [Español](Calidad-del-contenido)

# Content quality

Under **Curation** in the sidebar, for curators and above. It gathers the **quality work on what the graph already holds**: entities that are the same thing, facts that contradict each other, entities with a doubtful type and facts that need confirming again. It changes every day and curators do it.

The **framework** that makes this work appear (which relation is single-valued, how long each one lasts, which types exist) is in [[Vocabulary]], and administrators manage it.

## Summary
At the top, one card per tool with what is **waiting for a decision**: groups of possible duplicates, possible contradictions, doubtful types (administrators only), facts to review and proposed summaries. The counters are recalculated each time you open the page and after each change you make in it; the tab labels carry the same numbers.

A line below points to what stays elsewhere:
- **[[Facts]]**, to read and explore the memory (browse, search, timeline, entity page). A curator can also invalidate or reactivate facts there.
- **[[Ask]] → Quality** and **[[Reference queries]]**, which measure how well the recall answers. What they produce for a curator (corrections opened by an «incorrect» rating, reference queries that got worse) shows up under **To review** in [[Overview]].

## Tabs
| Tab | What it is for | Who decides |
|---|---|---|
| **Duplicates** ([[Merge duplicates]]) | Groups of entities with the same name except for capitalisation, spacing or a trailing version. Mark which to merge and which is the main one, or say they are not duplicates. The merge is undone from **Recent merges**. | Administrator (curators see the groups) |
| [[Contradictions]] | Current facts that cannot both be true: the same subject with two targets in a single-valued relation. Keep the one that is still true, or say it is not a contradiction. | Curator and above |
| **Doubtful types** ([[Type corrector]]) | Entities left without a type or with a catch-all one: the decider proposes a type from the ontology, and an administrator applies or discards it. Each change is undone on its own. | Administrator |
| **Summaries** | Entities whose summary is a list of their own facts: the engine proposes one to three sentences, and a curator edits it if needed and approves it. Each approval is undone from **Recent changes**. See below. | Curator and above (an administrator starts the analysis) |
| **Topics** | Topic reviews: the LLM reads everything the memory knows about one entity and proposes what to invalidate, merge, rewrite or add, each with its evidence. A curator approves or rejects each action. See below. | Curator and above (asked for from the [[Entity page]]) |
| **To review** | Current facts past their relation's shelf life. **Confirm** the ones still true (renews the date without touching the graph) or **invalidate** the others. | Curator and above |
| **Repeated aliases** | Merged names that only repeat the entity's own name (ignoring case and spacing) or another alias, left by older merges. The list says what goes and what stays, and writes nothing; **Clean** saves a copy of the graph first, then removes them as a background job. The change is in **Recent changes** and is undone from there or from **Earlier cleanups**; an entity that changed since the cleanup is left as it is. | Administrator |

Each tab starts by saying what it is for and what happens when you act, and each one links back to the place in [[Vocabulary]] where its switch lives: [[Ontology]] for single-valued relations and shelf lives, and **Aliases** for the relation aliases next to the merged entity names.

Readers and contributors do not see this entry in the sidebar; if they open its address, the page tells them it is for curators.

## Summaries
Many entities have **the list of their own facts as their summary**, because earlier ingestions appended the sentence of each new fact to it. The **Summaries** tab proposes a better one and a curator decides:
- **Analyse…** (a brain administrator) asks how many entities to review and looks at up to that number, the most connected first, whose summary is longer than 1,000 characters, has several lines, or only repeats its facts when it has more than one. A single short sentence with one fact is left alone. For each one the summary engine writes **one to three sentences** from the entity's current facts and the episodes that mention it; those texts are given to it as data, never as instructions. The proposed text goes through the brain's secret detector.
- **One entity, from its page:** on the [[Entity page]], when the summary is hidden or missing, a curator can choose **Propose a better summary** for that entity alone (one call, also for an entity with no summary); the proposal appears here, with the reason «asked for from its page».
- **Cost:** one call to the engine per entity, counted in [[AI consumption]] as **Summary review**. The analysis stops when the brain has spent its AI budget and is set to pause. The engine is **Engine for reviewing summaries** in the [[Settings reference]], or the default LLM engine.
- **Reviewing** (curators and above): each proposal shows the summary **now** and the **proposed** one side by side. The proposed text can be edited before approving it (**Approve with my changes**); who edited it is kept. **Approve all visible** applies the proposed texts as they are, with a filter by number of facts and by why the summary was picked; a proposal with something the secret detector flagged is left to approve one by one.
- **Approving replaces the entity's summary itself**, only if it is still the summary the proposal was written from; if it changed in between (for example, with an ingestion), the proposal is **withdrawn** and the next analysis looks at it again. Each approval goes to **Recent changes** in [[Entity types]] with the text before and after, and **Undo** (there or in the tab) puts the previous text back.
- An entity whose approved summary later gains many facts (at least five more, and twice as many) is proposed again; an approved text is never overwritten by itself.

## Topics
A **topic review** looks at one entity as a whole, which the other tabs, each about one kind of problem, do not: a provider that changed and left both the old and the new facts current, two facts that say the same thing, a fact worded badly, something the episodes say that no fact holds.
- **Asking for one:** on the [[Entity page]], under **Curation**, a curator chooses **Review this topic**. It runs as a background job, one per entity at a time, and the review opens when it finishes. It is refused when no LLM engine is configured, when the brain has spent its AI budget and pauses, and in a read-only brain.
- **What it reads:** the entity's current and earlier facts (up to 150, newest first), the episodes that mention it (up to 20, the first 800 characters of each), the current facts of the entities it is related to (up to 100) and the state of any probe on them ([[Verifiable facts]]). All of it goes to the engine as data, never as instructions.
- **Cost:** one call to the brain's default LLM engine, counted in [[AI consumption]] as the curator's. Two curator settings bound it: `topic_calls` (1 by default, up to 5) is how many calls one review may use when the topic does not fit in one, and `topic_max_tokens` (4,000 by default) the size of each reply. What does not fit is left out, and the review says how much.
- **What it proposes:** a short **state of the topic**, and actions, each citing the facts or episodes that support it: **Invalidate** (a fact a newer fact or episode contradicts), **Merge repeats** (keeps the most precise and invalidates the others), **Rewrite** (one fact, with a corrected sentence), **Drop as empty** (a fact with a placeholder or the memory itself at one end) and **Missing from the memory** (knowledge the episodes hold and no fact does). A reply that does not fit the expected format makes the review **fail**, and nothing of it is kept. An action that cites something it was not sent, cites nothing, acts on a fact that is not current or breaks its type's rule is discarded, and the review says how many and why. The brain's secret detector reads everything the engine wrote.
- **Deciding:** each action shows the facts it acts on and the evidence it cites; a fact struck through is no longer current. **Approve** turns it into a correction applied at once, with the review's reason and evidence, which keeps its audit and is undone from the correction with **Reactivate the fact**; a rewrite's correction carries the new text as its replacement, which is ingested. **Missing from the memory** becomes a free-text proposal in the [[Proposals]] queue instead. The text of a rewrite or of something missing can be edited before approving it. With two or more pending actions, each one is ticked and **Decide the ticked ones** approves the ticked ones, one by one and through the same path as their Approve button, and rejects the unticked ones with a note; one that cannot be applied says why and stays pending. A fact that stopped being current before the approval is left alone, and the action says so.
- **Precision by type:** the share of each kind of action that curators approved in this brain, shown next to the review. Nothing is approved on its own.

## Old links
`/vocabulario?tab=dup`, `?tab=conflicts`, `?tab=stale`, `?tab=corrector` and `/tipos` lead here, to the same tab.

## To review
The [[Overview]] shows curators a short block with the same counters, plus proposals and corrections waiting and reference queries that got worse, each line linking straight to the right tool. See «To review» in [[Overview]].
