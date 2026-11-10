**English** · [Español](Resumen)

# Overview

The home screen. It shows the state of the **active brain** at a glance: how much knowledge it holds, how it has evolved and what matters most in it. Apart from the **Getting started**, **To review** and **Movement** blocks, it is read-only.

## Getting started
Until you have tried the main parts of MimirSynth, the home screen starts with a **Getting started** list. Each step ticks itself when it happens in any of your brains (all of them, for an instance administrator), with no need to mark it, and shows the day it did:

| Step | Ticks when | Explained in |
|---|---|---|
| An agent makes its first recall | an agent recalls with an API token | [[Connect agents]] |
| The first proposal from an agent arrives | an agent sends a proposal | [[Proposals]] |
| The first proposal is approved | a curator, the decider or an auto-approval tier approves one (a curator's own, approved as it is sent, does not count) | [[Proposals]] |
| You add the first document or folder | a brain has a document, or a folder, wiki or repository as a source | [[Knowledge]] |
| You ask your first question in Ask | you search or ask for an answer in [[Ask]] yourself | [[Ask]] |
| You connect a second agent or invite another person | a brain has two live API tokens or two members (for an administrator, the instance has two users) | [[Brains and members]] |

Each pending step links to the screen where it is done and to its page in this wiki. A step stays ticked even if what showed it goes later (a revoked token, a recall log past its retention). The list disappears once every step is done; **Close the list** hides it for good, whatever is left. The list is yours: other people see their own.

## To review
Curators and above see first what is **waiting for a person's decision** in the brain, with the total at the top. Each line has its count, a note on what it is and a button to the tool where it is decided:

| Line | Button | Where it is decided |
|---|---|---|
| Proposals waiting for a decision (with the date of the oldest) | Review | [[Proposals]], filtered to pending |
| Pending corrections, from agents or from «incorrect» ratings | Review | [[Proposals]], filtered to pending corrections |
| Proposals whose ingestion failed | See | [[Proposals]] → Decided, filtered to failed |
| Entity summaries to approve | Review | [[Content quality]] → Summaries |
| Groups of possible duplicates | Merge | [[Content quality]] → Duplicates |
| Possible contradictions | Resolve | [[Content quality]] → Contradictions |
| Facts to review, past their shelf life | Review | [[Content quality]] → To review |
| Doubtful types with a proposed change (administrators only) | Correct | [[Content quality]] → Doubtful types |
| Reference queries that got worse in the last run | See | [[Ask]] → Reference queries |

Lines at zero are hidden, and when nothing is waiting it says «Nothing needs your attention». The pending proposals and what waits in Content quality also show as a counter next to **Proposals** and **Content quality** in the side menu. The counters are the same ones each page computes, kept for a minute so the home screen stays fast. Any change made in the brain (deciding a proposal, merging, resolving a contradiction, confirming a fact…) recalculates them, so it shows at once; what changes on its own (a fact going past its shelf life, an agent proposing over MCP, an ingestion that fails) shows within the minute. On a large brain, the first read after a change is slower, because the scans run then.

## Movement
Next to it, for the same people, **Movement** says what moved in the brain over the **last 24 hours**, the **last 7 days** or the **last 30 days** (you choose): new facts, invalidated facts, proposals received and decided, and documents added. Each figure has a small chart of the period (by hour over 24 hours, by day otherwise) and the comparison with the previous period of the same length, and opens its page. They are the same counts as the [[My account]] email summary, which sends them to whoever wants them without opening the application.

## What the brain knows
For everyone who can read the brain:
- **Totals:** current facts, invalidated ones (those that **stopped being true**, kept as history), entities, episodes and documents, each linking to its page, and since when there are episodes.
- **Weekly activity:** facts learned, episodes and facts invalidated per week, over the last **12 weeks**, **26 weeks** or **1 year**. It shows whether the brain is "alive" and whether there are peaks of change.
- **Most connected entities:** the nodes with most facts, usually the brain's central topics; each opens its entity page.
- **Entities by type:** the 6 classes with most entities. Many "untyped" or generic ones suggest working on the ontology ([[Vocabulary]]).
- **Documents:** how many are indexed and in how many chunks, and those queued, indexing or with an error. Documents are managed in [[Knowledge]].

## Memory health
Below, for curators and above, **Memory health** shows the last daily measurement of the brain: coverage of the reference queries, results with something outdated, noise, redundancy, open contradictions, proposals that are recalled and facts to review, each with the value of a week before. What cannot be measured in this brain (coverage without reference queries, for example) takes no card: it goes in one sentence, «Not measured», that says why. **Measure now** measures again. See [[Memory health]] for what each number means.

## AI usage
Next to it, for administrators of the brain only, what the brain has spent **this month** on AI engines: against its monthly budget when it has one (with the mark of the 80 % warning), where it will be by the end of the month at this rate, what it goes on (fact extraction, summaries, answers…, as a percentage of the tokens) and how many 429 responses the provider gave. **See the detail** opens Administration → AI consumption, where the budget is also set ([[AI providers]]).

## First steps (new instance)
An instance administrator who opens the home page while **no brain exists yet** sees **First steps** instead. The **Create your first brain** button opens the dialog to create it under Administration ([[Brains and members]]), and a short checklist links to each screen:
1. **Create a brain:** an isolated knowledge domain, with its own graph, ontology, members and tokens.
2. **Set up the AI models:** an LLM to extract facts and an embeddings engine, and test them ([[AI providers]]). Without them proposals are not ingested and recall returns nothing.
3. **Create an API token:** one per agent, for the brain it will use and with the Contributor role ([[My account]]).
4. **Connect an agent:** it reads the memory (recall) and proposes facts through the API or MCP ([[Connect agents]]).

Anyone else without access to a brain sees a message asking them to ask an administrator to add them.

## Tips
- If everything is zero, nothing has been ingested yet: create a proposal ([[Proposals]]).
- If episodes grow but facts do not, extraction is not working: check the LLM in [[AI providers]] and the failed [[Jobs]].
