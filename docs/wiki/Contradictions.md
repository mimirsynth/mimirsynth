**English** · [Español](Contradicciones)

# Contradictions

The **Contradictions** tab of [[Vocabulary]] (curators and above). It lists **current facts that contradict each other** in relations that can only hold one value at a time, and lets you choose which one stays current.

## Why it exists
When a new episode contradicts a fact, ingestion usually invalidates the old one. Not always: two episodes worded differently can leave «the laptop is in Office A» and «the laptop is in Office B» current at the same time. Recall then hands both to your agent as if both were true. This tab finds those cases **without any AI model** and leaves the decision to a person.

## Single-valued relations
Contradictions are only looked for in relation types marked as **single-valued**: a subject cannot have two current targets, such as where a device is installed or whom a person reports to.
- A brain administrator marks them in [[Ontology]]: edit the relation type and tick **A single value at a time**. Marked relations show a **single value** tag in the relation types table.
- **No relation is single-valued by default, not even in the standard packages.** Many relations look single-valued and are not: «located at» can point at a building, a network and a rack at the same time. Each brain marks its own **after measuring** (see below).
- If no relation is marked, the tab says so and searches nothing.

## What counts as a contradiction
Current facts with the **same subject** and the **same relation** and **different targets of the same entity type**:
- Relations are compared after normalising format and [aliases](Relations-and-aliases), so `LocatedAt` and `LOCATED_AT` are the same relation.
- Only targets of the **same entity type** are compared: «X located at a building» and «X located at a network» do not contradict each other.
- Two targets with the same name except for case and spacing count as the same target. That is a duplicate entity, not a contradiction: see [[Merge duplicates]].

## Reviewing a case
Each card shows the subject and the relation, the type of the targets and every current fact with its date. A tag says whether there is a suggestion:

| Tag | Meaning |
|---|---|
| **the newest is clear** | One fact has a strictly newer **validity date** (when it became true). It is preselected |
| **same date: your call** | The newest facts share the same date. Nothing is preselected |
| **learning date only: your call** | Some fact only has the date it was **learned**, which does not say which one is more current. Nothing is preselected |

To resolve it, pick the fact that is still true under **Choose which one stays** and press **Keep this one and invalidate the rest**.
- The other facts are **invalidated**, not deleted. Their end date is the validity date of the fact you kept when that one is newer (so the timeline shows when it changed), or the current time otherwise.
- Each invalidated fact is recorded in the vocabulary history (**Recent changes** in [[Entity types]]), where a brain administrator can **undo** it as long as no later vocabulary change was made. Undo the latest first. The resolution is also recorded in the [[Audit log]].
- [[Facts]] shows the invalidated ones as no longer current, like any other invalidation.

## Measure before marking
**Measure across all relations** looks at every relation, marked or not, **without changing anything**. The **Candidates by relation** table lists, for each relation with at least one case:

| Column | What it shows |
|---|---|
| **Relation** | The normalised relation name |
| **Subjects** | How many subjects use it |
| **With several targets** | How many of them have more than one current target of the same type |
| **Share** | The proportion between the two, from lowest to highest |
| **Single value** | Whether it is already marked |

Good candidates have a **low share and some cases**: most subjects have one target and a few have two, which is what a missed contradiction looks like. A relation with a high share probably allows several values: do not mark it. While measuring, the cases of every relation are listed, but only those of relations already marked can be resolved. **Back to the single-valued relations** returns to the normal view.

The same measurement is available from the command line, read-only, which helps before anything is marked:

```bash
docker compose exec mimirsynth python -m mimirsynth.conflicts <graph> [--brain-id N] [--top N]
```

`<graph>` is the brain's graph name (shown in Administration → Brains). With `--brain-id` the brain's aliases and marked relations are applied; `--top` limits how many cases are printed (20 by default). The output is JSON.

## Daily check and alert
Once a day, every brain with at least one single-valued relation is checked. If there are cases, the **`conflicts.found`** alert (information) shows up in the notification bell for that brain's curators and for instance administrators, and goes to the notification channels that include it; it closes by itself when no cases remain. Brains with no marked relation are never checked.

## Limits
- Up to 50,000 current facts are read per check, the most recent first; if the limit is reached the tab says so.
- Up to 200 cases are shown at a time, those with most facts first; the total is always counted.
