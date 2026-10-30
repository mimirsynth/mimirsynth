[English](Graph) · **Español**

# Grafo

Una vista de **mapa** del conocimiento: las entidades son nodos y los hechos son las aristas que los unen. Ideal para descubrir cómo se relaciona todo, ver **de dónde salió cada cosa** y detectar rarezas (entidades aisladas, nodos duplicados, relaciones inesperadas).

## Controles de carga
- **Semillas:** cuántas entidades de partida se cargan (las más conectadas), de 5 a 100.
- **Saltos:** cuántos «saltos» de vecindad (0–2) se traen alrededor de cada semilla.
- **Grado mín.:** oculta los nodos con menos conexiones que ese número (afina la vista cuando hay mucho ruido).
- **Buscar nodo:** selecciona la primera entidad cuyo nombre contiene el texto y hace zoom sobre ella.
- **Invalidados:** incluye los hechos que dejaron de ser ciertos (se dibujan con **línea discontinua**).
- **Viajar en el tiempo:** un deslizador desde el primer episodio hasta hoy (los últimos 90 días si el brain no tiene episodios, por ejemplo uno solo con hechos importados); el mapa muestra lo que se sabía **ese día**.

El indicador inferior cuenta los nodos y hechos cargados, y avisa si la carga se **recortó por el tope de nodos**. Mientras se calcula el grafo, un aviso «Calculando el grafo…» tapa el lienzo.

Si llegas desde [[Conocimiento]] (una entidad mencionada en un documento), el grafo se centra en esa entidad y la deja seleccionada.

## Disposiciones y 2D / 3D
- **Fuerza** (la de partida), **Radial** (anillos por nivel) y **Árbol** (cada padre centrado sobre sus hijos). Al cambiar de disposición, cada nodo se desplaza animado a su nuevo sitio.
- **2D** o **3D**. El 3D se dibuja con WebGL y solo se carga cuando lo eliges; conserva los mismos controles, leyenda, halos, foco, descripción emergente y expansión. Si el navegador no tiene WebGL, un aviso lo indica y el grafo sigue en 2D. Si el 3D va lento incluso con los efectos reducidos, un aviso ofrece **Volver a 2D**.
- Las posiciones son estables: al recargar, el grafo no se reordena.

## Halos por origen
En la disposición de **Fuerza**, cada **origen** envuelve sus nodos en un halo translúcido de su color, con su nombre y su recuento. Un nodo respaldado por varios orígenes queda donde se solapan sus halos, y los orígenes que comparten más nodos se colocan uno junto a otro. Los nodos sin origen conocido van a una zona neutra debajo. En 3D, un halo es un volumen translúcido con su nombre encima.

**Agrupar por** elige qué cuenta como origen, sin volver a cargar el grafo:
- **Tipo de origen** (el de partida): Texto, Mensaje, JSON, o Documento, Carpeta de archivos o Wiki cuando el conocimiento salió de un documento.
- **Documento:** el documento del que se promovió.
- **Contribuidor:** la persona que envió la propuesta.
- **Agente / token:** el token de API que la envió.
- **Tipo de entidad:** agrupa por tipo en lugar de por procedencia.

Los orígenes de un nodo son los de los episodios que lo mencionan y los de sus hechos visibles. Los **8 orígenes mayores** llevan halo propio; el resto se junta en «Otros».

- La leyenda **Orígenes** los enumera: pulsa uno para **encender o apagar su halo**. **Halos por origen** los apaga todos (solo está disponible en la disposición de Fuerza).
- Lo que respaldan **2 o más orígenes** se dibuja con un anillo en el nodo y aristas más gruesas. **Solo confirmados por 2 o más orígenes** deja solo esos nodos y las relaciones entre ellos. No está disponible al agrupar por **Tipo de entidad**, porque no hay orígenes que contar.

Cargar la procedencia añade algo de tiempo en brains muy grandes.

## Interacción
- **Pasar por encima de un nodo:** tras una breve pausa se resalta su vecindad y el resto se atenúa; una descripción emergente muestra su nombre, tipo, conexiones y orígenes, y unas partículas recorren sus hechos vigentes.
- **Clic en un nodo:** mantiene resaltada su vecindad (también con los efectos reducidos) y abre el panel lateral con su resumen, su tipo y su **grado**, sus **Orígenes**, sus **hechos** (los invalidados tachados) y los **documentos que lo mencionan** (con enlace a [[Conocimiento]]). **Ver página** abre su [[Página de entidad]].
- **Clic en una arista:** muestra el hecho, entre qué entidades, desde cuándo es válido, cuándo dejó de ser cierto (si es el caso) y sus **Orígenes**.
- **Clic derecho en un nodo:** **expande su vecindad**; los nodos nuevos brotan de él. **Deshacer última expansión** quita la última.
- **Rueda** para el zoom, **arrastrar el fondo** para moverte; **Ajustar a la vista** encuadra todo.
- **Arrastrar un nodo:** **se queda donde lo sueltas**, marcado con un punto. **Doble clic** lo suelta; **Restablecer posiciones** los suelta todos y vuelve a colocar el grafo.
- **Pausar / Reanudar simulación** (solo en Fuerza): detiene la disposición de fuerzas donde está.
- A partir de 60 nodos visibles, un **minimapa** muestra el grafo entero y la vista actual; pulsa en él para centrar la vista ahí.

## Leyenda
Además de **Orígenes**, la leyenda enumera los **Tipos** (los colores de los nodos) y las **Relaciones**, cada uno con su recuento. Pulsa un elemento para **ocultarlo o mostrarlo** sin mover el resto del grafo. La leyenda se puede plegar.

## Efectos gráficos
La opción **Efectos gráficos** se guarda **en este navegador, por dispositivo** (no en tu cuenta), porque lo que cuenta es la tarjeta gráfica del equipo. La pantalla [[Consulta Cypher]] sigue la misma opción.
- **Automático** (el de partida): efectos completos, que bajan solos a reducidos si el equipo sigue lento (por debajo de unos 30 fotogramas por segundo); el selector pasa a decir «Automático (reducido)».
- **Completo:** animaciones de entrada, partículas, minimapa y hasta 120 rótulos.
- **Reducido:** mantiene los halos pero quita la animación de entrada, las partículas y el minimapa, muestra menos rótulos (60) y pasar por encima ya no atenúa el resto; en 3D, además, dibuja esferas más sencillas.

Si tu sistema pide **reducir el movimiento**, nada se mueve solo sea cual sea la opción: sin animación de entrada ni partículas, la disposición se asienta de golpe y el zoom salta. En cualquier modo, nada se anima mientras el grafo está en reposo.

## Exportar
- **Exportar JSON:** los nodos y hechos cargados.
- **Exportar imagen:** un PNG de lo que ves.

## Consejos
- Empieza con pocas semillas y expande lo que te interese.
- Nodos muy grandes y conectados a todo suelen ser entidades genéricas («servidor»): candidatos a revisar en [[Vocabulario]].
- Dos nodos casi iguales (mismo nombre con distinta versión o mayúsculas) son **posibles duplicados**: fusiónalos en *Vocabulario → Duplicados*.
- Agrupa por **Contribuidor** o por **Agente / token** para ver quién enseñó qué, y activa **Solo confirmados por 2 o más orígenes** para quedarte con aquello en lo que coinciden fuentes independientes.
