**English** · [Español](Relaciones-y-alias)

# Relations and aliases

The **Relations** tab of [[Vocabulary]]. It lists all the **relation types** used by the graph's facts (for example `RUNS_ON`, `HOSTED_ON`, `DEPENDS_ON`), with how many facts each has.

## Why it is needed
The LLM names relations in its own way: "RunsOn", "IsHostedOn", "HostedOn"… They are the same thing under different names, and that fragments searches and dirties the graph. They have to be **unified**.

## The table
Sortable and filterable columns:
- **Relation (normalised):** the canonical name. Generic ones (`RELATES_TO`, `MENTIONED_IN`…) carry the **generic** label.
- **Facts:** how many facts use that relation.
- **Raw variants:** the original names grouped under it (with a variant filter).
You can show **only the long tail** (relations with 2 facts or fewer), which is where the noise usually is.

## Unifying with an alias
An **alias** says "this relation reads as that other one". To create it (brain administrator):
1. On the relation's row press **Unify with…**.
2. Under **Reads as**, choose an existing relation or type a new name.
3. Confirm.

What happens:
- The alias applies **on reading**: facts are shown, searched and counted under the canonical name.
- It **does not modify the graph data.** That is why it is safe and reversible.
- It also applies to future ingestions: new things arriving with the variant are normalised.
- [[Contradictions]] compares relations after applying aliases, so facts written with two variants of a single-valued relation are checked against each other.

## Removing an alias
In the **Aliases** tab you see all active aliases (alias → "reads as"). **Remove** returns the relation to its own name; the facts are untouched.

## Automatic format normalisation
Before anything else, MimirSynth already treats as equal the variants that differ only in format (capitalisation, hyphens, underscores). The summary card shows "raw → after format normalisation". Aliases are for *meaning* synonyms that format cannot resolve.

## When not to unify
Do not unify relations that mean different things even if they look alike (`DEPENDS_ON` vs `REQUIRES` may be nuances you want to keep). When in doubt, look at the facts of both in [[Facts]] filtering by relation.
