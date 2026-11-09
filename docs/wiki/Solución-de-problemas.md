[English](Troubleshooting) · **Español**

# Solución de problemas

Primero, mira el estado: `docker compose ps`, `docker compose logs mimirsynth --tail 100` y `curl http://localhost:8000/api/health` (`200` con `"db": true, "graph": true` significa que la aplicación llega a PostgreSQL y a FalkorDB; `503` dice cuál falla). La campana de la barra lateral también muestra los avisos que puedes ver. Después busca tu síntoma.

## Primer arranque
Los cuatro problemas que más a menudo paran una primera instalación. Si estás siguiendo [[Tus primeros 15 minutos]], su tabla te manda aquí.

### Docker no está en marcha
El instalador dice «Docker no está instalado» o «Docker Desktop no está en marcha», o un comando `docker` responde `Cannot connect to the Docker daemon`.
- **Windows:** abre Docker Desktop y espera a que diga que el motor está en marcha. Si no arranca, casi siempre le falta WSL2: ejecuta `wsl --install` en un PowerShell abierto como administrador y reinicia el equipo.
- **Windows, con `install.sh` dentro de WSL** («Docker no está disponible en esta distribución de WSL»): en Docker Desktop, activa *Settings → Resources → WSL integration* para esa distribución, o ejecuta `install.ps1` desde PowerShell.
- **macOS:** abre Docker Desktop y espera a que arranque (el instalador intenta arrancarlo él solo).
- **Linux:** arranca el servicio con `sudo systemctl start docker` (y `sudo systemctl enable docker` para que arranque con el equipo). Si falta Docker, el instalador se ofrece a instalarlo, o pasa `--install-docker`. Si dice que tu usuario no puede usar Docker sin `sudo`, esta vez sigue con `sudo`; para no necesitarlo, ejecuta `sudo usermod -aG docker "$USER"` y cierra la sesión y vuelve a entrar.
- **Linux, justo después de arrancar la máquina** («Esperando a apt», o «apt sigue en uso tras 300 s»): las propias actualizaciones del sistema (apt-daily, unattended-upgrades) o cloud-init tienen apt unos minutos tras el primer arranque, y el instalador espera a que terminen antes de instalar Docker. Si tardan más, se detiene sin haber instalado nada y dice qué programa es: espera a que termine (`systemctl status unattended-upgrades apt-daily-upgrade`) y vuelve a ejecutar el instalador, o deja que espere más con `curl -fsSL …/install.sh | APT_WAIT_SECONDS=900 bash`.

Después vuelve a ejecutar el instalador: no borra nada y retoma la configuración que ya escribió.

### El contenedor no llega a Ollama
La prueba de embeddings o del LLM falla con «conexión rechazada», un tiempo agotado o «no se llega», y la dirección apunta a Ollama.
- **No pongas `localhost` ni `127.0.0.1` en la dirección.** MimirSynth corre en un contenedor, y ahí `localhost` es el propio contenedor, no tu equipo. Usa:

  | Dónde corre Ollama | Dirección |
  |---|---|
  | En el contenedor que arrancó el instalador | `http://ollama:11434/v1` |
  | En el mismo equipo (la aplicación o el servicio de Ollama) | `http://host.docker.internal:11434/v1` |
  | En otra máquina | su dirección, p. ej. `http://192.168.1.20:11434/v1` |
