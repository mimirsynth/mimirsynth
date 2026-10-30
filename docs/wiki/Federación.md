[English](Federation) · **Español**

# Federación

Un brain puede **prestar la lectura** a otro brain. El brain que la recibe ve entonces, en sus propios recalls, lo que sabe el que presta, mezclado con su propia memoria y marcado con su origen. No se copia nada: los datos se quedan en el brain que los presta, y la concesión se puede revocar en cualquier momento.

Uso típico: el brain de un equipo que lee un brain común de «empresa» sin que nadie tenga que ser miembro de los dos, o el brain de un proyecto que toma prestada la documentación de otro.

## Qué se puede prestar
Una concesión va de un brain **de origen** (el que presta) a un brain **de destino** (el que recibe), con un alcance (**Qué presta**):

| Opción | Qué puede leer el destino |
|---|---|
| **Grafo y documentos** | Todo lo de abajo |
| **Solo grafo (hechos y episodios)** | Hechos (vigentes y caducados) y fragmentos del texto de los episodios |
| **Solo documentos** | Pasajes de documentos |

**Nunca se comparten:** embeddings, resúmenes de entidades, miembros, tokens, propuestas, la ontología ni nada que no sea el contenido que devuelve una consulta. Nunca se presta la escritura: `remember` siempre escribe en el brain al que pertenece su token.

## Prestar un brain
En **Administración → Acceso al brain → Federación**, con el brain de origen activo. Tienes que ser **administrador del brain de origen** y tener acceso al de destino (un brain que no puedes ver no se ofrece).
1. **Prestar a:** elige el brain de destino. Un brain que ya tiene una concesión de este no aparece: cambia o revoca la existente.
2. **Qué presta:** el alcance.
3. **Días de vigencia** (opcional, 1–3650): vacío = **sin caducidad**.
4. Pulsa **Conceder lectura**.

La tarjeta muestra entonces dos listas:
- **Este brain presta su lectura a:** cada destino con **Qué presta** (se puede cambiar ahí mismo), **Vigencia** (hasta una fecha, **caducada** o **sin caducidad**), **Último uso** y **Revocar**.
- **Este brain recibe lectura de:** cada origen con su alcance y su vigencia. Todos los miembros del brain ven esta lista; sus administradores pueden **Renunciar** a una concesión que ya no quieran.

Revocar o renunciar surte efecto en la **siguiente consulta**. Para volver a prestar hay que crear otra concesión.

## Reglas
- **En un sentido y de un salto.** A→B no da a A la memoria de B, y A→B más B→C no da a C acceso a A.
- **Caducidad.** Una concesión caducada deja de funcionar sola; sigue en la lista, marcada como **caducada**, hasta que alguien la revoque.
- **No es un rol.** Los miembros del destino leen lo prestado con su propio rol en el brain de destino. Una concesión nunca sube el rol de nadie y los tokens de API siguen valiendo solo en su propio brain.
- **Borrar un brain** elimina todas las concesiones que da o recibe.
- **Auditada.** Crear, cambiar y revocar una concesión queda en la [[Auditoría]] (`grant.create`, `grant.update`, `grant.revoke`), y cada concesión muestra cuándo se usó por última vez.

## Cómo la usa el recall
El **recall** del brain que recibe (REST, MCP y [[Preguntar]]) consulta el propio brain y todos los orígenes que le prestan, y mezcla los resultados con una fusión de rangos recíprocos ponderada: lo que el brain ya sabe pesa un poco más que lo prestado.
- Un hecho que el destino ya tiene no se repite desde un origen, y el mismo pasaje de documento se queda una sola vez.
- Cada elemento prestado lleva su **origen**: [[Preguntar]] muestra el brain de origen junto a cada hecho, fragmento y pasaje, y el contexto que recibe un agente lo marca con `· de «slug»` (en el idioma de quien llama).
- Un origen que falla nunca rompe la consulta; simplemente se queda fuera.
- Un agente puede pedir solo la memoria propia del brain con `federated: false` en el recall. Ver [[Conectar agentes]].

Detalles técnicos: [docs/es/FEDERATION.md](https://github.com/MimirSynth/mimirsynth/blob/main/docs/es/FEDERATION.md).
