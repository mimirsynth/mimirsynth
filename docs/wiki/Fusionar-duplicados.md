[English](Merge-duplicates) · **Español**

# Fusionar duplicados

Pestaña **Duplicados** de [[Calidad del contenido]]. Muestra **grupos de entidades que probablemente son la misma cosa**: mismo nombre salvo la versión o las mayúsculas (por ejemplo «Servidor 2» y «servidor 2», o «Nextcloud» y «Nextcloud 29»).

## Por qué molestan
Si la misma entidad existe dos veces, sus hechos quedan repartidos: una búsqueda encuentra la mitad, el grafo muestra dos nodos y el [[Resumen]] cuenta de más.

## Revisar un grupo
Cada grupo es una tabla con sus entidades (nombre, tipo, número de hechos y de menciones). Los administradores del brain pueden, en cada grupo:
- **Hacer principal** a una entidad: será la que se conserva.
- **Seleccionar** las que se fusionan en ella.
- **Revisar fusión (N):** abre una ventana de confirmación con el detalle.
- **No son duplicados:** descarta el grupo (por ejemplo, dos versiones que de verdad conviene tener separadas). Se guarda en la lista de **descartados**, desde donde puedes **restaurarlo**.

## La fusión
La ventana de confirmación avisa de que **cambia datos del grafo**. Al fusionar:
- Los hechos y las menciones de las entidades fusionadas pasan a la principal.
- Las entidades fusionadas quedan **ocultas, no borradas**.
- Se guarda una **copia previa** de lo afectado.
- **Los hechos que queden repetidos no se eliminan** (puedes invalidar o borrar los sobrantes en [[Hechos]]).

## Deshacer
En **Fusiones recientes** aparece cada operación. La **última** se puede **deshacer** mientras no hagas otro cambio de vocabulario después.

## Fusión automática
Al ingerir, MimirSynth ya fusiona por su cuenta los casos claros de normalización por alias. Lo que ves aquí es lo que quedó sin resolver.

## Consejos
- Elige como principal la que tiene **más hechos** y el nombre más canónico.
- Revisa que sean realmente la misma cosa: «Servidor 1» y «Servidor 2» **no** son duplicados.
- Tras fusionar, mira de nuevo el [[Grafo]] para comprobar que el nodo quedó bien conectado.
