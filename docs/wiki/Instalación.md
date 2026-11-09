[English](Installation) · **Español**

# Instalación

## Requisitos
- **Docker** con Compose v2 y unos **2 GB de RAM** libres para la aplicación, PostgreSQL y FalkorDB (más con el Ollama incluido).
- Un endpoint **compatible con OpenAI** para **embeddings** y otro para el **LLM** de extracción. Pueden ser locales (Ollama, vLLM…) o de un proveedor en la nube, y son independientes entre sí. Se configuran después, en el asistente de configuración. Sin ellos la instancia arranca, pero las propuestas no se ingieren y el recall no devuelve nada.
- Un puerto libre (por defecto el 8000).

## Instalar con un comando
Si todo esto es nuevo para ti, [[Tus primeros 15 minutos]] te lleva por la misma instalación con cada pregunta explicada.

El instalador comprueba Docker, hace dos preguntas, genera los secretos, arranca todo y abre el navegador en el asistente de configuración. No tienes que editar `.env`.

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
2. **Pregunta dónde vive tu grafo de conocimiento.** *Local* (la opción por defecto) arranca un FalkorDB incluido junto a MimirSynth. *Existente* pide el tipo (FalkorDB o Neo4j), el host, el puerto, el usuario y la contraseña de un servidor que ya tienes, y comprueba que responde antes de seguir. A un servidor en el mismo ordenador (`localhost`) el contenedor llega como `host.docker.internal`. La prueba completa de conexión (credenciales, versión, permisos) se hace en el asistente de configuración.
3. **Ofrece un Ollama incluido** para los embeddings y descarga `nomic-embed-text`. La imagen es una descarga de unos 3,5 GB y funciona con la CPU; si Ollama ya está en marcha en el ordenador, el instalador usa ese. En un Mac con Apple silicon la aplicación nativa de Ollama es más rápida: usa la GPU.
4. **Escribe `docker-compose.yml` y `.env`** en `~/mimirsynth` (`%USERPROFILE%\mimirsynth` en Windows), con un `POSTGRES_PASSWORD` y un `MIMIRSYNTH_SESSION_SECRET` aleatorios, la versión de la release fijada en `MIMIRSYNTH_VERSION`, un puerto libre (el 8000 o el siguiente) y los perfiles elegidos en `COMPOSE_PROFILES`, para que un simple `docker compose up -d` en esa carpeta arranque después los mismos servicios.
5. **Arranca los servicios**, espera a que responda `/api/health`, muestra la dirección y el **código de inicio**, y abre el navegador.

