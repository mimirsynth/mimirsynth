**English** · [Español](Contradicciones)

# Contradictions

The **Contradictions** tab of [[Vocabulary]] (curators and above). It lists **current facts that contradict each other** in relations that can only hold one value at a time, and lets you choose which one stays current.

## Why it exists
When a new episode contradicts a fact, ingestion usually invalidates the old one. Not always: two episodes worded differently can leave «the laptop is in Office A» and «the laptop is in Office B» current at the same time. Recall then hands both to your agent as if both were true. This tab finds those cases **without any AI model** and leaves the decision to a person.

## Single-valued relations
Contradictions are only looked for in relation types marked as **single-valued**: a subject cannot have two current targets, such as where a device is installed or whom a person reports to.
- A brain administrator marks them in [[Ontology]] (edit the relation type and tick **A single value at a time**; the relation types table has a **Single value** column) or straight from the measurement below with **Mark**.
- **No relation is single-valued by default, not even in the standard packages.** Many relations look single-valued and are not: «located at» can point at a building, a network and a rack at the same time. Each brain marks its own **after measuring** (see below).
- If no relation is marked, the tab says so and searches nothing, with shortcuts to **Measure now** and to the Ontology tab.
- **Generic relations** such as `RELATES_TO` (what the extractor writes when no type fits) are never compared and cannot be marked: they link anything, so they would only produce noise. The tab says how many facts were left out for that reason.

## What counts as a contradiction
Current facts with the **same subject** and the **same relation** and **different targets of the same entity type**:
- Relations are compared after normalising format and [aliases](Relations-and-aliases), so `LocatedAt` and `LOCATED_AT` are the same relation.
- Only targets of the **same entity type** are compared: «X located at a building» and «X located at a network» do not contradict each other.
- Two targets with the same name except for case and spacing count as the same target. That is a duplicate entity, not a contradiction: see [[Merge duplicates]].

## Reviewing a case
A short note at the top says what the tab is for and what each action does. The cases are a compact table with one row per group: **Subject**, **Relation**, **Target type** (the entity type of the targets; only targets of the same type are compared), **Facts** and **Suggestion**. **Review** opens a group. The **Suggestion** column says whether there is one:

| Tag | Meaning |
|---|---|
| *target* **the newest** | One fact has a strictly newer **validity date** (when it became true). It is preselected |
| **same date: your call** | The newest facts share the same date. Nothing is preselected |
| **learning date only: your call** | Some fact only has the date it was **learned**, which does not say which one is more current. Nothing is preselected |

An open group asks **Which fact is still true?** and lists each fact as a choice, with its target, its date («true since» or «learned on») and its sentence, cut to two lines with **Show all**. A long group scrolls inside its own area. Then:
- **Resolve: invalidate the other N** keeps the chosen fact. The button is off until a fact is chosen.
- **Not a contradiction** hides the group, for a false positive. It stays hidden while its facts are the same ones: if a new fact joins the group, it shows again. Hidden groups are listed under **Marked as not a contradiction**, where **Show again** brings one back.

When resolving:
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

Good candidates have a **low share and some cases**: most subjects have one target and a few have two, which is what a missed contradiction looks like. A relation with a high share probably allows several values: do not mark it. A brain administrator can **Mark** a relation from this table when it is in the ontology. While measuring, the cases of every relation are listed, but only those of relations already marked can be resolved. **Back to the single-valued relations** returns to the normal view.

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
