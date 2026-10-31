[English](Export-a-brain) · **Español**

# Exportar un brain

Una copia de **un solo brain** en un paquete, sin tocar los demás. Sirve para guardarlo aparte o para llevarlo a otra instancia. La copia de [[Actualización y copias de seguridad]] es de la instancia entera; esta es de un brain.

Para llevar un paquete a una instancia, ver [[Importar un brain]].

## Cómo
**Administración → Acceso al brain → Exportar.** Hace falta ser **administrador del brain** (un token de API nunca puede exportar), y queda en la [[Auditoría]].

1. Elige las opciones:
   - **Incluir los vectores:** los embeddings del índice de búsqueda y los del grafo en su copia JSON. Evitan recalcularlos al importar con el mismo modelo de embeddings, pero el paquete crece mucho.
   - **Cifrar con una contraseña** (al menos 12 caracteres).
2. Pulsa **Exportar**. El paquete se prepara como un trabajo ([[Trabajos]]) y la tarjeta muestra su avance.
3. Cuando esté listo, pulsa **Descargar**.

El paquete se descarga **una sola vez**: se borra del servidor al enviarlo. Si nadie lo descarga, **caduca** a las 24 horas (`MIMIRSYNTH_EXPORT_TTL_HOURS`). Si una descarga falla a medias, vuelve a exportar.

## Qué lleva el paquete
Un fichero `.tar.gz` (`<slug>-<fecha>.mimirsynth.tar.gz`) con un **`manifest.json`** versionado al principio. El manifiesto apunta la versión de MimirSynth, la de FalkorDB, el modelo de embeddings, las opciones, los recuentos, lo que encontró el detector de secretos y cada fichero con su tamaño y su `sha256`.

| Ruta | Contenido |
|---|---|
| `graph/graph.dump` | El `DUMP` del grafo: exacto y rápido de restaurar en la **misma versión de FalkorDB** |
| `graph/nodes.jsonl`, `graph/edges.jsonl` | El mismo grafo en JSON (etiquetas, propiedades, relaciones), para otra versión de FalkorDB. Los vectores de Graphiti, solo con la opción de vectores |
| `brain.json` | Nombre, descripción, slug, grafo y política de secretos |
| `ontology.json`, `vocabulary.json` | La [[Ontología]], los alias de relaciones, el historial de cambios de vocabulario y las correcciones de tipos |
| `proposals.jsonl` | Todas las propuestas con su revisión. Autores y revisores van solo por su nombre |
| `documents/` | Las fuentes (sin sus secretos) y, de cada documento, sus metadatos, su texto normalizado y su original |
| `ref_queries.json` | Las [[Consultas de referencia]] y el resumen de su última ejecución, para comprobar tras importar que el recall es el mismo |
| `vectors/` | Solo con la opción de vectores: los trozos del índice de búsqueda con sus embeddings |

**Lo que nunca va:** miembros, tokens de API, motores de IA, canales de aviso, concesiones de federación, trabajos y las instantáneas del grafo. Los motores y los canales llevan secretos sellados con la clave de esta instancia y no servirían en otra.

> **Exportar mientras se ingiere:** el volcado se toma de una vez, pero la copia JSON del grafo se lee por páginas. Si se ingiere algo mientras tanto, el JSON puede quedarse sin los hechos más recientes o tener una arista cuyo nodo no está. Para una copia exacta, exporta cuando no se esté ingiriendo nada (ver [[Trabajos]]), o quédate con el volcado.

> **Restaurar el volcado:** el `DUMP` lleva dentro el nombre del grafo. Restáuralo con ese mismo nombre (`manifest.json` → `graph.name`) en una instancia que no tenga ese grafo, y cópialo después a otro nombre si hace falta. Restaurarlo con otro nombre mientras el grafo original está cargado da conteos erróneos y puede dejar colgado FalkorDB. [[Importar un brain]] lo hace así.

## Secretos
Todo pasa por el detector de [[Secretos]] antes de empaquetarse, **sea cual sea la política del brain**. Un paquete sale de la instancia, así que el detector se aplica aunque el brain esté en «solo avisar».
- Un secreto **seguro** se enmascara como `[secreto eliminado: tipo]`. Uno **posible** solo se cuenta.
- Un grafo con un secreto seguro va **sin su volcado**, que no se puede editar, y solo como JSON enmascarado.
- Un documento va **sin su original** cuando el original tenía o tiene un secreto seguro, o cuando su texto nunca se revisó (un documento que nunca se indexó). Su texto enmascarado sí va.
- La tarjeta y el manifiesto dicen cuántos secretos se enmascararon y cuántos originales se quedaron fuera. Nunca el valor.

## Cifrado
Con contraseña, el paquete se cifra con AES-256-GCM en trozos de 1 MiB, con la clave derivada de la contraseña con scrypt. Sin la contraseña no se puede leer, y un paquete modificado o incompleto se detecta. La contraseña no se guarda en ningún sitio: solo está en memoria hasta que arranca el trabajo, así que si el servicio se reinicia antes de terminar la exportación, el trabajo falla diciéndolo y hay que volver a exportar. **Si la pierdes, el paquete no se puede recuperar.**

El fichero termina en `.mimirsynth.tar.gz.enc`. Para descifrarlo fuera de la aplicación, ejecuta la propia imagen desde la carpeta donde está el paquete (la contraseña se lee del entorno, así que nunca aparece en la orden):
```bash
read -rs MIMIRSYNTH_PACK_PASSWORD && export MIMIRSYNTH_PACK_PASSWORD
docker compose run --rm --no-deps -T -e MIMIRSYNTH_PACK_PASSWORD -v "$PWD:/work:ro" mimirsynth   python -m mimirsynth.packcrypt decrypt /work/paquete.mimirsynth.tar.gz.enc - > paquete.mimirsynth.tar.gz
```
Una contraseña equivocada, o un paquete modificado o incompleto, terminan con un error y sin salida.

## API
`POST /api/brains/{slug}/exports` (`{"vectors": false, "password": "…"}`, la contraseña es opcional) lanza la exportación y devuelve el trabajo. `GET /api/brains/{slug}/exports` lista las últimas con su estado (`queued`, `running`, `failed`, `ready`, `downloaded`, `expired`). `GET /api/brains/{slug}/exports/{id}/download` da el paquete una vez; después, o cuando caduca, responde 410. Ver [[API REST]].