Volver a ejecutarlo es seguro: si MimirSynth ya está instalado en esa carpeta, no cambia nada y ofrece actualizar con `update.sh` (en Linux; ver [[Actualización y copias de seguridad]]). Si se detiene a medias, dice por qué y no borra nada: corrige la causa ([Primer arranque](Soluci%C3%B3n-de-problemas#primer-arranque)) y vuelve a ejecutarlo.

### Sin preguntas
Cada respuesta tiene su opción (`--help` las enumera). Con `--yes` no pregunta nada: FalkorDB incluido, sin Ollama salvo con `--ollama` y sin instalar Docker salvo con `--install-docker`.
```bash
curl -fsSL https://github.com/MimirSynth/mimirsynth/releases/latest/download/install.sh | bash -s -- --yes --ollama
MIMIRSYNTH_GRAPH_PASSWORD='…' ./install.sh --yes --graph existing --graph-type neo4j --graph-host grafo.example.com
```
En PowerShell los parámetros se llaman igual (`-Yes`, `-Ollama`, `-Graph existing`, `-GraphType`, `-GraphHost`…). La contraseña de una base de datos de grafos existente se lee de `MIMIRSYNTH_GRAPH_PASSWORD`, nunca de la línea de comandos. Los mensajes siguen el idioma del sistema (`--lang es`), y el idioma por defecto de la instancia también.

### Comprobar la descarga
Cada release enumera el SHA-256 de sus ficheros en sus notas y en `SHA256SUMS`:
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
curl -fsSL https://get.docker.com | sudo sh          # Docker Engine con el plugin de Compose
sudo usermod -aG docker "$USER" && newgrp docker      # usar docker sin sudo
docker compose version                                 # debe responder v2.x
```

#### Preparar Ollama
Si los modelos van en [Ollama](https://ollama.com), descárgalos antes de empezar:
```bash
ollama pull nomic-embed-text        # embeddings (768 dimensiones, el valor por defecto)
ollama pull qwen2.5:14b-instruct    # extracción de hechos (se recomienda de unos 14B o más)
```
- **Ollama en el mismo host:** la dirección por defecto, `http://host.docker.internal:11434/v1`, funciona sin cambios: el fichero de Compose asocia ese nombre al host, también en Linux. Pero en Linux Ollama solo escucha en `127.0.0.1` por defecto, y desde el contenedor no se llega ahí. Haz que escuche en todas las interfaces y mantén el puerto 11434 cerrado hacia fuera con tu cortafuegos:
  ```bash
  sudo systemctl edit ollama    # añade, bajo [Service]:  Environment="OLLAMA_HOST=0.0.0.0"
  sudo systemctl restart ollama
  ```
- **Ollama en otra máquina:** usa su dirección, p. ej. `http://192.168.1.20:11434/v1`.

Para elegir el modelo de extracción (tamaño, qué esperar de los modelos pequeños), ver [[Proveedores de IA]].

### Qué se instala
El `docker-compose.yml` define (el instalador escribe el mismo):
- **mimirsynth**: la API y la interfaz en un solo contenedor (sin privilegios, sistema de ficheros de solo lectura). Asocia `host.docker.internal` al host, para llegar a los servicios que corren en él (Ollama, por ejemplo).
- **postgres**: PostgreSQL con la extensión pgvector (usuarios, brains, propuestas, avisos, índices de texto y de documentos).
- **falkordb** (perfil `bundled`, opcional): el motor de grafos. Si ya tienes un FalkorDB, no actives el perfil y apunta `MIMIRSYNTH_FALKOR_HOST` a él.

PostgreSQL y FalkorDB **no publican puertos** fuera de la red de Compose.

### Descargar y arrancar
Todo sale de la release oficial: un fichero de Compose y una plantilla de entorno. No necesitas el código fuente.
```bash
mkdir mimirsynth && cd mimirsynth
curl -fsSLO https://github.com/MimirSynth/mimirsynth/releases/latest/download/docker-compose.yml
curl -fsSL https://github.com/MimirSynth/mimirsynth/releases/latest/download/env.example -o .env
```
Edita `.env`. Lo imprescindible:

| Variable | Qué poner |
|---|---|
| `POSTGRES_PASSWORD` | Una contraseña (`openssl rand -hex 32`) |
| `MIMIRSYNTH_SESSION_SECRET` | Otro secreto largo y aleatorio. **Guárdalo**: firma las sesiones y cifra los secretos de la base de datos |

Opcionales frecuentes: `MIMIRSYNTH_PORT`, `MIMIRSYNTH_PUBLIC_URL`, `MIMIRSYNTH_COOKIE_SECURE`, `MIMIRSYNTH_DEFAULT_LANGUAGE`, `MIMIRSYNTH_EMBEDDING_BASE_URL`, `MIMIRSYNTH_FALKOR_HOST`. Lista completa en [[Variables de entorno]].

> **No pongas comentarios al final de una línea de valor** en `.env` (`CLAVE=valor  # comentario`): Docker Compose los leería como parte del valor.

Arranca:
```bash
docker compose --profile bundled up -d
```
La primera vez descarga la imagen publicada (`ghcr.io/mimirsynth/mimirsynth`, para amd64 y arm64). Para fijar una versión, pon `MIMIRSYNTH_VERSION=0.14.0` en `.env` (por defecto: `latest`). Comprueba que está sano:
```bash
docker compose ps                          # los servicios en "healthy"
curl -s http://localhost:8000/api/health   # {"ok":true,"db":true,"graph":true,...}
```

## Primer arranque
Una instancia sin administradores pide un **código de inicio** en la web y lo imprime en su registro. El instalador te lo muestra; tras una instalación manual:
```bash
docker compose logs mimirsynth | grep -A3 "PRIMER ARRANQUE"
```
El código solo existe mientras no haya ningún administrador (si lo pierdes, reinicia el contenedor para generar otro).

<!-- TODO(#361): contrastado con el código del asistente; comparar con el PR de #361 cuando se fusione. -->
Pégalo y crea la cuenta de administrador (el formulario marca cada regla de la contraseña mientras escribes). Después se abre la **Configuración inicial** en `/configuracion`, que sigue hasta el primer recall, un paso por pantalla, y retoma donde lo dejaste: **tu cuenta** → **base de datos del grafo** (la prueba de conexión tiene que pasar) → **embeddings** (el motor tiene que responder con la dimensión del índice) → **modelo LLM** (se puede saltar, con un recordatorio en el inicio) → **decisor** (opcional) → **tu primer brain** → **token de API** (Colaborador, 90 días) → **conecta tu agente**. Cada paso se explica en [[Tus primeros 15 minutos]]. **Configurar a mano** lo cierra; el botón **Asistente de configuración**, arriba en Administración, lo vuelve a abrir. Mientras no haya ningún brain y el asistente esté cerrado, un administrador llega a **Primeros pasos**, con un botón **Crea tu primer brain** y enlaces a cada pantalla.

Cualquier otra persona sin brain ve «No tienes acceso a ningún brain todavía. Pide a un administrador que te añada.»

## Después de instalar
1. Los modelos, el primer brain, un token y el primer agente llegan con el asistente; para cambiarlos después: [[Proveedores de IA]], [[Administrar brains y miembros]], [[Conectar agentes]].
2. Si vas a exponerlo, ponlo detrás de HTTPS: [[HTTPS y proxy inverso]].
3. Configura el correo y los usuarios: [[Correo SMTP]], [[Administrar usuarios]].
4. Planifica las copias y las actualizaciones: [[Actualización y copias de seguridad]], y vigila la instancia (abajo).

## Vigilar la instancia
MimirSynth avisa por sí mismo del grafo y de los modelos de IA (la campana y los canales de notificación), pero **no de su propio PostgreSQL**: los avisos se guardan en esa base de datos, así que mientras está caída no hay dónde guardarlos. Vigílalo desde fuera con cualquier monitor HTTP (Uptime Kuma, Gatus, un `curl` en cron…) apuntado a `GET /api/health`. No pide sesión y responde en menos de 3 segundos:

| Respuesta | Significado |
|---|---|
| `200` `{"ok": true, "db": true, "graph": true, "graphs": 3}` | Todo bien |
| `503` con `"db": false` | La aplicación está viva pero no llega a PostgreSQL |
| `503` con `"graph": false` | La aplicación está viva pero FalkorDB no responde |
| Sin respuesta o error de conexión | La aplicación está caída |
| `"secrets": "unreadable"` en el cuerpo (con cualquier código) | La aplicación funciona, pero `MIMIRSYNTH_SESSION_SECRET` no es la clave que cifró los secretos guardados: ver [[Actualización y copias de seguridad]] |

Avisa ante cualquier código distinto de `200`; para distinguir los casos, mira `db` y `graph` en el cuerpo. Cada comprobación espera como mucho 2 segundos, y la causa de un fallo va al log del contenedor (`docker compose logs mimirsynth`), nunca a la respuesta. Si el monitor está en otra máquina, usa la dirección pública detrás del proxy inverso (`https://memoria.example.com/api/health`). La comprobación de salud de Docker del contenedor usa el mismo endpoint, así que `docker ps` lo marca como `unhealthy` en ambos casos. Al ser pública, también informa de un problema de configuración, sin detalles (ni tipos ni cuántos): `"secrets": "unreadable"` cuando `MIMIRSYNTH_SESSION_SECRET` no abre los secretos guardados. Ese campo no cambia el código de respuesta.

Para ver cómo va (tiempo del recall, trabajos en cola, propuestas, errores de los motores de IA), activa las métricas de Prometheus en `/metrics` desde Administración → Métricas: consulta [[Métricas]].

## OCR para PDF escaneados e imágenes (opcional)

Un PDF escaneado no tiene capa de texto, y una imagen (`.png`, `.jpg`) solo tiene píxeles: para indexarlos MimirSynth necesita OCR. Tesseract corre en **su propio contenedor**, así que la imagen principal no crece.
1. Arráncalo con el perfil `ocr`, junto a los que ya uses: `docker compose --profile ocr up -d` (añade `--profile bundled` si usas el FalkorDB incluido).
2. Añade `MIMIRSYNTH_OCR_URL=http://ocr:8001` al `.env` y ejecuta `docker compose up -d mimirsynth`.

En **Conocimiento**, quien administra un brain ve si el OCR responde. La imagen lee castellano e inglés; para más idiomas, constrúyela con `docker build --build-arg LANGS="spa eng cat" -t mimirsynth-ocr ocr/` y haz que el servicio la use. En Administración → Ajustes → Documentos se eligen los idiomas (`spa+eng`) y el máximo de páginas que se leen con OCR por documento (50). El servicio no tiene autenticación: no publiques su puerto. `update.sh` lo actualiza junto con la aplicación.

En vez de Tesseract, un brain puede leer sus páginas escaneadas con el **modelo de visión** de un motor LLM (Conocimiento → *Leer con el modelo de visión*). Entonces cada página es una llamada al motor, así que está desactivado por defecto. Una imagen suelta no necesita el servicio OCR en ese caso, pero un PDF sí, para convertir sus páginas en imágenes.

## Instalar sin FalkorDB incluido
Si ya tienes un FalkorDB (por ejemplo, el de un Graphiti existente), no uses `--profile bundled`:
```bash
# en .env
MIMIRSYNTH_FALKOR_HOST=mi-falkordb
MIMIRSYNTH_FALKOR_PORT=6379
# opcional: adoptar sus grafos como brains en el primer arranque
MIMIRSYNTH_BOOTSTRAP_GRAPHS=docs:Documentación,equipo:Equipo
docker compose up -d
```
El formato es `slug:Nombre`. Solo se aplica en el primer arranque (cuando aún no hay ningún brain). Los slugs deben ser minúsculas, números y guiones. Un FalkorDB externo no entra en las copias que hace `update.sh`: guárdalo tú ([[Actualización y copias de seguridad]]).

## Instalar con Neo4j
Si tus grafos están en Neo4j (5.26 LTS o posterior, Community o Enterprise), no uses `--profile bundled`:
```bash
# en .env
MIMIRSYNTH_GRAPH_BACKEND=neo4j
MIMIRSYNTH_NEO4J_URI=bolt://mi-neo4j:7687
MIMIRSYNTH_NEO4J_USER=neo4j
MIMIRSYNTH_NEO4J_PASSWORD=…
# opcional: otra base de datos que no sea la predeterminada del servidor
MIMIRSYNTH_NEO4J_DATABASE=
docker compose up -d
```
Todos los brains comparten esa base de datos: un brain son los nodos cuyo `group_id` es su nombre, tal como los escribe Graphiti, y `MIMIRSYNTH_BOOTSTRAP_GRAPHS` adopta los `group_id` existentes del mismo modo. Una exportación lleva entonces solo la copia JSON del grafo, y la consola Cypher solo ejecuta lo que sabe mantener dentro del brain. Detalles y versiones soportadas en [la referencia de configuración](https://github.com/MimirSynth/mimirsynth/blob/main/docs/es/CONFIGURATION.md#base-de-datos-de-grafos), y qué separa los brains, con sus límites, en [Aislamiento entre brains con Neo4j](https://github.com/MimirSynth/mimirsynth/blob/main/docs/es/CONFIGURATION.md#aislamiento-entre-brains-con-neo4j). Neo4j no entra en las copias que hace `update.sh`: guárdalo tú.

## Modo desarrollo (sin inicio de sesión)
`MIMIRSYNTH_AUTH_MODE=off` desactiva el inicio de sesión y convierte a todo el mundo en administrador local. **Solo para desarrollo en tu máquina**; nunca lo uses en un servidor accesible.
