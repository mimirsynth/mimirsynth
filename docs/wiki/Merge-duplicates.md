**English** · [Español](Fusionar-duplicados)

# Merge duplicates

The **Duplicates** tab of [[Content quality]]. It shows **groups of entities that are probably the same thing**: same name except for capitalisation, spaces, `_`, `-` and `.`, or a version written as a separate word (for example "VM 201", "vm201" and "VM.201", or "Nextcloud" and "Nextcloud 29.0.1"). The brain's ontology package can also declare **equivalent prefixes**: `infrastructure` treats `CT` and `LXC`, and `VM` and `QEMU`, as the same, so "CT147" and "LXC 147" are one group. A number glued to the name is part of it ("ups@10.0.0.4", "min_similarity=0.55"), and a name that is only an address is compared whole. The name is only a hint: check that the members really are the same thing before merging.

## Why they are a nuisance
If the same entity exists twice, its facts are split: a search finds half, the graph shows two nodes and the [[Overview]] over-counts.

## Reviewing a group
Each group is a table of its entities (name, type, number of facts and mentions). Brain administrators can, for each group:
- Make an entity the **primary**: it is the one kept.
- **Select** the ones that merge into it.
- **Review merge (N):** opens a confirmation window with the detail.
- **Not duplicates:** dismisses the group (for example two versions that really should stay separate). It is kept in the list of **dismissed** ones, from where you can **restore** it.

## The merge
The confirmation window warns that it **changes graph data**. When merging:
- The facts and mentions of the merged entities move to the primary.
- The merged entities are **hidden, not deleted**.
- A **prior copy** of what is affected is saved.
- **Facts that end up repeated are not removed** (you can invalidate or delete the surplus in [[Facts]]).

## Undo
Under **Recent merges** each operation appears. The **latest** one can be **undone** as long as you have not made another vocabulary change afterwards.

## Automatic merging
On ingestion, MimirSynth already merges by itself the clear cases of alias normalisation. What you see here is what was left unresolved.

## Merged names
The name of each merged entity is kept as an alias of the one that stays, so it is still found by that name (search, entity page, the MCP tools). A name the entity already has, in any case or spacing, is not added again: merging «lyra» into «Lyra» adds no alias. Undoing a merge removes only the alias it added.

Merges made before this rule could leave aliases equal to the entity's own name, or the same alias twice. The entity page does not show them, and a brain administrator removes them from the graph in [[Content quality]] → **Repeated aliases**. Other aliases stay as they are, in their first spelling. The command `python -m mimirsynth.entity_aliases` does the same from a shell (it lists them in every brain, `--brain <slug>` for one, and `--apply` removes them), without the copy of the graph or the history; with Docker, `docker compose exec mimirsynth python -m mimirsynth.entity_aliases`.

## Tips
- Choose as primary the one with **most facts** and the most canonical name.
- Check they really are the same thing: "Server 1" and "Server 2" are **not** duplicates.
- After merging, look at the [[Graph]] again to check the node ended up well connected.
