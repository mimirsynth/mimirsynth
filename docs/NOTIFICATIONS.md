**English** · [Español](es/NOTIFICATIONS.md)

# Notifications

MimirSynth tells administrators when something needs attention: a model that stops responding, an ingestion that fails after its retries, a document source that cannot be synced, a new version. Alerts always appear in the **bell** of the interface; optionally they are also sent through **channels**.

What changed in a brain (new facts, proposals waiting…) is not an alert: each person can get it in a periodic **email summary**, set up in My account (see «My account» in the wiki).

## The bell

The bell (sidebar → Notifications) lists the alerts you can see and how many are unread.

- Instance administrators see every alert.
- A curator or administrator of a brain sees the alerts about that brain (failed ingestions, source errors), and nothing about the instance.
- A problem that repeats counts once («3 times») and is marked **resolved** when it clears.

## Events

| Event | Default severity | When |
|---|---|---|
| `model.unavailable` | critical | The default LLM, embedding or decider engine does not answer the periodic check |
| `graph.down` | critical | FalkorDB does not answer |
| `ingest.failed` | warning | An approved proposal could not be ingested after its retries |
| `job.failed` | warning | Any other background job failed |
| `docsource.error` | warning | A document source could not be synced |
| `security.lockout` | warning | An account was locked after too many failed sign-ins |
| `reindex.orphan` | warning | An embedding model change (shadow fill) has been failed or stalled for longer than the configured hours, with its shadow vectors taking up memory |
| `conflicts.found` | info | A brain has current facts that contradict each other in a single-valued relation (see «Single-valued relations and contradictions» in [ONTOLOGY.md](ONTOLOGY.md)); checked once a day |
| `refquery.regressed` | warning | After an embedding model change, a brain's reference queries stop finding expected items, or show new false positives, compared with the run before the change (as information if there is no earlier run to compare with) |
| `update.available` | info | A newer release exists (opt-in, see below) |

Messages carry metadata (what failed, where, how many times, a truncated error), **never the text of memories**.

## Channels

Administration → Notifications → Channels. Each channel chooses a **minimum severity** and, optionally, which events it receives (none selected = all). **Send test** delivers a test message right away and shows the result.

| Type | What you need |
|---|---|
| **Telegram** | The bot token (from @BotFather) and the chat ID; the bot must be in the chat. Optional group topic (`thread_id`) and a custom API server |
| **ntfy** | Server URL (default `https://ntfy.sh`), topic and, if protected, an access token |
| **Gotify** | Server URL and an application token |
| **Webhook** | A URL. With a signing key, each request carries `X-MimirSynth-Signature: sha256=<HMAC-SHA256 of the body>` so the receiver can verify it came from this instance |
| **Email** | Recipients. Uses the SMTP server of Administration → Email |

Webhook body:

```json
{"event": "model.unavailable", "kind": "alert", "severity": "critical", "title": "…", "body": "…", "brain": null, "count": 1, "instance": "MimirSynth · https://…", "ts": "2026-10-26T12:00:00+00:00"}
```

`kind` is `alert` or `recovery`. Tokens and keys are stored encrypted and are never shown again.

## Against noise

- **Grouping.** While a problem is open, the same event and key add to a counter instead of creating a new alert, and the channels are only notified again after the *repeated alert* period (default 60 minutes).
- **Recovery.** When the problem clears you get a «Recovered» message on the channels that received the alert.
- **Severity and events** per channel.
- **Quiet hours.** Between the two times set in Administration, only critical alerts are sent; the rest wait for the end of the quiet period.
- **Retries.** A failed delivery is retried with growing waits (1 min, 5 min, 30 min, 2 h, 12 h). After the last attempt it is marked failed; it appears in the delivery history, where an administrator can retry it by hand.

## Checks the instance runs

- Every *N* minutes (default 10; 0 = off) it checks FalkorDB and the default LLM, embedding and decider engines. A model behind a paid key receives one minimal call per check. An alert is only raised after **2 consecutive failures** (setting «Consecutive failures before alerting»; 1 = at the first one), so a one-off 500 or timeout from a provider does not notify; the recovery clears the count.
- **New versions** are checked once a day against the GitHub releases API, **only if you turn it on**. It is the only outbound connection the instance makes on its own.
- PostgreSQL cannot report its own outage (there would be nowhere to store the alert): watch it with an external monitor pointed at `GET /api/health`, which tells «application down» from «application alive, database down». See [Monitoring the instance](INSTALL.md#monitoring-the-instance).

## Security

- Only instance administrators create channels, and the URL is theirs to choose. Even so, links to the cloud metadata address (169.254.0.0/16) are always refused.
- **Forbid private networks** (off by default, because ntfy and Gotify often live on the LAN) also refuses private and local addresses.
- Redirects are not followed.
- Alert texts are stored in the language of the instance when they are generated.

## API

`GET /api/notifications` (the bell), `GET /api/notifications/summary`, `POST /api/notifications/read`; for instance administrators: `/api/notifications/channels` (CRUD, `POST /{id}/test`), `/api/notifications/deliveries` and `POST /deliveries/{id}/retry`.
