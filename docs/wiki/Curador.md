[English](Curator) · **Español**

# Curador

El **curador** recorre el grafo de un brain una vez al día y convierte lo que encuentra en **propuestas en cuarentena**, cada una con su evidencia. No cambia nada por su cuenta: un curador decide cada propuesta en [[Propuestas]], de una en una, y cada cambio queda en el historial del vocabulario y se puede deshacer. Está en [[Calidad del contenido]] → **Curador**.

## Qué busca
Por ahora, **contradicciones claras** en las relaciones marcadas como funcionales (un solo valor a la vez, ver [[Contradicciones]]): un sujeto con dos valores vigentes en el que uno tiene una fecha de validez estrictamente más reciente, todas las fechas son de validez y la relación no parece de varios valores. La propuesta se queda con el valor más reciente e invalida los demás, con la fecha del más reciente. Deja fuera:
- los grupos que un curador marcó como «no es una contradicción»;
- los que no están claros, que siguen en Calidad del contenido → Contradicciones para una persona;
- los hechos que ya tienen una propuesta pendiente.

El ruido, la redundancia y los hechos desactualizados vienen después ([#300](https://github.com/mimirsynth/mimirsynth/issues/300)).

## Activarlo
Está **desactivado por defecto**. Un administrador del brain marca **Activar el curador en este brain**. Desde entonces se ejecuta una vez al día (el día es la clave de la ejecución: un reinicio nunca lo ejecuta dos veces), y **Ejecutar ahora** lo lanza al momento. **Ver qué propondría** lo muestra sin crear nada.

## Una muestra antes de un lote
Si una ejecución fuera a proponer **más de 5 cambios** a la vez (el lote, ajustable por el API), no propone nada. En su lugar, espera con una muestra de lo que cambiaría y de lo que conserva. Cuando se retira un servicio pueden caer decenas de hechos a la vez, y solo una persona distingue «sigue siendo útil» de «ya no vale». **Crear las propuestas** las crea todas, y cada una se sigue decidiendo aparte; **Descartar** deja la ejecución sin efecto.

## Decidir sus propuestas
Sus propuestas no tienen texto, solo afirmaciones: sujeto, relación, el valor que se queda y el hecho al que sustituye cada una (ver [[Propuestas]] → Afirmaciones estructuradas). Como una corrección, se deciden de una en una: ni el decisor ni la aprobación en lote las aprueban. Al aprobar una, el hecho antiguo se invalida en cuanto pasan los 10 segundos para deshacer, sin necesidad de LLM. Al rechazarla, todo queda como estaba.

## Precisión
La pestaña dice cuántas de sus propuestas han aprobado y rechazado los curadores hasta ahora. Esa es la medida para confiar más en él más adelante ([#299](https://github.com/mimirsynth/mimirsynth/issues/299)).

## API
`GET/PUT /api/brains/{slug}/curator/settings` (`enabled`, `passes`, `batch`; cambiarlos requiere un administrador del brain), `POST …/curator/preview`, `POST …/curator/run`, `GET …/curator/runs`, `POST …/curator/runs/{id}/confirm` y `…/discard`.
