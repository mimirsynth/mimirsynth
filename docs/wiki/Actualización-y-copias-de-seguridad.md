[English](Upgrade-and-backups) · **Español**

# Actualización y copias de seguridad

## Actualizar con `update.sh`
Cada release incluye un script que **hace la copia de seguridad, actualiza y comprueba** de una vez. Descárgalo una vez en la carpeta donde están tu `docker-compose.yml` y tu `.env`:
```bash
cd mimirsynth
curl -fsSLO https://github.com/MimirSynth/mimirsynth/releases/latest/download/update.sh && chmod +x update.sh
```
| Orden | Qué hace |
|---|---|
| `./update.sh` | Actualiza a la última versión estable |
| `./update.sh --check` | Solo informa de qué está en marcha, qué está configurado y cuál es la última versión. No cambia nada |
| `./update.sh --version 0.8.0` | Actualiza (o va) a una versión concreta; también sirven las candidatas, como `0.8.0-rc.1` |
| `./update.sh --rollback` | Vuelve a la versión de la última copia. Añade `--with-db` para restaurar también la base de datos |

Una actualización sigue este orden:
1. **Descarga.** Baja primero la imagen nueva, así que una versión equivocada o la falta de red paran todo **antes de tocar nada**, y la copia que ya había sigue intacta.
2. **Copia de seguridad** en `./backup`: PostgreSQL, el volumen de documentos, el FalkorDB incluido (si usas `--profile bundled`), tu `docker-compose.yml` y tu `.env`. **Solo se conserva una copia**: la anterior se sustituye cuando la nueva ya está escrita y comprobada, así que las copias nunca se acumulan.
3. **Actualización.** Fija `MIMIRSYNTH_VERSION` en `.env` y recrea solo la aplicación; las **migraciones** de la base de datos se aplican al arrancar. Adopta el `docker-compose.yml` de la versión **solo si el tuyo es el original, sin modificar**, de la versión que tenías; si no, conserva el tuyo y te avisa.
4. **Comprobación.** Espera a que la aplicación responda con la versión nueva y esté sana, muestra la revisión de la base de datos y avisa si el log tiene errores en los últimos minutos. Si no se verifica, te dice cómo volver atrás.

Otras opciones: `--update-compose` adopta siempre el fichero de Compose de la versión, `--keep-compose` no lo toca nunca, `--no-files` se salta el volumen de documentos, `--backup-dir DIR` guarda la copia en otro sitio, `--yes` se salta la confirmación de una vuelta atrás y `--force` reinstala la misma versión. El script habla en español cuando tu `LANG` es español.

> **Si tu `.env` dice `MIMIRSYNTH_VERSION=latest`**, el script no puede saber de qué fichero de Compose partiste, así que conserva el tuyo: compáralo con el de la versión y usa `--update-compose` si no lo has cambiado. Si mantienes un fichero de Compose propio, revisa en las notas de la versión las líneas que haya que añadir a mano (por ejemplo, desde la 0.8.0 el servicio `mimirsynth` necesita `extra_hosts: ["host.docker.internal:host-gateway"]` para llegar a Ollama en un host Linux).

### Volver atrás
`./update.sh --rollback` devuelve el `docker-compose.yml` y el `.env` de la copia (y con ellos la versión anterior de la imagen) y comprueba que responde. Los ficheros de la versión fallida quedan como `*.rolledback`. Con `--with-db` también **restaura la base de datos** desde la copia: lo escrito desde entonces se pierde. El volumen de documentos y FalkorDB no se restauran solos: sus copias están en `./backup` si las necesitas (ver [Restaurar](#restaurar)).

### Sin el script
Haz una copia de seguridad (abajo) y después:
```bash
docker compose pull
docker compose --profile bundled up -d
```
Comprueba que sigue sano: `docker compose ps` y `curl -s http://localhost:8000/api/health`. Revisa antes las [releases](https://github.com/MimirSynth/mimirsynth/releases) por si alguna requiere un paso manual.

## Qué hay que guardar
Tres cosas, que deben ser coherentes entre sí (tómalas en el mismo momento); `update.sh` las guarda todas salvo un FalkorDB externo:

| Qué | Contiene | Cómo |
|---|---|---|
| **PostgreSQL** | usuarios, brains, miembros, propuestas, auditoría, ajustes, avisos, índices de texto y de documentos | `docker compose exec -T postgres pg_dump -U mimirsynth mimirsynth > mimirsynth.sql` |
| **Volumen `docstore`** | los originales de los documentos subidos | copia del volumen (p. ej. `docker run --rm -v mimirsynth_docstore:/d -v $PWD:/b busybox tar czf /b/docstore.tgz -C /d .`) |
| **FalkorDB** (`graphdata`) | el conocimiento (episodios, entidades, hechos) | copia del volumen, o un volcado RDB con `redis-cli` |

Guarda además tu **`.env`**, y en particular `MIMIRSYNTH_SESSION_SECRET`: sin él no se pueden descifrar las claves de los proveedores, la contraseña SMTP, los secretos OIDC ni los de los canales de notificación guardados en la base de datos (tendrías que volver a introducirlos).

Los nombres de los volúmenes llevan el prefijo del proyecto de Compose (normalmente el nombre de la carpeta); míralos con `docker volume ls`.

## Qué se puede reconstruir
- El **índice de texto de los episodios** se regenera desde el grafo («Reindexar ahora» en [[Preguntar]]).
- El **índice de documentos** se regenera desde los originales del almacén (reindexar el documento).
- No se puede reconstruir: el grafo en sí, ni los usuarios y permisos, ni los ficheros subidos.

## Restaurar
1. Instala la misma versión (o una posterior) con el mismo `.env`.
2. Arranca solo la base de datos: `docker compose up -d postgres`.
3. Restaura el volcado: `docker compose exec -T postgres psql -U mimirsynth mimirsynth < mimirsynth.sql` (desde una copia de `update.sh`: `gunzip -c backup/mimirsynth.sql.gz | docker compose exec -T postgres psql -U mimirsynth mimirsynth`).
4. Devuelve los volúmenes `docstore` y `graphdata` (`update.sh` los deja como `docstore.tar.gz` y `falkordb-dump.rdb`).
5. Arranca todo: `docker compose --profile bundled up -d`.

## Buenas prácticas
- Automatiza la copia (cron o el planificador de tu sistema) y **prueba una restauración** de vez en cuando.
- `update.sh` solo guarda la última copia, dentro de la carpeta de la instalación: **cópiala fuera del servidor** si necesitas historial.
- Haz siempre una copia antes de actualizar y antes de cambiar el modelo de embeddings ([[Proveedores de IA]]).
