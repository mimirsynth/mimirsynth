[English](Upgrade-and-backups) · **Español**

# Actualización y copias de seguridad

## Actualizar con `update.sh`
Cada release incluye un script que **hace la copia de seguridad, actualiza y comprueba** de una vez. Descárgalo una vez en la carpeta donde están tu `docker-compose.yml` y tu `.env`:
```bash
cd mimirsynth
curl -fsSLO https://github.com/MimirSynth/mimirsynth/releases/latest/download/update.sh && chmod +x update.sh
```
Si instalaste con el instalador, `update.sh` ya está en la carpeta de la instalación. Volver a ejecutar el instalador encuentra la instalación, no cambia nada y ofrece ejecutar `update.sh` (en Linux); `install.sh --upgrade` lo ejecuta sin preguntar. En ambos casos, el instalador pone antes al día ese `update.sh`.

| Orden | Qué hace |
|---|---|
| `./update.sh` | Actualiza a la última versión estable. Nunca baja a ella: en una versión más reciente, como una candidata, lo dice y no cambia nada |
| `./update.sh --check` | Solo informa de qué está en marcha, qué está configurado, cuál es la última versión y qué haría `./update.sh`. No cambia nada |
| `./update.sh --version 0.8.0` | Actualiza (o va) a una versión concreta; también sirven las candidatas, como `0.8.0-rc.1`. Una versión anterior se rechaza si su aplicación no conoce la revisión de la base de datos |
| `./update.sh --rollback` | Vuelve a la versión de la última copia. Añade `--with-db` para restaurar también la base de datos |

