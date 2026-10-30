**English** · [Español](Secretos)

# Secrets

A memory is easy to fill with credentials by accident: a note that pastes a connection string, an agent that remembers a command with its token, a document with a private key. Before anything is stored, MimirSynth runs a **secret detector** over it, and each brain decides what to do with what it finds.

## When it runs
- Before a **proposal** is stored, wherever it comes from: the [[Proposals]] screen, the REST API or `remember` over MCP.
- Before a **document** is indexed (uploads, folders and wikis; see [[Knowledge]]).
- On the texts of a **reference query** (Ask → Reference queries), so saving a graph fact as an expected text does not copy a credential.

It does not use any AI model: it is a set of rules, quick and local.

## What it looks for
Findings are of two kinds:
- **Certain:** formats that cannot be mistaken. Private keys (PEM), AWS access keys, GitHub, GitLab, Slack, npm, Hugging Face and Telegram bot tokens, Slack webhooks, Google, Stripe, SendGrid and AI provider API keys, JWTs, `Authorization` headers and passwords inside a URL (`https://user:password@…`).
- **Possible:** a random-looking value assigned to a word such as `password`, `secret`, `token` or `api_key`. These are **only flagged**, never changed: randomness alone would also catch checksums, UUIDs and container IDs, which are normal in technical notes.

## What to do with a secret
Each brain chooses it in **Administration → Brain access → Secrets** (brain administrators):

| Mode | Certain secrets | Possible secrets |
|---|---|---|
| **Mask (recommended)**, the default | Replaced with `[secret removed: type]` before storing | Flagged |
| **Block** | The proposal is rejected with a message saying which type it is; the document is not indexed (and leaves the index if it was) | Flagged |
| **Only warn** | Flagged, left untouched | Flagged |

What this means in practice:
- A proposal with anything **flagged** always **waits for a curator**: the decider does not approve it and it is not approved on submission, even when a curator sends it. Its detail shows a **Secrets detected** notice with what was masked or flagged.
- In a document, the **indexed text** is masked (passages, vectors and search text). **The downloadable original is not modified**: it keeps the value as it is, and the document viewer says so.
- The marker is written in the instance's language, because it stays in memory.
- Changing the mode does not reprocess what is already stored. To apply it to a document, **reindex** it.

## Exceptions
The **Exceptions** box takes one entry per line:
- `rule:jwt` turns a rule off for this brain. The rule names are `private_key`, `aws_access_key`, `github_token`, `gitlab_token`, `slack_token`, `slack_webhook`, `google_api_key`, `ai_api_key`, `stripe_key`, `npm_token`, `huggingface_token`, `telegram_bot_token`, `sendgrid_key`, `jwt`, `authorization`, `url_credentials` and `assigned_secret` (the possible ones).
- Any other line is a **regular expression**: a detected value that matches it is not treated as a secret (for instance, the dummy keys of your examples).
- Lines starting with `#` are comments.

An expression that would accept everything (such as `.*`) is refused when saving, since it would turn the detector off; use `rule:` to turn off a single rule.

## Scan what is already stored
**Scan what is already stored** runs the detector, with the saved exceptions, over the brain's proposals and indexed documents **without changing anything**. Use it to measure hits and false positives before changing the mode or adding exceptions.
- It shows how many proposals and documents were scanned, a summary by **Type** (with **certain** or **possible**, **Occurrences** and how many items they are **In**) and the list of findings with **Where** they are and the **Preceding text**. The value itself is never shown.
- Only the first 500 items are listed; the counts are complete. A very large brain may stop at the text limit and say that some documents were not scanned.
- What is already in the **graph** is not scanned.
- Each scan is recorded in the [[Audit log]] (`secrets.scan`, with the counts per rule).

## What is never stored
The detected value never reaches the [[Audit log]], the logs, the API responses or the [[Notifications]]: only the rule and its position. In the audit log and in [[Jobs]], whatever is flagged in a proposal's title is hidden too. A blocked proposal is recorded as `proposal.blocked` with the rules, not the value.

Technical details: «Secrets» in [docs/ARCHITECTURE.md](https://github.com/MimirSynth/mimirsynth/blob/main/docs/ARCHITECTURE.md).
