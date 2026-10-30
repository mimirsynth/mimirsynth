**English** · [Español](Auditor%C3%ADa)

# Audit log

The **Audit** section of administration (instance administrator only): the **log of administration and access actions**. It is used to know **who did what and when**.

## The table
It shows the **200 most recent actions**, with three columns:
- **Date.**
- **Action** (filterable): the type of event.
- **Detail**: the action's data (affected user, brain, role, etc.). With text search.
Each column can be sorted and filtered.

## What is recorded
| Family | Actions |
|---|---|
| **Access** | `login` (the detail says how: password, password and two-factor, passkey or a provider), `login.locked`, `setup` (first start), `password.set`, `password.change`, `password.forgot` |
| **Two-factor and passkeys** | `2fa.enable`, `2fa.disable`, `2fa.recovery`, `passkey.add`, `passkey.remove`, `user.mfa_reset` (also removes the person's passkeys) |
| **Users** | `user.create`, `user.status`, `user.role`, `user.link` (an invitation or reset link was generated), `user.logout`, `user.unlock`, `user.delete`, `user.autoprovision` |
| **Identity providers** | `oidc.create`, `oidc.update`, `oidc.delete`; `identity.link`, `identity.unlink` (a person links or unlinks a provider); `oidc.revoke.skipped` (the administrator role was not revoked after leaving the group because it was the last administrator) |
| **Brains and members** | `brain.create`, `brain.update` (including the description and the secrets policy), `brain.delete`, `member.set` (`via=oidc-default:<provider>` when it comes from a provider's initial access), `member.remove` |
| **Federation** | `grant.create`, `grant.update`, `grant.revoke` |
| **Tokens** | `token.create`, `token.revoke` |
| **Proposals** | `proposal.submit`, `proposal.approved`, `proposal.rejected`, `proposal.triage.*` (the decider's verdict), `proposal.ingested`, `proposal.failed`, `proposal.blocked` (rejected by the [[Secrets]] policy, with the rules, never the value) |
| **Secrets** | `secrets.scan` (counts per rule) |
| **Vocabulary** | `vocab.alias.add`, `vocab.alias.delete`, `vocab.revert`, `vocab.duplicates.ignore`, `vocab.*` (merges and entity and relation type changes), `ontology.update`, `retype.scan`, `retype.apply`, `retype.revert`, `conflict.resolve` (a contradiction resolved) |
| **Reference queries** | `refquery.create`, `refquery.update`, `refquery.delete`, `refquery.import`, `refquery.run` |
| **Documents** | `document.upload`, `document.delete`, `document.reindex`, `document.duplicates` (Find duplicates), `docsource.create/update/delete/scan`, `docroot.create/delete` |
| **AI providers** | `llm.*`, `embedding.*`, `decider.*` (create, update, delete, default); for an embedding model change also `embedding.reindex`, `embedding.reindex.filled`, `embedding.reindex.discard`, `embedding.switch` (with the backup confirmation) and `embedding.switched` |
| **Notifications** | `notify.channel.create`, `notify.channel.update`, `notify.channel.delete`, `notify.channel.test` |
| **Settings** | `settings.set`, `settings.reset`, `settings.secret` (without the secret's value) |
| **System** | `index.sync`, `job.cancel`, `job.retry` |
| **Account** | `account.profile`, `account.avatar`, `account.sessions.revoke` |

## What is **not** recorded
- The **values of secrets** (passwords, API keys, OIDC secrets, channel tokens): only that they were changed.
- **Credentials found in proposals and documents**: only the rule that matched. Whatever the detector flags in a proposal's title is hidden too ([[Secrets]]).
- Reading data (queries, recall).

## Your own activity
Each person sees their recent activity in [[My account]].

## Retention
The log is kept in the database with no automatic purge. It is part of the PostgreSQL backups ([[Upgrade and backups]]).
