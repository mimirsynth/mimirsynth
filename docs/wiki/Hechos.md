[English](Facts) · **Español**

# Hechos

Un **hecho** es una afirmación concreta entre dos entidades («El servicio de correo corre en el servidor 2») con la **fecha desde la que es cierta** y, si deja de serlo, **cuándo**. Se extraen de los episodios ([[Diario]]). Esta pantalla es el corazón de la memoria: aquí ves, corriges y controlas el conocimiento.

## Dos vistas
Con las pestañas **Lista** y **Línea temporal**:
- **Lista:** una tarjeta por hecho, con un contador por estado.
- **Línea temporal:** los eventos «aprendido» y «dejó de ser cierto» agrupados por día, del más reciente al más antiguo. Muestra los 300 más recientes de los filtros; acota las fechas para ir más atrás.

## Cómo leer una tarjeta
- El texto del hecho.
- Etiquetas: **entidad origen → relación → entidad destino**. Clic en una entidad para abrir su [[Página de entidad]].
- Fechas: *vigente desde*, *invalidado* (si aplica) y *registrado el* (cuándo lo supo el sistema). Distinguir cuándo ocurrió de cuándo se registró es lo que da la historia.
- Los hechos **invalidados** se muestran atenuados.

## Filtros
- **Búsqueda** por texto del hecho o por el nombre de una entidad.
- **Relación** (con contador de hechos por tipo).
- **Desde / Hasta** y **Orden**.
- **Estado** (solo en la lista): *Todos*, *Vigentes*, *Invalidados*, cada uno con su número.

## Corregir hechos (curador o superior)
Cada tarjeta tiene tres acciones si tu rol lo permite:
- **Editar:** cambia el texto del hecho y/o el tipo de relación (se normaliza a `MAYÚSCULAS_CON_GUIONES`). Al guardar se **recalcula su embedding** para que la búsqueda siga siendo correcta.
- **Invalidar / Reactivar:** marca el hecho como que **ya no es cierto** (conserva el historial) o lo devuelve a vigente. Es lo correcto cuando algo cambió. Si el hecho es simplemente *erróneo*, edítalo o bórralo.
- **Borrar:** lo elimina del grafo y de la lista de hechos de sus episodios. **Usa Invalidar** si solo dejó de ser cierto.

Tras cada acción aparece un aviso con **Deshacer**: puedes revertir el cambio mientras no hagas otro cambio de vocabulario después.

## Consejos
- Un hecho mal extraído suele indicar un problema de **vocabulario** (relación demasiado genérica, entidad duplicada): corrígelo en [[Vocabulario]] para que no se repita.
- Para que un cambio del mundo real quede bien registrado, lo mejor es **añadir un episodio nuevo** («Ahora X corre en Y») y dejar que el sistema invalide el hecho anterior; edita a mano solo para arreglar errores.
