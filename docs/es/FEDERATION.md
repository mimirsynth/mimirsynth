# Federación entre brains

Un brain puede prestar su lectura a otro. El que recibe ve entonces, en sus propios recalls, lo que sabe el que presta, fusionado con lo suyo y marcado con su origen. No se copia nada: los datos se quedan en el brain que presta.

## Qué se presta

Una concesión va de un brain de **origen** (el que presta) a un brain de **destino** (el que recibe), con un alcance:

| Alcance | Qué puede leer el destino |
|---|---|
| `graph` | Hechos (vigentes y caducados) y fragmentos de episodios |
| `docs` | Pasajes de documentos |
| `both` | Todo lo anterior |

Nunca se comparte: embeddings, resúmenes de entidades, tokens, miembros, propuestas, la ontología ni nada que no sea el contenido que devuelve una consulta. Jamás se concede escritura: `remember` siempre escribe en el brain al que pertenece el token.

## Reglas

- **Quién concede.** Un administrador del brain de origen, que además debe tener acceso al brain de destino. Un brain que no puedes ver responde «no encontrado», como en el resto de la aplicación.
- **En un sentido y un salto.** A→B no da a B acceso a A, y A→B más B→C no da a C acceso a A.
- **Caducidad opcional** en días. Una concesión caducada deja de valer sola; sigue en la lista, marcada como caducada, hasta que alguien la revoque.
- **Revocación inmediata.** El origen revoca (o el destino renuncia) y la siguiente consulta ya no lo incluye. Borrar cualquiera de los dos brains elimina sus concesiones.
- **Auditada.** Crear, cambiar y revocar una concesión queda en el registro de auditoría. Cada concesión muestra además cuándo se usó por última vez.
- **No es un rol.** Los miembros del destino leen lo prestado con su propio rol en el destino; una concesión nunca sube el rol de nadie, y los tokens de API siguen valiendo solo en su brain.

## Cómo la usa una consulta

`recall` (REST y MCP) consulta el brain de destino y todos los orígenes que le prestan, y fusiona las listas con Reciprocal Rank Fusion ponderado (lo que el destino ya sabe pesa algo más que lo prestado). Un hecho que el destino ya tiene no se repite desde un origen. Lo prestado lleva su origen: `· de «slug»` en el contexto inyectado y un campo `origin` en el JSON, además de una lista `federated` con el estado de cada origen (`ok`, `error`, `off`). Un origen que falla nunca rompe la consulta.

Pasa `federated: false` a `recall` para obtener solo la memoria propia del brain. La pantalla Consulta muestra el origen de cada elemento prestado.

## Gestionar las concesiones

Administración → Brains → Federación muestra a quién presta este brain (con alcance, vigencia, último uso y un botón Revocar) y quién le presta a él. La API REST está en `/api/brains/{slug}/grants` (`GET`, `POST`, `PATCH /{id}`, `DELETE /{id}`).
