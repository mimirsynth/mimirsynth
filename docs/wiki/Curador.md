[English](Curator) · **Español**

# Curador

El **curador** recorre el grafo de un brain una vez al día y convierte lo que encuentra en **propuestas en cuarentena**, cada una con su evidencia. No cambia nada por su cuenta: un curador decide cada propuesta en [[Propuestas]], de una en una, y cada cambio queda en el historial del vocabulario y se puede deshacer. Está en [[Calidad del contenido]] → **Curador**.

## Qué busca
Por ahora, **contradicciones claras** en las relaciones marcadas como funcionales (un solo valor a la vez, ver [[Contradicciones]]): un sujeto con dos valores vigentes en el que uno tiene una fecha de validez estrictamente más reciente, todas las fechas son de validez y la relación no parece de varios valores. La propuesta se queda con el valor más reciente e invalida los demás, con la fecha del más reciente. Deja fuera:
- los grupos que un curador marcó como «no es una contradicción»;
- los que no están claros, que siguen en Calidad del contenido → Contradicciones para una persona;
- los hechos que ya tienen una propuesta pendiente.

Y, cuando lo marca un administrador (está desactivado por defecto), **hechos repetidos**: hechos vigentes entre las mismas dos entidades que dicen lo mismo. Es decir, el mismo texto, o embeddings muy cercanos con los mismos números e identificadores, como cuenta la redundancia la [[Salud de la memoria]]: «PostgreSQL 14» y «PostgreSQL 16» son un cambio, no una repetición. La propuesta se queda con el más reciente e invalida los demás. Se leen hasta 3.000 hechos candidatos por ejecución, los más recientes primero.

Y, también desactivados por defecto, **hechos pasados de su vida útil**: los hechos vigentes que lista Calidad del contenido → A revisar (relaciones con vida útil, sin confirmar a tiempo), los más atrasados primero. Cada uno se convierte en una propuesta para invalidarlo. Rechazar la propuesta, o confirmar el hecho en A revisar, lo conserva.

Y, también desactivado por defecto, el **ruido**: hechos vigentes que no dicen nada útil, según cuatro reglas conservadoras a propósito.
- Un extremo es un comodín y no una cosa del mundo («it», «esto», «algo»…).
- Un extremo es la propia memoria («el grafo», «la memoria», «episodio», «hecho»…). No cuentan nombres que pueden ser cosas reales, como «node» (Node.js), «memory» (RAM) o «edge».
- Una relación genérica (`RELATES_TO`, `MENTIONS`…) cuyo texto no añade nada a sus dos entidades. Decide el texto, no la relación: un texto con un número (una versión, una fecha, un puerto), un identificador (`ready-for-review`, `host.lan`), un mes o una negación («Epsilon ya no aloja Vaultwarden», «not») nunca es ruido, y «está relacionado con», «is related to» y similares no cuentan como contenido.
- Un cambio contado como suceso («X se migró a Y») cuando otro hecho vigente entre las mismas entidades ya dice el resultado. Si es la única huella del cambio, se conserva.

Y, también desactivados por defecto, **hechos que nunca se recuperan**: hechos vigentes que ningún recall ha traído en los últimos 180 días (`archive_days`, ajustable por el API), aprendidos antes de eso y que nunca confirmó una persona ni una sonda. Aprobar uno lo **archiva**: sigue en el grafo sin cambios, pero el recall lo deja fuera salvo que se pida (`archived: true` en `POST /recall` o en el `recall` del MCP). La lista **Archivados** de esta pestaña restaura cualquiera con un clic. Cada recall registrado anota cuándo salieron sus hechos, y esta pasada solo propone cuando el brain lleva vigilado el periodo completo; antes, cualquier hecho antiguo parecería sin usar.

