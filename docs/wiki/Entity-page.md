**English** · [Español](Página-de-entidad)

# Entity page

Everything the brain knows about **one entity** (a service, a host, a person…) and **how it changed**, on one page. It answers "what do we know about X, and since when?", which is what a bitemporal memory is for.

## How to get there
- From [[Facts]]: click the source or target entity of a fact.
- From the [[Graph]]: select a node and click **View page** in the side panel.
- From [[Cypher query]]: an entity in the result table is a link, and a selected node in the graph tab has **View page**.
- From [[Ask]]: click an entity of a returned fact. A lent fact opens its entity in the brain that lends it.
- From the entity page itself: every related entity is a link.

## What it shows
- **Header:** name, type, the names merged into it ("Also: …") and its summary.
- **Facts grouped by relation.** Each group is one piece of data read as an **evolution**, oldest first: "HOSTED_ON → Eridani → Polaris → Notus". The current value is shown with its dates; the earlier ones are folded under **Show earlier (N)** and appear struck through, with the period in which they were true. A relation pointing to the entity is shown as "← RELATION". Groups with a possible contradiction come first, then those with most current values.
- **Other relations:** generic relations such as `RELATES_TO`, which the extractor writes when no type fits, link anything, so their «evolution» says little. They are folded into one section at the end, with the number of facts; **Show** opens it.
- **Two dates per fact:** since when it is true (*current since*, *valid … → …*) and when the brain **learned** it. They are different axes: a fact learned today can be true since last year.
- **Related:** the entities it has facts with, as links to their own pages.
- **Episodes that mention it:** the most recent ones, linking to the episode in the [[Journal]].
- **Documents that mention it:** passages from [[Knowledge]], when there are any. They come from a separate call (`GET /docs/mentions?entity=`), not from the entity endpoint, and are not shown for a lent entity.

## As it was on a day
**As it was on** picks a date: the page then shows what was **current that day**, by validity dates, as the [[Graph]]'s time travel does. Facts that were not yet true are left out (the page says how many). **Today** goes back to the present. While you look at a past day, the curator actions are hidden.

## Possible contradictions
If a relation is marked as **single-valued** in the [[Ontology]] and the entity has two different current values for it, the group says so and links to [[Contradictions]], where it can be resolved. The page shows the case rather than hiding it.

## Curator actions
- **Invalidate** a current fact, or **Reactivate** an earlier one, from the fact itself. They are the same actions as in [[Facts]] and can be undone from the vocabulary history.
- Links to **merge** the entity with another ([[Merge duplicates]]), **change its type** ([[Type corrector]], administrators) and **edit the text** of a fact ([[Facts]]).

## Lent entities
With [[Federation]], an entity of a brain that lends its graph opens with its origin ("from «slug»") and is **read-only**.

## Accessibility
Each relation's evolution is an ordered list, not a chart, so a screen reader reads it in order, and every entity, episode and action is reachable with the keyboard.
