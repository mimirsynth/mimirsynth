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
- **Cabecera:** nombre, tipo, los nombres fusionados en ella («También: …») y su resumen.
- **Hechos agrupados por relación.** Cada grupo es un dato que se lee como una **evolución**, de lo más antiguo a lo más reciente: «HOSTED_ON → Eridani → Polaris → Notus». El valor vigente se muestra con sus fechas; los anteriores quedan plegados en **Ver anteriores (N)** y aparecen tachados, con el periodo en que fueron ciertos. Una relación que apunta a la entidad se muestra como «← RELACIÓN». Primero van los grupos con una posible contradicción y después los que tienen más valores vigentes.
- **Otras relaciones:** las relaciones genéricas como `RELATES_TO`, que el extractor escribe cuando ningún tipo encaja, unen cualquier cosa, así que su «evolución» dice poco. Quedan plegadas en una sección al final, con el número de hechos; **Ver** la abre.
- **Dos fechas por hecho:** desde cuándo es cierto (*vigente desde*, *válido … → …*) y cuándo lo **aprendió** el brain. Son ejes distintos: un hecho aprendido hoy puede ser cierto desde el año pasado.
- **Relacionadas:** las entidades con las que tiene hechos, con enlace a su propia página.
- **Episodios que la mencionan:** los más recientes, con enlace al episodio en el [[Diario]].
- **Documentos que la mencionan:** pasajes de [[Conocimiento]], si los hay. Salen de una llamada aparte (`GET /docs/mentions?entity=`), no del endpoint de la entidad, y no se muestran en una entidad prestada.

## Cómo estaba un día
**Cómo estaba el día** elige una fecha: la página muestra entonces lo que estaba **vigente ese día**, según las fechas de validez, igual que el viaje en el tiempo del [[Grafo]]. Lo que aún no era cierto queda fuera (la página dice cuántos hechos). **Hoy** vuelve al presente. Mientras miras un día pasado, las acciones de curador se ocultan.

## Posibles contradicciones
Si una relación está marcada como de **un solo valor** en la [[Ontología]] y la entidad tiene dos valores vigentes distintos, el grupo lo dice y enlaza a [[Contradicciones]], donde se resuelve. La página muestra el caso en vez de esconderlo.

## Acciones de curador
- **Invalidar** un hecho vigente, o **Reactivar** uno anterior, desde el propio hecho. Son las mismas acciones que en [[Hechos]] y se deshacen desde el historial del vocabulario.
- Enlaces para **fusionar** la entidad con otra ([[Fusionar duplicados]]), **cambiar su tipo** ([[Corrector de tipos]], administradores) y **editar el texto** de un hecho ([[Hechos]]).

## Entidades prestadas
Con la [[Federación]], una entidad de un brain que presta su grafo se abre con su origen («de «slug»») y es **de solo lectura**.

## Accesibilidad
La evolución de cada relación es una lista ordenada, no un gráfico, así que un lector de pantalla la lee en orden, y cada entidad, episodio y acción se alcanza con el teclado.
