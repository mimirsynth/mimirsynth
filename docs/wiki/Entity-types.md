**English** · [Español](Tipos-de-entidad)

# Entity types

The **Entity types** tab of [[Vocabulary]]. It lists every type the graph's entities have (Service, Person, Server…) with its **number of entities** and its **description**.

## The table
- **Type:** the name. If the type exists in the graph but **is not defined in the ontology**, it carries the label "outside the ontology".
- **Entities:** how many entities have that type (filterable by "in the ontology / outside").
- **Description:** when that type is used. **It matters**: it guides both the LLM that extracts and the corrector's decider.

## Actions (brain administrator)
### Create type
**Create type** adds a new one to the ontology. The **name** is *PascalCase*, with no spaces (`Service`, `ExternalPerson`). The **description** must say **when** it is used, with examples and, if needed, **when not** ("An application or software service with a proper name. NEVER an organisation.").

### Edit / Add to the ontology
**Edit** changes the description of a defined type. **Add to the ontology** registers a type that already existed in the graph but outside it.

### Rename or merge
**Rename / merge** changes the type of **all the entities** of that type to a new one:
- If you choose a **new** type, it is a **rename**.
- If you choose an **existing** one, it is a **merge**.
Before applying, you see a **preview** with how many entities will be affected. The target name must follow the `PascalCase` format.

### Remove from the ontology
**Remove** takes the type out of the ontology: it stops guiding extraction and the corrector. **Entities that already have that type do not change**: they are shown as "outside the ontology". The map rules that use the type are removed.

## History and undo
Below the table, **Recent changes** lists the 15 latest vocabulary changes of the brain: those made here, ontology edits, entity merges and the facts invalidated when resolving [[Contradictions]]. The **latest** one has an **Undo** button (brain administrators; as long as no other change has been made afterwards); reverted ones are marked "undone".

## Good practices
- A few well-described types work better than many overlapping ones.
- Avoid catch-all types (Object, Topic): they attract everything the model does not know how to classify. If they show up, use the [[Type corrector]].
- Change descriptions carefully: they affect **future ingestions**, not what is already stored.
