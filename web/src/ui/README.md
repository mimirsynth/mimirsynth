# Componentes de la aplicación

Las pantallas no usan los primitivos de Mantine para estos elementos: usan siempre el componente de `src/ui`, para que cada tipo de elemento tenga una sola forma en toda la aplicación.

| Elemento | Componente | Notas |
|---|---|---|
| Etiqueta | `Pill` | Siempre píldora. Tonos: neutral, success, warn, danger, alt (`tone` o `color` heredado). `strong` la rellena con el acento; `circle` es un contador. |
| Botón | `Btn` | Por defecto SECUNDARIO (borde). `kind="primary"` (hidromiel) solo para la acción principal de una zona, como mucho una; `kind="ghost"` (sin borde: Cancelar, quitar filtros); `kind="danger"`; `kind="link"`. `size="row"` (28 px) solo en acciones de fila de tabla o tarjeta; en todo lo demás, 36 px como los campos. Con `icon` opcional. |
| Tabla | `DataTable` | Rayado, resalte y filetes fijos; solo se elige el tamaño de letra. |
| Cabecera de columna | `ColHead` | Dentro de `DataTable.Thead`: pulsar el título ordena y el embudo abre el filtro de esa columna (texto o selección). Para tablas con los datos en el cliente, `useTableView(rows, columnas)` da las filas visibles y los props de cada cabecera; con paginación en el servidor, se le pasan los valores y manejadores propios. Es el patrón de filtros de todas las tablas. |
| Filtros de una lista de tarjetas | `FilterBar` | Para listas que no son tablas (Diario, Hechos): búsqueda a la izquierda y, con su rótulo, un campo por filtro (selección o fecha). |
| Vistas de una misma lista | `Tabs` o `Segments` | `Tabs` para vistas distintas de los mismos datos (Lista / Línea temporal); `Segments` con contador para los estados de una bandeja (Propuestas, Corrector). |
| Búsqueda | `SearchBar` | `mode="live"` filtra al escribir (listas y tablas); `mode="submit"` ejecuta con «Buscar»/Intro (búsqueda semántica, Conocimiento). `FilterBar` ya la incluye. |
| Tabla con datos del servidor | `useServerTableView` | Filtros (los de texto con 300 ms de espera), orden de cabecera y página en un solo sitio; cualquier cambio vuelve a la primera página. Con `ColHead`, `Pager` y, para el estado, `Segments` con contador. |
| Pestaña en la dirección | `useTabParam` | `const [tab, setTab] = useTabParam("docs")`: la pestaña vive en `?tab=` (se puede enlazar y recargar). |
| Paginación | `Pager` | «1–50 de 492», anterior/siguiente y tamaño de página. |
| Selector de opción | `Segments` | Opciones en píldoras (la misma forma que `Pill`); la activa va rellena; contador opcional (`count`). |
| Pestañas | `Tabs` | Siempre subrayadas, también las de segundo nivel. |
| Diálogo | `Modal` | Centrado, con título en la tipografía de títulos. |
| Menú lateral | `NavItem` | Con icono (`icon`). |
| Iconos | `Icon`, `IconButton` | Tabler Icons (MIT). Se piden por nombre; para añadir uno, registrarlo en `ui/Icon.tsx`. |
| Deslizador | `Slider`, `SliderField` | `SliderField` añade etiqueta y valor. |
| Barra de progreso | `ProgressBar` | Con texto. |
| Tarjeta de cifra | `StatCard` | |
| Campos | `TextField`, `NumberField`, `PasswordField`, `TextArea`, `SelectField`, `ComboField`, `Check`, `Toggle` | Un solo tamaño y forma; el tamaño que pida un sitio de uso se ignora. |
| Aviso | `Notice` | Tonos info, warn, danger, success, con icono. |
| Confirmar una acción | `ConfirmDialog` | Toda acción que borra, quita o revoca pasa por él: aviso de lo que pasa, elemento afectado, «Cancelar» + la acción con su verbo. `onConfirm` devuelve la promesa (`mutateAsync`): él muestra la carga y el error y se cierra al acabar. `requireText` pide escribir un texto para los borrados grandes. |
| Error de una mutación | `MutationError` | `<MutationError error={m.error} />`; nunca un `Text` rojo propio. |
| Sin datos | `EmptyState` | Listas, tablas y paneles vacíos o cargando. |
| Consulta sin datos | `DataState` | `if (!data) return <DataState query={q} />`: «Cargando…» o error con «Reintentar». |
| Contenedor | `Panel` | Con filete sobre la superficie. |
| Copiar | `CopyBtn` | |
| Tema claro/oscuro | `ThemeToggle` | Interruptor con sol y luna. |
| Grafo (fuerzas, 2D) | `GraphCanvas` | Canvas propio con d3-force: recibe nodos, aristas y halos ya decididos (color, tamaño, visibilidad, `groups` de cada nodo, `ring` y `strong` para lo respaldado por varios orígenes) y avisa de clic, clic derecho y fondo; `ref` da `fit()` y `toPng()`. Cambiar la visibilidad no recoloca; un grafo nuevo se asienta antes de pintarse y una expansión crece animada. Cada halo tiene un ancla y un nodo va a la media de las anclas de sus halos, así que uno de dos orígenes queda en la intersección. Colores de `CANVAS` y `HALO_PALETTE` (`palette.ts`). |

