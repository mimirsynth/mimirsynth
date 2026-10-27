[English](../INSTALL.md) · **Español**

# Instalación

## Requisitos
- Docker con Compose v2 y unos 2 GB de RAM libres para la aplicación, PostgreSQL y FalkorDB.
- Un endpoint compatible con OpenAI para **embeddings** (p. ej. [Ollama](https://ollama.com) con `nomic-embed-text`) y otro para el **LLM** que extrae los hechos. Pueden ser locales o de un proveedor en la nube. Se configuran después, en la interfaz.

## Primera instalación
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
Descarga la imagen oficial (`ghcr.io/mimirsynth/mimirsynth`, para amd64 y arm64). Para fijar una versión, pon `MIMIRSYNTH_VERSION=0.7.1` en `.env` (por defecto, `latest`).
- `--profile bundled` arranca también un FalkorDB incluido. Si ya tienes uno, omite el perfil y pon su dirección en `MIMIRSYNTH_FALKOR_HOST`.
- La aplicación queda en `http://localhost:8000` (cambia el puerto con `MIMIRSYNTH_PORT`).

### Asistente de primer arranque
Una instancia sin administradores imprime un **código de instalación** en su registro:
```bash
docker compose logs mimirsynth | grep -A3 "FIRST START"
```
Abre la aplicación, introduce el código y crea la cuenta de administrador. Guarda `MIMIRSYNTH_SESSION_SECRET`: si lo pierdes o lo cambias, los secretos guardados (claves de los proveedores, contraseña SMTP, secreto OIDC) dejan de poder descifrarse y hay que volver a introducirlos.

### Primeros pasos
1. En **Administración → Modelo LLM** y **Embeddings**, añade un motor (endpoint, clave y modelo) y márcalo como predeterminado. «Probar» comprueba que responde.
2. Crea un **brain** (Administración → Acceso al brain → Crear brain) y, si quieres, aplica un paquete de ontología en Vocabulario → Ontología.
3. Crea un token de API para tus agentes: ver [AGENTS.md](AGENTS.md).
4. Opcional: correo SMTP (invitaciones y recuperación de contraseña), OIDC, doble factor obligatorio y carpetas de documentos. Ver [CONFIGURATION.md](CONFIGURATION.md).

## HTTPS y proxy inverso
No publiques el puerto 8000 a Internet sin TLS. Pon un proxy inverso (Caddy, Traefik, nginx…) delante, define `MIMIRSYNTH_PUBLIC_URL` con la dirección pública y `MIMIRSYNTH_COOKIE_SECURE=true`. Si subes ficheros grandes, comprueba el límite de tamaño de petición del proxy: las subidas se envían por partes (por defecto de 64 MB).

PostgreSQL y FalkorDB no publican puertos fuera de la red de Compose. No los expongas.

## Actualizar
La release incluye un script que hace la copia de seguridad, actualiza y comprueba de una vez:
```bash
curl -fsSLO https://github.com/MimirSynth/mimirsynth/releases/latest/download/update.sh && chmod +x update.sh
./update.sh              # última versión estable; ./update.sh --check solo informa; --version 0.7.1 elige una
```
Hace, por este orden:
1. **Descarga** primero la imagen nueva: una versión equivocada o la falta de red paran todo antes de tocar nada.
2. **Copia de seguridad** de PostgreSQL, del volumen `docstore`, del FalkorDB incluido (si usas `--profile bundled`) y de tu `docker-compose.yml` y `.env` en `./backup`. **Solo se conserva una copia**: la anterior se sustituye cuando la nueva ya está escrita y comprobada, así que las copias nunca se acumulan.
3. **Actualiza**: fija `MIMIRSYNTH_VERSION` en `.env` y recrea solo la aplicación (las migraciones se aplican al arrancar). Adopta el `docker-compose.yml` de la versión solo si el tuyo es el original, sin modificar, de la versión que tenías; si no, conserva el tuyo y te avisa (`--update-compose` lo fuerza, `--keep-compose` no lo toca nunca).
4. **Comprueba** que responde con la versión nueva y está sana, y muestra la revisión de la base de datos. Si no se verifica, te dice cómo volver atrás.

Para volver atrás: `./update.sh --rollback` restaura la imagen y los ficheros anteriores; añade `--with-db` para restaurar también la base de datos (lo escrito desde la copia se pierde). Un FalkorDB externo no forma parte de la copia: guárdalo tú. Sin el script, a mano es `docker compose pull` y `docker compose --profile bundled up -d`, tras una copia de seguridad.

## Copias de seguridad
Hay tres cosas que guardar, y deben ser coherentes entre sí:
- **PostgreSQL** (usuarios, brains, propuestas, índices): `docker compose exec -T postgres pg_dump -U mimirsynth mimirsynth > mimirsynth.sql`
- **El volumen `docstore`** (originales de los documentos subidos).
- **FalkorDB** (el conocimiento): el volumen `graphdata`, o un volcado con `redis-cli --rdb`.
Guarda también tu `.env`.

Restaurar es el camino inverso: arranca los servicios, restaura la base de datos (`psql`) y devuelve los volúmenes. El índice de texto se puede reconstruir desde el grafo y el de documentos desde los originales.

## Contribuir
Construir desde el código es cosa de colaboradores: ver [CONTRIBUTING.md](CONTRIBUTING.md).

## Problemas frecuentes
- **«define POSTGRES_PASSWORD» o «define MIMIRSYNTH_SESSION_SECRET» al arrancar:** faltan en `.env`.
- **Las propuestas aprobadas se quedan en «aprobada»:** no hay LLM configurado. Añade un motor en Administración → Modelo LLM.
- **El recall no devuelve nada:** comprueba los embeddings (Administración → Embeddings → Probar) y que el índice de texto esté sincronizado (pestaña Preguntar muestra su estado).
- **No encuentro el código de instalación:** solo aparece mientras no haya ningún administrador. Reinicia el contenedor para que genere uno nuevo.
- **Se perdió el acceso del único administrador:** con acceso al servidor, pon `is_admin = false` a ese usuario en la tabla `users` y reinicia el contenedor: el asistente de primer arranque volverá a aparecer con un código nuevo.
