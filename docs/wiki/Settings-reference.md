**English** · [Español](Referencia-de-ajustes)

# Settings reference

All the settings changed under **Administration** (instance administrator only), grouped by section. They apply **without a restart**. If the equivalent environment variable exists (`MIMIRSYNTH_<KEY_IN_UPPERCASE>`), it acts as the **default value**, and "Restore" goes back to it. The SMTP password is stored encrypted and not shown.

Not listed here because they are not single settings: the OIDC providers (each with its own fields, see [[OIDC identity]]), the AI engines ([[AI providers]]), the notification channels ([[Notifications]]) and each brain's own options, such as federation and secrets ([[Brains and members]]).

This page is generated from the code; see also [[Administration overview]].

## General

Guide: [[Administration overview]]

| Setting | Key | Default | Range or values | Description |
|---|---|---|---|---|
| Default language | `default_language` | `en` | `es` (Español) / `en` (English) | Language of the interface and emails for anyone who has not chosen their own in “My account”. Each person can change it. |

## Account security

Guide: [[Security and two-factor]]

| Setting | Key | Default | Range or values | Description |
|---|---|---|---|---|
| Minimum password length | `password_min_length` | `12` characters | 8–64 characters | Applied when creating or changing passwords. |
| Failed attempts before locking | `login_max_attempts` | `5` | 3–20 | After this many consecutive wrong passwords the account is temporarily locked. |
| Lockout duration | `lockout_minutes` | `15` min | 1–1440 min | How long an account stays locked after too many failed attempts. |
| Require two-factor | `require_2fa` | `no` | `no` (No) / `yes` (Yes, everyone) | Anyone signing in with a password must enable two-factor (authenticator app) before using the application. It does not affect those signing in through the identity provider, which applies its own rules. |
| Longest life of API tokens | `token_max_days` | `0` days | 0–3650 days | New tokens must expire within this time at most, also when they are rotated. 0: no limit. Existing ones do not change. |
| Validity of invitations and recovery links | `invite_days` | `7` days | 1–30 days | After this period the link stops working and another must be generated. |

## Email (SMTP)

Guide: [[SMTP email]]

| Setting | Key | Default | Range or values | Description |
|---|---|---|---|---|
| SMTP server | `smtp_host` | — | text | Needed to send invitations and recovery links by email. Without it, links are copied from Administration. |
| Port | `smtp_port` | `587` | 1–65535 | Typical: 587 (STARTTLS), 465 (SSL) or 25. |
| Encryption | `smtp_security` | `starttls` | `starttls` (STARTTLS) / `ssl` (SSL/TLS) / `none` (None) | STARTTLS (587), SSL/TLS (465) or none (trusted networks only). |
| User | `smtp_user` | — | text | Empty if the server does not require authentication. |
| Sender | `smtp_from` | — | text | Address shown as the sender, e.g. mimirsynth@example.com. |

## Identity

Guide: [[OIDC identity]]

