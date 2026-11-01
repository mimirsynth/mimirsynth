[English](Contradictions) · **Español**

# Contradicciones

Pestaña **Contradicciones** de [[Calidad del contenido]] (curadores y superiores). Lista los **hechos vigentes que se contradicen** en relaciones que solo admiten un valor a la vez y te deja elegir cuál sigue vigente.

## Por qué existe
Cuando un episodio nuevo contradice un hecho, la ingesta suele invalidar el antiguo. No siempre: dos episodios redactados de forma distinta pueden dejar vigentes a la vez «el portátil está en la Oficina A» y «el portátil está en la Oficina B». El recall le pasa entonces los dos a tu agente como si ambos fueran ciertos. Esta pestaña encuentra esos casos **sin ningún modelo de IA** y deja la decisión a una persona.

## Relaciones de un solo valor
Solo se buscan contradicciones en los tipos de relación marcados como **de un solo valor**: un sujeto no puede tener dos destinos vigentes, como dónde está instalado un equipo o a quién informa una persona.
- Las marca un administrador del brain en [[Ontología]] (edita el tipo de relación y marca **Un solo valor a la vez**; la tabla de tipos de relación tiene una columna **Un solo valor**) o directamente desde la medición de abajo, con **Marcar**.
- **Ninguna relación es de un solo valor por defecto, tampoco en los paquetes estándar.** Muchas lo parecen y no lo son: «ubicado en» puede apuntar a la vez a un edificio, a una red y a un armario. Cada brain marca las suyas **después de medir** (ver abajo).
- Si no hay ninguna marcada, la pestaña lo avisa y no busca nada, con atajos a **Medir ahora** y a la pestaña Ontología.
- Las **relaciones genéricas** como `RELATES_TO` (lo que escribe el extractor cuando ningún tipo encaja) no se comparan nunca ni se pueden marcar: unen cualquier cosa, así que solo darían ruido. La pestaña dice cuántos hechos se dejaron fuera por eso.

## Qué cuenta como contradicción
Hechos vigentes con el **mismo sujeto**, la **misma relación** y **destinos distintos del mismo tipo de entidad**:
- Las relaciones se comparan tras normalizar el formato y los [alias](Relaciones-y-alias), así que `LocatedAt` y `LOCATED_AT` son la misma relación.
- Solo se comparan destinos del **mismo tipo de entidad**: «X ubicado en un edificio» y «X ubicado en una red» no se contradicen.
- Dos destinos con el mismo nombre salvo mayúsculas y espacios cuentan como el mismo. Eso es una entidad duplicada, no una contradicción: ver [[Fusionar duplicados]].

## Revisar un caso
Una nota arriba explica para qué sirve la pestaña y qué hace cada acción. Los casos son una tabla compacta con una fila por grupo: **Sujeto**, **Relación**, **Tipo del destino** (el tipo de entidad de los destinos; solo se comparan destinos del mismo tipo), **Hechos** y **Propuesta**. **Revisar** abre un grupo. La columna **Propuesta** dice si la hay:

| Etiqueta | Significado |
|---|---|
| *destino* **el más reciente** | Un hecho tiene una **fecha de validez** (cuándo empezó a ser cierto) estrictamente más reciente. Viene preseleccionado |
| **misma fecha: decide tú** | Los hechos más recientes comparten fecha. No se preselecciona nada |
| **solo fecha de aprendizaje: decide tú** | Algún hecho solo tiene la fecha en que se **aprendió**, que no dice cuál es más actual. No se preselecciona nada |
| **probablemente varios valores** | La relación parece admitir varios valores a la vez (ver más abajo). No se preselecciona nada |

Un grupo abierto muestra cada hecho con su destino, su fecha («cierto desde» o «aprendido el») y su frase, recortada a dos líneas con **Ver entero**. Un grupo largo se desplaza dentro de su propia zona. **Cómo resolver** tiene dos modos:
- **Quedarse solo con uno** pregunta **¿Qué hecho sigue siendo cierto?**, con una opción por hecho. **Resolver: invalidar los otros N** conserva el hecho elegido; el botón no se activa hasta elegir uno. Es el modo para una relación de un solo valor de verdad.
- **Invalidar los que ya no son ciertos** pregunta **¿Qué hechos ya no son ciertos?**, con una casilla por hecho. **Invalidar los marcados (N)** invalida solo los marcados y deja vigentes los demás; no se activa hasta marcar uno, ni mientras estén todos marcados, porque siempre tiene que quedar alguno vigente. Es el modo para un grupo en el que solo algunos hechos han caducado.

