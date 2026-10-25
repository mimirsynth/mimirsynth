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
| `MIMIRSYNTH_PUBLIC_URL` | vacío | URL pública, para OIDC y enlaces de invitación |
| `MIMIRSYNTH_COOKIE_SECURE` | `false` | `true` si sirves por HTTPS |
| `MIMIRSYNTH_EMBEDDING_*`, `MIMIRSYNTH_LLM_*` | vacío | Motores por defecto si aún no hay ninguno configurado en la interfaz |
| `MIMIRSYNTH_SOURCES_DIR` | `./sources` | Carpeta del host montada en solo lectura en `/sources` |

## Proveedores de IA
En **Administración → Modelo LLM / Embeddings / Decisor**. Cada motor es un endpoint compatible con OpenAI (URL base, clave y modelo). Las claves se guardan cifradas.
- **Modelo LLM:** extrae entidades y hechos al ingerir propuestas. Para modelos que «razonan» y devuelven JSON vacío, usa un proxy que desactive el *thinking*.
- **Embeddings:** modelo y dimensión **no se pueden cambiar** una vez creados el índice (los vectores dependen del modelo). Debe ser el mismo que use Graphiti sobre ese FalkorDB.
- **Decisor:** modelo de decisión cerrada (con probabilidades) para el triaje de propuestas y el corrector de tipos. Solo aprueba lo factual con confianza suficiente; nunca rechaza por su cuenta.

## Cuentas y seguridad
- **Usuarios:** Administración → Usuarios. Alta por invitación (enlace de un solo uso) o con contraseña temporal; roles, brains, deshabilitar, restablecer y eliminar.
- **Seguridad de cuentas:** longitud mínima de contraseña, bloqueo tras intentos fallidos, validez de los enlaces y **doble factor obligatorio**.
- **Correo (SMTP):** necesario para enviar invitaciones y recuperar contraseñas por email. Sin él, el administrador copia los enlaces desde la ficha del usuario.
- **Identidad (OIDC):** lista de proveedores de inicio de sesión; puedes añadir varios y cada uno muestra su propio botón en la pantalla de entrada. Cada proveedor tiene su emisor, Client ID, secreto, scopes, política de alta automática (por dominio de email) y roles por grupo. Cada uno muestra la URL de retorno a registrar en el proveedor y permite probar la conexión. Por defecto solo entra quien ya tiene cuenta o invitación con el mismo email verificado. Las variables `MIMIRSYNTH_OIDC_*` y los ajustes antiguos de un único proveedor se importan una sola vez, al actualizar a la 0.5, como el proveedor `oidc` (misma URL de retorno, `/api/auth/callback`); a partir de ahí se gestionan solo aquí.
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
