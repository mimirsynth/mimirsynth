**English** · [Español](Escribir-buena-memoria)

# Writing good memory

The quality of what MimirSynth remembers depends on what you tell it. A model extracts facts from your texts: if the text is clear, concrete and dated, the graph comes out clean; if it is vague, it comes out noisy. These guidelines apply to people and agents.

## The golden rules
1. **One concrete fact per idea, with exact proper names.** "On 12 October the production database moved from server db01 to server db02" is far better than "we migrated the database".
2. **Put the date.** If what you describe happened earlier, say so in the text (or in `reference_time` if you send it through the API). That way facts are ordered in time and old ones are invalidated properly.
3. **Always use the same name for the same thing.** "Server db02", not "the new one", "the database machine" and "db-2" in three different texts: duplicate entities would be created.
4. **Tell the change, not just the state.** "X now runs on Y (it used to run on Z)" makes clear what is invalidated. If an old value stays current next to the new one, and the relation is marked as single-valued, it shows up under Content quality → **Contradictions** for a curator to resolve.
5. **Write self-contained statements.** Each paragraph must be understood without the context of the conversation ("that" and "the thing from before" do not work).
6. **Include the why when it matters.** Decisions are worth more with their reason: "We chose PostgreSQL because…".

## What is worth remembering (and what is not)
| Yes | No |
|---|---|
| Decisions and their reason | Trivial conversation or greetings |
| Configuration and infrastructure changes | Data that changes every minute (live figures) |
| Causes of failures and how they were fixed | Secrets: passwords, keys, tokens |
| Procedures that will be repeated | Other people's personal information without need |
| Team preferences and rules | Text copied wholesale from a long document (better upload it to [[Knowledge]]) |

> **Never store secrets.** Everything that enters the graph is sent to the extraction LLM (which may be a third party's) and stays in the database. Write **where** a credential is kept ("in the team's password manager"), not its value. The brain's secret detector masks or blocks what looks like a credential, and a proposal with a possible secret always waits for a curator, but it is a safety net, not a licence.

## Size
- A proposal of **a few paragraphs** (up to ~50,000 characters technical maximum) is ideal. For long texts, **documents**.
- Better several small, clear proposals than one huge one.

## Confidence
The **confidence** field (0–1) indicates how much you trust the data. Use it honestly: an agent that is not sure should put 0.5, not 1. The reviewer and the decider take it into account.

## For agents
- Write **only what was learned** and is worth keeping, not a log of everything that happens. Over MCP this is the `remember` tool; tell the agent in its instructions when to use it ([[Claude Code integration]]).
- Use a **descriptive title** and a **self-contained text**.
- Check with recall first whether it is already recorded, to avoid repeating it.
- Use a **contributor** token: if you make a mistake, a curator rejects it.

## Documents or proposals
- Is it **a short, concrete statement** you want the system to remember and reason about? → **Proposal**.
- Is it **a long reference text** (a manual, a wiki page)? → **Document** ([[Knowledge]]). If a specific passage is important, **promote it to memory**.

## After writing
Look at the result in [[Facts]] and in the proposal's report ([[Proposals]]): was what you expected extracted? If the system creates many duplicate entities or odd relations, the problem is usually in the vocabulary (see [[Vocabulary]]) or in a too small extraction model ([[AI providers]]). To check over time that the important questions still bring the right answers, keep a few **reference queries** (Ask → Reference queries).