- **Linux, con Ollama en el mismo equipo:** Ollama solo escucha en `127.0.0.1` por defecto, y el contenedor no llega ahí. Haz que escuche en todas las interfaces y mantén el puerto 11434 cerrado al exterior con tu cortafuegos: `sudo systemctl edit ollama`, añade `Environment="OLLAMA_HOST=0.0.0.0"` bajo `[Service]` y después `sudo systemctl restart ollama` ([Preparar Ollama](Instalaci%C3%B3n#preparar-ollama)).
- **El modelo no está descargado** (la prueba llega a Ollama, pero responde que no encuentra el modelo): `ollama pull nomic-embed-text` o, con el Ollama incluido, `docker compose exec ollama ollama pull nomic-embed-text` en la carpeta de la instalación. Lo mismo para el modelo del LLM.
- **El Ollama incluido no está en marcha:** `docker compose ps` en la carpeta de la instalación debe listar `ollama`. Si no aparece, la instalación se hizo sin él: instala Ollama en el equipo, o añade `ollama` a `COMPOSE_PROFILES` en el `.env` y ejecuta `docker compose up -d`.
- **Con un `docker-compose.yml` propio:** en Linux, el servicio `mimirsynth` necesita `extra_hosts: ["host.docker.internal:host-gateway"]`.

### Errores de conexión al grafo
Falla la prueba de la base de datos del grafo, el instalador avisa de que el servidor no responde o `/api/health` responde `"graph": false`. La prueba dice qué ha fallado:

| Mensaje | Qué hacer |
|---|---|
| «… rechaza la conexión: comprueba que el servidor está en marcha y escucha en ese puerto» | El servidor está parado o escucha en otro sitio. Con el FalkorDB incluido, `docker compose ps` debe mostrar `falkordb` sano y el `.env` debe incluir `bundled` en `COMPOSE_PROFILES`; `docker compose logs falkordb` dice por qué se paró. Con tu propio servidor, revisa el puerto: 6379 para FalkorDB, 7687 (Bolt) para Neo4j |
| «… no responde a tiempo: revisa la dirección, el puerto y el cortafuegos» | Un cortafuegos corta la conexión, o la dirección está mal. Un servidor en el mismo equipo es `host.docker.internal`, nunca `localhost`; en Linux debe escuchar en una dirección a la que lleguen los contenedores, no solo en `127.0.0.1` |
| «No se encuentra el servidor «…»: revisa el nombre» | El nombre no se resuelve desde el contenedor. Usa una dirección IP o `host.docker.internal` |
| «El servidor rechaza el usuario o la contraseña» | Credenciales incorrectas. En Neo4j el usuario suele ser `neo4j` |
| «El usuario no puede escribir: MimirSynth necesita permiso de lectura y escritura» | Da permiso de escritura a ese usuario, o usa otro |
| «El servidor no tiene la base de datos «…»» | Neo4j: deja la base de datos vacía para usar la predeterminada del usuario, o créala. En Neo4j Aura la base de datos se llama como el id de la instancia, no `neo4j`. Con `bolt://` o `bolt+s://` un clúster como Aura responde esto con cualquier base de datos: usa `neo4j+s://` |
| «El servidor no encuentra la base de datos predeterminada de este usuario» | La dirección usa `bolt://` o `bolt+s://` y el servidor es un clúster, como Neo4j Aura: usa `neo4j+s://` (`neo4j://` sin TLS). Una instancia instalada con la 0.15.0-rc.1 tiene `bolt+s://` en `.env`: cámbialo y ejecuta `docker compose up -d` |
| «… responde, pero no se llega a los servidores que anuncia para enrutar» | Un clúster de Neo4j da direcciones (su dirección anunciada, `server.default_advertised_address`) a las que el contenedor no llega. Corrígelas en el servidor o, con un solo servidor, conecta con `bolt://` |
| «… no está soportado: hace falta la … o posterior» | MimirSynth necesita FalkorDB 4.0 o posterior, o Neo4j 5.26 o posterior |
| «… es un servidor Redis sin el módulo de grafos: hace falta FalkorDB» | El puerto es de un Redis normal. Apunta a un FalkorDB |
| «… acepta la conexión pero no responde como …» | Es el puerto de otro servicio, o el servidor espera TLS: marca **Conexión cifrada (TLS)** |

Tras la instalación, la conexión se cambia en **Administración → Base de datos del grafo**, que la prueba antes de guardar. Si esa página dice que la conexión viene de las variables de entorno, cámbiala en el `.env` y ejecuta `docker compose up -d`.

### La dimensión de los embeddings no coincide
El asistente de configuración dice «text-embedding-3-small da 1536 dimensiones y el índice es de 768», guardar el primer motor de embeddings falla con «el índice de texto es de 768 dimensiones y este modelo da 1536», el botón **Probar** de un motor responde «dimensión 1024, esperada 768», o al editar uno responde «el endpoint devuelve otra dimensión para ese modelo».

Cada modelo de embeddings da vectores de un tamaño fijo, su **dimensión**, y el índice donde MimirSynth busca los textos se crea en el primer arranque con el tamaño de `MIMIRSYNTH_EMBEDDING_DIM`: 768 por defecto, el de `nomic-embed-text`. Un modelo de otro tamaño no cabe en él.
- **Lo más sencillo:** usa un modelo de 768 dimensiones, como `nomic-embed-text`.
- **En el asistente de configuración, con la memoria aún vacía:** añade el motor con el modelo que quieres en Administración → Embeddings y pásate a él con **Reindexar**, como dice el asistente; sin nada guardado tarda segundos. Después vuelve al asistente (el botón **Asistente de configuración**, arriba en Administración) y pulsa **Siguiente**.
- **Una instalación nueva, antes del primer arranque o sin el asistente**, y quieres otro modelo: pon `MIMIRSYNTH_EMBEDDING_MODEL` y `MIMIRSYNTH_EMBEDDING_DIM` (por ejemplo `1536` para `text-embedding-3-small`) en el `.env` y ejecuta `docker compose down -v` y `docker compose up -d` en la carpeta de la instalación. **`down -v` borra todos los datos**, también la cuenta de administrador: hazlo solo en una instalación recién hecha. Aparece un código de inicio nuevo en el log.
- **Una instancia que ya tiene memoria:** nunca cambies el modelo a mano. Añade un motor con el modelo nuevo y pásalo todo a él con **Reindexar** en Administración → Embeddings, que recalcula todos los vectores antes de cambiar ([Cambiar el modelo de embeddings](Proveedores-de-IA#cambiar-el-modelo-de-embeddings)).
- **«el endpoint devuelve otra dimensión»:** el modelo que hay detrás de ese nombre ha cambiado en el proveedor (por ejemplo, otra etiqueta descargada en Ollama). Vuelve al modelo que tenías, o reindexa a un motor nuevo.

## Arranque e instalación
| Síntoma | Causa y solución |
|---|---|
| `define POSTGRES_PASSWORD` / `define MIMIRSYNTH_SESSION_SECRET` | Faltan en `.env`. Defínelas |
| La aplicación se detiene al arrancar con un error sobre `MIMIRSYNTH_SESSION_SECRET` | Con login activo no se admite el secreto por defecto: pon uno aleatorio |
| «La clave secreta de la instancia no abre los secretos guardados» en Administración, o «No se puede leer un secreto guardado» en una acción | `MIMIRSYNTH_SESSION_SECRET` no es la clave con la que se cifró la base de datos (una copia restaurada en otro servidor, una copia para pruebas, un `.env` editado). Vuelve a poner la correcta y reinicia; si se ha perdido, ver [[Actualización y copias de seguridad]] |
| Aparecen brains con nombres raros en el primer arranque | Un comentario al final de línea en `MIMIRSYNTH_BOOTSTRAP_GRAPHS` en `.env`. Quita comentarios de línea ([[Variables de entorno]]) |
| Una variable de `.env` no tiene efecto | El compose oficial solo pasa las variables que enumera en `environment:`. Añádela ahí ([[Variables de entorno]]) |
| `bind: address already in use` | El puerto 8000 está ocupado: cambia `MIMIRSYNTH_PORT` |
| Un servicio en «unhealthy» | `docker compose logs <servicio>`. PostgreSQL/FalkorDB tardan unos segundos; si persiste, revisa memoria y espacio en disco. La aplicación también se marca como «unhealthy» mientras no llega a PostgreSQL o a FalkorDB |
| Los embeddings o el LLM fallan con un error de conexión, con Ollama | Ver [El contenedor no llega a Ollama](#el-contenedor-no-llega-a-ollama) |
| No encuentro el código de inicio | Solo aparece mientras no haya administradores; reinicia el contenedor para generar uno nuevo |
| He perdido el acceso del único administrador | En la base de datos, pon `is_admin = false` a ese usuario y reinicia: vuelve el asistente de primer arranque |
| Una actualización no se ha verificado | `update.sh` te dice cómo volver atrás: `./update.sh --rollback` (añade `--with-db` para restaurar también la base de datos). Ver [[Actualización y copias de seguridad]] |

## Inicio de sesión
| Síntoma | Causa y solución |
|---|---|
| «Email o contraseña incorrectos, o cuenta bloqueada» | Contraseña mal, cuenta deshabilitada o bloqueada tras varios intentos. Espera el tiempo de bloqueo o pide a un administrador que la desbloquee |
| «Demasiados intentos» | Límite por IP/cuenta; espera unos minutos |
| No acepta la contraseña al crearla o cambiarla | El formulario muestra todas las reglas (longitud mínima, que no sea tu email ni tu nombre, que no sea común ni una secuencia, al menos 5 caracteres distintos) y marca las que cumples; el botón desactivado dice qué falta |
| La sesión se pierde al recargar (con HTTPS) | Usa `MIMIRSYNTH_COOKIE_SECURE=true` solo si sirves por HTTPS; y `MIMIRSYNTH_PUBLIC_URL` correcta |
| No se ofrecen las llaves de acceso o fallan | Necesitan HTTPS y el dominio de `MIMIRSYNTH_PUBLIC_URL`; una llave creada en otro dominio no sirve. Entra con tu contraseña y registra una nueva ([[Seguridad y doble factor]]) |
| No llega el correo de recuperación | SMTP sin configurar, o límite de peticiones. Ver [[Correo SMTP]] |
| El enlace de invitación «no es válido o ha caducado» | Usado, caducado (7 días) o anulado por uno nuevo: genera otro ([[Administrar usuarios]]) |
| Pide un código de 6 dígitos y no puedo | Usa un código de recuperación o una llave de acceso, o que un administrador te restablezca el doble factor |
| OIDC dice que ya tienes una cuenta y que vincules el proveedor | El proveedor no marcó tu email como verificado, así que no se vincula solo a una cuenta activa. Entra como siempre y vincula el proveedor desde Mi cuenta → Seguridad |
| El botón de OIDC falla | Ver la tabla de [[Identidad OIDC]] |

## Memoria
| Síntoma | Causa y solución |
|---|---|
| Propuestas aprobadas que no se ingieren («Aprobadas») | No hay LLM configurado: [[Proveedores de IA]] |
| Ingestas **fallidas** con «límite de tasa» | Tu proveedor limita las peticiones. Sube los reintentos ([[Recuerdo e ingesta]]) y, si hace falta, baja `MIMIRSYNTH_INGEST_CONCURRENCY` (añádela al fichero de Compose); reintenta desde [[Propuestas]] |
| Ingestas fallidas con JSON inválido o respuestas vacías | Modelo «razonador» que no devuelve JSON. Usa otro modelo o un proxy que desactive el *thinking* |
| Entidades mal formadas o que faltan, hechos en inglés de un texto en otro idioma | El modelo de extracción es demasiado pequeño (4B o menos). Usa uno de unos 14B o más, o un modelo pequeño por API con salida estructurada ([[Proveedores de IA]]) |
| La propuesta se ingiere pero genera 0 hechos | Texto sin información concreta, o extracción fallida: revisa el [[Diario]] y [[Escribir buena memoria]] |
| Una propuesta se rechaza con `422` y un tipo de secreto | El brain **bloquea** los secretos. Quita la credencial y escribe dónde está guardada |
| La propuesta de un curador se queda pendiente | Contiene un posible secreto: una propuesta marcada siempre espera la revisión de una persona ([[Propuestas]]) |
| El recall no devuelve nada | Brain vacío, embeddings caídos o índice sin sincronizar. [[Preguntar]]: mira el estado del índice y «Reindexar ahora» |
| El recall no trae pasajes de documentos tras cambiar el modelo de embeddings | Las similitudes de modelos distintos no son comparables: recalibra «Similitud mínima de un pasaje» (Administración → Recuerdo). Las consultas de referencia pueden simular otros umbrales |
| Errores de dimensión de embeddings | Ver [La dimensión de los embeddings no coincide](#la-dimensi%C3%B3n-de-los-embeddings-no-coincide) |
| Un cambio de modelo se queda a medias (aviso `reindex.orphan`) | Un relleno en sombra falló o se paró. En Administración → Embeddings, **Reintentar** o **Descartar**; descartar libera la memoria que ocupa |
| Un aviso de «modelo de IA que no responde» que se resuelve solo | La comprobación de estado avisa tras 2 fallos seguidos por defecto («Fallos seguidos para avisar», Administración → Notificaciones). Súbelo si tu proveedor tiene errores puntuales frecuentes |
| «índice de texto desactivado» | La instancia no tiene PostgreSQL con pgvector (p. ej. SQLite de desarrollo) |

## Documentos
| Síntoma | Causa y solución |
|---|---|
| Un documento queda «con error» | Pasa el ratón por el estado o abre el detalle para ver el motivo. Causas: tamaño excesivo, PDF sin texto, embeddings caídos, o un secreto cuando el brain los bloquea |
| Un documento aparece como **duplicado** | Su texto repite el de otro ya indexado en el brain, así que no se indexa dos veces; el detalle enlaza al original. Si el original desaparece, se indexa en su lugar el duplicado más antiguo ([[Conocimiento]]) |
| La subida falla con ficheros grandes | Tu proxy limita el tamaño de petición: baja «Tamaño de cada parte» ([[Carpetas y límites]]) |
| «No hay carpetas autorizadas» | El administrador de la instancia debe registrar raíces en [[Carpetas y límites]] |
| Un escaneo programado falla con la carpeta vacía | Protección: probablemente el volumen se desmontó. Revisa el montaje. Un escaneo manual sí vacía el índice |
| Una wiki «corta» el escaneo a mitad | Clave caducada, caída o límite de tasa de la wiki. No se borra nada; revisa la clave y reescanea |

## Agentes
| Síntoma | Causa y solución |
|---|---|
| El servidor MCP responde `401` | Falta la cabecera `Authorization: Bearer mst_…` o el token no es válido. El MCP solo admite tokens de API, nunca la sesión del navegador |
| El servidor MCP responde `403` «origen no permitido» | La petición vino de una página web de otro origen. Los clientes de agentes no lo envían; si pasas por un proxy, no añadas una cabecera `Origin` |
| `remember` dice que el token solo puede leer | El token tiene rol de lector: crea uno de colaborador ([[Conectar agentes]]) |
| Los mensajes de error llegan en otro idioma | Siguen `Accept-Language`, después el idioma de la persona dueña del token y después el de la instancia. Envía `Accept-Language` o compara códigos de estado |

## Vigilancia
| Síntoma | Causa y solución |
|---|---|
| No llegó ningún aviso cuando se cayó PostgreSQL | No puede avisar de sí mismo: los avisos se guardan ahí. Vigila `/api/health` con un monitor externo ([Vigilar la instancia](Instalaci%C3%B3n#vigilar-la-instancia)) |

## Rendimiento
- **Ingesta lenta:** depende del LLM. Un modelo más rápido o más concurrencia (si tu proveedor lo permite) la acelera.
- **Interfaz lenta con muchos datos:** usa filtros y fechas en [[Hechos]] y reduce las «semillas» del [[Grafo]].
- **Grafo lento (3D, sin GPU):** pon **Efectos gráficos** en **Reducido** en la pantalla [[Grafo]] (se guarda por dispositivo), o vuelve a 2D.
- **Disco que crece:** revisa el volumen de documentos y la retención de [[Trabajos]].

## Cómo pedir ayuda
Abre un [issue](https://github.com/MimirSynth/mimirsynth/issues) con: versión de MimirSynth, qué esperabas y qué pasó, y los pasos para reproducirlo. **Revisa que los registros no contengan secretos** antes de pegarlos. Para vulnerabilidades, usa el [aviso privado de seguridad](https://github.com/MimirSynth/mimirsynth/security/advisories/new), no un issue público.
