**English** · [Español](Webhooks-de-entrada)

# Incoming webhooks

What happens in the infrastructure (an alert, a deployment, a pipeline, a failed backup) is exactly the episodic memory you look for later: «what happened to X last week?», «when was Y updated?». An **incoming webhook** lets a tool send those events to a brain, where they come in as **proposals** written as «what happened and when». Brain administrators manage them under Administration → Brain access → **Incoming webhooks**.

## Templates
Each webhook has a template that reads the JSON of its emitter:

| Template | Emitter | What becomes memory |
|---|---|---|
| **Alertmanager** | Prometheus Alertmanager, `webhook_configs` | Each alert of the group: firing opens it, resolved closes it |
| **CheckMK** | The notification script in `integrations/checkmk` | `PROBLEM` opens an alert and `RECOVERY` closes it; acknowledgements, downtimes and flapping are left out |
| **Uptime Kuma** | Notification «Webhook», JSON body | Down opens an alert and up closes it |
| **Proxmox VE** | Notification target «Webhook» (8.3 or later), with the body below | Each notification, as an event (a backup, a replication, fencing) |
| **GitHub Actions** | Repository webhook, events `workflow_run` and `deployment_status` | A finished run or a final deployment status |
| **GitLab CI** | Project webhook, pipeline and deployment events | A pipeline or deployment that finished (success, failed, canceled) |
| **Generic** | Any JSON | Title and text with `{{path}}` placeholders; optionally the paths of the date, the state and the fingerprint |

A body that announces nothing final (a pipeline still running, a GitHub ping) is accepted and ignored.

For **Proxmox VE**, set the webhook body to:
```json
{"title": "{{ escape title }}", "message": "{{ escape message }}", "severity": "{{ severity }}", "timestamp": {{ timestamp }}, "fields": {{ json fields }}}
```

The **Generic** template takes `{{campo.subcampo}}` placeholders (lists with their number, such as `alerts.0.labels.alertname`). With a **State** path, the values `resolved`, `ok`, `up` or `recovery` close the alert and any other value opens it; without it, every request is one event.

**Try the template** in the webhook's dialog: paste a sample JSON and see the events it would make, without creating anything.

## Address and secret
Each webhook has its address, `https://<instance>/api/brains/<slug>/hooks/<key>`, and a secret shown **once** when it is created (and again when you press **New secret**, which stops the old one at once). The emitter proves it has it in one of these ways:
- an **HMAC-SHA256 signature** of the body in `X-Hub-Signature-256` or `X-MimirSynth-Signature`, as `sha256=<hex>` (GitHub signs this way; the CheckMK script too);
- the secret itself in `Authorization: Bearer <secret>`, `X-Gitlab-Token` (GitLab's «Secret token») or `X-Webhook-Token`.

Comparisons are in constant time. An unknown address, a disabled webhook or a wrong secret all answer the same `401` and create nothing. The body is limited to 256 KB, and it must be JSON.

## From an event to a proposal
- Every event becomes a proposal of the brain, with the webhook in its source, and goes through the [[Secrets]] detector and then the decider and the curators like any other ([[Proposals]]). Nothing is invalidated by a webhook: the infrastructure ontology already has **Incident** and **Event** types, and the decider and the curators decide what each episode means.
- **Grouping.** An alert that keeps firing (the same fingerprint) does not make a proposal per notice: the repetitions are counted. If it resolves within *Group the alerts of a webhook* (15 minutes by default), it leaves **one** proposal with its start, its end and the number of notices. If it is still firing past that window (counted from the first notice received), one proposal says it is active, and another one says when it was resolved.
- **Trusted webhooks.** Marking a webhook as trusted approves its proposals without review. Use it only for reliable emitters: the daily cap still applies, and a proposal where the secret detector flags something always goes to review.

## Limits
- **Requests per minute** per webhook (60 by default): past it the answer is `429`, and the emitter retries.
- **Proposals per day** per webhook (200 by default): what goes over is kept in the log as «over the cap», without being proposed, and the `webhook.capped` notification warns once a day ([[Notifications]]). Proposals are calls to the AI engine: this protects the provider's rate limit and the brain's [[AI consumption]].

## The log
**Log** shows what each webhook received: the title, whether it was an alert or an event, how many notices, from when to when, its state and the proposals it became. **Nothing of the received body is kept.** The log is forgotten after 90 days. The list also shows how many requests came in, how many were rejected and the last problem (a wrong secret, a body that was not JSON, a request the template did not understand).

## API
`POST /api/brains/{slug}/hooks/{key}` answers `202` with the number of events and what happened to each (`open`, `grouped`, `resolved`, `proposed`, `capped` or `blocked`). Management, for brain administrators: `GET/POST /webhooks`, `PUT/DELETE /webhooks/{id}`, `POST /webhooks/{id}/rotate`, `GET /webhooks/{id}/events` and `POST /webhooks/preview`. See [[REST API]].
