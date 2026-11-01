**English** · [Español](Vocabulario)

# Vocabulary

The **vocabulary** is the brain's **framework**: what kinds of things and relations exist, and how their names are normalised. It holds for the whole brain, changes rarely, applies to what is ingested from then on, and administrators manage it. Without it, the LLM creates hundreds of variants ("RunsOn", "IsHostedOn", "HostedOn"…) and types that say nothing.

The work on the **content** the graph already holds (duplicate entities, facts that contradict each other, doubtful types, facts to review) is not here: it is in [[Content quality]], under Curation, and curators do it.

## Declared and observed
- **Ontology** is what is **declared**: what the ingestor is asked for (which entity and relation types to extract, between which types, and which relations are single-valued or have a shelf life).
- **Relations** and **Entity types** are what is **observed**: what is actually in the graph, with how many facts or entities use each one.

Comparing them tells what is missing from the declaration (a widely used relation the ontology does not have) and what is left over (a variant worth unifying).

## Summary cards
| Card | What it counts |
|---|---|
| **Relation types** | How many there are "raw" and how many after normalising the format |
| **Generic facts** | Facts in uninformative relations (`RELATES_TO`, `MENTIONED_IN`…) |
| **Long tail** | Relations used by very few facts (≤ 2), which are usually noise |
| **Entities** | Total |

## Tabs
Each tab starts with one or two sentences saying what it is for, who uses it and what happens when you act.

| Tab | Purpose | Who |
|---|---|---|
| [[Relations and aliases]] | See the relations in the graph and unify variants with an alias | Reading: everyone · Aliases: administrator |
| [[Entity types]] | See, define, rename and merge entity types | Reading: everyone · Changes: administrator |
| [[Ontology]] | Declare which types and relations the ingestor extracts, which relations are **single-valued** and what their **shelf life** is | Reading: everyone · Changes: administrator |
| **Aliases** | The active relation aliases, with the option to remove them | Reading: everyone · Removing: administrator |

## Aliases, between the framework and the content
An **alias** makes one relation name read as another (`HostedOn` as `HOSTED_ON`), when reading and when ingesting, without changing the graph's data. They are created with **Unify with…** in Relations and removed in Aliases.

The **names of merged entities** are something else: when a duplicate is merged in [[Content quality]] → Duplicates, its name is kept on the main entity (its [[Entity page]] shows it), and whatever is ingested later with that name goes to it. The Aliases tab explains this and links to Duplicates, where the merge is undone from **Recent merges**.

## From the framework to the content
Two settings of each relation in [[Ontology]] create work for curators:
- **A single value at a time**: two current targets of the same subject show up in [[Content quality]] → [[Contradictions]].
- **Shelf life**: a fact that goes past it without confirmation shows up in [[Content quality]] → **To review**.

The relation's dialog and the Ontology header link to those tabs, and they link back to Ontology.

## A good order of work
1. Apply an **ontology package** or define your types ([[Ontology]]): it keeps the mess from growing.
2. After a few weeks of use, review **Relations**: unify variants with aliases, and declare in the ontology the relations that are used and missing.
3. Mark as single-valued, or give a shelf life to, only the relations that need it; measure first in [[Contradictions]] → **Measure across all relations**.
4. What comes out of that (duplicates, contradictions, doubtful types, facts to review) is worked on in [[Content quality]].
5. Look at the cards again: the long tail and the generic facts should go down.

## Reversibility
**Aliases** do not modify the graph (they apply on reading) and can be removed whenever you like. Renaming or merging types does change data: it shows a **preview**, keeps what is needed to revert it, and is **undone** from its history as long as you have not made another vocabulary change afterwards. Changes are recorded in the [[Audit log]].

## Old links
The addresses of the tabs that moved to Content quality (`/vocabulario?tab=dup`, `conflicts`, `stale` and `corrector`, and `/tipos`) still work: they lead to the same tool in its new place.
