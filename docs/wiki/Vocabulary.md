**English** · [Español](Vocabulario)

# Vocabulary

The **vocabulary** is the set of relation and entity types that exist in the graph. Over time the LLM creates hundreds of variants ("RunsOn", "IsHostedOn", "HostedOn"…) and duplicate entities ("Server 1", "server-1"), and sometimes leaves two facts current that cannot both be true. This screen is for **seeing that mess and fixing it** without touching the graph by hand.

## Summary cards
| Card | What it counts |
|---|---|
| **Relation types** | How many there are "raw" and how many after normalising the format |
| **Generic facts** | Facts in uninformative relations (`RELATES_TO`, `MENTIONED_IN`…) |
| **Long tail** | Relations used by very few facts (≤ 2), which are usually noise |
| **Entities** | Total and by type |
| **Possible duplicates** | Entities with the same name except for version or capitalisation |

## Tabs
| Tab | Purpose | Who |
|---|---|---|
| [[Relations and aliases]] | See all relations and unify similar ones with aliases | Reading: everyone · Aliases: administrator |
| [[Entity types]] | See, rename, merge and define entity types | Reading: everyone · Changes: administrator |
| [[Type corrector]] | Reclassify entities left without a type or with a catch-all one | Administrator |
| [[Ontology]] | Define which types and relations the ingestor may extract, and which relations are single-valued | Reading: everyone · Changes: administrator |
| **Aliases** | List of active aliases, with the option to remove them | Reading: everyone · Removing: administrator |
| [[Merge duplicates]] | Join entities that are the same thing | Reading: everyone · Merging: administrator |
| [[Contradictions]] | Resolve current facts that contradict each other in single-valued relations, and **Measure across all relations** to find which relations are single-valued | Curator and above |

## A good order of work
1. Apply an **ontology package** or define your types ([[Ontology]]): it keeps the mess from growing.
2. After a few weeks of use, review **Relations**: unify variants with aliases.
3. Review **Duplicates** and merge.
4. Run the **Type corrector** to reclassify generic entities.
5. In **Contradictions**, use **Measure across all relations** and mark as single-valued in the ontology only the relations that really allow one value at a time; then resolve the cases it finds.
6. Look at the cards again: the long tail and the duplicates should go down.

## Reversibility
**Aliases** do not modify the graph (they apply on reading) and can be removed whenever you like. Operations that do change data (renaming or merging types, merging entities, invalidating facts when resolving a contradiction) show a **preview** or a confirmation, keep what is needed to revert them and can be **undone** from their history as long as you have not made another vocabulary change afterwards. Each type correction can be undone on its own from **Applied** in the [[Type corrector]]. Changes are recorded in the [[Audit log]].
