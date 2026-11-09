[English](../CONFIGURATION.md) · **Español**

# Configuración

La configuración tiene dos niveles:

1. **Entorno (`.env`):** solo lo necesario para arrancar y conectar. Se lee al iniciar.
2. **Interfaz (Administración):** todo lo demás. Se aplica sin reiniciar y cada cambio queda en la auditoría. Si una variable de entorno equivalente existe, hace de valor por defecto, y «Restaurar» en la interfaz vuelve a él.

## Variables de entorno
Plantilla comentada: `env.example` en la [última release](https://github.com/MimirSynth/mimirsynth/releases/latest) (o [`.env.example`](../../.env.example) en el repositorio).

| Variable | Por defecto | Descripción |
|---|---|---|
| `POSTGRES_PASSWORD` | – | Contraseña de PostgreSQL (obligatoria) |
| `MIMIRSYNTH_SESSION_SECRET` | – | Firma las sesiones y cifra los secretos guardados (obligatoria) |
| `MIMIRSYNTH_PORT` | `8000` | Puerto publicado en el host |
| `MIMIRSYNTH_GRAPH_BACKEND` | vacío | `falkordb` o `neo4j`. Vacía, y también `MIMIRSYNTH_FALKOR_HOST` y `MIMIRSYNTH_NEO4J_URI`: la conexión guardada en **Administración → Base de datos del grafo** o, sin ella, el FalkorDB incluido. Ver [Base de datos de grafos](#base-de-datos-de-grafos) |
| `MIMIRSYNTH_FALKOR_HOST` / `_PORT` | vacío / `6379` | Un FalkorDB existente |
| `MIMIRSYNTH_FALKOR_USERNAME` / `_PASSWORD` | vacío | Credenciales de un FalkorDB existente |
| `MIMIRSYNTH_NEO4J_URI` / `_USER` / `_PASSWORD` / `_DATABASE` | vacío | Un Neo4j existente (`bolt://host:7687`; base de datos vacía: la predeterminada del servidor) |
| `COMPOSE_PROFILES` | vacío | Perfiles que arranca un simple `docker compose up -d`: `bundled` (FalkorDB), `ollama` (embeddings), `ocr`. Lo define el instalador |
| `MIMIRSYNTH_BOOTSTRAP_GRAPHS` | vacío | Grafos existentes a adoptar como brains en el primer arranque (`slug:Nombre,otro:Otro`) |
| `MIMIRSYNTH_AUTH_MODE` | `local` | `local` (cuentas propias, OIDC opcional) o `off` (solo desarrollo, sin inicio de sesión) |
| `MIMIRSYNTH_PUBLIC_URL` | vacío | URL pública, para OIDC, enlaces de invitación y **llaves de acceso** (su dominio es el identificador de la parte confiante: defínela, con HTTPS, antes de que nadie registre una) |
| `MIMIRSYNTH_COOKIE_SECURE` | `false` | `true` si sirves por HTTPS |
| `MIMIRSYNTH_EMBEDDING_*`, `MIMIRSYNTH_LLM_*` | vacío | Motores por defecto si aún no hay ninguno configurado en la interfaz |
| `MIMIRSYNTH_SOURCES_DIR` | `./sources` | Carpeta del host montada en solo lectura en `/sources` |

## Base de datos de grafos
Cada instancia guarda los grafos de conocimiento de sus brains en una base de datos de grafos. De dónde sale su conexión, por este orden:
1. **El entorno**, cuando `MIMIRSYNTH_GRAPH_BACKEND`, `MIMIRSYNTH_FALKOR_HOST` o `MIMIRSYNTH_NEO4J_URI` tienen valor (el instalador las escribe cuando eliges una base de datos existente). Manda sobre la interfaz, que la muestra en solo lectura; se cambia en `.env`, con un reinicio.
2. **Administración → Base de datos del grafo**: un administrador pone el servidor (FalkorDB o Neo4j, host, puerto, usuario, contraseña, TLS y, con Neo4j, la base de datos) y lo prueba. La prueba comprueba que la dirección responde, las credenciales, la versión y que se puede escribir (un nodo de prueba que se crea y se borra en el acto), y lista los grafos o `group_id` que ya tiene la base de datos, con sus nodos. Una conexión que no pasa la prueba no se puede guardar. Al guardarla, la instancia pasa a usarla sin reiniciar, y la contraseña se guarda cifrada con `MIMIRSYNTH_SESSION_SECRET`.
3. **El FalkorDB incluido** (perfil `bundled`, `MIMIRSYNTH_FALKOR_BUNDLED_HOST`, que compose pone a `falkordb`), cuando ninguno de los anteriores dice nada.

Para gestionar desde la interfaz una conexión que está en `.env`, quita esas variables de `.env` y reinicia. `/api/health` y `/api/ai-status` dicen qué backend está en uso (`backend`).

| Backend | Versiones soportadas | Un brain es | Conexión |
|---|---|---|---|
| `falkordb` (por defecto) | FalkorDB 4.x (la CI usa v4.22.0) | un grafo propio | El incluido (perfil `bundled`) o uno existente: `MIMIRSYNTH_FALKOR_HOST` / `_PORT`, y `_USERNAME` / `_PASSWORD` si tiene usuarios ACL |
| `neo4j` | Neo4j 5.26 LTS o posterior, Community o Enterprise (la CI usa 5.26 Community) | los nodos cuyo `group_id` es su nombre, en una sola base de datos | `MIMIRSYNTH_NEO4J_URI` (`bolt://` o `neo4j://`), `_USER`, `_PASSWORD` y `_DATABASE` (vacío: la predeterminada del servidor) |

Qué cambia con Neo4j:
- Los brains comparten la base de datos. MimirSynth limita cada consulta al `group_id` del brain, igual que hace Graphiti con las suyas, y la consola Cypher de solo lectura solo ejecuta lo que sabe limitar (ver [Aislamiento entre brains con Neo4j](#aislamiento-entre-brains-con-neo4j)).
- Enterprise se usa igual, con una sola base de datos. MimirSynth no crea una base de datos por brain.
- Una exportación lleva solo la copia JSON del grafo, porque Neo4j no tiene una copia exacta (volcado) como la de FalkorDB. Un paquete exportado desde FalkorDB entra en Neo4j por su copia JSON, y al revés.
- La comprobación de memoria libre antes de cambiar el modelo de embeddings solo existe con FalkorDB. Con Neo4j, vigila tú la memoria del servidor.
- 5.26 es la versión más antigua cuyo Cypher pone etiquetas y tipos de relación a partir de los datos, algo que necesita la copia de un brain (la instantánea antes de fusionar entidades o el cambio de nombre del grafo de un brain).

Hay un backend por instancia, y cambiarlo, en `.env` o en Administración → Base de datos del grafo, no mueve los datos: un brain cuyo grafo no esté en la base de datos nueva se ve vacío hasta que vuelves a la anterior. Para llevar brains de uno a otro, expórtalos e impórtalos en una instancia con el otro backend.

### Aislamiento entre brains con Neo4j
Con FalkorDB cada brain es un grafo propio, y una consulta no puede llegar a otro brain. Con Neo4j los brains comparten una base de datos, y es MimirSynth quien los separa, no la base de datos:
- **Acotado.** Antes de ejecutar una consulta, MimirSynth reescribe su Cypher para que cada patrón de nodo lleve el `group_id` del brain, como un parámetro que la consulta no puede sustituir. Una relación está en un brain cuando sus dos extremos lo están. Un patrón de nodo que no sabe leer se rechaza; nunca se ejecuta sin acotar.
- **Una comprobación de los resultados.** Un nodo o una relación de otro brain en un resultado se rechaza, lo que cubre lo que el acotado no ve, como los resultados de un procedimiento. La comprobación ve nodos, relaciones y caminos, no valores escalares (`n.name`, `count(*)`): esos dependen solo del acotado.
- **La consola Cypher de solo lectura** ejecuta Cypher que escriben personas, así que con Neo4j solo ejecuta lo que sabe acotar, y dice por qué rechaza lo demás:
  - `CALL`, `SHOW`, `USE`, `LOAD` y `TERMINATE`: los procedimientos y las otras bases de datos quedan fuera del acotado.
  - Cualquier función que no sea de las propias de Neo4j (`SHOW FUNCTIONS`, sin `graph.*`). No se ejecuta ninguna función de un plugin, tampoco las de APOC, y algunas de ellas ejecutan Cypher escrito en una cadena.
  - Las relaciones de longitud variable (`-[*1..3]-` y, por tanto, `shortestPath`) y los caminos y relaciones cuantificados (`((a)-->(b)){1,3}`, `-->+`): sus nodos intermedios no tienen un patrón que acotar.
  - Las expresiones de etiqueta que no sabe leer (`:%`, `IS`, `:(A|B)`, etiquetas dinámicas `:$(…)`), los comentarios, los parámetros, los caracteres fuera de ASCII fuera de las cadenas y los escapes `\u`, que Neo4j decodifica antes de leer la consulta.
- **Qué exige a la base de datos.** Una base de datos solo para MimirSynth o, al menos, una en la que ninguna otra aplicación escriba relaciones entre nodos de `group_id` distintos. MimirSynth no necesita ningún plugin: no usa APOC y la consola no llega a él, así que no hay motivo para instalarlo por MimirSynth. Quien llegue a la base de datos en sí (Neo4j Browser, `cypher-shell`, las credenciales de `.env`) ve todos los brains: da ese acceso solo a quien administre la instancia.
- **Límites.** Con Neo4j, el aislamiento es una reescritura del Cypher, revisada y probada en la CI con una batería de consultas de un lector de un brain contra los datos de otro, no una frontera que imponga la base de datos. Donde los brains deban separarse con una garantía firme, usa FalkorDB, o una instancia (y una base de datos) por cada grupo de personas. Una base de datos por brain con Neo4j Enterprise es una opción posible más adelante.

### Adoptar los grafos que ya hay
Si la base de datos ya tiene datos de Graphiti (tuyos o de otra herramienta), **Administración → Base de datos del grafo → Grafos de la base de datos** lista cada grafo (FalkorDB) o `group_id` (Neo4j) con sus entidades, aristas y episodios, la dimensión de sus vectores y el brain del que es, si lo es. Cualquier grafo que no sea de ningún brain se puede adoptar como brain, tal cual:
- **Completo:** se consulta y aprende (propuestas, ingesta, curación). Sus vectores deben tener la dimensión del motor de embeddings por defecto, porque el recall los compara con los de la pregunta.
- **Solo lectura:** se consulta (recall, hechos, línea temporal, entidades), pero nada lo escribe: ni propuestas, ni ingesta, ni curación, y un cambio de modelo de embeddings deja sus vectores como están. La propia base de datos rechaza cualquier escritura en él, venga de donde venga. Un administrador puede pasarlo de un modo a otro desde la misma lista; completo exige vectores compatibles.

Un grafo que no adoptes no se toca nunca. Un brain nuevo nunca cae sobre un grafo que no es de nadie: crear un brain cuyo slug coincide con uno de esos grafos se rechaza, y el mensaje remite a adoptarlo.

## Proveedores de IA
En **Administración → Modelo LLM / Embeddings / Decisor**. Cada motor es un endpoint compatible con OpenAI (URL base, clave y modelo). Las claves se guardan cifradas.
- **Modelo LLM:** extrae entidades y hechos al ingerir propuestas. Para modelos que «razonan» y devuelven JSON vacío, usa un proxy que desactive el *thinking*.
- **Embeddings:** los vectores dependen del modelo, así que cambiar el modelo o su dimensión con el índice ya creado obliga a recalcularlos: usa **Reindexar** (ver más abajo), nunca edites el motor sin más. Debe ser el mismo que use Graphiti sobre ese FalkorDB.

El LLM de extracción y el modelo de embeddings son **independientes**: pueden venir de proveedores distintos (embeddings en local y LLM por API, por ejemplo), y solo el de embeddings queda atado al índice.

### Elegir el modelo de extracción
Lo que entra en el grafo es tan bueno como el modelo de extracción: lee cada propuesta, nombra las entidades y devuelve los hechos en JSON.
- **Recomendado:** en local, un modelo *instruct* de unos **14B parámetros o más** (p. ej. `qwen2.5:14b-instruct` en Ollama, que necesita unos 10 GB de memoria); por API, un modelo pequeño y barato con salida estructurada (la gama *mini* de OpenAI, por ejemplo).
- **Los modelos pequeños (4B o menos, como `llama3.2:3b`)** sirven para probar la instalación, pero no para una memoria que quieras conservar: espera entidades mal formadas, entidades del texto que se pierden y hechos escritos en inglés aunque el texto esté en otro idioma. Lo que se extrae mal se queda en el grafo hasta que un curador lo corrige.
- Evita los modelos que «razonan» por defecto salvo que lo desactives: ver la nota del modelo LLM más arriba.
- **Decisor:** modelo de decisión cerrada (con probabilidades) para el triaje de propuestas y el corrector de tipos. Solo aprueba lo factual con confianza suficiente; nunca rechaza por su cuenta. No supone ningún dominio: juzga cada propuesta frente al ámbito del brain, hecho con su **descripción** (Administración → Brain → Brain activo → Editar) y los tipos de entidad y de relación de su ontología. Lo que no encaja en ese ámbito va a un curador. Sin descripción ni ontología, solo comprueba que sea una afirmación factual sin instrucciones dirigidas al sistema.

### Cambiar el modelo de embeddings
**Desde la interfaz:** Administración → Embeddings → **Reindexar** en un motor con otro modelo muestra la estimación y, tras confirmar, calcula los vectores en sombra; un panel en la misma pantalla muestra el progreso (con Cancelar), las sombras sin terminar (Reintentar, Descartar) y, cuando están listas, **Cambiar al modelo nuevo**, que pide marcar que has hecho copia de FalkorDB y PostgreSQL. Al terminar, recuerda recalibrar la similitud mínima de un pasaje y pasar al modelo nuevo los agentes que escriban directamente en Graphiti. El resto de esta sección describe la API que hay detrás.

El paso a un motor con otro modelo se hace en dos pasos: primero se calculan con el motor nuevo todos los vectores **en sombra**, sin tocar los que se usan (el motor por defecto, el recall, la ingesta y el índice siguen funcionando igual), y después se **intercambian** y el motor nuevo pasa a ser el por defecto.
- `GET /api/embedding-engines/{id}/reindex/estimate`: una cota superior de los elementos (entidades y hechos del grafo, trozos de episodios y documentos), las llamadas aproximadas al motor y la memoria que hará falta en FalkorDB. Usa consultas baratas y acotadas (un recuento por tipo y una muestra de 1000 elementos para el tamaño del texto; las estadísticas de las tablas en PostgreSQL), se para a los 5 segundos y responde `partial: true`, y el último resultado se reutiliza durante 5 minutos (`?refresh=true` lo rehace). En PostgreSQL se estima lo que ocuparán la columna nueva y su índice HNSW, pero el espacio libre en disco no se puede consultar por SQL: compruébalo tú.
- `POST /api/embedding-engines/{id}/reindex`: lanza el trabajo *Cambio de modelo de embeddings (relleno en sombra)*, reanudable, con progreso, cancelación y reintento (`POST /api/embedding-engines/reindex/{trabajo}/cancel|retry`). La petición no estima nada (solo rechaza si la última estimación ya decía que no hay memoria): el trabajo hace la estimación completa al empezar, la deja en su registro y no sigue si FalkorDB no tiene esa memoria libre con un margen del 50 %. No usa el LLM. En FalkorDB (formato de graphiti-core 0.30.2) rellena `name_embedding_reindex` de los nodos `Entity` y `Community` y `fact_embedding_reindex` de las aristas `RELATES_TO`, con el texto de origen en `*_reindex_src`; en pgvector, una columna `embedding_reindex vector(<dimensión nueva>)` con su propio índice HNSW (creado con `CONCURRENTLY`, sin bloquear las escrituras del índice) en `episode_chunks` y `doc_chunks`. Un reintento solo calcula lo que falta o lo que cambió entretanto. Los cambios de estructura de esas tablas usan un `lock_timeout` corto y se reintentan: el trabajo nunca se queda esperando detrás de la sincronización del índice.
- **Límites de tasa:** tamaño de lote y pausa entre lotes en Administración → Ingesta y trabajos; ante un 429 el trabajo espera lo que indique `Retry-After` (hasta 5 minutos).
- **Cancelar** el trabajo o `POST /api/embedding-engines/reindex/discard` (si no está en marcha) borra todo lo auxiliar: las propiedades sombra en FalkorDB y la columna y el índice sombra en PostgreSQL.
- **Sombras sin terminar:** mientras haya sombras, un marcador (`reindex_shadow`) guarda el motor, el estado (`running`, `failed` o `ready`) y las fechas, así que `GET /api/embedding-engines/reindex` las muestra sin recorrer el grafo, con `orphan: true` si las hay y ningún relleno está en marcha. Si un relleno sigue fallido o parado más tiempo del que indica *Avisar de un cambio de modelo parado* (24 h por defecto, Administración → Ingesta y trabajos), salta el aviso `reindex.orphan`, que se resuelve al descartar las sombras o al terminar el relleno. Un relleno terminado (`ready`) espera al intercambio y no avisa.

**Intercambio.** `POST /api/embedding-engines/reindex/switch` con `{"backup_confirmed": true}` (hace falta un relleno terminado y confirmar que has hecho copia de FalkorDB y PostgreSQL; la confirmación queda en el registro del trabajo y en la auditoría) lanza el trabajo *Cambio de modelo de embeddings (intercambio)*:
1. Calcula lo que cambió desde el relleno, fuera de la pausa.
2. Pausa las escrituras de vectores (ingesta, sincronización del índice, indexado de documentos y edición de hechos). Las nuevas esperan; el cambio espera a las que estén en curso como mucho *Espera del cambio de modelo* segundos (60 por defecto, Administración → Ingesta y trabajos). Si no terminan, se retira, las escrituras siguen y lo vuelve a intentar más tarde (3 intentos): se aplaza el cambio, nunca se cortan las escrituras. El recall no pasa por la pausa (solo espera los milisegundos de la transacción final de PostgreSQL).
3. Con las escrituras en pausa, completa lo que quede, intercambia los vectores de cada grafo (los anteriores quedan en `*_prev`) y, en **una sola transacción de PostgreSQL**, sustituye las columnas `embedding` y sus índices HNSW por las nuevas (con la dimensión nueva si cambia), marca el motor nuevo por defecto y borra el marcador. Si algo falla antes de confirmar esa transacción, los grafos vuelven a sus vectores anteriores y todo sigue con el motor anterior, con el relleno listo para reintentar. El registro del trabajo apunta cuánto duró la pausa.
4. Si el servicio muere a mitad, en el siguiente arranque, **antes de servir**, cada grafo queda coherente con el motor por defecto: si el cambio no se confirmó vuelve a los vectores anteriores; si se confirmó, solo se borran los anteriores.

La compuerta es por proceso: supone que el servicio corre en un solo proceso (como la imagen). Después del cambio, **recalibra la similitud mínima de un pasaje** (Administración → Recuerdo): las similitudes de modelos distintos no son comparables. Los agentes que escriban directamente en Graphiti siguen escribiendo con el modelo anterior hasta que los cambies: pásalos al mismo modelo.

**Tu `.env` tras el cambio.** Una vez cambiado el motor, el modelo vive en Administración → Embeddings y no en las variables. `MIMIRSYNTH_EMBEDDING_DIM` (y `MIMIRSYNTH_EMBEDDING_MODEL` / `MIMIRSYNTH_EMBEDDING_BASE_URL`) conservan sus valores antiguos. Solo importan en dos casos: una instalación nueva (que crea el índice con ese tamaño) y el respaldo que se usa cuando **no** hay ningún motor registrado en Administración. Mantén un motor registrado y, si dependes de las variables, actualízalas al modelo y la dimensión nuevos.

## Cuentas y seguridad
- **Usuarios:** Administración → Usuarios. Alta por invitación (enlace de un solo uso) o con contraseña temporal; roles, brains, deshabilitar, restablecer y eliminar.
- **Llaves de acceso:** cada persona puede añadir llaves de acceso (WebAuthn) en Mi cuenta → Seguridad para entrar con la huella, el rostro o el PIN de su dispositivo, o usarlas como segundo paso tras la contraseña. Una llave exige verificación de usuario, así que cuenta como doble factor, también cuando el administrador lo hace obligatorio. Una llave solo funciona en el dominio donde se creó (el de `MIMIRSYNTH_PUBLIC_URL`); cambiar de dominio las invalida, así que conviene mantener la contraseña como respaldo. «Reiniciar doble factor» de un administrador sobre una persona también le quita sus llaves.
- **Seguridad de cuentas:** longitud mínima de contraseña, bloqueo tras intentos fallidos, validez de los enlaces y **doble factor obligatorio**.
- **Correo (SMTP):** necesario para enviar invitaciones y recuperar contraseñas por email. Sin él, el administrador copia los enlaces desde la ficha del usuario.
- **Identidad (OIDC):** lista de proveedores de inicio de sesión; puedes añadir varios y cada uno muestra su propio botón en la pantalla de entrada. Cada proveedor tiene su emisor, Client ID, secreto, scopes, política de alta automática (por dominio de email) y roles por grupo. Los roles concedidos por un grupo se retiran cuando la persona deja el grupo (nunca los puestos a mano ni el del último administrador). Cada persona puede vincular varios proveedores a su cuenta desde Mi cuenta → Seguridad. Cada uno muestra la URL de retorno a registrar en el proveedor y permite probar la conexión. Por defecto solo entra quien ya tiene cuenta o invitación con el mismo email verificado. Las variables `MIMIRSYNTH_OIDC_*` y los ajustes antiguos de un único proveedor se importan una sola vez, al actualizar a la 0.5, como el proveedor `oidc` (misma URL de retorno, `/api/auth/callback`); a partir de ahí se gestionan solo aquí.
  - **Alta automática:** con «Sí» y una lista de **dominios permitidos**, quien entre con un email *verificado* de esos dominios se da de alta solo, como usuario con el **acceso inicial** del proveedor y el que le den sus grupos. Nunca se aplica a emails sin verificar, aunque actives «Aceptar emails sin verificar».
  - **Acceso inicial:** brains a los que entra quien se da de alta solo, como `brain:rol` separados por comas (p. ej. `docs:reader, wiki:contributor`). Solo se admiten `reader` y `contributor`: lo recibe cualquiera de esos dominios sin que nadie lo revise, y lo que proponga sigue la política del brain (un curador o el decisor). Se aplica **una vez**, al crear la cuenta, como una membresía normal: un administrador puede cambiarla o quitarla en Usuarios y ningún inicio de sesión posterior la repone. Si un grupo da un rol mayor en el mismo brain, gana el mayor. Al guardar el proveedor se rechaza una entrada con otro rol o con un brain que no existe; un brain borrado después se ignora. No se aplica a las invitaciones, que traen sus propios roles.
  - **Grupos:** si tu proveedor envía los grupos de la persona (claim `groups` por defecto), puedes nombrar un **grupo de administradores de la instancia** y reglas **grupo=brain:rol** (p. ej. `curadores=docs:curator`). Al iniciar sesión se *concede* el rol si no tiene ya uno igual o mayor, y el rol que dio un grupo se **retira** cuando la persona deja de estar en ese grupo (vuelve el que tenía antes, si lo había). Los roles puestos a mano no se tocan nunca, nunca se retira al último administrador y no se retira nada si el proveedor no envía el claim de grupos. Por grupo nunca se concede «propietario».
  - **Emails sin verificar:** «Aceptar emails sin verificar» existe para proveedores que no marcan el email como verificado (Entra ID, por ejemplo), para que se puedan aceptar invitaciones a través de ellos. Con él, un email sin verificar solo se vincula a una **invitación** (una cuenta aún sin credenciales). Una cuenta que ya está activa solo se vincula sola con un email verificado; si no, la pantalla de entrada le pide que entre como siempre y vincule el proveedor desde Mi cuenta → Seguridad. Los emails declarados como administradores de la instancia también necesitan un email verificado para crear su cuenta.

## Idioma
**Administración → General → Idioma por defecto** fija el idioma de la interfaz y de los correos para quien no haya elegido uno. Cada persona elige el suyo en Mi cuenta → Perfil. Se incluyen inglés y español.

## Memoria documental
- **Carpetas:** Administración → Carpetas registra las raíces bajo `/sources` que los administradores de un brain pueden usar como fuentes. En Conocimiento se añaden fuentes de tipo carpeta y wiki (Outline, Confluence, Notion); las subidas van a la fuente «Subidas» de cada brain. Ver [DOCUMENTS.md](DOCUMENTS.md).
- **Límites:** tamaño máximo de fichero, de cada parte de subida y del texto extraído (Administración → Límites).
- **Recall:** similitud mínima, pasajes por consulta y tiempo máximo de la búsqueda documental (Administración → Recuerdo). La similitud depende del modelo de embeddings: recalíbrala si lo cambias.

## Sistema
- **Ingesta y trabajos:** reintentos y plazos de retención (los reescaneos programados sin incidencias se purgan a los 7 días por defecto; el resto, a los 60).
- **Auditoría:** registro de acciones de administración y de acceso.