Y, también desactivado por defecto, **destilar**: episodios que repiten la misma lección con palabras algo distintas.
- **Grupos.** Varios episodios forman un grupo si mencionan la misma entidad y cada par se parece: coseno ≥ 0,85 (`distil_similarity`) entre sus vectores del índice de episodios. Un grupo necesita al menos 3 episodios (`distil_min`), y se prueba primero la entidad más concreta. Agrupar no llama a la IA, así que **Ver qué propondría** no cuesta nada.
- **La nota.** Para cada grupo, el LLM del brain escribe una nota corta con la lección tal como está ahora y la fecha desde la que vale; si los originales no coinciden, manda el más reciente. Cada grupo es una llamada, como mucho 5 por ejecución diaria (`distil_calls`).
- **Aprobación.** La propuesta (`curator.distil`) muestra sus originales. **Nunca se aprueba sola**: ni niveles de aprobación automática, ni decisor, ni aprobación en bloque. Una persona lee lo que escribió el LLM, una a una.
- **Los originales.** Cada uno va marcado «borrar si la nota lo cubre»; desmarca antes de aprobar los que deban quedarse. Al ingerir la nota, un original está **cubierto** si cada hecho que salió solo de él sigue vigente y coincide con un hecho de la nota: las mismas dos entidades y la misma relación o un texto parecido. Los cubiertos y marcados se **borran**, y no se puede deshacer; los demás se quedan, y la propuesta dice qué aporta cada uno. Borrar un episodio quita los hechos que solo él sostiene y las entidades que se quedan sin nada; un hecho que también sostienen otros episodios se queda.

Los tres ajustes van en `PUT …/curator/settings`; si una petición no trae alguno, conserva su valor.

Cada pasada es una fila de **Pasadas**, con su interruptor, su precisión, que dice cuánto fiarse de ella.

## Se detiene si baja la cobertura
Antes de proponer nada, el curador mira la [[Salud de la memoria]]. Si la cobertura de las consultas de referencia bajó más de *Salud de la memoria: avisar si la cobertura baja* respecto a la medición anterior, y entre medias se aprobaron propuestas suyas, ese día no propone nada. La ejecución termina **detenida**, con las cifras, y lo avisa la notificación **curator.stopped**.

## Activarlo
Está **desactivado por defecto**. Un administrador del brain enciende **Activar el curador en este brain**, la primera fila de **Pasadas**. Desde entonces se ejecuta una vez al día (el día es la clave de la ejecución: un reinicio nunca lo ejecuta dos veces), y **Ejecutar ahora** lo lanza al momento. **Ver qué propondría** lo muestra sin crear nada; en la pasada de ruido agrupa los hallazgos por regla, con cuántos encuentra cada una, para ver qué regla mete ruido antes de activarla.

## Una muestra antes de un lote
Si una ejecución fuera a proponer **más de 5 cambios** a la vez (el lote, ajustable por el API), no propone nada. En su lugar, espera con una muestra de lo que cambiaría y de lo que conserva. Cuando se retira un servicio pueden caer decenas de hechos a la vez, y solo una persona distingue «sigue siendo útil» de «ya no vale». **Crear las propuestas** las crea todas, y cada una se sigue decidiendo aparte; **Descartar** deja la ejecución sin efecto.

## Decidir sus propuestas
Sus propuestas no tienen texto, solo afirmaciones: sujeto, relación, el valor que se queda y el hecho al que sustituye cada una (ver [[Propuestas]] → Afirmaciones estructuradas). Como una corrección, se deciden de una en una: ni el decisor ni la aprobación en lote las aprueban. Al aprobar una, el hecho antiguo se invalida en cuanto pasan los 10 segundos para deshacer, sin necesidad de LLM. Al rechazarla, todo queda como estaba.

## Precisión
La pestaña dice cuántas de sus propuestas han aprobado y rechazado los curadores hasta ahora. Esa es la medida para confiar más en él más adelante ([#299](https://github.com/mimirsynth/mimirsynth/issues/299)).

## API
`GET/PUT /api/brains/{slug}/curator/settings` (`enabled`, `passes`, `batch`; cambiarlos requiere un administrador del brain), `POST …/curator/preview` (con `by_rule` en la pasada de ruido), `POST …/curator/run`, `GET …/curator/runs`, `POST …/curator/runs/{id}/confirm` y `…/discard`.