**Versiones candidatas.** Las versiones se comparan según [SemVer](https://semver.org/lang/es/): `0.15.0` es más reciente que `0.15.0-rc.2`, que es más reciente que `0.15.0-rc.1`, que es más reciente que `0.14.0`. En una candidata, `./update.sh` pasa a la versión final cuando sale, y hasta entonces no cambia nada; si sale una candidata más reciente de la misma versión, la nombra (`./update.sh --version 0.15.0-rc.2`). El instalador (`install.sh --upgrade`) sigue la misma regla.

**Bajar de versión.** Una aplicación anterior no arranca sobre una base de datos que ha migrado una más reciente. Por eso `./update.sh --version` con una versión anterior comprueba primero, con la imagen que acaba de descargar, que esa aplicación conoce la revisión de la base de datos; si no, se para antes de cambiar nada. Para volver a una versión anterior, restaura también la base de datos de esa versión: `./update.sh --rollback --with-db`, si la copia es de la versión que quieres. `--force` baja sin la comprobación.

**Primero se actualiza a sí mismo.** Antes de decidir nada, se compara con el `update.sh` de la versión a la que va (con `--check`, el de la última). Si son distintos, se sustituye por ese, tras comprobarlo con el `SHA256SUMS` de la versión, y se vuelve a ejecutar con las mismas opciones. Nunca toma el `update.sh` de una versión anterior (bajar con `--version` conserva el actual), y si la descarga o la suma de comprobación fallan sigue como está y lo dice; `--no-self-update` conserva el tuyo. Volver a ejecutar el instalador también da a una instalación existente el `update.sh` de la versión del instalador, comprobado igual y nunca uno anterior.

Una actualización sigue este orden:
1. **Descarga.** Baja primero la imagen nueva, así que una versión equivocada o la falta de red paran todo **antes de tocar nada**, y la copia que ya había sigue intacta.
2. **Copia de seguridad** en `./backup`: PostgreSQL, el volumen de documentos, el FalkorDB incluido (cuando su contenedor existe en esa carpeta), tu `docker-compose.yml` y tu `.env`. **Solo se conserva una copia**: la anterior se sustituye cuando la nueva ya está escrita y comprobada, así que las copias nunca se acumulan. Si la aplicación no responde cuando empieza la actualización (tras una actualización fallida, por ejemplo), esa copia **no** sustituye a la anterior: se guarda a su lado como `./backup.failed-FECHA` (solo se conserva la más reciente de esas), y `./backup` sigue siendo la copia de la última instancia que funcionaba, la que usa `--rollback`.
3. **Actualización.** Fija `MIMIRSYNTH_VERSION` en `.env` y recrea solo la aplicación, y el servicio de OCR cuando su contenedor existe en esa carpeta; las **migraciones** de la base de datos se aplican al arrancar. Adopta el `docker-compose.yml` de la versión **solo si el tuyo es el original, sin modificar**, de la versión que tenías; si no, conserva el tuyo y te avisa.
4. **Comprobación.** Espera a que la aplicación responda con la versión nueva y esté sana, muestra la revisión de la base de datos y avisa si el log tiene errores en los últimos minutos. Si no se verifica, te dice cómo volver atrás.

Otras opciones: `--update-compose` adopta siempre el fichero de Compose de la versión, `--keep-compose` no lo toca nunca, `--no-files` se salta el volumen de documentos, `--backup-dir DIR` guarda la copia en otro sitio, `--yes` se salta la confirmación de una vuelta atrás y `--force` reinstala la misma versión o baja sin comprobar la base de datos, y `--no-self-update` conserva el `update.sh` que tienes. El script habla en español cuando tu `LANG` es español.

**El Ollama incluido** (el perfil `ollama`) no se actualiza: su imagen está fijada en `docker-compose.yml`, y `update.sh` nunca la descarga ni la recrea. Cuando una versión sube esa imagen (lo dicen las notas de la versión) y se adopta su fichero de Compose, ejecuta después `docker compose up -d ollama`.

> **Si tu `.env` dice `MIMIRSYNTH_VERSION=latest`**, el script no puede saber de qué fichero de Compose partiste, así que conserva el tuyo: compáralo con el de la versión y usa `--update-compose` si no lo has cambiado. Si mantienes un fichero de Compose propio, revisa en las notas de la versión las líneas que haya que añadir a mano (por ejemplo, desde la 0.8.0 el servicio `mimirsynth` necesita `extra_hosts: ["host.docker.internal:host-gateway"]` para llegar a Ollama en un host Linux).

### En macOS y Windows
`update.sh` corre en Linux: necesita herramientas de GNU (`flock`, `sed` y `stat` de GNU). En Windows, ejecútalo desde WSL en la carpeta de la instalación. En macOS, haz la copia de seguridad y actualiza [sin el script](#sin-el-script); el instalador lo dice cuando encuentra una instalación.

### Volver atrás
`./update.sh --rollback` devuelve el `docker-compose.yml` y el `.env` de la copia (y con ellos la versión anterior de la imagen) y comprueba que responde. Los ficheros de la versión fallida quedan como `*.rolledback`. Con `--with-db` también **restaura la base de datos** desde la copia: lo escrito desde entonces se pierde. Solo vuelve a una copia de una instancia que funcionaba: una cuyo `INFO` no tiene versión (hecha con la aplicación sin responder, por un `update.sh` anterior) se rechaza antes de cambiar nada. El volumen de documentos y FalkorDB no se restauran solos: sus copias están en `./backup` si las necesitas (ver [Restaurar](#restaurar)).

### Sin el script
Haz una copia de seguridad (abajo) y después:
```bash
docker compose pull
docker compose --profile bundled up -d
```
**Perfiles.** Una instalación hecha con el instalador guarda sus perfiles en `COMPOSE_PROFILES` en `.env`, así que un simple `docker compose up -d` arranca los mismos servicios y no hacen falta los `--profile` de esta página. Sin esa variable, nombra cada perfil que uses: `--profile bundled` para el FalkorDB incluido, `--profile ocr`, `--profile ollama` ([Perfiles de Compose](Variables-de-entorno#perfiles-de-compose)).

Comprueba que sigue sano: `docker compose ps` y `curl -s http://localhost:8000/api/health`. Revisa antes las [releases](https://github.com/MimirSynth/mimirsynth/releases) por si alguna requiere un paso manual.

## Qué hay que guardar
Tres cosas, que deben ser coherentes entre sí (tómalas en el mismo momento); `update.sh` las guarda todas salvo un FalkorDB externo:

| Qué | Contiene | Cómo |
|---|---|---|
| **PostgreSQL** | usuarios, brains, miembros, propuestas, auditoría, ajustes, avisos, índices de texto y de documentos | `docker compose exec -T postgres pg_dump -U mimirsynth mimirsynth > mimirsynth.sql` |
| **Volumen `docstore`** | los originales de los documentos subidos | copia del volumen (p. ej. `docker run --rm -v mimirsynth_docstore:/d -v $PWD:/b busybox tar czf /b/docstore.tgz -C /d .`) |
| **FalkorDB** (`graphdata`) | el conocimiento (episodios, entidades, hechos) | copia del volumen, o un volcado RDB con `redis-cli` |

Guarda además tu **`.env`**, y en particular `MIMIRSYNTH_SESSION_SECRET`: sin él no se pueden descifrar las claves de los proveedores, la contraseña SMTP, los secretos OIDC, las semillas del doble factor ni los secretos de los canales de notificación guardados en la base de datos (tendrías que volver a introducirlos). Una restauración, o una copia de la base de datos para una instalación de pruebas, necesita ese mismo valor.

Los nombres de los volúmenes llevan el prefijo del proyecto de Compose (normalmente el nombre de la carpeta); míralos con `docker volume ls`.

Esto copia la instancia entera. Para guardar **un solo brain** aparte, o llevarlo a otra instancia, ver [[Exportar un brain]] e [[Importar un brain]].

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

### Con otro `MIMIRSYNTH_SESSION_SECRET`
Si la instancia arranca con otra clave que la que cifró la base de datos, arranca igual, pero lo dice:
- **en su log**, una línea: «MIMIRSYNTH_SESSION_SECRET does not match the one that sealed the stored secrets», con cuántos valores no se pueden leer, por tipo (nunca los valores);
- **arriba en Administración**, para los administradores de la instancia, un aviso con lo que no se puede leer;
- **en `/api/health`**, el campo `"secrets": "unreadable"`, sin cambiar el código: reiniciar el contenedor no devolvería la clave;
- **en cada acción que necesita uno de esos secretos** (probar un motor, enviar un correo, entrar con la app de autenticación…), un error claro en lugar de uno interno. En el paso del doble factor sigue valiendo un código de recuperación o una llave de acceso.

Vuelve a poner el valor correcto en `.env` y reinicia. Si se ha perdido, introduce de nuevo esos secretos (motores, SMTP, proveedores de identidad, canales de notificación, webhooks, fuentes de documentos) y quita el doble factor de las cuentas afectadas en Administración → Usuarios; el aviso desaparece en cuanto no queda nada sin leer.

## Buenas prácticas
- Automatiza la copia (cron o el planificador de tu sistema) y **prueba una restauración** de vez en cuando.
- `update.sh` solo guarda la última copia, dentro de la carpeta de la instalación: **cópiala fuera del servidor** si necesitas historial.
- Haz siempre una copia antes de actualizar y antes de cambiar el modelo de embeddings ([[Proveedores de IA]]).
