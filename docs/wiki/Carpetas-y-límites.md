[English](Folders-and-limits) · **Español**

# Carpetas y límites

Dos secciones del grupo **Documentos** de la administración (solo el administrador de la instancia).

## Carpetas (raíces autorizadas)
Los administradores de un brain pueden conectar **carpetas del servidor** como fuentes de documentos ([[Conocimiento]]). Para que sea seguro, no escriben rutas libres: eligen entre las **raíces autorizadas** que registras aquí.

Una raíz es un directorio **bajo `/sources`**, que es la carpeta del host que Docker monta **en solo lectura** en el contenedor (`MIMIRSYNTH_SOURCES_DIR`, por defecto `./sources`). MimirSynth **nunca escribe** en ellas.

### Montar las carpetas
En `.env`: `MIMIRSYNTH_SOURCES_DIR=/srv/documentos` (la carpeta del host). Dentro de ella, cada subcarpeta puede ser una raíz: `/sources/manuales`, `/sources/wiki-export`… Lo que montes **después** bajo esa carpeta en el host (un NFS, por ejemplo) **aparece dentro sin reiniciar**.

### Registrar una raíz
Botón de añadir:
- **Nombre:** identificador corto (minúsculas, números, `_` y `-`, hasta 40 caracteres). Es el que verán los administradores de los brains.
- **Ruta:** la ruta **dentro del contenedor**, bajo `/sources` (p. ej. `/sources/manuales`).
- **Descripción:** opcional.
La tabla muestra para cada raíz si está **disponible** (si el directorio existe) y cuántas **fuentes** la usan. Una raíz con fuentes no se puede borrar.

> **Por seguridad**, la ruta debe estar bajo `/sources`: no se admiten rutas arbitrarias. Una carpeta vacía o desmontada en un escaneo *programado* **falla sin borrar nada** (por si el volumen se desmontó).

## Límites
Tres ajustes que acotan el tamaño de lo que se sube o se indexa:
| Ajuste | Por defecto | Rango | Qué hace |
|---|---|---|---|
| **Tamaño máximo de un fichero** | 2048 MB | 1–20480 | Los ficheros más grandes se rechazan al subirlos o al escanear carpetas |
| **Tamaño de cada parte de una subida** | 64 MB | 1–64 | Las subidas se envían por partes de este tamaño. **Bájalo si tu proxy limita el tamaño de petición** |
| **Texto máximo extraído por documento** | 100 MB | 1–2048 | Un documento cuyo texto supere este tamaño no se indexa |

## Formatos admitidos
Texto y Markdown (`.md`, `.markdown`, `.txt`, `.rst`, `.log`), HTML (`.html`, `.htm`) y PDF (`.pdf`). Un PDF **escaneado** (solo imagen, sin texto) no contiene texto que indexar.
- **Markdown y Obsidian:** una bóveda no es más que una carpeta de Markdown, así que se conecta como fuente de carpeta. Se quita el frontmatter YAML (se usa su `title:`), los enlaces de estilo wiki (entre dobles corchetes) conservan su texto y se descartan los incrustados, los `%%comentarios%%` y las marcas `^bloque`, también en ficheros guardados con finales de línea de Windows. Las carpetas ocultas como `.obsidian/` se ignoran.
- **Ficheros repetidos:** un documento cuyo texto coincide con otro ya indexado en el brain (sin distinguir mayúsculas ni espacios), por ejemplo la misma nota en dos carpetas, queda marcado como **duplicado** y no se indexa dos veces ([[Conocimiento]]).
- **Secretos:** la política de secretos del brain se aplica también a los documentos: con **Enmascarar**, las credenciales se quitan del texto indexado; con **Bloquear**, un documento que contenga una segura no se indexa. El fichero original nunca se modifica ([[Conectar agentes]] explica las políticas).
