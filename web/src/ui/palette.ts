/** Colores con nombre que no cambian con el tema: series de las gráficas y lienzo del grafo (siempre oscuro). Un solo sitio; las pantallas no escriben colores literales. */
export const HIDROMIEL = "#d4a03a";
export const PIZARRA = "#7f93a8";
export const SERIES = ["var(--ms-accent)", HIDROMIEL, "var(--ms-invalidado)", PIZARRA];

/** Colores de los tipos de entidad en los grafos (Grafo y Consulta). */
export const NODE_PALETTE = ["#4dabf7", "#69db7c", "#ffa94d", "#da77f2", "#ff8787", "#38d9a9", "#ffd43b", "#74c0fc", "#a9e34b", "#f783ac", "#b197fc", "#ced4da"];
/** Colores de los halos por origen en el Grafo: distintos de los de tipo de entidad, que ya rellenan los nodos. El último, gris, es «Otros». */
export const HALO_PALETTE = ["#f59f00", "#22b8cf", "#e64980", "#94d82d", "#845ef7", "#ff922b", "#20c997", "#f06595", "#868e96"];
export const CANVAS = { background: "#101113", foreground: "#e9ecef", link: "#5c7cfa", linkInvalid: "#6b7280", label: "#909296", selected: "#ffd43b" };