Los estilos están en `src/theme.css` (sección «Componentes de la aplicación») y salen de los tokens de la identidad (artefacto de diseño). `npm run check:ui` falla si una pantalla importa de Mantine uno de estos primitivos (Badge, Button, Table, SegmentedControl, Tabs, Modal, NavLink, ActionIcon, Slider, Progress, Tooltip, TextInput, NumberInput, PasswordInput, Textarea, Select, Autocomplete, Checkbox, Switch, Alert, Card, Paper, CopyButton).


**Regla de estado.** El estado de una bandeja (Propuestas, Corrector de tipos, Trabajos, Documentos) es siempre `Segments` con contador, encima de la tabla y con «Todos» primero; la columna Estado no lleva filtro.

**Orden de una pantalla con lista.** Cabecera → `Tabs` (vistas) → búsqueda (`SearchBar`, siempre sin rótulo visible, con lupa; en la búsqueda semántica lleva «Buscar») → `Segments label="Estado"` → contenido. El estado nunca es un desplegable: es `Segments` con contador y su rótulo «Estado» (Hechos, Propuestas, Corrector, Trabajos, Documentos). La búsqueda vive dentro de la pestaña a la que se aplica.

**Pantallas de ajustes.** Una sección por tema: `SettingsLayout` con `SubNav` a la izquierda (arriba en móvil) y `SettingsGroup` a la derecha, con una `SettingsRow` por ajuste (nombre y ayuda a la izquierda, control a la derecha, «Guardar» solo si hay cambios). Nunca columnas de campos apilados. Administración usa el mismo esquema para todas sus secciones: navegación lateral agrupada (Brain, Cuentas, Modelos de IA, Documentos, Sistema) y, a la derecha, una `SettingsGroup` por sección con `SettingsBody` para tablas y formularios.

**Regla de filtros.** Tabla → filtros y orden en la cabecera (`ColHead`). Lista de tarjetas → `FilterBar`. Vista alternativa o estado de bandeja → `Tabs`/`Segments`. Nunca botones sueltos ni controles propios de una pantalla.

**Verbos de las acciones.** *Añadir* incorpora algo existente a una colección (una fuente, un miembro); *Crear* da identidad propia a algo nuevo (un brain, un token); *Borrar* destruye datos; *Quitar* desvincula sin destruir lo de fuera (una fuente, un alias, una carpeta); *Revocar* invalida una credencial; *Cancelar* descarta un diálogo; *Cerrar* oculta un panel; *Deshacer* revierte la última operación; *Buscar* lanza una consulta; *Ejecutar* lanza una tarea. El icono sigue al verbo (`plus`, `trash`, `check`…).

**Responsive y teclado.** `StatGrid` reparte las tarjetas de cifras en las columnas que caben; `SplitView` pone el panel lateral debajo por debajo de 1000 px; toda `DataTable` desplaza en horizontal dentro de su caja. Lo clicable es siempre un botón real o lleva `role="button"` + Intro/Espacio (`ListCard` con `onOpen`, `rowOpen()` en las filas). `Segments` se recorre con las flechas y `ColHead` expone `aria-sort`. Un `Check` sin etiqueta visible lleva `aria-label`.

**Móvil (< 768 px).** Cada fila de una `DataTable` se pinta como tarjeta: las celdas toman su rótulo de la cabecera de su columna y las celdas sin cabecera (acciones) van alineadas a la derecha. Las cabeceras `ColHead` se quedan como barra de píldoras «Ordenar y filtrar» sobre las tarjetas (mismo orden y filtro que en pantalla ancha). La barra superior lleva el botón del menú y la página se desplaza entera.

**Guardián (`npm run check:ui`, también en `prebuild`).** Falla, con `fichero:línea`, si una pantalla (fuera de `src/ui`): importa de Mantine un elemento que tiene componente propio; usa `style={{…}}`; usa un elemento HTML nativo (`button`, `input`, `table`, `pre`, `a`…); escribe un color literal (`#hex`, `rgb()`, `c="red"`, `--mantine-color-*`); pasa `variant`/`color` a `Btn` o `Pill`; da un tamaño a `Btn` que no sea `row`; fija alturas en `vh`; o pinta «Cargando…»/«No hay…» como `Text` suelto. Una excepción justificada se marca con `// ui-ok: motivo` en la misma línea, o `// ui-ok-file: motivo` en la primera línea del fichero (solo `Logo.tsx` y `main.tsx`, por la identidad).
Componentes añadidos al kit para cumplirlo: `FilePicker`, `Legend`, `ColGrid`.
