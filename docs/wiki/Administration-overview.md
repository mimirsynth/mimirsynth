**English** · [Español](Visi%C3%B3n-general-de-la-administraci%C3%B3n)

# Administration overview

The gear icon in the side bar opens **Administration**. Sections are in a list on the left, grouped (on mobile, on top), and each one is a card with its title and description. The active section is in the address (`?seccion=…`), so you can link to it.

## What each person sees
- **Anyone** sees **Brain access** for the active brain: its name and role, what other brains lend it ([[Federation]]) and its API tokens.
- **Administrators of a brain** also manage its members, what it lends to other brains and its [[Secrets]] policy, and can edit it.
- **The instance administrator** sees every section.

## Map of sections
| Group | Section | Purpose | Page |
|---|---|---|---|
| **Brain** | Brain access | Create/edit/delete brains, members, federation, secrets and tokens | [[Brains and members]], [[Federation]], [[Secrets]] |
| **Accounts** | Users | Sign-ups, invitations, roles, locks | [[Administer users]] |
| | Security | Passwords, lockout, mandatory two-factor | [[Security and two-factor]] |
| | Identity | Sign-in with one or several external providers | [[OIDC identity]] |
| | Email (SMTP) | Sending invitations and recoveries | [[SMTP email]] |
| **AI models** | LLM model, Embeddings, Decider | The three engines, and changing the embedding model | [[AI providers]] |
| **Documents** | Folders | Roots of folder sources | [[Folders and limits]] |
| | Limits | Maximum file sizes | [[Folders and limits]] |
| **System** | General | Default language | [[Settings reference]] |
| | Recall | Document recall and index parameters | [[Recall and ingestion]] |
| | Ingestion and jobs | Retries, retention and the pace of an embedding model change | [[Recall and ingestion]] |
| | Notifications | Alert channels, delivery history and the instance's own checks | [[Notifications]] |
| | Metrics | The token that reads the Prometheus metrics at `/metrics` | [[Metrics]] |
| | Audit | Log of actions | [[Audit log]] |

All numeric and text parameters, with their defaults and ranges, are in [[Settings reference]].

## How settings work
- Each setting is a **row** with its name, its help and the control on the right.
- The **Save** and **Cancel** buttons only appear if you change something; **Restore** only if the value differs from the default.
- They apply **without a restart** (there is a cache of about 5 seconds, so it may take a moment to be noticed).
- Each field validates its format and range.
- **Secrets** (SMTP password, OIDC client secrets, engine keys, notification channel tokens) are stored **encrypted** and **never shown again**: to change them you must type a new one.
- Every change is recorded in the [[Audit log]] (secrets without their value).
- A setting's **default value** is its equivalent environment variable, if any, or the factory value. See [[Environment variables]].

## For a new instance
While no brain exists yet, the instance administrator's home page shows **First steps**: a **Create your first brain** button and a short checklist (AI models, an API token, connecting an agent) with links to each screen.
