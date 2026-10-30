[English](Troubleshooting) · **Español**

# Solución de problemas

Primero, mira el estado: `docker compose ps`, `docker compose logs mimirsynth --tail 100` y `curl http://localhost:8000/api/health` (`200` con `"db": true, "graph": true` significa que la aplicación llega a PostgreSQL y a FalkorDB; `503` dice cuál falla). La campana de la barra lateral también muestra los avisos que puedes ver. Después busca tu síntoma.

## Arranque e instalación
| Síntoma | Causa y solución |
|---|---|
| `define POSTGRES_PASSWORD` / `define MIMIRSYNTH_SESSION_SECRET` | Faltan en `.env`. Defínelas |
| La aplicación se detiene al arrancar con un error sobre `MIMIRSYNTH_SESSION_SECRET` | Con login activo no se admite el secreto por defecto: pon uno aleatorio |
| Aparecen brains con nombres raros en el primer arranque | Un comentario al final de línea en `MIMIRSYNTH_BOOTSTRAP_GRAPHS` en `.env`. Quita comentarios de línea ([[Variables de entorno]]) |
| Una variable de `.env` no tiene efecto | El compose oficial solo pasa las variables que enumera en `environment:`. Añádela ahí ([[Variables de entorno]]) |
| `bind: address already in use` | El puerto 8000 está ocupado: cambia `MIMIRSYNTH_PORT` |
| Un servicio en «unhealthy» | `docker compose logs <servicio>`. PostgreSQL/FalkorDB tardan unos segundos; si persiste, revisa memoria y espacio en disco. La aplicación también se marca como «unhealthy» mientras no llega a PostgreSQL o a FalkorDB |
| Los embeddings o el LLM fallan con un error de conexión, con Ollama en el mismo host Linux | Ollama solo escucha en `127.0.0.1`: haz que escuche en todas las interfaces ([Preparar Ollama](Instalaci%C3%B3n#preparar-ollama)). Con un `docker-compose.yml` propio, comprueba que el servicio `mimirsynth` tiene `extra_hosts: ["host.docker.internal:host-gateway"]` |
| No encuentro el código de instalación | Solo aparece mientras no haya administradores; reinicia el contenedor para generar uno nuevo |
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
| Errores de dimensión de embeddings | Se cambió el modelo de embeddings a mano con vectores del anterior ya guardados. Cámbialo solo con **Reindexar** en Administración → Embeddings, que recalcula todos los vectores antes de cambiar ([[Proveedores de IA]]) |
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
