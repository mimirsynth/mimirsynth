**English** · [Español](Corrector-de-tipos)

# Type corrector

The **Doubtful types** tab of [[Content quality]] (brain administrators only), also called the type corrector. It reclassifies **entities left without a type, with a type the ontology does not have, or with a catch-all type** that are really something else.

## Why it exists
Graphiti does not change the type of entities that already exist. If an application was classified once as "Organization" (a typical mistake), it stays that way for ever, even if the ontology improves. The corrector has the **decider** review each entity, with the ontology's types as options, and propose the right one. **You approve**, and the change is **reversible**.

## What it reviews
It does not assume any domain: what it looks at comes from the brain's [[Ontology]], in this order:
1. Entities **without a type**.
2. Entities whose type **is not in the ontology** (for example, the default types of an agent that writes to Graphiti directly).
3. Entities of the catch-all or easily confused types that the package lists (for example `Topic` or `Item`).

Everything else is left alone. A hand-written ontology, or one whose package no longer exists, reviews `Object`, `Thing` and `Topic`.

Since `infrastructure` has a `Software` type, a version at the end of a name (`Debian 13`) is no longer a reason to set it aside in brains with that type. Some names are set aside as **Doubtful** without asking the decider: names of five words or more in every brain and, only if the package enables them, technical names (file paths, command-line options, code, versions at the end of the name, problem descriptions). `infrastructure` enables all of them, `software-knowledge` only command-line options, and the other packages none. Details: «Type corrector» in [`docs/ONTOLOGY.md`](https://github.com/MimirSynth/mimirsynth/blob/main/docs/ONTOLOGY.md).

## Requirements
- An **ontology** applied to the brain (otherwise you see a notice: [[Ontology]]).
- A **decider** configured ([[AI providers]]).

## How to use it
1. Press **Analyse…**, say in the dialog how many entities to review (1–1000) and press **Analyse**. A background job is launched with a progress bar (see [[Jobs]]); if it fails, the last error is shown.
2. When it finishes, filter by **State**:
   | State | What is there |
   |---|---|
   | **Proposed** | The decider proposes a type, with its confidence as a percentage |
   | **Doubtful** | Names that do not look like a concrete entity (see above). There is no point typing them: merge them into the entity they are a detail of (below), or dismiss them |
   | **No suitable type** | No ontology type fits. If there are many of the same kind, **a type is missing from the ontology** |
   | **Applied** | Already corrected |
   | **Merged** | Names that were not an entity and were merged into the one they are a detail of |
   | **Rejected** | The ones you dismissed; they are not offered again |
   | **Already correct** | The decider confirms the current type |
3. In **Proposed**, adjust **Minimum confidence** with the slider (0.5–0.99) to see only the surest proposals. A note says how many are hidden below the threshold, with **View all**.
4. **Apply** on a row applies that one proposal. **Select** the ones you want (there is "select all") or work on everything the filter shows:
   - **Apply selected** / **Apply all visible**: a confirmation shows a summary by proposed type before changing anything. Applying more than one at a time is **off until you have decided 20 proposals one by one** in this brain (applied, applied as another type or rejected, each on its own; dismissing a doubtful one does not count): the decider's confidence means little until it has been measured against your own decisions. After that, next to the threshold, the corrector says what share of the proposals above it that you decided one by one you applied as proposed and kept (not rejected, not applied as another type, not undone).
   - **Apply as…** (the pencil on a row): applies it with another type of the ontology than the one proposed, when the decider got the kind right but not the type.
   - **Reject selected** / **Reject all visible** (the latter asks for confirmation). In **Doubtful**, **Dismiss selected**.

   Only the rows the filter shows are applied or rejected: rows hidden by the confidence threshold are never touched.
4b. In **Doubtful**, a name that is a detail of another entity (the option of a tool, the file of a project, the field of an API) can be **merged into** it. When the analysis sets a name aside, the decider also says which of the entities it shares current facts with it belongs to (up to 8, or none of them); the row shows it under **A detail of**, with its confidence. **Merge** moves its facts to that entity and keeps its name as an alias of it, as merging duplicates does ([[Merge duplicates]]); a fact between the two («tool has a --help flag») becomes a fact of the entity itself, and the old node does not stay as an orphan. **Merge into…** shows how many facts move and lets you pick another of those entities, or one when the decider proposed none; with no entity to merge into, it offers to dismiss the name. It is undone with **Undo** in the message, in **Merged**, or in Vocabulary → Recent changes; as there, the most recent change is undone first. If a merge fails halfway, what it already moved is recorded and undone the same way.
5. A message reports the result, including how many changes **did not fit the current ontology** (for example, a type removed since the analysis) and were not applied.
6. If you make a mistake, every applied change has its own **Undo** in **Applied**, and every merge in **Merged**.

A curator can also fix **one entity** without the corrector, with **Change type** on its [[Entity page]]. Its suggestion, if it had one, is then no longer pending.

## Tips
- Start with small batches (50–100) and decide the first ones one by one: bulk apply waits for 20 of them, and then the share you kept tells you how far the threshold can go down.
- Look at "No suitable type": it is the best clue to which types to add to the ontology.
- If you get many "Doubtful", the ingestor is creating low-quality entities: improve the extraction instructions. Flags, field paths, file paths, URLs, dates and phrases are no longer created as entities at ingestion ([[Ontology]]), so those are left from before.
