**English** · [Español](Soluci%C3%B3n-de-problemas)

# Troubleshooting

First, look at the state: `docker compose ps`, `docker compose logs mimirsynth --tail 100` and `curl http://localhost:8000/api/health` (`200` with `"db": true, "graph": true` means the application reaches PostgreSQL and FalkorDB; `503` says which one fails). The bell in the sidebar also lists the alerts you can see. Then look for your symptom.

## Startup and installation
| Symptom | Cause and solution |
|---|---|
| `define POSTGRES_PASSWORD` / `define MIMIRSYNTH_SESSION_SECRET` | They are missing from `.env`. Set them |
| The application stops on start with an error about `MIMIRSYNTH_SESSION_SECRET` | With sign-in on, the default secret is not accepted: set a random one |
| Brains with odd names appear on first start | A trailing comment on the `MIMIRSYNTH_BOOTSTRAP_GRAPHS` line in `.env`. Remove line-end comments ([[Environment variables]]) |
| A variable in `.env` has no effect | The official compose only forwards the variables it lists under `environment:`. Add it there ([[Environment variables]]) |
| `bind: address already in use` | Port 8000 is taken: change `MIMIRSYNTH_PORT` |
| A service "unhealthy" | `docker compose logs <service>`. PostgreSQL/FalkorDB take a few seconds; if it persists, check memory and disk space. The application is also marked unhealthy while it cannot reach PostgreSQL or FalkorDB |
| Embeddings or the LLM fail with a connection error, with Ollama on the same Linux host | Ollama only listens on `127.0.0.1`: make it listen on all interfaces ([Preparing Ollama](Installation#preparing-ollama)). With your own `docker-compose.yml`, check that the `mimirsynth` service has `extra_hosts: ["host.docker.internal:host-gateway"]` |
| I cannot find the installation code | It only appears while there are no administrators; restart the container to generate a new one |
| The only administrator lost access | In the database, set `is_admin = false` for that user and restart: the first-start wizard returns |
| An update did not verify | `update.sh` tells you how to go back: `./update.sh --rollback` (add `--with-db` to restore the database too). See [[Upgrade and backups]] |

## Signing in
| Symptom | Cause and solution |
|---|---|
| "Incorrect email or password, or account temporarily locked" | Wrong password, disabled account or locked after several attempts. Wait out the lockout time or ask an administrator to unlock it |
| "Too many attempts" | IP/account limit; wait a few minutes |
| The password is not accepted when creating or changing it | The form lists every rule (minimum length, not your email or name, not common or a sequence, at least 5 different characters) and ticks the ones you meet; the disabled button says what is missing |
| The session is lost on reload (with HTTPS) | Use `MIMIRSYNTH_COOKIE_SECURE=true` only if you serve over HTTPS; and a correct `MIMIRSYNTH_PUBLIC_URL` |
| Passkeys are not offered or fail | They need HTTPS and the domain of `MIMIRSYNTH_PUBLIC_URL`; a passkey created on another domain does not work. Sign in with your password and register a new one ([[Security and two-factor]]) |
| The recovery email does not arrive | SMTP not configured, or request limit. See [[SMTP email]] |
| The invitation link "is not valid or has expired" | Used, expired (7 days) or replaced by a newer one: generate another ([[Administer users]]) |
| It asks for a 6-digit code and I cannot | Use a recovery code or a passkey, or have an administrator reset your two-factor |
| OIDC says you already have an account and must link the provider | The provider did not mark your email as verified, so it is not linked to an active account automatically. Sign in as usual and link the provider from My account → Security |
| The OIDC button fails | See the table in [[OIDC identity]] |

## Memory
| Symptom | Cause and solution |
|---|---|
| Approved proposals not ingested ("Approved") | No LLM configured: [[AI providers]] |
| **Failed** ingestions with "rate limit" | Your provider limits requests. Raise the retries ([[Recall and ingestion]]) and, if needed, lower `MIMIRSYNTH_INGEST_CONCURRENCY` (add it to the compose file); retry from [[Proposals]] |
| Failed ingestions with invalid JSON or empty answers | A "reasoning" model that does not return JSON. Use another model or a proxy that disables *thinking* |
| Malformed entities, entities missing, facts in English for a text in another language | The extraction model is too small (4B or less). Use one of about 14B or more, or a small API model with structured output ([[AI providers]]) |
| The proposal is ingested but produces 0 facts | Text with no concrete information, or failed extraction: check the [[Journal]] and [[Writing good memory]] |
| A proposal is rejected with `422` and a secret type | The brain **blocks** secrets. Remove the credential and write where it is kept instead |
| A curator's proposal stays pending | It contains a possible secret: a flagged proposal always waits for a person's review ([[Proposals]]) |
| Recall returns nothing | Empty brain, embeddings down or index not synchronised. [[Ask]]: look at the index status and "Reindex now" |
| Recall brings no document passages after changing the embedding model | Similarities of different models are not comparable: recalibrate "Minimum similarity of a passage" (Administration → Recall). Reference queries can simulate other thresholds |
| Embedding dimension errors | The embedding model was changed by hand while vectors of the previous one were stored. Change it only with **Reindex** under Administration → Embeddings, which recomputes every vector before switching ([[AI providers]]) |
| A model change is left half-way (`reindex.orphan` alert) | A shadow fill failed or stalled. In Administration → Embeddings, **Retry** or **Discard** it; discarding frees the memory it uses |
| An "AI model not responding" alert that solves itself | The health check alerts after 2 consecutive failures by default ("Consecutive failures before alerting", Administration → Notifications). Raise it if your provider has frequent one-off errors |
| "text index disabled" | The instance has no PostgreSQL with pgvector (e.g. development SQLite) |

## Documents
| Symptom | Cause and solution |
|---|---|
| A document stays "with error" | Hover the state or open the detail to see the reason. Causes: excessive size, PDF without text, embeddings down, or a secret when the brain blocks them |
| A document appears as **duplicate** | Its text repeats one already indexed in the brain, so it is not indexed twice; the detail links to the original. If the original goes away, the oldest duplicate is indexed in its place ([[Knowledge]]) |
| Upload fails with large files | Your proxy limits request size: lower "Size of each part" ([[Folders and limits]]) |
| "No authorised folders" | The instance administrator must register roots in [[Folders and limits]] |
| A scheduled scan fails with an empty folder | Protection: the volume was probably unmounted. Check the mount. A manual scan does empty the index |
| A wiki "cuts" the scan halfway | Expired key, outage or the wiki's rate limit. Nothing is deleted; check the key and rescan |

## Agents
| Symptom | Cause and solution |
|---|---|
| The MCP server answers `401` | The `Authorization: Bearer mst_…` header is missing or the token is not valid. MCP accepts only API tokens, never the browser session |
| The MCP server answers `403` "origin not allowed" | The request came from a web page of another origin. Agent clients do not send one; if you proxy it, do not add an `Origin` header |
| `remember` says the token can only read | The token has the reader role: create a contributor one ([[Connect agents]]) |
| Error messages come in another language | They follow `Accept-Language`, then the token owner's language, then the instance's. Send `Accept-Language` or compare status codes |

## Monitoring
| Symptom | Cause and solution |
|---|---|
| No alert arrived when PostgreSQL went down | It cannot alert about itself: alerts are stored there. Watch `/api/health` with an external monitor ([Monitoring the instance](Installation#monitoring-the-instance)) |

## Performance
- **Slow ingestion:** depends on the LLM. A faster model or more concurrency (if your provider allows it) speeds it up.
- **Slow interface with lots of data:** use filters and dates in [[Facts]] and reduce the "seeds" of the [[Graph]].
- **Slow graph (3D, no GPU):** set **Graphic effects** to **Reduced** on the [[Graph]] screen (it is stored per device), or go back to 2D.
- **Growing disk:** check the documents volume and the [[Jobs]] retention.

## How to ask for help
Open an [issue](https://github.com/MimirSynth/mimirsynth/issues) with: MimirSynth version, what you expected and what happened, and the steps to reproduce. **Check that logs contain no secrets** before pasting them. For vulnerabilities, use the [private security advisory](https://github.com/MimirSynth/mimirsynth/security/advisories/new), not a public issue.
