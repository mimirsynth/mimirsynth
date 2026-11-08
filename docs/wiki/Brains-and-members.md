**English** · [Español](Administrar-brains-y-miembros)

# Brains and members

The **Brain** group of administration: one entry per topic of the active brain (the one you choose in the side bar selector), each in its own card:

| Entry | What it holds | Who sees it |
|---|---|---|
| **Active brain** | Name, slug and graph; **Edit**, **Delete**, **Create brain** and **Import a brain** | Anyone (creating and importing: the instance administrator) |
| **Members** | Who has access and with which role | Anyone with a role in the brain |
| **API tokens** | The brain's tokens | Anyone with a role in the brain |
| **Federation** | What it lends and what it receives | Anyone with a role in the brain (lending: its administrators) |
| **Secrets**, **Incoming webhooks**, **AI consumption**, **Export** | See below | Brain administrators |
| **Retention** | See below | The brain's owner |

Each entry has its own address (`?seccion=members`, `?seccion=federation`…). Links to the old single page (`/admin`, `?seccion=brains`) open **Active brain**.

## Creating a brain
Only the **instance administrator**. **Create brain** button:
- **Slug:** permanent identifier in lowercase letters, digits and hyphens (2–41 characters). It goes in the API addresses (`/api/brains/<slug>/…`).
- **Name:** what you will see in the interface.
- **Description** (optional): what the brain is about. The **decider** uses it, together with the brain's ontology, to judge whether a proposal fits in the brain ([[AI providers]]). Worth filling in if you use a decider.
- **Existing graph (optional):** name of the FalkorDB graph the brain will use (letters, digits, `_` and `-`). Empty means a new graph named after the slug. If a graph with that name already exists, the brain **adopts** it; if not, the graph is created on the first write.

As instance administrator you are an implicit owner of the brain you create.

## Editing a brain
Brain administrators (**Edit** button):
- **Name** and **Description**.
- **Slug.** If you change it, **tokens keep working** but you must **update the URL** in your hooks and plugins.
- **Graph** (instance administrator only): changing it **copies the graph under the new name, rewrites the group identifier of every node and edge and checks the counts**. The **original is kept** as a backup: delete it once you have checked everything is fine. Agents writing directly to Graphiti with the old name will keep writing to the old graph: they must be repointed.

## Deleting a brain
Only the **owner**. You must **type the slug** to confirm. Its members, API tokens, proposals, ontology, type corrections, documents, text index and federation grants are removed. Optionally the FalkorDB **graph is also deleted** (episodes, entities and facts). If you do not tick it, the graph is kept without a brain and can be associated again by creating a brain with that graph name. **It cannot be undone.**

## Members
Who has access to the brain and with what role ([[Roles and permissions]]). Only brain administrators manage its members.
- **Add by email:** type the email and choose the role. If that person **already has an account**, they get access immediately. If **not**, an **invited** account is created: they will be able to sign in once they accept an invitation ([[Administer users]]) or, if you use OIDC, when signing in with that verified email.
- **Change the role** of a member.
- **Remove:** the person loses access to the brain. **Their API tokens keep existing** until revoked.
- You cannot assign or modify a role **higher than yours**. Instance administrators appear marked as implicit owners.

## Federation
Lend this brain's memory, read-only, to another brain, or see which brains lend theirs to this one. Brain administrators grant, change and revoke; everyone with access to the brain sees what it receives. See [[Federation]].

## Secrets
What to do when a proposal or a document carries a password, a token or a key: **mask** it (the default), **block** it or **only warn**, plus a list of exceptions and **Scan what is already stored**. Only brain administrators see this card. See [[Secrets]].

## Retention
How long what is no longer useful is kept, only for the brain's **owner** (or the instance administrator):
- **Text of rejected proposals:** after this many days since it was rejected, a proposal loses its text (title, body, source, review note, the decider's reasoning and the correction's detail). Its status, authors and dates remain, and [[Proposals]] shows «(text purged)».
- **Finished jobs:** the brain's done, failed and cancelled jobs are deleted after this many days, sooner than with the instance's general period.
- **Recall ratings:** the ratings of the recall ([[Ask]]) and the logs of the queries they rated are deleted after this many days.

