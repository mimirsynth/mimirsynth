**English** · [Español](Métricas)

# Metrics

`/api/health` says whether the instance is alive ([[Installation]], «Monitoring the instance»), but not how it is doing: how long a recall takes, how many jobs are waiting, how many calls to the AI engines fail. **`GET /metrics`** gives all that in the Prometheus text format, for Prometheus or for any agent that reads it (Grafana Agent or Alloy, VictoriaMetrics, Telegraf, the Prometheus plugin of a monitoring tool…).

## Turning it on
It is **off** by default: without a token, `/metrics` answers `404`, as if it did not exist. To turn it on, generate a token and put it in `.env`:
```bash
# in .env
MIMIRSYNTH_METRICS_TOKEN=<the output of: openssl rand -hex 32>
docker compose up -d
```
From then on, a request needs `Authorization: Bearer <token>`; without it, or with another one, it answers `401`. Signing in to the interface does not open it: only the token does. A reverse proxy usually publishes every path, `/metrics` included, so the token is what keeps it private; if Prometheus reaches the container directly, you can also block `/metrics` in the proxy.

Check it:
```bash
curl -s -H "Authorization: Bearer $MIMIRSYNTH_METRICS_TOKEN" http://localhost:8000/metrics | head
```

Prometheus:
```yaml
scrape_configs:
  - job_name: mimirsynth
    scrape_interval: 60s
    authorization:
      credentials_file: /etc/prometheus/mimirsynth.token   # the token, alone in a file
    static_configs:
      - targets: ["mimirsynth:8000"]
```

## What it measures
**What happens in the application.** Counted in memory: they start again from zero on each restart, so read them with `rate()` or `increase()`.

| Metric | Labels | What it is |
|---|---|---|
| `mimirsynth_recall_seconds` (histogram) | `brain`, `part` | Time of each recall by part: `embed` (the query's vector), `facts`, `chunks`, `documents` and `total`. The document search is measured to its end, also when the recall stopped waiting for it |
| `mimirsynth_recall_documents_total` | `brain`, `state` | Recalls by state of their document search: `ok`, `timeout` (it took longer than «Maximum time of the document search»), `error` or `off` |
| `mimirsynth_job_seconds` (histogram) | `kind`, `status` | Time of each background job that finished, by kind (`proposal.ingest`, `doc.index`, `doc.scan`…) and status: `done`, `failed` or `cancelled`. Ingestion is `proposal.ingest` |
| `mimirsynth_ai_requests_total` | `kind`, `model`, `outcome` | Calls to AI engines (`llm`, `embedding`, `decision`) by outcome: `ok`, `rate_limited` (429), `server_error` (5xx) or `client_error` (other 4xx) |
| `mimirsynth_ai_request_seconds` (histogram) | `kind`, `model` | Time of the calls to AI engines that got an answer |
| `mimirsynth_ai_tokens_total` | `kind`, `model`, `direction` | Tokens sent (`in`) and received (`out`), the same ones [[AI consumption]] counts |

**What is stored.** Read from the database on each scrape, so they survive restarts.

| Metric | Labels | What it is |
|---|---|---|
| `mimirsynth_jobs` | `kind`, `status` | Jobs `queued` or `running` |
| `mimirsynth_jobs_oldest_queued_seconds` | `kind` | Age of the oldest job still waiting |
| `mimirsynth_proposals` | `brain`, `status` | Proposals by state: `pending`, `approved`, `rejected`, `ingested`, `failed` |
| `mimirsynth_proposals_oldest_pending_seconds` | `brain` | Age of the oldest proposal waiting for a curator |
| `mimirsynth_documents` | `brain`, `status` | Documents by state: `pending`, `indexing`, `active`, `error` |
| `mimirsynth_notify_deliveries` | `status` | Notification deliveries `pending` or `failed`: if they grow, nobody is getting the alerts |
| `mimirsynth_brain_entities`, `mimirsynth_brain_episodes` | `brain` | Size of each brain's graph |
| `mimirsynth_brain_facts` | `brain`, `state` | Facts `current` or `invalidated` |
| `mimirsynth_info` | `version` | Always 1; the label is the running version |

The size of the graphs is counted in the background **at most every 5 minutes**, so a large graph never slows a scrape; right after a start it is missing until the first count ends. Whether PostgreSQL and FalkorDB answer is not here: that is what `/api/health` is for.

## Labels
The labels are a **closed list**: `brain` (the brain's slug), `kind`, `model`, `part`, `state`, `status`, `outcome`, `direction` and `version`, plus `le` in the histograms. Never a query, a document, a person or any text of the memories: they would multiply the series and leak content. A test checks it.

## Example alerts
```yaml
groups:
  - name: mimirsynth
    rules:
      - alert: MimirSynthProposalsWaiting
        expr: mimirsynth_proposals_oldest_pending_seconds > 3 * 86400
        annotations: {summary: "Proposals in {{ $labels.brain }} have been waiting for a curator for more than 3 days"}
      - alert: MimirSynthJobsStuck
        expr: mimirsynth_jobs_oldest_queued_seconds > 1800
        annotations: {summary: "A {{ $labels.kind }} job has been waiting for more than 30 minutes"}
      - alert: MimirSynthAiErrors
        expr: sum by (kind, model) (rate(mimirsynth_ai_requests_total{outcome!="ok"}[15m])) > 0.1
        annotations: {summary: "{{ $labels.kind }} engine {{ $labels.model }} is failing"}
      - alert: MimirSynthSlowRecall
        expr: histogram_quantile(0.95, sum by (le) (rate(mimirsynth_recall_seconds_bucket{part="total"}[15m]))) > 2
        annotations: {summary: "95 % of recalls take more than 2 seconds"}
      - alert: MimirSynthDeliveriesFailing
        expr: mimirsynth_notify_deliveries{status="failed"} > 0
        annotations: {summary: "Some notifications could not be delivered"}
```

## Grafana
[`docs/grafana/mimirsynth.json`](https://github.com/mimirsynth/mimirsynth/blob/main/docs/grafana/mimirsynth.json) is an example dashboard: recall time by part, documents in the recall, jobs, proposals, AI engine calls and errors, and the size of each brain. Import it under Dashboards → New → Import and choose your Prometheus data source.

## Limits
- The counters are kept by the process that serves the API: a restart starts them again, which Prometheus handles with `rate()` and `increase()`.
- Traces (OpenTelemetry) are not available yet.