| Setting | Key | Default | Range or values | Description |
|---|---|---|---|---|
| Public URL | `public_url` | — | URL | Address used to reach the application; it is used to build the sign-in return URL (e.g. https://mimirsynth.example.com). |
| Instance administrators | `admin_emails` | — | text | Emails (comma-separated) that become administrators the first time they sign in through OIDC, only if the provider marks the email as verified. |
| Account management | `account_url` | — | URL | Page at your provider where password, passkeys and two-factor are managed; it is linked from “My account”. |

## Documents

Guide: [[Folders and limits]]

| Setting | Key | Default | Range or values | Description |
|---|---|---|---|---|
| Maximum file size | `doc_max_mb` | `2048` MB | 1–20480 MB | Larger files are rejected when uploaded or when scanning folders. |
| Size of each upload part | `doc_part_mb` | `64` MB | 1–64 MB | Uploads are sent in parts of this size (maximum 64). |
| Maximum text extracted per document | `doc_text_max_mb` | `100` MB | 1–2048 MB | A document whose text exceeds this size is not indexed. |

## Recall

Guide: [[Recall and ingestion]]

| Setting | Key | Default | Range or values | Description |
|---|---|---|---|---|
| Minimum similarity of a passage | `doc_min_similarity` | `0.66` | 0–1 | Minimum cosine for a document passage to enter the recall. It depends on the embedding model; with nomic-embed-text, 0.66. |
| Document passages per recall | `doc_passages` | `2` | 0–10 | Maximum number of document passages that accompany the facts in each recall. |
| Maximum time of the document search | `doc_search_timeout` | `0.6` s | 0.1–10 s | If it takes longer, the recall answers without documents. |
| Text index synchronisation | `index_sync_minutes` | `10` min | 0–1440 min | How many minutes between copies of the episode text into the index. 0 = disabled. |

## Ingestion and jobs

Guide: [[Recall and ingestion]]

| Setting | Key | Default | Range or values | Description |
|---|---|---|---|---|
| Ingestion retries | `ingest_retries` | `4` | 1–20 | Attempts when the model answers with a rate limit or a transient error. |
| Batch size when changing the embedding model | `reindex_batch` | `64` texts | 1–512 texts | Texts per batch when recomputing the vectors with another model. Smaller spreads the load on the provider better. |
| Pause between batches when changing model | `reindex_pause` | `0` s | 0–600 s | Seconds to wait between batches to respect the provider's rate limit. On a 429 it also waits for whatever Retry-After says. |
| Model change wait | `reindex_switch_wait` | `60` s | 1–3600 s | Seconds the embedding model change waits for in-progress vector writes (ingestions, indexing) to finish. If they do not, the change is postponed and retried; writes are never cut off. |
| Alert about a stalled model change | `reindex_orphan_hours` | `24` h | 0–8760 h | Hours an embedding fill can stay failed or stalled, with its shadow vectors taking up memory, before alerting (event “reindex.orphan”). |
| Keep finished jobs | `jobs_keep_days` | `60` days | 1–3650 days | After this period finished, failed and cancelled jobs are deleted. |
| Retention: text of rejected proposals | `retention_rejected_days` | `0` days | 0–3650 days | After this period since it was rejected, a proposal loses its text (its status, authors and dates remain). Each brain can set its own. 0: no period. |
| Retention: finished jobs of each brain | `retention_jobs_days` | `0` days | 0–3650 days | After this period a brain's finished, failed and cancelled jobs are deleted, sooner than with the general period above. Each brain can set its own. 0: no period. |
| Keep scheduled rescans | `jobs_keep_scheduled_days` | `7` days | 1–365 days | Automatic rescans with no issues are noise (one every few minutes): they are deleted sooner. |

## Notifications

Guide: [[Notifications]]

| Setting | Key | Default | Range or values | Description |
|---|---|---|---|---|
| Repeated alert | `notify_cooldown_minutes` | `60` min | 1–10080 min | While a problem stays open it is not announced again on the channels until this time has passed (the bell only counts one more occurrence). A resolved problem announces the recovery. |
| Quiet from | `notify_quiet_start` | — | text | Time (HH:MM) from which only critical alerts are sent; the rest wait until the quiet period ends. Empty = no quiet hours. |
| Quiet until | `notify_quiet_end` | — | text | Time (HH:MM) when the quiet period ends. Server time is used. |
| Check status every | `notify_health_minutes` | `10` min | 0–1440 min | How many minutes between checks that the graph and the AI models respond (a model behind a paid key receives one minimal call). 0 = do not check. |
| Consecutive failures before alerting | `notify_health_failures` | `2` | 1–10 | How many checks in a row must fail before alerting that the graph or a model is not responding. With 2, a one-off provider error raises no alert. With 1 you are alerted on the first failure. |
| Notify about new versions | `notify_update_check` | `no` | `no` (No) / `yes` (Yes) | Once a day it asks GitHub whether a newer version exists. It is the only outbound connection the instance makes on its own; off by default. |
| Forbid private networks | `notify_block_private` | `no` | `no` (No) / `yes` (Yes) | Stops channels from pointing at private or local addresses (protects against a channel being used to reach internal services). Leave it on «No» if your ntfy or Gotify is on the local network. |
| Keep notifications | `notify_keep_days` | `30` days | 1–3650 days | After this time notifications and their delivery history are deleted. |
## How they are stored
- A setting is only stored if it **differs** from its default value.
- Changes to a setting are recorded in the [[Audit log]] (`settings.set`, `settings.reset`, `settings.secret`).
- Secrets are encrypted with a key derived from `MIMIRSYNTH_SESSION_SECRET`: if you change that secret you must enter them again.
