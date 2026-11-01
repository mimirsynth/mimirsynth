**English** · [Español](Resumen)

# Overview

The home screen. It shows the state of the **active brain** at a glance: how much knowledge it holds, how it has evolved and what matters most in it. Apart from the **Needs your attention** block, it is read-only.

## Needs your attention
Curators and above see first a short list of what is **waiting for a person's decision** in the brain, each line with its count and a link to the tool where it is decided:

| Line | Where it is decided |
|---|---|
| Proposals waiting for a decision | [[Proposals]], filtered to pending |
| Pending corrections, from agents or from «incorrect» ratings | [[Proposals]], filtered to pending corrections |
| Groups of possible duplicates | [[Content quality]] → Duplicates |
| Possible contradictions | [[Content quality]] → Contradictions |
| Facts to review, past their shelf life | [[Content quality]] → To review |
| Doubtful types with a proposed change (administrators only) | [[Content quality]] → Doubtful types |
| Reference queries that got worse in the last run | [[Ask]] → Reference queries |

Lines at zero are hidden, and when nothing is waiting it says «Nothing needs your attention». The counters are the same ones each page computes, kept for a minute so the home screen stays fast: something you have just resolved may still be counted for that minute (Content quality always shows them recalculated).

## First steps (new instance)
An instance administrator who opens the home page while **no brain exists yet** sees **First steps** instead. The **Create your first brain** button opens the dialog to create it under Administration ([[Brains and members]]), and a short checklist links to each screen:
1. **Create a brain:** an isolated knowledge domain, with its own graph, ontology, members and tokens.
2. **Set up the AI models:** an LLM to extract facts and an embeddings engine, and test them ([[AI providers]]). Without them proposals are not ingested and recall returns nothing.
3. **Create an API token:** one per agent, for the brain it will use and with the Contributor role ([[My account]]).
4. **Connect an agent:** it reads the memory (recall) and proposes facts through the API or MCP ([[Connect agents]]).

Anyone else without access to a brain sees a message asking them to ask an administrator to add them.

## Figures
| Figure | Meaning |
|---|---|
| **Episodes** | Texts stored as they were told (notes, messages, approved proposals). Below, how many were added this week. |
| **Entities** | Distinct things the graph knows (servers, people, applications…). |
| **Facts** | Statements between entities, current and invalidated. Below, those learned this week. |
| **Invalidated** | Facts that **stopped being true**: they are kept as history. |
| **Communities** | Groups of strongly related entities (only if computed). |

The header text also gives the **last episode** and when it arrived.

## Charts
- **Weekly activity (last 26 weeks):** facts learned, episodes and facts invalidated per week. It shows whether the brain is "alive" and whether there are peaks of change.
- **State of the facts:** current, invalidated and *future* (those with a start date later than today).
- **Entities by type:** the 8 classes with most entities. Many "untyped" or generic ones suggest working on the ontology ([[Vocabulary]]).
- **Most used relations:** the relation types with most facts. A huge tail of odd relations usually means the vocabulary is not normalised.
- **Most connected entities:** the nodes with most facts; they are usually the brain's central topics.

## Document knowledge
At the bottom, how many **documents** and **indexed chunks** there are and in what state: *indexed*, *indexing*, *queued*, *with error* or *duplicate* (a document that repeats another one and is not indexed twice). Documents are managed in [[Knowledge]].

## Tips
- If everything is zero, nothing has been ingested yet: create a proposal ([[Proposals]]).
- If episodes grow but facts do not, extraction is not working: check the LLM in [[AI providers]] and the failed [[Jobs]].
