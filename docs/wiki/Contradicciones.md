[English](Contradictions) · **Español**

# Contradicciones

Pestaña **Contradicciones** de [[Vocabulario]] (curadores y superiores). Lista los **hechos vigentes que se contradicen** en relaciones que solo admiten un valor a la vez y te deja elegir cuál sigue vigente.

## Por qué existe
Cuando un episodio nuevo contradice un hecho, la ingesta suele invalidar el antiguo. No siempre: dos episodios redactados de forma distinta pueden dejar vigentes a la vez «el portátil está en la Oficina A» y «el portátil está en la Oficina B». El recall le pasa entonces los dos a tu agente como si ambos fueran ciertos. Esta pestaña encuentra esos casos **sin ningún modelo de IA** y deja la decisión a una persona.

## Relaciones de un solo valor
Solo se buscan contradicciones en los tipos de relación marcados como **de un solo valor**: un sujeto no puede tener dos destinos vigentes, como dónde está instalado un equipo o a quién informa una persona.
- Las marca un administrador del brain en [[Ontología]]: edita el tipo de relación y marca **Un solo valor a la vez**. Las relaciones marcadas llevan la etiqueta **un solo valor** en la tabla de tipos de relación.
- **Ninguna relación es de un solo valor por defecto, tampoco en los paquetes estándar.** Muchas lo parecen y no lo son: «ubicado en» puede apuntar a la vez a un edificio, a una red y a un armario. Cada brain marca las suyas **después de medir** (ver abajo).
- Si no hay ninguna marcada, la pestaña lo avisa y no busca nada.

## Qué cuenta como contradicción
Hechos vigentes con el **mismo sujeto**, la **misma relación** y **destinos distintos del mismo tipo de entidad**:
- Las relaciones se comparan tras normalizar el formato y los [alias](Relaciones-y-alias), así que `LocatedAt` y `LOCATED_AT` son la misma relación.
- Solo se comparan destinos del **mismo tipo de entidad**: «X ubicado en un edificio» y «X ubicado en una red» no se contradicen.
- Dos destinos con el mismo nombre salvo mayúsculas y espacios cuentan como el mismo. Eso es una entidad duplicada, no una contradicción: ver [[Fusionar duplicados]].

## Revisar un caso
Cada tarjeta muestra el sujeto y la relación, el tipo de los destinos y cada hecho vigente con su fecha. Una etiqueta indica si hay propuesta:

| Etiqueta | Significado |
|---|---|
| **el más reciente es claro** | Un hecho tiene una **fecha de validez** (cuándo empezó a ser cierto) estrictamente más reciente. Viene preseleccionado |
| **misma fecha: decide tú** | Los hechos más recientes comparten fecha. No se preselecciona nada |
| **solo fecha de aprendizaje: decide tú** | Algún hecho solo tiene la fecha en que se **aprendió**, que no dice cuál es más actual. No se preselecciona nada |

Para resolverlo, escoge en **Elige cuál se queda** el hecho que sigue siendo cierto y pulsa **Dejar este e invalidar el resto**.
- Los demás hechos se **invalidan**, no se borran. Su fecha de fin es la fecha de validez del que se queda si es posterior (así la línea temporal dice cuándo cambió) o, si no, la hora actual.
- Cada hecho invalidado queda en el historial del vocabulario (**Cambios recientes** en [[Tipos de entidad]]), desde donde un administrador del brain puede **deshacerlo** mientras no se haya hecho otro cambio de vocabulario después. Se deshace primero el más reciente. La resolución queda también en la [[Auditoría]].
- [[Hechos]] muestra los invalidados como no vigentes, igual que cualquier otra invalidación.

## Medir antes de marcar
**Medir en todas las relaciones** revisa todas las relaciones, marcadas o no, **sin cambiar nada**. La tabla **Candidatos por relación** muestra, por cada relación con algún caso:

| Columna | Qué muestra |
|---|---|
| **Relación** | El nombre normalizado de la relación |
| **Sujetos** | Cuántos sujetos la usan |
| **Con varios destinos** | Cuántos tienen más de un destino vigente del mismo tipo |
| **Proporción** | La proporción entre ambos, de menor a mayor |
| **Un solo valor** | Si ya está marcada |

Las buenas candidatas tienen **proporción baja y algún caso**: la mayoría de sujetos tienen un destino y unos pocos dos, que es como se ve una contradicción que se escapó. Una relación con proporción alta probablemente admite varios valores: no la marques. Mientras mides se listan los casos de todas las relaciones, pero solo se pueden resolver los de relaciones ya marcadas. **Volver a las relaciones de un solo valor** regresa a la vista normal.

La misma medición está disponible desde la línea de comandos, en solo lectura, lo que ayuda antes de marcar nada:

```bash
docker compose exec mimirsynth python -m mimirsynth.conflicts <grafo> [--brain-id N] [--top N]
```

`<grafo>` es el nombre del grafo del brain (aparece en Administración → Brains). Con `--brain-id` se aplican los alias y las relaciones marcadas del brain; `--top` limita cuántos casos se imprimen (20 por defecto). La salida es JSON.

## Revisión diaria y aviso
Una vez al día se revisa cada brain que tenga al menos una relación de un solo valor. Si hay casos, el aviso **`conflicts.found`** (información) aparece en la campana de notificaciones de los curadores del brain y de los administradores de la instancia, y llega a los canales de notificación que lo incluyan; se cierra solo cuando ya no quedan casos. Los brains sin ninguna relación marcada no se revisan nunca.

## Límites
- Se leen hasta 50.000 hechos vigentes por revisión, los más recientes primero; si se llega al límite, la pestaña lo indica.
- Se muestran hasta 200 casos a la vez, primero los que tienen más hechos; el total siempre se cuenta.
