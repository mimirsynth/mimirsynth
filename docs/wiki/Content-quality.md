**English** · [Español](Calidad-del-contenido)

# Content quality

Under **Curation** in the sidebar, for curators and above. It gathers the **quality work on what the graph already holds**: entities that are the same thing, facts that contradict each other, entities with a doubtful type and facts that need confirming again. It changes every day and curators do it.

The **framework** that makes this work appear (which relation is single-valued, how long each one lasts, which types exist) is in [[Vocabulary]], and administrators manage it.

## Summary
At the top, one card per tool with what is **waiting for a decision**: groups of possible duplicates, possible contradictions, doubtful types (administrators only) and facts to review. The counters are recalculated each time you open the page and after each change you make in it; the tab labels carry the same numbers.

A line below points to what stays elsewhere:
- **[[Facts]]**, to read and explore the memory (browse, search, timeline, entity page). A curator can also invalidate or reactivate facts there.
- **[[Ask]] → Quality** and **[[Reference queries]]**, which measure how well the recall answers. What they produce for a curator (corrections opened by an «incorrect» rating, reference queries that got worse) shows up under **Needs your attention** in [[Overview]].

## Tabs
| Tab | What it is for | Who decides |
|---|---|---|
| **Duplicates** ([[Merge duplicates]]) | Groups of entities with the same name except for version or capitalisation. Mark which to merge and which is the main one, or say they are not duplicates. The merge is undone from **Recent merges**. | Administrator (curators see the groups) |
| [[Contradictions]] | Current facts that cannot both be true: the same subject with two targets in a single-valued relation. Keep the one that is still true, or say it is not a contradiction. | Curator and above |
| **Doubtful types** ([[Type corrector]]) | Entities left without a type or with a catch-all one: the decider proposes a type from the ontology, and an administrator applies or discards it. Each change is undone on its own. | Administrator |
| **To review** | Current facts past their relation's shelf life. **Confirm** the ones still true (renews the date without touching the graph) or **invalidate** the others. | Curator and above |

Each tab starts by saying what it is for and what happens when you act, and each one links back to the place in [[Vocabulary]] where its switch lives: [[Ontology]] for single-valued relations and shelf lives, and **Aliases** for the relation aliases next to the merged entity names.

Readers and contributors do not see this entry in the sidebar; if they open its address, the page tells them it is for curators.

## Old links
`/vocabulario?tab=dup`, `?tab=conflicts`, `?tab=stale`, `?tab=corrector` and `/tipos` lead here, to the same tab.

## Needs your attention
The [[Overview]] shows curators a short block with the same counters, plus proposals and corrections waiting and reference queries that got worse, each line linking straight to the right tool. See «Needs your attention» in [[Overview]].
