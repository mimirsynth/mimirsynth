# Federation between brains

A brain can lend read access to another brain. The receiving brain then sees, in its own recalls, what the lending brain knows, merged with its own and marked with where it came from. Nothing is copied: the data stays in the lending brain.

## What is lent

A grant goes from a **source** brain (the one that lends) to a **target** brain (the one that receives), with a scope:

| Scope | What the target can read |
|---|---|
| `graph` | Facts (current and expired) and episode fragments |
| `docs` | Document passages |
| `both` | Both of the above |

Never shared: embeddings, entity summaries, tokens, members, proposals, the ontology or anything that is not the content a query returns. Write access is never granted: `remember` always writes to the brain the token belongs to.

## Rules

- **Who grants.** An administrator of the source brain, who must also have access to the target brain. A brain you cannot see answers «not found», as everywhere else.
- **One way, one hop.** A→B does not give B access to A, and A→B plus B→C does not give C access to A.
- **Optional expiry** in days. An expired grant stops working by itself; it stays listed, marked as expired, until someone revokes it.
- **Immediate revocation.** The source revokes (or the target declines) and the next query no longer includes it. Deleting either brain removes its grants.
- **Audited.** Creating, changing and revoking a grant is recorded in the audit log. Each grant also shows when it was last used.
- **Not a role.** The target's members read the lent content with their own role in the target brain; a grant never raises anyone's role, and API tokens keep working only in their own brain.

## How a query uses it

`recall` (REST and MCP) queries the target brain and every source that lent to it, then merges the lists with weighted Reciprocal Rank Fusion (what the target already knows weighs a bit more than what it is lent). A fact the target already has is not repeated from a source. Lent items carry their origin: `· de «slug»` in the injected context and an `origin` field in the JSON result, plus a `federated` list with the state of each source (`ok`, `error`, `off`). A source that fails never breaks the query.

Pass `federated: false` to `recall` to get only the brain's own memory. The Query screen shows the origin of each lent item.

## Managing grants

Administration → Brains → Federation shows who this brain lends to (with scope, expiry, last use and a Revoke button) and who lends to it. The REST API is under `/api/brains/{slug}/grants` (`GET`, `POST`, `PATCH /{id}`, `DELETE /{id}`).