An empty field uses the instance's period ([[Settings reference]]: `retention_rejected_days`, `retention_jobs_days`) and **0 keeps forever**. By default there is no period, so nothing is purged until someone sets one. A daily job applies them and leaves a summary (the card shows the last one); **Purge now** runs it at once. Every change is audited (`brain.retention`). The audit log and the episodes are never purged from here.

## Right to be forgotten

MimirSynth invalidates instead of deleting, which is the base of its timeline. When someone asks for their data to be deleted, invalidating is not enough. The first step is a **report**: on an entity's page, the brain's owner opens **Right to be forgotten: see what would be deleted**. The report changes nothing. The same report is `POST /api/brains/{slug}/forget/report` with `entity` and `aliases`; it needs a session, not an API token.

- **What is looked for:** the entity, its name, its aliases and any other names given (an email, a nickname), as whole words, ignoring case and accents. Terms shorter than three characters are ignored.
- **What it says, layer by layer**, with what deleting would do there:
  - **Deleted:** the entity and its facts, the episodes that mention it, their chunks in the index, the recall sample and recall logs with their ratings, proposed summaries, jobs, notifications, and the confirmations, probes and dates of its facts.
  - **Text deleted:** proposals keep their status, authors and dates.
  - **Cleaned:** the graph copies kept to undo an entity merge, so the undo keeps working; replays of the sample, webhook events and the audit log.
  - **Blocked:** a Knowledge document that names it would not be indexed again until it changes at its source.
  - **To review, never deleted on their own:** facts and summaries of other entities that name it, other entities named like it, and reference queries.
  - **Out of reach:** backups, application logs and other systems.
- **Audit:** the audit log records `forget.report` with the entity's id and the counts per layer, never names or text.

**Deleting.** Under the report, **Delete for good** asks for the entity's name typed exactly, then runs as a job (`POST …/forget/run` with `entity`, `aliases` and `confirm`). It does what the report says, and it cannot be undone:
- **Before deleting episodes:** each episode that mentions the entity is sent to the brain's LLM, up to 50, to be written again without it. When something useful is left and the rewrite no longer names it, it becomes a pending proposal (category `forget.rewrite`) that a curator decides. Without an LLM, or with the AI budget spent, the episodes are deleted without a rewrite.
- **The graph:** the entity, its facts, the duplicates merged into it and the episodes are deleted. Deleting an episode removes only the facts no other episode supports; a shared fact just loses the reference. The graph copies kept to undo merges get the same deletions inside.
- **Documents:** a document that names it loses its chunks and is **blocked**. A sync does not index it again until it changes at its source. Re-indexing it by hand answers 409 unless it is asked on purpose (`unblock=true`).
- **The database:** proposals lose their text, and pending ones are rejected. Finished jobs are deleted, while running ones are reported as pending. In the cleaned tables, whatever names the entity becomes `[olvidado]`. Undoing old vocabulary changes that named it may stop working.
- **What stays:** what was «to review» is not touched. Note it down before deleting, because afterwards the entity no longer exists and the report cannot be made again.
- **Afterwards:** the job's parameters, which name the person, are wiped when it ends. Its result and the audit row (`forget.run`) keep only counts per layer.

## Incoming webhooks
Alerts, deployments and other events from your tools as the brain's episodic memory: each webhook has its address, its secret and a template for its emitter (Alertmanager, CheckMK, Uptime Kuma, Proxmox VE, GitHub Actions, GitLab CI or a generic one), with a daily cap of proposals. Only brain administrators see this card. See [[Incoming webhooks]].

## Export
A copy of this brain in a package (graph, curation, proposals, documents and reference queries; never members, tokens or secrets), optionally encrypted, to keep apart or to take to another instance. Prepared as a job and downloaded once. Only brain administrators see this card. See [[Export a brain]].

## Import a brain
The instance administrator can create a new brain from an exported package, in full or only its structure (ontology and aliases). The package is checked in full before anything is written, and a failure removes whatever was created. See [[Import a brain]].

## The brain's API tokens
Tokens for plugins and MCP, scoped to this brain. The token's role **never exceeds yours** and it cannot be administrator. They are shown **only once** when created. You can see the prefix, the owner and the last use, and **revoke** them. Usage in [[Connect agents]]. Your own tokens across all brains are also in [[My account]].
