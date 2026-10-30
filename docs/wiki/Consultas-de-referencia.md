[English](Reference-queries) · **Español**

# Consultas de referencia

Una **consulta de referencia** es una pregunta junto con lo que su recall **debe** traer y lo que **no**. Tener un conjunto de ellas por brain permite medir con datos la calidad del recall antes y después de cambiar el umbral de los pasajes, el modelo de embeddings o los pesos, en vez de juzgarla por unas pocas búsquedas en [[Preguntar]].

## Quién puede usarlas
Están en **Preguntar → Consultas de referencia**, para **curadores y roles superiores** (ver [[Roles y permisos]]); lectores y colaboradores no ven la pestaña. Cada brain tiene las suyas, hasta 500.

## Crear consultas
**Nueva consulta** abre el formulario:
- **Consulta:** la pregunta, tal como la haría un agente.
- **Debe aparecer:** un texto por línea. Cuenta como encontrado si aparece en algún resultado (hecho, fragmento de episodio o pasaje de documento), sin contar mayúsculas ni espacios. Empieza la línea por `fact:`, `chunk:` o `doc:` para exigir ese tipo de resultado.
- **No debe aparecer:** falsos positivos conocidos, con el mismo formato.
- **Sección de documentos:** **Da igual**, **Debe haber pasajes de documentos** o **No debe haber pasajes de documentos**.
- **Nota:** texto libre para ti.

Cada lista admite hasta 50 textos de hasta 500 caracteres. Cada fila tiene **Editar** y **Borrar**; borrar una consulta no cambia el resultado de las ejecuciones anteriores.

También puedes crearlas desde [[Preguntar]]: tras una búsqueda, marca resultados como **Debe salir** o **Sobra** y pulsa **Guardar como consulta de referencia**; el formulario se abre ya relleno.

Los textos pasan por el detector de secretos del brain, así que guardar un hecho del grafo como texto esperado nunca copia una credencial: según el ajuste del brain, el secreto se enmascara o la consulta se rechaza.

## Importar y exportar
- **Exportar** descarga todas las consultas del brain en JSON, para llevarlas a otro brain o a otra instancia.
- **Importar** añade las consultas de un archivo JSON. Una consulta cuyo texto coincide con otra ya guardada (sin contar mayúsculas ni espacios) se salta, y se indica cuántas se importaron y cuántas se saltaron.

```json
{"items": [
  {"query": "¿Dónde corre el servicio de correo?",
   "expect": [{"text": "el servicio de correo corre en el servidor 2", "kind": "fact"}],
   "avoid": [{"text": "servidor de correo antiguo", "kind": "any"}],
   "docs": null,
   "note": ""}
]}
```

`kind` es `any`, `fact`, `chunk` o `doc`; `docs` es `true` (debe haber pasajes), `false` (no debe haberlos) o `null` (da igual). También se acepta una lista de consultas sin envoltorio.

## Ejecutar
**Ejecutar** mide todas las consultas con los ajustes en vigor del brain, lanzando el mismo recall que recibe un agente (incluido lo que le presten otros brains, si es el caso). Se ejecuta como un trabajo (ver [[Trabajos]]) y la tabla **Ejecuciones** se actualiza mientras avanza:
- **Parámetros:** «ajustes en vigor», o el umbral simulado.
- **Encontrados:** textos esperados encontrados sobre el total, y el porcentaje.
- **Falsos positivos:** textos que no debían aparecer y aparecieron.
- **Documentos al revés:** consultas cuya sección de documentos salió al contrario de lo que piden.
- **Mediana:** la mediana del tiempo de recall.
- **Frente a la anterior:** **mejora**, **empeora** o **igual**, con la diferencia de encontrados y de falsos positivos y cuántas consultas se compararon.

**Ver** abre el detalle de una ejecución: lo encontrado por tipo y, por cada consulta, lo que **falta**, lo que **sobra** y si su sección de documentos salió bien. Si la ejecución empeora, enumera lo que **deja de salir** y cada **falso positivo nuevo**.

Se conservan las **20 últimas ejecuciones** de cada brain.

## Simular
Escribe uno o varios umbrales de similitud de los pasajes en **Umbrales a simular** (por ejemplo `0,68 0,70 0,72`, hasta 6) y pulsa **Simular**: se hace una ejecución por umbral, **sin cambiar el ajuste**. Compáralas y, cuando hayas elegido, pon el valor de *Similitud mínima de un pasaje* en Administración → Recuerdo (recall) ([[Recuerdo e ingesta]]).

## Cómo se comparan las ejecuciones
- Cada ejecución se compara con la anterior hecha con los **ajustes en vigor**; las simulaciones nunca sirven de base.
- Solo cuenta lo que está en **las dos ejecuciones**: las mismas consultas y los mismos textos. Añadir, borrar o editar una consulta nunca aparece como un empeoramiento.
- Una ejecución **empeora** si un texto esperado que salía deja de salir, aparece un falso positivo nuevo o la sección de documentos de una consulta se pone al revés.

## Durante un cambio de modelo de embeddings
Cuando se cambia el modelo de embeddings (Administración → Embeddings → **Reindexar**, ver [[Proveedores de IA]]), cada brain con consultas de referencia las ejecuta solo dos veces: cuando empiezan a calcularse los vectores nuevos, todavía con el modelo anterior, como base (marcada «antes del cambio de modelo»), y cuando termina el cambio («tras el cambio de modelo»).

Si la segunda empeora, salta la alerta **`refquery.regressed`** (aviso) con cuántos textos esperados se perdieron y cuántos falsos positivos son nuevos. Si no había una ejecución anterior con la que comparar, la misma alerta lo dice como información, y esa ejecución queda como base para el próximo cambio. Las alertas salen en la campana y van a los canales configurados (ver [Notificaciones](https://github.com/MimirSynth/mimirsynth/blob/main/docs/es/NOTIFICATIONS.md)).

Tras un cambio de modelo es buen momento para **Simular** unos cuantos umbrales: el umbral adecuado de los pasajes depende del modelo.

Más detalle: «Consultas de referencia» en [ARCHITECTURE.md](https://github.com/MimirSynth/mimirsynth/blob/main/docs/es/ARCHITECTURE.md).
