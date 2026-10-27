[English](../CONFIGURATION.md) · **Español**

# Configuración

La configuración tiene dos niveles:

1. **Entorno (`.env`):** solo lo necesario para arrancar y conectar. Se lee al iniciar.
2. **Interfaz (Administración → Ajustes y demás secciones):** todo lo demás. Se aplica sin reiniciar y cada cambio queda en la auditoría. Si una variable de entorno equivalente existe, hace de valor por defecto, y «Restaurar» en la interfaz vuelve a él.

## Variables de entorno
Plantilla comentada: `env.example` en la [última release](https://github.com/MimirSynth/mimirsynth/releases/latest) (o [`.env.example`](../../.env.example) en el repositorio).

| Variable | Por defecto | Descripción |
|---|---|---|
| `POSTGRES_PASSWORD` | – | Contraseña de PostgreSQL (obligatoria) |
| `MIMIRSYNTH_SESSION_SECRET` | – | Firma las sesiones y cifra los secretos guardados (obligatoria) |
| `MIMIRSYNTH_PORT` | `8000` | Puerto publicado en el host |
| `MIMIRSYNTH_FALKOR_HOST` / `_PORT` | `falkordb` / `6379` | FalkorDB |
| `MIMIRSYNTH_BOOTSTRAP_GRAPHS` | vacío | Grafos existentes a adoptar como brains en el primer arranque (`slug:Nombre,otro:Otro`) |
| `MIMIRSYNTH_AUTH_MODE` | `local` | `local` (cuentas propias, OIDC opcional) o `off` (solo desarrollo, sin inicio de sesión) |
| `MIMIRSYNTH_PUBLIC_URL` | vacío | URL pública, para OIDC, enlaces de invitación y **llaves de acceso** (su dominio es el identificador de la parte confiante: defínela, con HTTPS, antes de que nadie registre una) |
| `MIMIRSYNTH_COOKIE_SECURE` | `false` | `true` si sirves por HTTPS |
| `MIMIRSYNTH_EMBEDDING_*`, `MIMIRSYNTH_LLM_*` | vacío | Motores por defecto si aún no hay ninguno configurado en la interfaz |
| `MIMIRSYNTH_SOURCES_DIR` | `./sources` | Carpeta del host montada en solo lectura en `/sources` |

## Proveedores de IA
En **Administración → Modelo LLM / Embeddings / Decisor**. Cada motor es un endpoint compatible con OpenAI (URL base, clave y modelo). Las claves se guardan cifradas.
- **Modelo LLM:** extrae entidades y hechos al ingerir propuestas. Para modelos que «razonan» y devuelven JSON vacío, usa un proxy que desactive el *thinking*.
- **Embeddings:** modelo y dimensión **no se pueden cambiar** una vez creados el índice (los vectores dependen del modelo). Debe ser el mismo que use Graphiti sobre ese FalkorDB.
- **Decisor:** modelo de decisión cerrada (con probabilidades) para el triaje de propuestas y el corrector de tipos. Solo aprueba lo factual con confianza suficiente; nunca rechaza por su cuenta. No supone ningún dominio: juzga cada propuesta frente al ámbito del brain, hecho con su **descripción** (Administración → Acceso al brain → Editar) y los tipos de entidad y de relación de su ontología. Lo que no encaja en ese ámbito va a un curador. Sin descripción ni ontología, solo comprueba que sea una afirmación factual sin instrucciones dirigidas al sistema.

### Cambiar el modelo de embeddings (en curso, #48)
El paso a un motor con otro modelo se hace por pasos. El primero, de momento solo por la API, calcula con el motor nuevo todos los vectores **en sombra**, sin tocar los que se usan: el motor por defecto, el recall, la ingesta y el índice siguen funcionando igual.
- `GET /api/embedding-engines/{id}/reindex/estimate`: una cota superior de los elementos (entidades y hechos del grafo, trozos de episodios y documentos), las llamadas aproximadas al motor y la memoria que hará falta en FalkorDB. Usa consultas baratas y acotadas (un recuento por tipo y una muestra de 1000 elementos para el tamaño del texto; las estadísticas de las tablas en PostgreSQL), se para a los 5 segundos y responde `partial: true`, y el último resultado se reutiliza durante 5 minutos (`?refresh=true` lo rehace). En PostgreSQL se estima lo que ocuparán la columna nueva y su índice HNSW, pero el espacio libre en disco no se puede consultar por SQL: compruébalo tú.
- `POST /api/embedding-engines/{id}/reindex`: lanza el trabajo *Cambio de modelo de embeddings (relleno en sombra)*, reanudable, con progreso, cancelación y reintento (`POST /api/embedding-engines/reindex/{trabajo}/cancel|retry`). La petición no estima nada (solo rechaza si la última estimación ya decía que no hay memoria): el trabajo hace la estimación completa al empezar, la deja en su registro y no sigue si FalkorDB no tiene esa memoria libre con un margen del 50 %. No usa el LLM. En FalkorDB (formato de graphiti-core 0.30.2) rellena `name_embedding_reindex` de los nodos `Entity` y `Community` y `fact_embedding_reindex` de las aristas `RELATES_TO`, con el texto de origen en `*_reindex_src`; en pgvector, una columna `embedding_reindex vector(<dimensión nueva>)` con su propio índice HNSW (creado con `CONCURRENTLY`, sin bloquear las escrituras del índice) en `episode_chunks` y `doc_chunks`. Un reintento solo calcula lo que falta o lo que cambió entretanto. Los cambios de estructura de esas tablas usan un `lock_timeout` corto y se reintentan: el trabajo nunca se queda esperando detrás de la sincronización del índice.
- **Límites de tasa:** tamaño de lote y pausa entre lotes en Administración → Ingesta y trabajos; ante un 429 el trabajo espera lo que indique `Retry-After` (hasta 5 minutos).
- **Cancelar** el trabajo o `POST /api/embedding-engines/reindex/discard` (si no está en marcha) borra todo lo auxiliar: las propiedades sombra en FalkorDB y la columna y el índice sombra en PostgreSQL.
- **Sombras sin terminar:** mientras haya sombras, un marcador (`reindex_shadow`) guarda el motor, el estado (`running`, `failed` o `ready`) y las fechas, así que `GET /api/embedding-engines/reindex` las muestra sin recorrer el grafo, con `orphan: true` si las hay y ningún relleno está en marcha. Si un relleno sigue fallido o parado más tiempo del que indica *Avisar de un cambio de modelo parado* (24 h por defecto, Administración → Ingesta y trabajos), salta el aviso `reindex.orphan`, que se resuelve al descartar las sombras o al terminar el relleno. Un relleno terminado (`ready`) espera al intercambio y no avisa.

El intercambio de vectores y el cambio del motor por defecto llegarán en un paso posterior. Antes de él, haz una copia de FalkorDB y PostgreSQL.

## Cuentas y seguridad
- **Usuarios:** Administración → Usuarios. Alta por invitación (enlace de un solo uso) o con contraseña temporal; roles, brains, deshabilitar, restablecer y eliminar.
- **Llaves de acceso:** cada persona puede añadir llaves de acceso (WebAuthn) en Mi cuenta → Seguridad para entrar con la huella, el rostro o el PIN de su dispositivo, o usarlas como segundo paso tras la contraseña. Una llave exige verificación de usuario, así que cuenta como doble factor, también cuando el administrador lo hace obligatorio. Una llave solo funciona en el dominio donde se creó (el de `MIMIRSYNTH_PUBLIC_URL`); cambiar de dominio las invalida, así que conviene mantener la contraseña como respaldo. «Reiniciar doble factor» de un administrador sobre una persona también le quita sus llaves.
- **Seguridad de cuentas:** longitud mínima de contraseña, bloqueo tras intentos fallidos, validez de los enlaces y **doble factor obligatorio**.
- **Correo (SMTP):** necesario para enviar invitaciones y recuperar contraseñas por email. Sin él, el administrador copia los enlaces desde la ficha del usuario.
- **Identidad (OIDC):** lista de proveedores de inicio de sesión; puedes añadir varios y cada uno muestra su propio botón en la pantalla de entrada. Cada proveedor tiene su emisor, Client ID, secreto, scopes, política de alta automática (por dominio de email) y roles por grupo. Los roles concedidos por un grupo se retiran cuando la persona deja el grupo (nunca los puestos a mano ni el del último administrador). Cada persona puede vincular varios proveedores a su cuenta desde Mi cuenta → Seguridad. Cada uno muestra la URL de retorno a registrar en el proveedor y permite probar la conexión. Por defecto solo entra quien ya tiene cuenta o invitación con el mismo email verificado. Las variables `MIMIRSYNTH_OIDC_*` y los ajustes antiguos de un único proveedor se importan una sola vez, al actualizar a la 0.5, como el proveedor `oidc` (misma URL de retorno, `/api/auth/callback`); a partir de ahí se gestionan solo aquí.
  - **Alta automática:** con «Sí» y una lista de **dominios permitidos**, quien entre con un email *verificado* de esos dominios se da de alta solo, como usuario sin acceso a ningún brain. Nunca se aplica a emails sin verificar, aunque actives «Aceptar emails sin verificar».
  - **Grupos:** si tu proveedor envía los grupos de la persona (claim `groups` por defecto), puedes nombrar un **grupo de administradores de la instancia** y reglas **grupo=brain:rol** (p. ej. `curadores=docs:curator`). Al iniciar sesión se *concede* el rol si no tiene ya uno igual o mayor; nunca se rebaja ni se retira (quitar a alguien de un grupo no le quita el acceso: hazlo en Usuarios), y por grupo nunca se concede «propietario».

## Idioma
**Administración → General → Idioma por defecto** fija el idioma de la interfaz y de los correos para quien no haya elegido uno. Cada persona elige el suyo en Mi cuenta → Perfil. Se incluyen inglés y español.

## Memoria documental
- **Carpetas:** Administración → Carpetas registra las raíces bajo `/sources` que los administradores de un brain pueden usar como fuentes. En Conocimiento se añaden fuentes de tipo directorio, wiki (Outline) o subidas.
- **Límites:** tamaño máximo de fichero, de cada parte de subida y del texto extraído (Administración → Límites).
- **Recall:** similitud mínima, pasajes por consulta y tiempo máximo de la búsqueda documental (Administración → Recuerdo). La similitud depende del modelo de embeddings: recalíbrala si lo cambias.

## Sistema
- **Ingesta y trabajos:** reintentos y plazos de retención (los reescaneos programados sin incidencias se purgan a los 7 días por defecto; el resto, a los 60).
- **Auditoría:** registro de acciones de administración y de acceso.
