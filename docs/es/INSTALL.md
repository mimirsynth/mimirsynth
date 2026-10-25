[English](../INSTALL.md) · **Español**

# Instalación

## Requisitos
- Docker con Compose v2 y unos 2 GB de RAM libres para la aplicación, PostgreSQL y FalkorDB.
- Un endpoint compatible con OpenAI para **embeddings** (p. ej. [Ollama](https://ollama.com) con `nomic-embed-text`) y otro para el **LLM** que extrae los hechos. Pueden ser locales o de un proveedor en la nube. Se configuran después, en la interfaz.

## Primera instalación
```bash
git clone https://github.com/MimirSynth/mimirsynth.git && cd mimirsynth
cp .env.example .env
```
Edita `.env` y define, como mínimo, `POSTGRES_PASSWORD` y `MIMIRSYNTH_SESSION_SECRET` (genera ambos con `openssl rand -hex 32`). Después:
```bash
docker compose --profile bundled up -d
```
Descarga la imagen publicada (`ghcr.io/mimirsynth/mimirsynth`). Para construirla desde el código de tu copia, añade `--build`; para fijar una versión, pon `MIMIRSYNTH_VERSION=0.3.0` en `.env`.
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
```bash
docker compose pull        # o `git pull` + `--build` si construyes desde el código
docker compose --profile bundled up -d
```
Las migraciones de la base de datos se aplican solas al arrancar. Haz una copia de seguridad antes de actualizar.

## Copias de seguridad
Hay tres cosas que guardar, y deben ser coherentes entre sí:
- **PostgreSQL** (usuarios, brains, propuestas, índices): `docker compose exec -T postgres pg_dump -U mimirsynth mimirsynth > mimirsynth.sql`
- **El volumen `docstore`** (originales de los documentos subidos).
- **FalkorDB** (el conocimiento): el volumen `graphdata`, o un volcado con `redis-cli --rdb`.
Guarda también tu `.env`.

Restaurar es el camino inverso: arranca los servicios, restaura la base de datos (`psql`) y devuelve los volúmenes. El índice de texto se puede reconstruir desde el grafo y el de documentos desde los originales.

## Desarrollo
Ver [CONTRIBUTING.md](CONTRIBUTING.md).

## Problemas frecuentes
- **«define POSTGRES_PASSWORD» o «define MIMIRSYNTH_SESSION_SECRET» al arrancar:** faltan en `.env`.
- **Las propuestas aprobadas se quedan en «aprobada»:** no hay LLM configurado. Añade un motor en Administración → Modelo LLM.
- **El recall no devuelve nada:** comprueba los embeddings (Administración → Embeddings → Probar) y que el índice de texto esté sincronizado (pestaña Preguntar muestra su estado).
- **No encuentro el código de instalación:** solo aparece mientras no haya ningún administrador. Reinicia el contenedor para que genere uno nuevo.
- **Se perdió el acceso del único administrador:** con acceso al servidor, pon `is_admin = false` a ese usuario en la tabla `users` y reinicia el contenedor: el asistente de primer arranque volverá a aparecer con un código nuevo.
