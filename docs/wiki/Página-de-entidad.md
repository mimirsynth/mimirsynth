[English](Entity-page) · **Español**

# Página de entidad

Todo lo que el brain sabe de **una entidad** (un servicio, un host, una persona…) y **cómo ha cambiado**, en una sola página. Responde a «¿qué sabemos de X y desde cuándo?», que es para lo que sirve una memoria bitemporal.

## Cómo se llega
- Desde [[Hechos]]: clic en la entidad origen o destino de un hecho.
- Desde el [[Grafo]]: selecciona un nodo y pulsa **Ver página** en el panel lateral.
- Desde [[Consulta Cypher]]: una entidad de la tabla de resultados es un enlace, y un nodo seleccionado en la pestaña del grafo tiene **Ver página**.
- Desde [[Preguntar]]: clic en una entidad de un hecho devuelto. Un hecho prestado abre su entidad en el brain que lo presta.
- Desde la propia página: cada entidad relacionada es un enlace.

## Qué muestra
- **La tarjeta de arriba:** a la izquierda, el nombre, su tipo (para los curadores, un botón con un lápiz que abre «Cambiar tipo») y los nombres fusionados en ella como chips pequeños (un nombre fusionado igual al de la propia entidad, salvo mayúsculas o espacios, no se muestra nunca), y debajo el **Resumen** de la entidad (cortado tras unas líneas, con **Ver más**). El resumen no se muestra cuando al menos la mitad de sus líneas son las frases de los propios hechos de la entidad, algo frecuente porque el extractor lo escribe como una lista de ellos: ya lo dicen los hechos de abajo. Un curador puede pedir que se escriba uno mejor y aprobarlo en [[Calidad del contenido]] → Resúmenes. A la derecha, el grafo pequeño que se describe en **Relacionadas**. En el móvil la tarjeta es una sola columna: el nombre, el grafo y después el resumen. **← Hechos**, encima, vuelve atrás; **Hechos** es la sección marcada en la barra lateral, y **Cómo estaba el día** sigue arriba a la derecha.
- **Hechos agrupados por relación.** Cada grupo es un dato que se lee como una **evolución**, de lo más antiguo a lo más reciente: «HOSTED_ON → Eridani → Polaris → Notus». El valor vigente se muestra con sus fechas; los anteriores quedan plegados en **Ver anteriores (N)** y aparecen tachados, con el periodo en que fueron ciertos. El encabezado de cada grupo se lee como una frase en el mismo orden en los dos sentidos, con la entidad de la página en su lado: «Lyra → hosted on → Hetzner» para un hecho del que la entidad es el sujeto, «Arcane → hosted on → Lyra» para uno que apunta a ella. La relación se escribe en palabras (`HOSTED_ON` se lee «hosted on»; el nombre original aparece al pasar el ratón), los valores vigentes son enlaces (los tres primeros, y cuántos más), y «—» significa que no hay valor vigente. Primero van los grupos con una posible contradicción y después los que tienen más valores vigentes.
- **Otras relaciones:** las relaciones genéricas como `RELATES_TO`, que el extractor escribe cuando ningún tipo encaja, unen cualquier cosa, así que su «evolución» dice poco. Quedan plegadas en una sección al final, con el número de hechos; **Ver** la abre.
- **Dos fechas por hecho:** desde cuándo es cierto (*vigente desde*, *válido … → …*) y cuándo lo **aprendió** el brain. Son ejes distintos: un hecho aprendido hoy puede ser cierto desde el año pasado.
- **Relacionadas:** el grafo de la tarjeta de arriba, con la entidad y las 12 entidades con las que comparte más hechos vigentes, una arista por vecina con su relación más frecuente (×N cuando las unen varios hechos; discontinua si ninguno está vigente). Para que las etiquetas no se pisen, solo las tres aristas más fuertes muestran la suya; al señalar una vecina se ven su nombre y todas sus relaciones. Un clic en una vecina abre su página; en el móvil el primer toque la nombra y el segundo la abre. «y N más» dice cuántas quedan fuera, y **Ampliar** abre el [[Grafo]] con la entidad seleccionada. Las mismas vecinas están también como enlaces para el teclado y los lectores de pantalla.
- **Hechos y episodios lado a lado:** los hechos ocupan la izquierda, en torno al 70 %, y la columna de la derecha enumera los **episodios que la mencionan**, los más recientes, con enlace al episodio en el [[Diario]]. En el móvil los episodios van después de los hechos.
- **Entidades como chips del color de su tipo:** allí donde se nombra una entidad (los encabezados de relación, las tarjetas de hecho), es el mismo chip, con un punto y un borde del color de su tipo y el tipo como ayuda emergente. Cada tipo tiene **un solo color en todas las pantallas**: los chips, este grafo, el [[Grafo]] y la [[Consulta Cypher]] usan el mismo reparto. La entidad de la página va sin enlace.
- **Documentos que la mencionan:** pasajes de [[Conocimiento]], si los hay. Salen de una llamada aparte (`GET /docs/mentions?entity=`), no del endpoint de la entidad, y no se muestran en una entidad prestada.

## Cómo estaba un día
**Cómo estaba el día** elige una fecha: la página muestra entonces lo que estaba **vigente ese día**, según las fechas de validez, igual que el viaje en el tiempo del [[Grafo]]. Lo que aún no era cierto queda fuera (la página dice cuántos hechos). **Hoy** vuelve al presente. Mientras miras un día pasado, las acciones de curador se ocultan.

## Posibles contradicciones
Si una relación está marcada como de **un solo valor** en la [[Ontología]] y la entidad tiene dos valores vigentes distintos, el grupo lo dice y enlaza a [[Contradicciones]], donde se resuelve. La página muestra el caso en vez de esconderlo.

## Acciones de curador
- **Invalidar** un hecho vigente, o **Reactivar** uno anterior, desde el propio hecho. Son las mismas acciones que en [[Hechos]] y se deshacen desde el historial del vocabulario.
- **Cambiar tipo**: el tipo de la entidad en la cabecera es un botón con un lápiz para los curadores: eliges uno de los tipos de la [[Ontología]] del brain (la misma lista cerrada que usa el [[Corrector de tipos]]; no se acepta otro). El cambio se ve al momento aquí y en el [[Grafo]], queda en el registro de auditoría y se deshace desde el mensaje que lo confirma o desde **Cambios recientes** en [[Tipos de entidad]]. Si el corrector de tipos tenía una propuesta pendiente para esta entidad, deja de ofrecerse, y un análisis posterior no la vuelve a proponer.
- Enlaces para **fusionar** la entidad con otra ([[Fusionar duplicados]]), revisar los **tipos dudosos** de todo el brain ([[Corrector de tipos]], administradores) y **editar el texto** de un hecho ([[Hechos]]).

## Entidades prestadas
Con la [[Federación]], una entidad de un brain que presta su grafo se abre con su origen («de «slug»») y es **de solo lectura**.

## Accesibilidad
La evolución de cada relación es una lista ordenada, no un gráfico, así que un lector de pantalla la lee en orden, y cada entidad, episodio y acción se alcanza con el teclado.
