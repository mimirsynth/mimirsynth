[English](../INSTALL.md) · **Español**

# Instalación

## Requisitos
- Docker con Compose v2 y unos 2 GB de RAM libres para la aplicación, PostgreSQL y FalkorDB.
- Un endpoint compatible con OpenAI para **embeddings** (p. ej. [Ollama](https://ollama.com) con `nomic-embed-text`) y otro para el **LLM** que extrae los hechos ([qué modelo](CONFIGURATION.md#elegir-el-modelo-de-extracción)). Pueden ser locales o de un proveedor en la nube. Se configuran después, en la interfaz. Sin ellos la instancia arranca, pero no hay nada útil que ver: las propuestas no se ingieren y el recall no devuelve nada.

## Instalar con un comando
El instalador comprueba Docker, hace dos preguntas, genera los secretos, arranca todo y abre el navegador en el asistente de primer arranque. No tienes que editar `.env`.

En **Linux** o **macOS**:
```bash
curl -fsSL https://github.com/MimirSynth/mimirsynth/releases/latest/download/install.sh | bash
```
En **Windows**, en PowerShell, con [Docker Desktop](https://docs.docker.com/desktop/setup/install/windows-install/) instalado:
```powershell
irm https://github.com/MimirSynth/mimirsynth/releases/latest/download/install.ps1 | iex
```
Qué hace, en este orden:
1. **Comprueba Docker y Compose v2.** En Linux, si falta Docker, ofrece instalarlo con el script oficial de Docker (`get.docker.com`, necesita `sudo`). En macOS y Windows te remite a Docker Desktop, y lo arranca si está instalado pero parado; en Windows, Docker Desktop necesita WSL2 (`wsl --install` en un PowerShell abierto como administrador).
2. **Pregunta dónde vive tu grafo de conocimiento.** *Local* (la opción por defecto) arranca un FalkorDB incluido junto a MimirSynth. *Existente* pide el tipo (FalkorDB o Neo4j), el host, el puerto, el usuario y la contraseña de un servidor que ya tienes, y comprueba que responde. Después, antes de arrancar nada, hace la prueba completa de conexión, la misma que Administración → Base de datos de grafos (dirección, TLS, credenciales, versión, permiso de escritura y los grafos que ya tiene), desde un contenedor de MimirSynth, para llegar al servidor igual que llegará MimirSynth. Si la prueba falla, dice en qué paso y por qué y vuelve a preguntar; sin preguntas, se para y no deja nada instalado. A Neo4j se llega con `neo4j://`, o con `neo4j+s://` con `--graph-tls`: el esquema con enrutamiento, que necesita un clúster como Neo4j Aura y que un servidor suelto también acepta (`--graph-scheme bolt` pide en su lugar una conexión directa `bolt://`). La prueba usa la misma dirección que se escribe en `.env`. Sin `--graph-database` usa la base de datos predeterminada del usuario y dice cuál es: en Neo4j Aura esa base de datos se llama como el id de la instancia, no `neo4j`, y el instalador la encuentra solo. A un servidor en el mismo ordenador (`localhost`) el contenedor llega como `host.docker.internal`; en Linux debe escuchar en una dirección que alcancen los contenedores, no solo en `127.0.0.1`. La conexión se escribe en `.env`, que manda sobre la interfaz: Administración → Base de datos de grafos la muestra en solo lectura, y se cambia en `.env` con un reinicio.
3. **Ofrece un Ollama incluido** para los embeddings (el perfil `ollama`) y descarga `nomic-embed-text`. La imagen es una descarga de unos 3,5 GB y funciona con la CPU; si Ollama ya está en marcha en el ordenador, el instalador usa ese. En un Mac con Apple silicon la aplicación nativa de Ollama es más rápida: usa la GPU.
4. **Escribe `docker-compose.yml` y `.env`** en `~/mimirsynth` (`%USERPROFILE%\mimirsynth` en Windows), con un `POSTGRES_PASSWORD` y un `MIMIRSYNTH_SESSION_SECRET` aleatorios, la versión de la release fijada en `MIMIRSYNTH_VERSION`, un puerto libre (el 8000 o el siguiente) y los perfiles elegidos en `COMPOSE_PROFILES`, para que un simple `docker compose up -d` en esa carpeta arranque después los mismos servicios.
5. **Arranca los servicios**, espera a que responda `/api/health`, muestra la dirección y el **código de primer arranque**, y abre el navegador. Si la instancia ya arrancada no puede usar una base de datos de grafos existente, termina con un error en su lugar: MimirSynth sigue en marcha, y el mensaje dice que corrijas la conexión en `.env` y ejecutes `docker compose up -d`.

Volver a ejecutarlo es seguro: si MimirSynth ya está instalado en esa carpeta, no cambia nada y ofrece actualizar con `update.sh` (en Linux; ver [Actualizar](#actualizar)).

### Sin preguntas
Cada respuesta tiene su opción, para scripts y automatización (`--help` las enumera). Con `--yes` no pregunta nada: FalkorDB incluido, sin Ollama salvo con `--ollama` y sin instalar Docker salvo con `--install-docker`.
```bash
curl -fsSL https://github.com/MimirSynth/mimirsynth/releases/latest/download/install.sh | bash -s -- --yes --ollama
MIMIRSYNTH_GRAPH_PASSWORD='…' ./install.sh --yes --graph existing --graph-type neo4j --graph-host grafo.example.com
# Neo4j Aura: el host de su URI de conexión, con TLS y sin base de datos (el instalador encuentra la de la instancia)
MIMIRSYNTH_GRAPH_PASSWORD='…' ./install.sh --yes --graph existing --graph-type neo4j --graph-host abcd1234.databases.neo4j.io --graph-tls
```
En PowerShell los parámetros se llaman igual (`-Yes`, `-Ollama`, `-Graph existing`, `-GraphType`, `-GraphHost`, `-GraphPort`, `-GraphUser`, `-GraphDatabase`, `-GraphTls`, `-GraphScheme`, `-SkipGraphCheck`, `-Dir`, `-Port`, `-Version`, `-Lang`, `-NoBrowser`, `-NoStart`):
```powershell
& ([scriptblock]::Create((irm https://github.com/MimirSynth/mimirsynth/releases/latest/download/install.ps1))) -Yes -Ollama
```
La contraseña de una base de datos de grafos existente se lee de `MIMIRSYNTH_GRAPH_PASSWORD`, nunca de la línea de comandos, para que no quede en el historial. Los mensajes salen en inglés o en castellano según el idioma del sistema (`--lang es`), y el idioma por defecto de la instancia sigue al de los mensajes.

Neo4j necesita una release posterior a la 0.14.0. Con una anterior, el instalador no puede hacer la prueba completa antes del arranque (lo dice y solo comprueba que el servidor responde), escribe la conexión en `.env` y la instancia solo habla con FalkorDB.

### Comprobar la descarga
Cada release enumera el SHA-256 de sus ficheros en sus notas y en `SHA256SUMS`. Para comprobar el instalador antes de ejecutarlo:
```bash
curl -fsSLO https://github.com/MimirSynth/mimirsynth/releases/latest/download/install.sh
curl -fsSLO https://github.com/MimirSynth/mimirsynth/releases/latest/download/SHA256SUMS
sha256sum -c SHA256SUMS --ignore-missing && bash install.sh
```

## Instalación manual
El instalador no hace nada que no puedas hacer a mano. Estos son los mismos pasos, para cuando quieras controlar cada uno.

### Antes de empezar
En un servidor Linux vacío (p. ej. un Debian o Ubuntu mínimo), instala `curl` y Docker y comprueba que está Compose v2. En macOS o Windows, instala [Docker Desktop](https://docs.docker.com/desktop/).
```bash
sudo apt-get update && sudo apt-get install -y curl openssl
curl -fsSL https://get.docker.com | sudo sh    # Docker Engine con el plugin de Compose, menos de un minuto
sudo usermod -aG docker "$USER" && newgrp docker    # usar docker sin sudo
docker compose version    # debe responder v2.x
```

### Preparar Ollama
Si los modelos van en [Ollama](https://ollama.com), descárgalos antes de empezar:
```bash
ollama pull nomic-embed-text        # embeddings (768 dimensiones, el valor por defecto)
ollama pull qwen2.5:14b-instruct    # extracción de hechos: ver «Elegir el modelo de extracción» en CONFIGURATION.md
```
- **Ollama en el mismo host:** la dirección por defecto, `http://host.docker.internal:11434/v1`, funciona sin cambios; el fichero de Compose asocia ese nombre al host, también en Linux. Pero en Linux Ollama solo escucha en `127.0.0.1` por defecto, y desde el contenedor no se llega ahí. Haz que escuche en todas las interfaces y mantén el puerto 11434 cerrado hacia fuera con tu cortafuegos:
  ```bash
  sudo systemctl edit ollama    # añade, bajo [Service]:  Environment="OLLAMA_HOST=0.0.0.0"
  sudo systemctl restart ollama
  ```
- **Ollama en otra máquina:** usa su dirección, p. ej. `http://192.168.1.20:11434/v1`.

### Descargar y arrancar
Todo sale de la release oficial: un fichero de Compose y una plantilla de entorno. No necesitas el código fuente.
```bash
mkdir mimirsynth && cd mimirsynth
curl -fsSLO https://github.com/MimirSynth/mimirsynth/releases/latest/download/docker-compose.yml
curl -fsSL  https://github.com/MimirSynth/mimirsynth/releases/latest/download/env.example -o .env
```
Edita `.env` y define, como mínimo, `POSTGRES_PASSWORD` y `MIMIRSYNTH_SESSION_SECRET` (genera ambos con `openssl rand -hex 32`). Después:
```bash
docker compose --profile bundled up -d
```
Descarga la imagen oficial (`ghcr.io/mimirsynth/mimirsynth`, para amd64 y arm64). Para fijar una versión, pon `MIMIRSYNTH_VERSION=0.15.0` en `.env` (por defecto, `latest`).
- `--profile bundled` arranca también un FalkorDB incluido, que es el que se usa si no eliges otro. Si ya tienes un FalkorDB o un Neo4j, omite el perfil y ponlo en **Administración → Base de datos del grafo** tras el primer arranque, o en `.env` (ver [Base de datos de grafos](CONFIGURATION.md#base-de-datos-de-grafos)).
- La aplicación queda en `http://localhost:8000` (cambia el puerto con `MIMIRSYNTH_PORT`).

> No pongas comentarios al final de una línea con valor en `.env` (`CLAVE=valor # comentario`): Docker Compose los leería como parte del valor.

## Asistente de primer arranque
Una instancia sin administradores imprime un **código de instalación** en su registro (el instalador te lo muestra):
```bash
docker compose logs mimirsynth | grep -A3 "FIRST START"
```
Abre la aplicación, introduce el código y crea la cuenta de administrador. Guarda `MIMIRSYNTH_SESSION_SECRET`: cifra los secretos guardados (claves de los proveedores, contraseña SMTP, secreto OIDC, semillas del doble factor…), así que restaurar una copia en otro servidor o copiar la base de datos a una instalación de pruebas exige el **mismo** valor. Con otro la aplicación arranca igual, pero lo dice: una línea en su log, un aviso arriba en Administración y `"secrets": "unreadable"` en `/api/health`; lo que necesita esos secretos responde con un error claro. Vuelve a poner el valor correcto y reinicia. Si se ha perdido, introduce de nuevo esos secretos y quita el doble factor de las cuentas afectadas (Administración → Usuarios); el aviso desaparece cuando ya no queda nada sin leer.

## Primeros pasos: el asistente de configuración
En cuanto existe el administrador, se abre solo el **asistente de configuración**, que te lleva paso a paso hasta el primer recall de tu agente:
1. **Base de datos del grafo:** la que está en uso (el FalkorDB incluido, o la que puso el instalador), con su prueba, la opción de cambiarla y la de adoptar grafos que ya existan.
2. **Embeddings:** busca un Ollama local (el incluido, el de tu equipo), puede descargar `nomic-embed-text`, o usa un servicio compatible con OpenAI.
3. **LLM** (saca los hechos de lo que proponen los agentes) y **decisor** (aprueba solo las propuestas claramente factuales): los dos se pueden saltar. Sin LLM, las propuestas aprobadas esperan y el inicio lo avisa hasta que añadas uno.
4. **Tu primer brain**, un **token de API** para tu agente (rol Colaborador, se muestra una vez) y **conectar tu agente**, que se pone en verde cuando hace su primera llamada.

Los pasos del grafo y de los embeddings no se pueden saltar: «Siguiente» pide al servidor que los compruebe. Cada paso se guarda al pasarlo, así que puedes dejarlo en cualquier momento y el asistente sigue donde lo dejaste, en cualquier dispositivo; «Configurar a mano» lo cierra del todo. Un administrador puede volver a abrirlo desde **Administración → Asistente de configuración**. Una instancia que ya tenía brains antes de esta versión no lo abre sola.

Después, si quieres: aplica un paquete de ontología en Vocabulario → Ontología, y configura el correo SMTP (invitaciones y recuperación de contraseña), OIDC, el doble factor obligatorio y las carpetas de documentos. Ver [CONFIGURATION.md](CONFIGURATION.md) y [AGENTS.md](AGENTS.md).

## OCR para PDF escaneados e imágenes (opcional)

Un PDF escaneado no tiene capa de texto, y una imagen (`.png`, `.jpg`) solo tiene píxeles: para indexarlos MimirSynth necesita OCR. Tesseract corre en **su propio contenedor**, así que la imagen principal no crece.
1. Arráncalo con el perfil `ocr`, junto a los que ya uses: `docker compose --profile ocr up -d` (añade `--profile bundled` si usas el FalkorDB incluido).
2. Añade `MIMIRSYNTH_OCR_URL=http://ocr:8001` al `.env` y ejecuta `docker compose up -d mimirsynth`.

En **Conocimiento**, quien administra un brain ve si el OCR responde. La imagen lee castellano e inglés; para más idiomas, constrúyela con `docker build --build-arg LANGS="spa eng cat" -t mimirsynth-ocr ocr/` y haz que el servicio la use. En Administración → Ajustes → Documentos se eligen los idiomas (`spa+eng`) y el máximo de páginas que se leen con OCR por documento (50). El servicio no tiene autenticación: no publiques su puerto. `update.sh` lo actualiza junto con la aplicación.

En vez de Tesseract, un brain puede leer sus páginas escaneadas con el **modelo de visión** de un motor LLM (Conocimiento → *Leer con el modelo de visión*). Entonces cada página es una llamada al motor, así que está desactivado por defecto. Una imagen suelta no necesita el servicio OCR en ese caso, pero un PDF sí, para convertir sus páginas en imágenes.

## HTTPS y proxy inverso
No publiques el puerto 8000 a Internet sin TLS. Pon un proxy inverso (Caddy, Traefik, nginx…) delante, define `MIMIRSYNTH_PUBLIC_URL` con la dirección pública y `MIMIRSYNTH_COOKIE_SECURE=true`. Si subes ficheros grandes, comprueba el límite de tamaño de petición del proxy: las subidas se envían por partes (por defecto de 64 MB).

PostgreSQL y FalkorDB no publican puertos fuera de la red de Compose. No los expongas.

## Actualizar
La release incluye un script que hace la copia de seguridad, actualiza y comprueba de una vez. El instalador lo deja en la carpeta de la instalación; si no, descárgalo:
```bash
curl -fsSLO https://github.com/MimirSynth/mimirsynth/releases/latest/download/update.sh && chmod +x update.sh
./update.sh              # última versión estable; ./update.sh --check solo informa; --version 0.7.1 elige una
```
Nunca baja de versión por su cuenta: en una versión más reciente que la última estable, como una candidata, lo dice y no cambia nada. Con `--version` y una versión anterior, se para antes de cambiar nada si la aplicación de esa versión no conoce la revisión de la base de datos (`--force` lo hace igualmente); volver atrás necesita también la base de datos de esa versión, con `./update.sh --rollback --with-db`.

Hace, por este orden:
1. **Descarga** primero la imagen nueva: una versión equivocada o la falta de red paran todo antes de tocar nada.
2. **Copia de seguridad** de PostgreSQL, del volumen `docstore`, del FalkorDB incluido (si usas `--profile bundled`) y de tu `docker-compose.yml` y `.env` en `./backup`. **Solo se conserva una copia**: la anterior se sustituye cuando la nueva ya está escrita y comprobada, así que las copias nunca se acumulan.
3. **Actualiza**: fija `MIMIRSYNTH_VERSION` en `.env` y recrea solo la aplicación (las migraciones se aplican al arrancar). Adopta el `docker-compose.yml` de la versión solo si el tuyo es el original, sin modificar, de la versión que tenías; si no, conserva el tuyo y te avisa (`--update-compose` lo fuerza, `--keep-compose` no lo toca nunca).
4. **Comprueba** que responde con la versión nueva y está sana, y muestra la revisión de la base de datos. Si no se verifica, te dice cómo volver atrás.

Para volver atrás: `./update.sh --rollback` devuelve el `docker-compose.yml` y el `.env` anteriores (y con ellos la imagen anterior), y guarda los fallidos como `*.rolledback`; añade `--with-db` para restaurar también la base de datos (lo escrito desde la copia se pierde). La vuelta atrás no restaura el volumen de documentos ni FalkorDB (están en la copia, para restaurarlos a mano si hace falta), y un FalkorDB externo no forma parte de la copia: guárdalo tú. Sin el script, a mano es `docker compose pull` y `docker compose --profile bundled up -d`, tras una copia de seguridad.

`update.sh` funciona en Linux (necesita las herramientas de GNU). En Windows, ejecútalo desde WSL en la carpeta de la instalación; en macOS, haz una copia de seguridad y actualiza a mano como se indica arriba.

## Copias de seguridad
Hay tres cosas que guardar, y deben ser coherentes entre sí:
- **PostgreSQL** (usuarios, brains, propuestas, índices): `docker compose exec -T postgres pg_dump -U mimirsynth mimirsynth > mimirsynth.sql`
- **El volumen `docstore`** (originales de los documentos subidos, instantáneas de las páginas de wiki y el texto extraído de cada documento).
- **FalkorDB** (el conocimiento): el volumen `graphdata`, o un volcado con `redis-cli --rdb`.
Guarda también tu `.env`.

Restaurar es el camino inverso: arranca los servicios, restaura la base de datos (`psql`) y devuelve los volúmenes. El índice de texto se puede reconstruir desde el grafo y el de documentos desde los originales.

Esto copia la instancia entera. Un solo brain se puede exportar a un paquete desde Administración → Brain → Exportar; ver «Exportar un brain» en la wiki.

## Vigilar la instancia
MimirSynth avisa por sí mismo del grafo y de los modelos de IA ([NOTIFICATIONS.md](NOTIFICATIONS.md)), pero **no de su propio PostgreSQL**: los avisos se guardan en esa base de datos, así que mientras está caída no hay dónde guardarlos. Vigílalo desde fuera con cualquier monitor HTTP (Uptime Kuma, Gatus, un `curl` en cron…) apuntado a `GET /api/health`. No pide sesión y responde en menos de 3 segundos:

| Respuesta | Significado |
|---|---|
| `200` `{"ok": true, "db": true, "graph": true, "graphs": 3}` | Todo bien |
| `503` con `"db": false` | La aplicación está viva pero no llega a PostgreSQL |
| `503` con `"graph": false` | La aplicación está viva pero FalkorDB no responde |
| Sin respuesta o error de conexión | La aplicación está caída |
| `"secrets": "unreadable"` en el cuerpo (con cualquier código) | La aplicación funciona, pero `MIMIRSYNTH_SESSION_SECRET` no es la clave que cifró los secretos guardados: ver el asistente de primer arranque, más arriba |

Avisa ante cualquier código distinto de `200`; para distinguir los casos, mira `db` y `graph` en el cuerpo. Cada comprobación espera como mucho 2 segundos, y la causa de un fallo va al log del contenedor (`docker compose logs mimirsynth`), nunca a la respuesta. Si el monitor está en otra máquina, usa la dirección pública detrás del proxy inverso (`https://memoria.example.com/api/health`). La comprobación de salud de Docker del contenedor usa el mismo endpoint, así que `docker ps` lo marca como `unhealthy` en ambos casos. Al ser pública, también informa de un problema de configuración, sin detalles (ni tipos ni cuántos): `"secrets": "unreadable"` cuando `MIMIRSYNTH_SESSION_SECRET` no abre los secretos guardados. Ese campo no cambia el código de respuesta.

Para ver cómo va (tiempo del recall, trabajos en cola, propuestas, errores de los motores de IA), activa las métricas de Prometheus en `/metrics` desde Administración → Métricas: consulta «Métricas» en la wiki.

## Contribuir
Construir desde el código es cosa de colaboradores: ver [CONTRIBUTING.md](CONTRIBUTING.md).

## Problemas frecuentes
- **«define POSTGRES_PASSWORD» o «define MIMIRSYNTH_SESSION_SECRET» al arrancar:** faltan en `.env`.
- **El instalador dice que Docker necesita `sudo`:** tu usuario se acaba de añadir al grupo `docker`, y eso surte efecto en el siguiente inicio de sesión. Mientras tanto el instalador usa `sudo`; cierra la sesión y vuelve a entrar para usar `docker` sin él.
- **El instalador se para en «nada responde» o en «la prueba de conexión ha fallado» con una base de datos de grafos existente:** el mensaje dice qué paso ha fallado (dirección, TLS, credenciales, versión o permiso de escritura). Comprueba desde ese ordenador el host, el puerto y el cortafuegos, y el usuario y la contraseña. Para instalar de todos modos, responde que quieres continuar o añade `--skip-graph-check`: la instancia arranca con esa conexión, y el paso del grafo del asistente espera a que pase, cuando la corrijas en `.env` y ejecutes `docker compose up -d`.
- **Neo4j Aura: «El servidor no tiene la base de datos «neo4j»», «El servidor no encuentra la base de datos predeterminada de este usuario» o `Database … not found` en el log:** deja la base de datos vacía (Aura la llama como el id de la instancia, y la prueba la encuentra) y conecta con `neo4j+s://` (`--graph-tls`), no con `bolt+s://`: con `bolt+s://` el driver habla con un solo miembro del clúster, que puede no tener la base de datos. Una instancia instalada con la 0.15.0-rc.1 tiene `bolt+s://` en `.env`: cámbialo por `neo4j+s://` y ejecuta `docker compose up -d`.
- **Las propuestas aprobadas se quedan en «aprobada»:** no hay LLM configurado. Añade un motor en Administración → Modelo LLM.
- **Los embeddings fallan con un error de conexión, con Ollama en el mismo host Linux:** Ollama solo escucha en `127.0.0.1`; ver [Preparar Ollama](#preparar-ollama). Si usas un `docker-compose.yml` propio, comprueba que el servicio `mimirsynth` tiene `extra_hosts: ["host.docker.internal:host-gateway"]`.
- **El recall no devuelve nada:** comprueba los embeddings (Administración → Embeddings → Probar) y que el índice de texto esté sincronizado (pestaña Preguntar muestra su estado).
- **No llegó ningún aviso cuando se cayó PostgreSQL:** no puede avisar de sí mismo. Vigílalo con un monitor externo: ver [Vigilar la instancia](#vigilar-la-instancia).
- **No encuentro el código de instalación:** solo aparece mientras no haya ningún administrador. Reinicia el contenedor para que genere uno nuevo.
- **Se perdió el acceso del único administrador:** con acceso al servidor, pon `is_admin = false` a ese usuario en la tabla `users` y reinicia el contenedor: el asistente de primer arranque volverá a aparecer con un código nuevo.
