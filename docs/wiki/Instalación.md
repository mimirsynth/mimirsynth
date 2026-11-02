[English](Installation) · **Español**

# Instalación

## Requisitos
- **Docker** con Compose v2 y unos **2 GB de RAM** libres para la aplicación, PostgreSQL y FalkorDB.
- Un endpoint **compatible con OpenAI** para **embeddings** y otro para el **LLM** de extracción. Pueden ser locales (Ollama, vLLM…) o de un proveedor en la nube, y son independientes entre sí. Se configuran después, en la interfaz. Sin ellos la instancia arranca, pero las propuestas no se ingieren y el recall no devuelve nada.
- Un puerto libre (por defecto el 8000).

## Antes de empezar
En un servidor Linux vacío (p. ej. un Debian o Ubuntu mínimo), instala `curl` y Docker y comprueba que está Compose v2. En macOS o Windows, instala [Docker Desktop](https://docs.docker.com/desktop/).
```bash
sudo apt-get update && sudo apt-get install -y curl openssl
curl -fsSL https://get.docker.com | sudo sh          # Docker Engine con el plugin de Compose
sudo usermod -aG docker "$USER" && newgrp docker      # usar docker sin sudo
docker compose version                                 # debe responder v2.x
```

### Preparar Ollama
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

## Qué se instala
El `docker-compose.yml` define:
- **mimirsynth**: la API y la interfaz en un solo contenedor (sin privilegios, sistema de ficheros de solo lectura). Asocia `host.docker.internal` al host, para llegar a los servicios que corren en él (Ollama, por ejemplo).
- **postgres**: PostgreSQL con la extensión pgvector (usuarios, brains, propuestas, avisos, índices de texto y de documentos).
- **falkordb** (perfil `bundled`, opcional): el motor de grafos. Si ya tienes un FalkorDB, no actives el perfil y apunta `MIMIRSYNTH_FALKOR_HOST` a él.

PostgreSQL y FalkorDB **no publican puertos** fuera de la red de Compose.

## Pasos
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
La primera vez descarga la imagen publicada (`ghcr.io/mimirsynth/mimirsynth`, para amd64 y arm64). Para fijar una versión, pon `MIMIRSYNTH_VERSION=0.10.0` en `.env` (por defecto: `latest`). Comprueba que está sano:
```bash
docker compose ps                          # los servicios en "healthy"
curl -s http://localhost:8000/api/health   # {"ok":true,"db":true,"graph":true,...}
```

## Primer arranque
Una instancia sin administradores imprime un **código de instalación** en su registro y muestra un asistente en la web:
```bash
docker compose logs mimirsynth | grep -A3 "PRIMER ARRANQUE"
```
El código solo existe mientras no haya ningún administrador (si lo pierdes, reinicia el contenedor para generar otro). Abre la aplicación, pégalo y crea la cuenta de administrador. Los campos de contraseña muestran todas las reglas y las van marcando mientras escribes.

Después llegas a **Primeros pasos**: mientras no exista ningún brain, un administrador ve un botón **Crea tu primer brain** y una lista corta (modelos de IA, token de API, conectar un agente) con un enlace a cada pantalla. Cualquier otra persona sin brain ve «No tienes acceso a ningún brain todavía. Pide a un administrador que te añada.»

## Después de instalar
1. Configura los modelos: [[Proveedores de IA]].
2. Crea un brain: [[Administrar brains y miembros]].
3. Crea un token de API y conecta tu primer agente: [[Conectar agentes]].
4. Si vas a exponerlo, ponlo detrás de HTTPS: [[HTTPS y proxy inverso]].
5. Configura el correo y los usuarios: [[Correo SMTP]], [[Administrar usuarios]].
6. Planifica las copias y las actualizaciones: [[Actualización y copias de seguridad]], y vigila la instancia (abajo).

## Vigilar la instancia
MimirSynth avisa por sí mismo del grafo y de los modelos de IA (la campana y los canales de notificación), pero **no de su propio PostgreSQL**: los avisos se guardan en esa base de datos, así que mientras está caída no hay dónde guardarlos. Vigílalo desde fuera con cualquier monitor HTTP (Uptime Kuma, Gatus, un `curl` en cron…) apuntado a `GET /api/health`. No pide sesión y responde en menos de 3 segundos:

| Respuesta | Significado |
|---|---|
| `200` `{"ok": true, "db": true, "graph": true, "graphs": 3}` | Todo bien |
| `503` con `"db": false` | La aplicación está viva pero no llega a PostgreSQL |
| `503` con `"graph": false` | La aplicación está viva pero FalkorDB no responde |
| Sin respuesta o error de conexión | La aplicación está caída |

Avisa ante cualquier código distinto de `200`; para distinguir los casos, mira `db` y `graph` en el cuerpo. Cada comprobación espera como mucho 2 segundos, y la causa de un fallo va al log del contenedor (`docker compose logs mimirsynth`), nunca a la respuesta. Si el monitor está en otra máquina, usa la dirección pública detrás del proxy inverso (`https://memoria.example.com/api/health`). La comprobación de salud de Docker del contenedor usa el mismo endpoint, así que `docker ps` lo marca como `unhealthy` en ambos casos.

Para ver cómo va (tiempo del recall, trabajos en cola, propuestas, errores de los motores de IA), activa las métricas de Prometheus en `/metrics` desde Administración → Métricas: consulta [[Métricas]].

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

## Modo desarrollo (sin inicio de sesión)
`MIMIRSYNTH_AUTH_MODE=off` desactiva el inicio de sesión y convierte a todo el mundo en administrador local. **Solo para desarrollo en tu máquina**; nunca lo uses en un servidor accesible.
