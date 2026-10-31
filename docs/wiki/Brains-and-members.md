**English** · [Español](Administrar-brains-y-miembros)

# Brains and members

The **Brain access** section of administration. It has five cards: the **active brain**, its **members**, **federation**, **secrets** (brain administrators only) and its **API tokens**. The active brain is the one you choose in the side bar selector.

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

## Export
A copy of this brain in a package (graph, curation, proposals, documents and reference queries; never members, tokens or secrets), optionally encrypted, to keep apart or to take to another instance. Prepared as a job and downloaded once. Only brain administrators see this card. See [[Export a brain]].

## Import a brain
The instance administrator can create a new brain from an exported package, in full or only its structure (ontology and aliases). The package is checked in full before anything is written, and a failure removes whatever was created. See [[Import a brain]].

## The brain's API tokens
Tokens for plugins and MCP, scoped to this brain. The token's role **never exceeds yours** and it cannot be administrator. They are shown **only once** when created. You can see the prefix, the owner and the last use, and **revoke** them. Usage in [[Connect agents]]. Your own tokens across all brains are also in [[My account]].
