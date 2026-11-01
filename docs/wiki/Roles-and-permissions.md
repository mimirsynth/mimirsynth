**English** · [Español](Roles-y-permisos)

# Roles and permissions

There are two levels: the **role within each brain** and the **instance role**.

## Role in a brain
Each role includes everything from the previous one.

| Role | Can |
|---|---|
| **Reader** | See the whole brain: [[Overview]], [[Journal]], [[Facts]], [[Graph]], [[Cypher query]], [[Knowledge]] (search and open documents), [[Ask]] and [[Vocabulary]] (read-only), including what other brains lend it ([[Federation]]). Create reader API tokens. |
| **Contributor** | Also **propose** memory ([[Proposals]]; it goes into quarantine) and **upload documents**. Sees their own proposals. |
| **Curator** | Also **approve or reject** proposals (their own are approved on submission, unless the [[Secrets]] detector flagged something), **edit, invalidate, reactivate and delete facts**, work in [[Content quality]] (resolve **contradictions**, confirm or invalidate **facts to review**), see what needs a decision under **Needs your attention** in [[Overview]], undo vocabulary operations, reindex the episode text and manage the brain's **reference queries** in [[Ask]] (create, import, run and simulate). Sees the brain's alerts in the [[Notifications]] bell. |
| **Administrator** | Also manage the **vocabulary** (aliases, entity types, ontology), **merge duplicates** and apply the **doubtful types** in [[Content quality]], the **document sources** (folders and wikis) and **Find duplicates** in [[Knowledge]], the brain's **members** and tokens, what it **lends** to other brains ([[Federation]]) and its **secrets** policy ([[Secrets]]), and edit the brain's name, description and slug. |
| **Owner** | Also **delete the brain**. |
| **Denied** | No access. It prevails over any other role. |

A federation grant is **not a role**: the members of the receiving brain read what it is lent with their own role there, and nobody's role goes up.

## Instance role
**Instance administration** is independent of brains. Whoever has it:
- creates brains and is an **implicit owner of all of them**;
- manages **users**, account security, email, OIDC, AI providers (including changing the embedding model), authorised folders and limits, notification channels, and sees the audit log (see [[Administration overview]]);
- sees **every alert** in the [[Notifications]] bell.

A person without that role only sees "Brain access" under Administration.

## API tokens
A token belongs to a user and to **a single brain**, and can never have more role than whoever created it. The maximum is **curator**: no token administers the instance. A token stops working if its account is disabled or deleted. It only works in its own brain, even if that brain receives memory from others through federation. See [[Connect agents]].

## Protection rules
- You cannot disable or delete yourself, or remove your own administrator role.
- The **last active administrator** cannot be deleted or demoted.
- Roles granted by the identity provider's groups are **revoked** when the person leaves the group, but those set by hand are never touched and "owner" is never granted by group. See [[OIDC identity]].
