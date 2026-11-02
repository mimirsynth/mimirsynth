[English](Metrics) · **Español**

# Métricas

`/api/health` dice si la instancia está viva ([[Instalación]], «Vigilar la instancia»), pero no cómo va: cuánto tarda el recall, cuántos trabajos esperan, cuántas llamadas a los motores de IA fallan. **`GET /metrics`** da todo eso en el formato de texto de Prometheus, para Prometheus o para cualquier agente que lo lea (Grafana Agent o Alloy, VictoriaMetrics, Telegraf, el plugin de Prometheus de una herramienta de monitorización…).

## Activarlo
Viene **desactivado**: sin token, `/metrics` responde `404`, como si no existiera. Para activarlo, genera un token y ponlo en `.env`:
```bash
# en .env
MIMIRSYNTH_METRICS_TOKEN=<la salida de: openssl rand -hex 32>
docker compose up -d
```
Desde entonces, una petición necesita `Authorization: Bearer <token>`; sin él, o con otro, responde `401`. Haber iniciado sesión en la interfaz no lo abre: solo el token. Un proxy inverso suele publicar todas las rutas, `/metrics` incluida, así que lo que la mantiene privada es el token; si Prometheus llega directamente al contenedor, también puedes bloquear `/metrics` en el proxy.

Compruébalo:
```bash
curl -s -H "Authorization: Bearer $MIMIRSYNTH_METRICS_TOKEN" http://localhost:8000/metrics | head
```

Prometheus:
```yaml
scrape_configs:
  - job_name: mimirsynth
    scrape_interval: 60s
    authorization:
      credentials_file: /etc/prometheus/mimirsynth.token   # el token, solo, en un fichero
    static_configs:
      - targets: ["mimirsynth:8000"]
```

## Qué mide
**Lo que pasa en la aplicación.** Se cuenta en memoria: empieza de cero en cada reinicio, así que se lee con `rate()` o `increase()`.

| Métrica | Etiquetas | Qué es |
|---|---|---|
| `mimirsynth_recall_seconds` (histograma) | `brain`, `part` | Tiempo de cada recall por partes: `embed` (el vector de la consulta), `facts`, `chunks`, `documents` y `total`. La búsqueda documental se mide hasta que termina, también cuando el recall ha dejado de esperarla |
| `mimirsynth_recall_documents_total` | `brain`, `state` | Recalls según el estado de su búsqueda documental: `ok`, `timeout` (tardó más que el «Tiempo máximo de la búsqueda documental»), `error` u `off` |
| `mimirsynth_job_seconds` (histograma) | `kind`, `status` | Tiempo de cada trabajo en segundo plano terminado, por tipo (`proposal.ingest`, `doc.index`, `doc.scan`…) y estado: `done`, `failed` o `cancelled`. La ingesta es `proposal.ingest` |
| `mimirsynth_ai_requests_total` | `kind`, `model`, `outcome` | Llamadas a los motores de IA (`llm`, `embedding`, `decision`) por resultado: `ok`, `rate_limited` (429), `server_error` (5xx) o `client_error` (otros 4xx) |
| `mimirsynth_ai_request_seconds` (histograma) | `kind`, `model` | Tiempo de las llamadas a los motores de IA que obtuvieron respuesta |
| `mimirsynth_ai_tokens_total` | `kind`, `model`, `direction` | Tokens enviados (`in`) y recibidos (`out`), los mismos que cuenta [[Consumo de IA]] |

**Lo que está guardado.** Se lee de la base de datos en cada consulta de Prometheus, así que sobrevive a los reinicios.

| Métrica | Etiquetas | Qué es |
|---|---|---|
| `mimirsynth_jobs` | `kind`, `status` | Trabajos `queued` (en cola) o `running` (en marcha) |
| `mimirsynth_jobs_oldest_queued_seconds` | `kind` | Antigüedad del trabajo más antiguo que sigue en cola |
| `mimirsynth_proposals` | `brain`, `status` | Propuestas por estado: `pending`, `approved`, `rejected`, `ingested`, `failed` |
| `mimirsynth_proposals_oldest_pending_seconds` | `brain` | Antigüedad de la propuesta más antigua que espera a un curador |
| `mimirsynth_documents` | `brain`, `status` | Documentos por estado: `pending`, `indexing`, `active`, `error` |
| `mimirsynth_notify_deliveries` | `status` | Envíos de notificaciones `pending` (pendientes) o `failed` (fallidos): si crecen, nadie está recibiendo los avisos |
| `mimirsynth_brain_entities`, `mimirsynth_brain_episodes` | `brain` | Tamaño del grafo de cada brain |
| `mimirsynth_brain_facts` | `brain`, `state` | Hechos `current` (vigentes) o `invalidated` (invalidados) |
| `mimirsynth_info` | `version` | Siempre 1; la etiqueta es la versión en marcha |

El tamaño de los grafos se cuenta en segundo plano **como mucho cada 5 minutos**, para que un grafo grande nunca retrase una consulta; justo después de arrancar falta hasta que termina el primer recuento. Si PostgreSQL y FalkorDB responden no está aquí: para eso está `/api/health`.

## Etiquetas
Las etiquetas son una **lista cerrada**: `brain` (el slug del brain), `kind`, `model`, `part`, `state`, `status`, `outcome`, `direction` y `version`, más `le` en los histogramas. Nunca una consulta, un documento, una persona ni texto de las memorias: multiplicarían las series y filtrarían contenido. Un test lo comprueba.

## Alertas de ejemplo
```yaml
groups:
  - name: mimirsynth
    rules:
      - alert: MimirSynthProposalsWaiting
        expr: mimirsynth_proposals_oldest_pending_seconds > 3 * 86400
        annotations: {summary: "Hay propuestas en {{ $labels.brain }} esperando a un curador desde hace más de 3 días"}
      - alert: MimirSynthJobsStuck
        expr: mimirsynth_jobs_oldest_queued_seconds > 1800
        annotations: {summary: "Un trabajo {{ $labels.kind }} lleva más de 30 minutos en cola"}
      - alert: MimirSynthAiErrors
        expr: sum by (kind, model) (rate(mimirsynth_ai_requests_total{outcome!="ok"}[15m])) > 0.1
        annotations: {summary: "El motor {{ $labels.kind }} {{ $labels.model }} está fallando"}
      - alert: MimirSynthSlowRecall
        expr: histogram_quantile(0.95, sum by (le) (rate(mimirsynth_recall_seconds_bucket{part="total"}[15m]))) > 2
        annotations: {summary: "El 95 % de los recalls tarda más de 2 segundos"}
      - alert: MimirSynthDeliveriesFailing
        expr: mimirsynth_notify_deliveries{status="failed"} > 0
        annotations: {summary: "Hay notificaciones que no se han podido enviar"}
```

## Grafana
[`docs/grafana/mimirsynth.json`](https://github.com/mimirsynth/mimirsynth/blob/main/docs/grafana/mimirsynth.json) es un panel de ejemplo: tiempo del recall por partes, documentos en el recall, trabajos, propuestas, llamadas y errores de los motores de IA y tamaño de cada brain. Impórtalo en Dashboards → New → Import y elige tu origen de datos de Prometheus.

## Límites
- Los contadores los guarda el proceso que sirve la API: un reinicio los pone a cero, cosa que Prometheus resuelve con `rate()` e `increase()`.
- Las trazas (OpenTelemetry) todavía no están disponibles.