Invalidar más de un hecho pide confirmación antes, con la lista de destinos. Después:
- **No es una contradicción** oculta el grupo, para un falso positivo. Sigue oculto mientras sus hechos sean los mismos: si llega un hecho nuevo al grupo, vuelve a salir. Los grupos ocultos se listan en **Marcados como no contradicción**, donde **Volver a mostrar** recupera uno.

Al resolver:
- Los hechos se **invalidan**, no se borran. Con **Quedarse solo con uno**, su fecha de fin es la fecha de validez del que se queda si es posterior (así la línea temporal dice cuándo cambió) o, si no, la hora actual; con **Invalidar los que ya no son ciertos**, la hora actual.
- Siempre queda vigente al menos un hecho del grupo: el servidor rechaza una resolución que no dejaría ninguno.
- Cada hecho invalidado queda en el historial del vocabulario (**Cambios recientes** en [[Tipos de entidad]]), desde donde un administrador del brain puede **deshacerlo** mientras no se haya hecho otro cambio de vocabulario después. Se deshace primero el más reciente. La resolución queda también en la [[Auditoría]].
- [[Hechos]] muestra los invalidados como no vigentes, igual que cualquier otra invalidación.

## Relaciones que probablemente admiten varios valores
Una relación como `MONITORS` puede tener muchos destinos por naturaleza: un servidor de monitorización vigila decenas de servicios, y todos son ciertos. Si se marcó por error como de un solo valor, cada sujeto con varios destinos sale como contradicción. Una relación se señala como **probablemente varios valores** cuando algún sujeto tiene **3 destinos vigentes o más** del mismo tipo, o cuando al menos **una cuarta parte** de sus sujetos (con dos casos como mínimo) tiene varios. Entonces:
- Sus grupos no traen ningún hecho preseleccionado, y el grupo se abre en **Invalidar los que ya no son ciertos**.
- Un grupo abierto avisa **Probablemente no es una contradicción**: cuántos destinos vigentes tiene el sujeto (o qué proporción de sujetos tiene varios) y que, si la relación admite varios valores, hay que desmarcar «Un solo valor a la vez» en [[Ontología]]. **Editar la relación** abre el diálogo de edición de esa relación en la pestaña Ontología, y un administrador del brain puede **Desmarcar ahora** desde ahí mismo; el grupo deja entonces de salir.
- La tabla de la medición muestra la misma señal junto al nombre de la relación.

## Medir antes de marcar
**Medir en todas las relaciones** revisa todas las relaciones, marcadas o no, **sin cambiar nada**. La tabla **Candidatos por relación** muestra, por cada relación con algún caso:

| Columna | Qué muestra |
|---|---|
| **Relación** | El nombre normalizado de la relación, con **probablemente varios valores** si lo parece (ver arriba) |
| **Sujetos** | Cuántos sujetos la usan |
| **Con varios destinos** | Cuántos tienen más de un destino vigente del mismo tipo |
| **Proporción** | La proporción entre ambos, de menor a mayor |
| **Un solo valor** | Si ya está marcada |

Las buenas candidatas tienen **proporción baja y algún caso**: la mayoría de sujetos tienen un destino y unos pocos dos, que es como se ve una contradicción que se escapó. Una relación con proporción alta, o señalada como **probablemente varios valores**, probablemente admite varios valores: no la marques. Un administrador del brain puede **Marcar** una relación desde esta tabla si está en la ontología, y **Desmarcar** una marcada que salga señalada. Mientras mides se listan los casos de todas las relaciones, pero solo se pueden resolver los de relaciones ya marcadas. **Volver a las relaciones de un solo valor** regresa a la vista normal.

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
