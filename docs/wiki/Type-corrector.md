**English** · [Español](Corrector-de-tipos)

# Type corrector

The **Type corrector** tab of [[Vocabulary]] (brain administrators only). It reclassifies **entities left without a type, with a type the ontology does not have, or with a catch-all type** that are really something else.

## Why it exists
Graphiti does not change the type of entities that already exist. If an application was classified once as "Organization" (a typical mistake), it stays that way for ever, even if the ontology improves. The corrector has the **decider** review each entity, with the ontology's types as options, and propose the right one. **You approve**, and the change is **reversible**.

## What it reviews
It does not assume any domain: what it looks at comes from the brain's [[Ontology]], in this order:
1. Entities **without a type**.
2. Entities whose type **is not in the ontology** (for example, the default types of an agent that writes to Graphiti directly).
3. Entities of the catch-all or easily confused types that the package lists (for example `Topic` or `Item`).

Everything else is left alone. A hand-written ontology, or one whose package no longer exists, reviews `Object`, `Thing` and `Topic`.

Some names are set aside as **Doubtful** without asking the decider: names of five words or more in every brain and, only if the package enables them, technical names (file paths, command-line options, code, versions at the end of the name, problem descriptions). `infrastructure` enables all of them, `software-knowledge` only command-line options, and the other packages none. Details: «Type corrector» in [`docs/ONTOLOGY.md`](https://github.com/MimirSynth/mimirsynth/blob/main/docs/ONTOLOGY.md).

## Requirements
- An **ontology** applied to the brain (otherwise you see a notice: [[Ontology]]).
- A **decider** configured ([[AI providers]]).

## How to use it
1. Under **Entities to analyse** say how many to review (1–1000) and press **Analyse**. A background job is launched with a progress bar (see [[Jobs]]); if it fails, the last error is shown.
2. When it finishes, filter by **State**:
   | State | What is there |
   |---|---|
   | **Proposed** | The decider proposes a type, with its confidence as a percentage |
   | **Doubtful** | Names that do not look like a concrete entity (see above). There is no point typing them; you may dismiss them |
   | **No suitable type** | No ontology type fits. If there are many of the same kind, **a type is missing from the ontology** |
   | **Applied** | Already corrected |
   | **Rejected** | The ones you dismissed; they are not offered again |
   | **Already correct** | The decider confirms the current type |
3. In **Proposed**, adjust **Minimum confidence** with the slider (0.5–0.99) to see only the surest proposals. A note says how many are hidden below the threshold, with **View all**.
4. **Select** the ones you want (there is "select all") or work on everything the filter shows:
   - **Apply selected** / **Apply all visible**: a confirmation shows a summary by proposed type before changing anything.
   - **Reject selected** / **Reject all visible** (the latter asks for confirmation). In **Doubtful**, **Dismiss selected**.

   Only the rows the filter shows are applied or rejected: rows hidden by the confidence threshold are never touched.
5. A message reports the result, including how many changes **did not fit the current ontology** (for example, a type removed since the analysis) and were not applied.
6. If you make a mistake, every applied change has its own **Undo** in **Applied**.

## Tips
- Start with small batches (50–100) and high confidence (0.9) to trust the decider's judgement; lower the threshold gradually.
- Look at "No suitable type": it is the best clue to which types to add to the ontology.
- If you get many "Doubtful", the ingestor is creating low-quality entities: improve the extraction instructions.
