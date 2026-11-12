**English** · [Español](Página-de-entidad)

# Entity page

Everything the brain knows about **one entity** (a service, a host, a person…) and **how it changed**, on one page. It answers "what do we know about X, and since when?", which is what a bitemporal memory is for.

## How to get there
- From [[Facts]]: click the source or target entity of a fact.
- From the [[Graph]]: select a node and click **View page** in the side panel.
- From the [[Cypher|Cypher query]] tab of the [[Graph]]: an entity in the result table is a link, and a selected node on the canvas has **View page**.
- From [[Ask]]: click an entity of a returned fact. A lent fact opens its entity in the brain that lends it.
- From the entity page itself: every related entity is a link.

## What it shows
- **The top card:** on the left, the name, its type as the same coloured chip used in the facts (for curators, a small pencil next to it opens «Change type») and the names merged into it as small chips (a merged name equal to the entity's own name, apart from case or spacing, is never shown), and the entity's **Summary** below them (cut after a few lines, with **Show more**). A summary is not shown when at least half of its lines are the sentences of the entity's own facts, which happens often because the extractor writes the summary as a list of them: the facts below already say it. **When there is no summary to read** (hidden, or the entity has none), that space shows the entity's **key figures** instead: the description of its type in the [[Ontology]], its current and earlier facts and the episodes that mention it, the first and last date of its facts, and its related entities counted by type, as type chips. A line says why there is no summary, and curators get **Propose a better summary** (or **Propose a summary**): one call to the summary engine for this entity alone, which opens the proposal in [[Content quality]] → Summaries to edit and approve it (a pending proposal for the entity is opened as it is, without a new call). On the right, the small graph described under **Related**. On a phone the card is one column: the name, the graph, then the summary. **← Facts** above it goes back, **Facts** is the section marked in the side bar, and **As it was on** stays at the top right.
- **Facts grouped by relation**, under the heading **Facts** with how many are current and how many earlier. Each group is one piece of data read as an **evolution**, oldest first. When the relation is single-valued, or it has at most three values in all, a line under the heading chains them: "HOSTED_ON → Eridani → Polaris → Notus". A relation with many values at once (such as «participates in») has no chain, because each value did not replace the one before; its earlier facts stay under **Show earlier (N)**. The current value is shown with its dates; the earlier ones are folded under **Show earlier (N)** and appear struck through, with the period in which they were true. Each group's heading reads as a sentence in the same order for both directions, with the entity of the page on its side: «Lyra → hosted on → Hetzner» for a fact the entity is the subject of, «Arcane → hosted on → Lyra» for one pointing to it. The relation is written in words (`HOSTED_ON` reads «hosted on»; the raw name shows on hover), the current values are links (the first three, and how many more), and «—» means there is no current value. Groups with a possible contradiction come first, then those with most current values.
- **Other relations:** generic relations such as `RELATES_TO`, which the extractor writes when no type fits, link anything, so their «evolution» says little. They are folded into one section at the end, with the number of facts; **Show** opens it.
- **Two dates per fact:** since when it is true (*current since*, *valid … → …*) and when the brain **learned** it. They are different axes: a fact learned today can be true since last year.
- **Related:** the graph in the top card, with the entity and the 12 entities it shares most current facts with, one edge per neighbour with its most frequent relation (×N when several facts join them; dashed when none is current). So that labels never overlap, only the three strongest edges show theirs; pointing at a neighbour shows its name and all its relations. A click on a neighbour opens its page; on a phone the first tap names it and the second opens it. «and N more» says how many are left out, and **Expand** opens the [[Graph]] with the entity selected. The same neighbours are also there as links for the keyboard and screen readers.
- **Facts and episodes side by side:** the facts take the left, about 70 %, and the right column lists the **episodes that mention it**, the most recent ones, linking to the episode in the [[Journal]]. Episodes and documents use the same list as the facts, with the same type size, and their date as the second line. On a phone the episodes come after the facts.
- **Entities as chips coloured by their type:** wherever an entity is named (the relation headings, the fact cards), it is the same chip, with a dot and an edge of its type's colour and its type as the tooltip. Each type has **one colour on every screen**: the chips, this graph, the [[Graph]] and [[Cypher query]] use the same mapping. The entity of the page is plain, not a link.
- **Documents that mention it:** passages from [[Knowledge]], when there are any. They come from a separate call (`GET /docs/mentions?entity=`), not from the entity endpoint, and are not shown for a lent entity.

## As it was on a day
**As it was on** picks a date: the page then shows what was **current that day**, by validity dates, as the [[Graph]]'s time travel does. Facts that were not yet true are left out (the page says how many). **Today** goes back to the present. While you look at a past day, the curator actions are hidden.

## Possible contradictions
If a relation is marked as **single-valued** in the [[Ontology]] and the entity has two different current values for it, the group says so and links to [[Contradictions]], where it can be resolved. The page shows the case rather than hiding it.

## Curator actions
- **Invalidate** a current fact, or **Reactivate** an earlier one, with the small button next to the fact. They are the same actions as in [[Facts]] and can be undone from the vocabulary history.
- **Change type**: the pencil next to the entity's type in the header, for curators: pick one of the types of the brain's [[Ontology]] (the same closed list the [[Type corrector]] uses; nothing else is accepted). The change is seen at once here and in the [[Graph]], goes to the audit log, and can be undone from the message that confirms it or from **Recent changes** in [[Entity types]]. If the type corrector had a suggestion pending for this entity, it is no longer offered, and a later analysis does not propose the entity again.
- Links to **merge** the entity with another ([[Merge duplicates]]), review the **doubtful types** of the whole brain ([[Type corrector]], administrators) and **edit the text** of a fact ([[Facts]]).

## Lent entities
With [[Federation]], an entity of a brain that lends its graph opens with its origin ("from «slug»") and is **read-only**.

## Accessibility
Each relation's evolution is an ordered list, not a chart, so a screen reader reads it in order, and every entity, episode and action is reachable with the keyboard.
