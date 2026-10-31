[English](Import-a-brain) · **Español**

# Importar un brain

Crea un **brain nuevo** a partir de un paquete hecho con [[Exportar un brain]], de esta instancia o de otra. Los demás brains no se tocan.

## Cómo
**Administración → Acceso al brain → Importar un brain.** Hace falta el **administrador de la instancia** (un token de API nunca puede importar), y queda en la [[Auditoría]].

1. Pulsa **Elegir paquete** y elige el fichero `.mimirsynth.tar.gz` (o `.tar.gz.enc`). Se sube por partes, así que el límite de tamaño de un proxy no estorba.
2. Si el paquete no está cifrado, la tarjeta enseña lo que dice su manifiesto: el brain original, cuándo y con qué versión se exportó, sus recuentos y qué pasará aquí con el grafo y los vectores.
3. Rellena el **slug** y el **nombre** del brain nuevo. Su grafo se llama igual que el slug, así que no puede existir ninguno de los dos.
4. Elige qué importar:
   - **Completo:** el grafo, la ontología y el vocabulario con su historial, las correcciones de tipos, las consultas de referencia, las propuestas y los documentos.
   - **Solo la estructura:** la ontología y los alias, como plantilla de un brain nuevo. Sin grafo, propuestas ni documentos.
5. Si el paquete está cifrado, escribe su **contraseña**.
6. Pulsa **Importar**. Se hace como un trabajo ([[Trabajos]]) y la tarjeta enseña su progreso. Al terminar, **Abrir** cambia al brain nuevo.

Solo se hace una importación a la vez. Un paquete subido que nadie importa se borra a las 24 horas.

## Se comprueba antes de escribir nada
El paquete viene de fuera, así que se lee entero y se comprueba antes de crear nada:
- Solo lleva ficheros normales (ni enlaces ni carpetas), cada uno en el manifiesto y en las rutas que escribe una exportación. Una ruta con `..`, absoluta o que no esté en esa lista rechaza el paquete.
- Cada fichero tiene el tamaño y el `sha256` que dice el manifiesto, y están todos los que lista.
- El manifiesto es de un paquete de MimirSynth con una versión de formato que esta instancia sabe leer.
- Las etiquetas y los tipos de relación del grafo son nombres simples, cada relación une dos nodos del paquete y el número de nodos y relaciones coincide con el del manifiesto.
- Cada documento apunta solo a sus propios ficheros, y los vectores que se reutilizan tienen la dimensión del modelo de embeddings en uso.

Un paquete que no pasa alguna comprobación se rechaza con el motivo, sin escribir nada.

## El grafo
- **La copia exacta** (el volcado) se restaura cuando el paquete la trae y el módulo de grafos de FalkorDB de aquí tiene la misma versión que donde se exportó. Es lo más rápido y lo conserva todo, índices incluidos.
- Si no, entra la **copia JSON**, por lotes, y se crean los índices de Graphiti. La tarjeta dice por qué: el paquete no trae la copia exacta (se quedó fuera por un secreto), otra versión de FalkorDB, o su grafo original existe en esta instancia (el volcado lleva el nombre de su grafo y solo se puede restaurar con él).
- Con un slug distinto del original se reescribe el `group_id` de cada nodo y relación, como al cambiar el grafo de un brain en [[Administrar brains y miembros]].

Los agentes que escribían en el grafo original con el `group_id` de Graphiti tienen que repuntarse al nuevo.

## Los vectores
- **Mismo modelo de embeddings** y misma dimensión que donde se exportó: se reutilizan los vectores que trae el paquete (los del grafo y, si se exportó con **Incluir los vectores**, los del índice de búsqueda). Solo se calculan los que faltan.
- **Otro modelo:** se calculan todos de nuevo en el mismo trabajo: los de Graphiti en el grafo, el índice de los episodios y el de los documentos. Eso llama al motor de embeddings para todo el brain, así que tarda.

## Qué recibe el brain nuevo
- **Eres su propietario.** Los miembros, los tokens de API, los motores de IA y los canales de aviso no van en el paquete: se configuran aquí.
- **Las propuestas** conservan su texto y su revisión. Su autor eres tú, y los nombres del autor y del revisor originales se quedan en la propuesta. Una aprobada que aún no se había ingerido vuelve a **pendiente**: la decide de nuevo un curador.
- **Los documentos** conservan sus metadatos, su texto normalizado y, si el paquete lo trae, su original. Uno sin texto se queda con un error para reindexarlo. Las fuentes de **subidas** llegan activas; las de **carpeta y wiki** llegan **desactivadas** y sin sus credenciales. Revisa su configuración (la raíz de la carpeta tiene que existir aquí) y actívalas.
- La política de secretos y sus excepciones son las del brain original.
- Si el brain tiene [[Consultas de referencia]], se ejecutan al terminar la importación. Compara el resultado con la última ejecución del brain original (viene en el paquete) para comprobar que el recall es el mismo.

## Si algo falla
Un fallo en cualquier punto elimina todo lo que la importación había creado: el brain, su grafo, sus filas, sus ficheros y su índice. El trabajo dice por qué.

- **Contraseña incorrecta:** el paquete se queda subido, y **Probar otra contraseña** en la tarjeta lo vuelve a importar.
- **El servicio se reinicia a mitad:** el trabajo falla diciéndolo, y el siguiente arranque elimina lo que había creado. Vuelve a subir el paquete. La contraseña, si la había, solo estaba en memoria.

## Límites
- El paquete más grande es `MIMIRSYNTH_IMPORT_MAX_MB` (20.480 MB). El almacén de documentos necesita sitio para el paquete y para lo que ocupa desempaquetado.

## API
Todas son rutas del administrador de la instancia, bajo `/api/brain-imports`:
- `POST /uploads` (`{"filename", "size"}`) empieza una subida; `PUT /uploads/{id}/parts/{n}` envía cada parte; `POST /uploads/{id}/complete` las une y devuelve el resumen del manifiesto (`null` si el paquete está cifrado); `DELETE /uploads/{id}` la descarta.
- `POST /api/brain-imports` (`{"upload_id", "slug", "name", "mode": "full" | "structure", "password"}`) lanza la importación y devuelve el trabajo.
- `GET /api/brain-imports` lista las últimas con su estado, cómo entró el grafo y los recuentos.

Ver [[API REST]].
