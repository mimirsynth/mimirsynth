**English** · [Español](Federaci%C3%B3n)

# Federation

A brain can **lend read access** to another brain. The receiving brain then sees, in its own recalls, what the lending brain knows, merged with its own memory and marked with where it came from. Nothing is copied: the data stays in the brain that lends it, and the grant can be revoked at any time.

Typical use: a team brain that reads a shared "company" brain without anyone having to be a member of both, or a project brain that borrows the documentation of another.

## What can be lent
A grant goes from a **source** brain (the one that lends) to a **target** brain (the one that receives), with a scope (**What is lent**):

| Option | What the target can read |
|---|---|
| **Graph and documents** | Everything below |
| **Graph only (facts and episodes)** | Facts (current and expired) and fragments of the episode text |
| **Documents only** | Document passages |

**Never shared:** embeddings, entity summaries, members, tokens, proposals, the ontology or anything that is not the content a query returns. Write access is never lent: `remember` always writes to the brain its token belongs to.

## Lending a brain
In **Administration → Brain access → Federation**, with the source brain active. You must be an **administrator of the source brain** and have access to the target brain (a brain you cannot see is not offered).
1. **Lend to:** choose the target brain. A brain that already has a grant from this one is not listed: change or revoke the existing one instead.
2. **What is lent:** the scope.
3. **Days valid** (optional, 1–3650): empty means **no expiry**.
4. Press **Grant read access**.

The card then shows two lists:
- **This brain lends its read access to:** each target with **What is lent** (it can be changed in place), **Validity** (until a date, **expired** or **no expiry**), **Last used** and **Revoke**.
- **This brain receives read access from:** each source with its scope and validity. Every member of the brain sees this list; its administrators can **Decline** a grant they no longer want.

Revoking or declining takes effect on the **next query**. To lend again you create a new grant.

## Rules
- **One way, one hop.** A→B does not give B's memory to A, and A→B plus B→C does not give C access to A.
- **Expiry.** An expired grant stops working by itself; it stays listed, marked as **expired**, until someone revokes it.
- **Not a role.** The target's members read the lent content with their own role in the target brain. A grant never raises anyone's role and API tokens keep working only in their own brain.
- **Deleting a brain** removes every grant it gives or receives.
- **Audited.** Creating, changing and revoking a grant is recorded in the [[Audit log]] (`grant.create`, `grant.update`, `grant.revoke`), and each grant shows when it was last used.

## How recall uses it
The receiving brain's **recall** (REST, MCP and [[Ask]]) queries the brain itself and every source that lends to it, and merges the results with weighted reciprocal rank fusion: what the brain already knows weighs a little more than what it is lent.
- A fact the target already has is not repeated from a source, and the same document passage is kept only once.
- Every lent item carries its **origin**: [[Ask]] shows the source brain next to each fact, fragment and passage, and the context an agent receives marks it with `· from «slug»` (in the caller's language).
- A source that fails never breaks the query; it is simply left out.
- An agent can ask for the brain's own memory only, with `federated: false` in the recall. See [[Connect agents]].

Technical details: [docs/FEDERATION.md](https://github.com/MimirSynth/mimirsynth/blob/main/docs/FEDERATION.md).
