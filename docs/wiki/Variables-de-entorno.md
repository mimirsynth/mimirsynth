[English](Environment-variables) · **Español**

# Variables de entorno

El entorno (`.env`) lleva **solo lo necesario para arrancar y conectar**. Todo lo demás se cambia en [Administración](Visión-general-de-la-administración) y se aplica sin reiniciar; si una variable equivalente existe, solo hace de **valor por defecto** (ver [[Referencia de ajustes]]).

Plantilla comentada: `env.example` en la [última release](https://github.com/MimirSynth/mimirsynth/releases/latest) (o [`.env.example`](https://github.com/MimirSynth/mimirsynth/blob/main/.env.example) en el repositorio). Cópiala a `.env`, que **no se sube al repositorio**.

> **Sin comentarios al final de línea.** `CLAVE=valor  # comentario` hace que Docker Compose lea el comentario como parte del valor. Pon los comentarios en su propia línea.

> **A la aplicación solo llega lo que pasa el fichero de Compose.** El `docker-compose.yml` oficial enumera, en el `environment:` del servicio `mimirsynth`, las variables que toma de `.env`: las de las tablas de abajo, salvo que una fila diga otra cosa. Para usar otra variable `MIMIRSYNTH_*` (por ejemplo `MIMIRSYNTH_INGEST_CONCURRENCY`), añádela también ahí; escribirla solo en `.env` no tiene efecto.

## Obligatorias
| Variable | Descripción |
|---|---|
| `POSTGRES_PASSWORD` | Contraseña de PostgreSQL. Genérala con `openssl rand -hex 32` |
| `MIMIRSYNTH_SESSION_SECRET` | Firma las sesiones y **cifra** los secretos guardados en la base de datos (claves de los proveedores, contraseña SMTP, secretos OIDC y de los canales de notificación). **Guárdala**; si cambia hay que reintroducir esos secretos. La aplicación **no arranca** con el valor por defecto en modo con login |

## Conexión y arranque
| Variable | Por defecto | Descripción |
|---|---|---|
| `MIMIRSYNTH_VERSION` | `latest` | Versión de la imagen que se ejecuta (una etiqueta de release como `0.8.0`). Solo Compose; `update.sh` la fija por ti ([[Actualización y copias de seguridad]]) |
| `MIMIRSYNTH_PORT` | `8000` | Puerto del host en el que se publica la aplicación. Solo Compose |
| `MIMIRSYNTH_FALKOR_HOST` | `falkordb` (compose) / `localhost` | Host de FalkorDB |
| `MIMIRSYNTH_FALKOR_PORT` | `6379` | Puerto de FalkorDB |
| `MIMIRSYNTH_DATABASE_URL` | SQLite local | Base de datos del plano de control. En producción, PostgreSQL con pgvector (`postgresql+psycopg://…`). El compose oficial la construye a partir de `POSTGRES_PASSWORD`: no la pongas en `.env` |
| `MIMIRSYNTH_BOOTSTRAP_GRAPHS` | vacío | Grafos existentes a adoptar como brains **solo en el primer arranque**: `slug:Nombre,otro:Otro`. Las entradas con formato inválido se ignoran con un aviso |
| `MIMIRSYNTH_DEFAULT_GRAPH` | `default` | Grafo por defecto |
| `MIMIRSYNTH_STATIC_DIR` | — | Carpeta de la web compilada (la fija la imagen Docker) |
| `MIMIRSYNTH_CORS_ORIGINS` | `*` | Orígenes CORS permitidos. Con `*` solo se admite `http://localhost:5173` (desarrollo). Solo hace falta tocarlo si sirves la web desde otro dominio. El compose oficial no la pasa |

## Acceso, direcciones e idioma
| Variable | Por defecto | Descripción |
|---|---|---|
| `MIMIRSYNTH_AUTH_MODE` | `local` | `local`: cuentas propias (y OIDC si se configura). `off`: **solo desarrollo**, sin login, todos son administradores |
| `MIMIRSYNTH_PUBLIC_URL` | vacío | URL pública, con HTTPS en producción. Se usa para la URL de retorno de OIDC, los enlaces de invitación y recuperación y las **llaves de acceso**: su dominio es el identificador de la parte que confía (*relying party*) de las llaves, así que defínela antes de que nadie registre una (cambiar de dominio después las invalida). El servidor MCP solo acepta peticiones de navegador desde este origen. También se edita en Administración → Identidad |
| `MIMIRSYNTH_COOKIE_SECURE` | `false` | `true` si sirves por HTTPS |
| `MIMIRSYNTH_DEFAULT_LANGUAGE` | `en` | Idioma por defecto (`en` o `es`) de la interfaz y los correos para quien no haya elegido uno, y último recurso para el idioma de los errores de la API, los textos del MCP y los encabezados del recall ([[Conectar agentes]]). También en Administración → General |
| `MIMIRSYNTH_ADMIN_EMAILS` | vacío | Emails que pasan a administradores de la instancia la primera vez que entran por OIDC, **solo con un email que el proveedor marque como verificado** |
| `MIMIRSYNTH_ACCOUNT_URL` | vacío | Página de tu proveedor de identidad donde se gestionan contraseña, llaves de acceso y doble factor; se enlaza desde Mi cuenta |
| `MIMIRSYNTH_OIDC_*` | — | **Solo se leen una vez**, en el primer arranque tras actualizar a la 0.5, para importar el proveedor que tuvieras como `oidc`. Después los proveedores se gestionan en Administración → Identidad y estas variables se pueden quitar |

## Motores por defecto
Se usan **solo si no hay ningún motor configurado en la interfaz** ([[Proveedores de IA]]).
| Variable | Por defecto | Descripción |
|---|---|---|
| `MIMIRSYNTH_EMBEDDING_BASE_URL` | `http://host.docker.internal:11434/v1` (compose) | Endpoint de embeddings: por defecto, Ollama en el mismo host (el compose asocia ese nombre al host, también en Linux). Debe ser el mismo que use Graphiti sobre ese FalkorDB |
| `MIMIRSYNTH_EMBEDDING_MODEL` | `nomic-embed-text` | Modelo |
| `MIMIRSYNTH_EMBEDDING_API_KEY` | vacío | Clave |
| `MIMIRSYNTH_EMBEDDING_DIM` | `768` | Dimensión del modelo |
| `MIMIRSYNTH_LLM_BASE_URL` | vacío | Endpoint del LLM. **Vacío = ingesta desactivada** |
| `MIMIRSYNTH_LLM_API_KEY` | vacío | Clave |
| `MIMIRSYNTH_LLM_MODEL` | vacío | Modelo |
| `MIMIRSYNTH_LLM_SMALL_MODEL` | vacío | Modelo pequeño opcional (por defecto el mismo) |
| `MIMIRSYNTH_INGEST_CONCURRENCY` | `2` | Llamadas simultáneas al LLM por ingesta. **Solo se lee al arrancar** y el compose oficial no la pasa (añádela ahí); bájala si tu proveedor limita las peticiones |

**Después de cambiar el modelo de embeddings** desde la interfaz (**Reindexar** en Administración → Embeddings), el modelo vive en la interfaz y las `MIMIRSYNTH_EMBEDDING_*` conservan sus valores antiguos. Solo cuentan en una instalación nueva (que crea el índice con `MIMIRSYNTH_EMBEDDING_DIM`) y como último recurso cuando **no** hay ningún motor registrado: mantén un motor registrado o actualízalas al modelo y la dimensión nuevos.

## Documentos
| Variable | Por defecto | Descripción |
|---|---|---|
| `MIMIRSYNTH_SOURCES_DIR` | `./sources` | Carpeta del **host** montada en solo lectura en `/sources`. Solo Compose |
| `MIMIRSYNTH_DOC_STORE` | `/data/documents` | Volumen con los originales subidos. **Entra en las copias de seguridad**. Fija en el compose oficial |
| `MIMIRSYNTH_DOC_ROOTS_BASE` | `/sources` | Las raíces de carpetas solo pueden estar bajo esta ruta. Fija en el compose oficial |

## Valores por defecto de ajustes (opcionales)
Estas variables existen, pero **se gestionan desde la interfaz**; defínelas solo si quieres otro valor de partida (y añádelas al fichero de Compose): `MIMIRSYNTH_DOC_MAX_MB` (el compose la pasa), `…_DOC_PART_MB`, `…_DOC_TEXT_MAX_MB`, `…_DOC_MIN_SIMILARITY`, `…_DOC_PASSAGES`, `…_DOC_SEARCH_TIMEOUT`, `…_INDEX_SYNC_MINUTES`, `…_INGEST_RETRIES`, `…_REINDEX_BATCH`, `…_REINDEX_PAUSE`, `…_REINDEX_SWITCH_WAIT`, `…_REINDEX_ORPHAN_HOURS`, `…_JOBS_KEEP_DAYS`, `…_JOBS_KEEP_SCHEDULED_DAYS`, `…_NOTIFY_*` (aviso repetido, horas de silencio, comprobaciones de estado, aviso de versiones, redes privadas, conservación), `…_PASSWORD_MIN_LENGTH`, `…_LOGIN_MAX_ATTEMPTS`, `…_LOCKOUT_MINUTES`, `…_INVITE_DAYS`, `…_REQUIRE_2FA` y las de SMTP (`…_SMTP_*`). Tabla completa en [[Referencia de ajustes]].
