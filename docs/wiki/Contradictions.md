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
| **probably several values** | The relation looks like it holds several values at a time (see below). Nothing is preselected |

An open group lists each fact with its target, its date («true since» or «learned on») and its sentence, cut to two lines with **Show all**. A long group scrolls inside its own area. **How to resolve** has two modes:
- **Keep only one** asks **Which fact is still true?**, one choice per fact. **Resolve: invalidate the other N** keeps the chosen fact; the button is off until a fact is chosen. This is the mode for a really single-valued relation.
- **Invalidate the ones that are no longer true** asks **Which facts are no longer true?**, with a tick per fact. **Invalidate selected (N)** invalidates only the ticked ones and leaves the rest current; it is off until one is ticked, and while every fact is ticked, because one always has to stay current. This is the mode for a group where only some facts are stale.

Invalidating more than one fact asks for confirmation first, with the list of targets. Then:
- **Not a contradiction** hides the group, for a false positive. It stays hidden while its facts are the same ones: if a new fact joins the group, it shows again. Hidden groups are listed under **Marked as not a contradiction**, where **Show again** brings one back.

When resolving:
- The facts are **invalidated**, not deleted. With **Keep only one**, their end date is the validity date of the fact you kept when that one is newer (so the timeline shows when it changed), or the current time otherwise; with **Invalidate the ones that are no longer true**, the current time.
- At least one fact of the group always stays current: the server refuses a resolution that would leave none.
- Each invalidated fact is recorded in the vocabulary history (**Recent changes** in [[Entity types]]), where a brain administrator can **undo** it as long as no later vocabulary change was made. Undo the latest first. The resolution is also recorded in the [[Audit log]].
- [[Facts]] shows the invalidated ones as no longer current, like any other invalidation.

## Relations that probably hold several values
A relation such as `MONITORS` can have many targets by nature: a monitoring server watches dozens of services, and each one is true. If it was marked single-valued by mistake, every subject with several targets shows up as a contradiction. A relation is flagged as **probably several values** when some subject has **3 or more** current targets of the same type, or when at least **a quarter** of its subjects (with two cases at least) have several. Then:
- Its groups get no preselected fact, and the group opens in **Invalidate the ones that are no longer true**.
- An open group says **Probably not a contradiction**: how many current targets the subject has (or which share of subjects has several) and that, if the relation holds several values, «A single value at a time» should be unticked in [[Ontology]]. **Edit the relation** opens that relation's edit dialog in the Ontology tab, and a brain administrator can **Unmark now** right there; the group then stops showing.
- The measurement table shows the same flag next to the relation's name.

## Measure before marking
**Measure across all relations** looks at every relation, marked or not, **without changing anything**. The **Candidates by relation** table lists, for each relation with at least one case:

| Column | What it shows |
|---|---|
| **Relation** | The normalised relation name, with **probably several values** when it looks like one (see above) |
| **Subjects** | How many subjects use it |
| **With several targets** | How many of them have more than one current target of the same type |
| **Share** | The proportion between the two, from lowest to highest |
| **Single value** | Whether it is already marked |

Good candidates have a **low share and some cases**: most subjects have one target and a few have two, which is what a missed contradiction looks like. A relation with a high share, or flagged as **probably several values**, probably allows several values: do not mark it. A brain administrator can **Mark** a relation from this table when it is in the ontology, and **Unmark** a marked one that is flagged. While measuring, the cases of every relation are listed, but only those of relations already marked can be resolved. **Back to the single-valued relations** returns to the normal view.

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
