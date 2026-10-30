**English** · [Español](Hechos)

# Facts

A **fact** is a concrete statement between two entities ("The mail service runs on server 2") with the **date from which it is true** and, if it stops being so, **when**. Facts are extracted from the episodes ([[Journal]]). This screen is the heart of the memory: here you see, correct and control the knowledge.

## Two views
With the **List** and **Timeline** tabs:
- **List:** one card per fact, with a counter per state.
- **Timeline:** the "learned" and "stopped being true" events grouped by day, most recent first. It shows the 300 most recent ones matching the filters; narrow the dates to go further back.

## Reading a card
- The fact text.
- Labels: **source entity → relation → target entity**. Click an entity to open its [[Entity page]].
- Dates: *current since*, *invalidated* (if applicable) and *recorded on* (when the system learned it). Telling apart when it happened from when it was recorded is what gives the history.
- **Invalidated** facts are shown dimmed.

## Filters
- **Search** by fact text or by an entity's name.
- **Relation** (with a count of facts per type).
- **From / To** and **Order**.
- **State** (list only): *All*, *Current*, *Invalidated*, each with its number.

## Correcting facts (curator or higher)
Each card has three actions if your role allows it:
- **Edit:** change the fact text and/or the relation type (normalised to `UPPERCASE_WITH_UNDERSCORES`). On saving, its **embedding is recalculated** so search stays correct.
- **Invalidate / Reactivate:** mark the fact as **no longer true** (keeps the history) or return it to current. It is the right action when something changed. If the fact is simply *wrong*, edit or delete it.
- **Delete:** removes it from the graph and from its episodes' fact list. **Use Invalidate** if it merely stopped being true.

After each action a notice appears with **Undo**: you can revert the change as long as you have not made another vocabulary change since.

## Tips
- A badly extracted fact usually points to a **vocabulary** problem (too-generic relation, duplicate entity): fix it in [[Vocabulary]] so it does not repeat.
- To record a real-world change properly, it is best to **add a new episode** ("X now runs on Y") and let the system invalidate the previous fact; edit by hand only to fix errors.
