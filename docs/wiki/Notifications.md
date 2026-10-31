**English** · [Español](Notificaciones)

# Notifications

MimirSynth tells you when something needs attention: a model that stops responding, an ingestion that fails after its retries, a document source that cannot be synced, a new version. Alerts always appear in the **bell**; an instance administrator can also send them to **channels** (Telegram, ntfy, Gotify, a webhook or email).

Alerts carry metadata only (what failed, where, how many times, a shortened error), **never the text of your memories**.

## The bell
**Notifications**, at the bottom of the side bar, opens the list of alerts you can see. Next to it, a counter shows the unread ones (red if one is critical) or, when everything is read, how many problems are still open.
- **Instance administrators** see every alert.
- **Curators and administrators of a brain** see the alerts about that brain (failed ingestions, source errors, contradictions, reference queries that got worse), and nothing about the instance.
- Each alert shows its severity (**Critical**, **Warning** or **Information**), whether it is **new**, and whether the problem is still **open** or already **resolved**. A problem that repeats counts once («3 times»).
- Filter **All** or **Unread**, and **Mark all as read**.

## Events
| Event | Severity | When |
|---|---|---|
| `model.unavailable` | critical | The default LLM, embedding or decider engine does not answer the periodic check |
| `graph.down` | critical | The graph (FalkorDB) does not answer |
| `ingest.failed` | warning | An approved proposal could not be ingested after its retries |
| `job.failed` | warning | Any other background job failed |
| `docsource.error` | warning | A document source could not be synced |
| `security.lockout` | warning | An account was locked after too many failed sign-ins |
| `reindex.orphan` | warning | An embedding model change has been failed or stalled for longer than the configured hours, with its shadow vectors taking up memory ([[AI providers]]) |
| `refquery.regressed` | warning | After an embedding model change, a brain's reference queries stop finding expected items or show new false positives. If there was no earlier run to compare with, it says so, as information |
| `token.expiring` | info | An API token expires within 7 days; announced once per token, with its name and prefix, never the token. A rotated token is not announced ([[Connect agents]]) |
| `conflicts.found` | info | A brain has current facts that contradict each other in a single-valued relation; checked once a day ([[Vocabulary]]) |
| `update.available` | info | A newer release exists (only if you turn it on, see below) |

## Channels
**Administration → Notifications → Channels** (instance administrator). **Add channel**, give it a **Name** and a **Type**:

| Type | What you need |
|---|---|
| **Telegram** | The **Bot token** (from @BotFather) and the **Chat** ID; the bot must be in the chat (group IDs start with `-100…`). Optionally a **Group topic** and your own **API server** |
| **ntfy** | **Server URL** (default `https://ntfy.sh`), **Topic** and, if protected, an **Access token**. On a public server anyone who knows the topic can read it: use a hard-to-guess name or your own server |
| **Gotify** | **Server URL** and an **Application token** |
| **Webhook** | A URL. With an **HMAC signing key**, each request carries `X-MimirSynth-Signature: sha256=<HMAC-SHA256 of the body>` so the receiver can check it came from this instance |
| **Email** | **Recipients**, comma-separated. Uses the server in [[SMTP email]] |

Each channel also has:
- **Minimum severity:** nothing below it is sent through this channel.
- **Events:** which ones it receives; with none selected, it receives all.
- **Channel enabled.**

**Send test** delivers a test message straight away and shows the result. Tokens and keys are stored encrypted and never shown again (leave the field empty when editing to keep them). The list shows each channel's last delivery and whether it worked.

The webhook body is JSON with `event`, `kind` (`alert` or `recovery`), `severity`, `title`, `body`, `brain`, `count`, `instance` and `ts`. More in [docs/NOTIFICATIONS.md](https://github.com/MimirSynth/mimirsynth/blob/main/docs/NOTIFICATIONS.md).

## Against noise
- **Grouping.** While a problem is open, the same event adds to a counter instead of creating a new alert, and channels are only notified again after **Repeated alert** (60 minutes by default).
- **Recoveries.** When the problem clears, the channels that received the alert get a «Recovered» message.
- **Severity and events** per channel.
- **Quiet hours.** Between **Quiet from** and **Quiet until** (server time) only critical alerts are sent; the rest wait for the end of the quiet period.
- **Retries.** A failed delivery is retried with growing waits (1 min, 5 min, 30 min, 2 h, 12 h). After the last attempt it is marked failed. **Delivery history** lists every delivery with its result (filter by status) and lets you **Retry** a failed one by hand.

## What the instance checks on its own
The settings at the bottom of the section:

| Setting | Default | What it does |
|---|---|---|
| **Repeated alert** | 60 min | Waiting time before a still-open problem is announced again on the channels |
| **Quiet from** / **Quiet until** | empty | Quiet hours (HH:MM). Empty = none |
| **Check status every** | 10 min | How often the graph and the default AI engines are checked. 0 = no checks. A model behind a paid key receives one minimal call per check |
| **Consecutive failures before alerting** | 2 | A one-off provider error does not raise an alert. 1 = alert at the first failure |
| **Notify about new versions** | No | Once a day it asks GitHub whether there is a newer release. It is the only outbound connection the instance makes on its own |
| **Forbid private networks** | No | Refuses channels pointing at private or local addresses. Leave it on «No» if your ntfy or Gotify lives on the local network |
| **Keep notifications** | 30 days | After that, alerts and their delivery history are deleted |

Links to the cloud metadata address are always refused, and redirects are not followed.

> PostgreSQL cannot report its own outage (there would be nowhere to store the alert). Watch it with an external monitor pointed at `GET /api/health`, which tells «application down» from «application alive, database down». See [Monitoring the instance](https://github.com/MimirSynth/mimirsynth/blob/main/docs/INSTALL.md#monitoring-the-instance).

Alert texts are stored in the instance's language when they are generated. Creating, changing, deleting and testing a channel is recorded in the [[Audit log]].
