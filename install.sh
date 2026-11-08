#!/usr/bin/env bash
# MimirSynth installer for Linux and macOS (Docker Desktop). On Windows, use install.ps1.
#   curl -fsSL https://github.com/MimirSynth/mimirsynth/releases/latest/download/install.sh | bash
# It checks Docker, asks a few questions, writes docker-compose.yml and .env (with generated secrets), starts the stack, waits
# until it answers and opens the browser on the first-start wizard. Run it again at any time: it detects an existing install and
# offers update.sh instead. Without a terminal, or with --yes, it asks nothing and uses the flags and the defaults (see --help).
set -Eeuo pipefail

REPO="MimirSynth/mimirsynth"
EMBED_MODEL="nomic-embed-text"
WAIT_SECONDS="${WAIT_SECONDS:-300}"
DIR=""; VERSION=""; PORT=""; FROM=""; YES=0; LANG_OPT=""
GRAPH=""; GTYPE=""; GHOST=""; GPORT=""; GUSER=""; GDB=""; GPASS="${MIMIRSYNTH_GRAPH_PASSWORD:-}"; SKIP_GRAPH_CHECK=0
OLLAMA=""; INSTALL_DOCKER=0; UPGRADE=0; START=1; BROWSER=1

usage() {
  cat <<'EOF'
MimirSynth installer (Linux and macOS with Docker Desktop).
  curl -fsSL https://github.com/MimirSynth/mimirsynth/releases/latest/download/install.sh | bash
  curl -fsSL .../install.sh | bash -s -- --yes --ollama          # no questions

Options:
  --dir DIR                where to install (default: the current folder if it holds an install, else ~/mimirsynth)
  --version X              release to install, e.g. 0.15.0 (default: the latest stable one)
  --port N                 host port (default: 8000, or the next free one)
  --graph local|existing   local: start the bundled FalkorDB (default); existing: use your FalkorDB or Neo4j server
  --graph-type falkordb|neo4j   --graph-host HOST   --graph-port N   --graph-user USER   --graph-database DB
                           the password is read from MIMIRSYNTH_GRAPH_PASSWORD, never from the command line
  --skip-graph-check       go on even if the existing graph database does not answer
  --ollama | --no-ollama   start a bundled Ollama for embeddings and download nomic-embed-text (default without
                           questions: no)
  --install-docker         on Linux, install Docker with its official script if it is missing
  --upgrade                if MimirSynth is already installed in DIR, run its update.sh without asking
  --no-start               only write docker-compose.yml and .env
  --no-browser             do not open the browser
  --lang en|es             language of the messages and default language of the instance
  -y, --yes                ask nothing
  --from DIR               take docker-compose.yml, env.example and update.sh from DIR instead of the release
EOF
}

parse_args() {
while [ $# -gt 0 ]; do
  case "$1" in
    --dir) DIR="${2:-}"; shift ;;
    --version) VERSION="${2:-}"; shift ;;
    --port) PORT="${2:-}"; shift ;;
    --graph) GRAPH="${2:-}"; shift ;;
    --graph-type) GTYPE="${2:-}"; shift ;;
    --graph-host) GHOST="${2:-}"; shift ;;
    --graph-port) GPORT="${2:-}"; shift ;;
    --graph-user) GUSER="${2:-}"; shift ;;
    --graph-database) GDB="${2:-}"; shift ;;
    --skip-graph-check) SKIP_GRAPH_CHECK=1 ;;
    --ollama) OLLAMA=1 ;;
    --no-ollama) OLLAMA=0 ;;
    --install-docker) INSTALL_DOCKER=1 ;;
    --upgrade) UPGRADE=1 ;;
    --no-start) START=0 ;;
    --no-browser) BROWSER=0 ;;
    --lang) LANG_OPT="${2:-}"; shift ;;
    --from) FROM="${2:-}"; shift ;;
    -y|--yes) YES=1 ;;
    -h|--help) usage; exit 0 ;;
    *) printf 'ERROR: unknown option / opción desconocida: %s\n' "$1" >&2; exit 2 ;;
  esac
  shift
done
}

setup_lang() {
  if [ -n "$LANG_OPT" ]; then L="$LANG_OPT"; else case "${LC_ALL:-${LANG:-}}" in es*) L=es ;; *) L=en ;; esac; fi
  [ "$L" = es ] || L=en
}
L=en
say()  { if [ "$L" = es ]; then printf '%s\n' "$2"; else printf '%s\n' "$1"; fi; }
step() { printf '\n== '; say "$@"; }
warn() { { printf 'WARN: '; say "$@"; } >&2; }
die()  { { printf 'ERROR: '; say "$@"; } >&2; exit 1; }

# ---- questions: through the terminal even when the script itself arrives through a pipe (curl | bash) ----
TTY=0
setup_tty() { if [ "$YES" != 1 ] && [ -r /dev/tty ] && (: </dev/tty) 2>/dev/null; then exec 3</dev/tty; TTY=1; fi; }
ask() {  # $1 English question, $2 Spanish question, $3 default -> REPLY
  REPLY="$3"; [ "$TTY" = 1 ] || return 0
  local q; if [ "$L" = es ]; then q="$2"; else q="$1"; fi
  if [ -n "$3" ]; then printf '%s [%s]: ' "$q" "$3" >&2; else printf '%s: ' "$q" >&2; fi
  read -r REPLY <&3 || REPLY=""
  [ -n "$REPLY" ] || REPLY="$3"
}
ask_secret() {  # $1 English, $2 Spanish -> REPLY (not echoed)
  REPLY=""; [ "$TTY" = 1 ] || return 0
  if [ "$L" = es ]; then printf '%s: ' "$2" >&2; else printf '%s: ' "$1" >&2; fi
  read -rs REPLY <&3 || REPLY=""; printf '\n' >&2
}
yesno() {  # $1 English, $2 Spanish, $3 default y|n -> status 0 for yes
  if [ "$TTY" != 1 ]; then [ "$3" = y ]; return; fi
  local h a
  if [ "$3" = y ]; then h="Y/n"; [ "$L" = es ] && h="S/n"; else h="y/N"; [ "$L" = es ] && h="s/N"; fi
  if [ "$L" = es ]; then printf '%s [%s] ' "$2" "$h" >&2; else printf '%s [%s] ' "$1" "$h" >&2; fi
  read -r a <&3 || a=""
  case "$a" in "") [ "$3" = y ] ;; y|Y|yes|s|S|si|sí|Sí) return 0 ;; *) return 1 ;; esac
}

# ---- helpers ----
OS="$(uname -s)"; WSL=0
if [ "$OS" = Linux ] && grep -qi microsoft /proc/version 2>/dev/null; then WSL=1; fi
SUDO=""; if [ "$(id -u)" != 0 ] && command -v sudo >/dev/null; then SUDO="sudo"; fi
DOCKER="docker"
dc() { $DOCKER compose "$@"; }
norm() { printf '%s' "${1#v}"; }
gen_secret() { if command -v openssl >/dev/null; then openssl rand -hex 32; else od -An -N32 -tx1 /dev/urandom | tr -d ' \n'; fi; }
port_busy() { (exec 4<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null; }
tcp_check() {  # host port -> 0 if a TCP connection opens within 5 seconds
  (exec 4<>"/dev/tcp/$1/$2") 2>/dev/null &
  local pid=$! i=0
  while kill -0 "$pid" 2>/dev/null; do
    if [ "$i" -ge 50 ]; then kill "$pid" 2>/dev/null || true; wait "$pid" 2>/dev/null || true; return 1; fi
    sleep 0.1; i=$((i + 1))
  done
  wait "$pid"
}
envget() { local v; v=$(grep -E "^$1=" "$2" 2>/dev/null | tail -1 | cut -d= -f2- || true); v="${v%\"}"; v="${v#\"}"; v="${v%\'}"; v="${v#\'}"; printf '%s' "$v"; }
env_quote() {  # a value as Docker Compose reads it literally from .env
  case "$1" in
    *[!A-Za-z0-9._@:/+=,-]*) ;;
    *) printf '%s' "$1"; return ;;
  esac
  case "$1" in
    *"'"*) local v="$1"; v="${v//\\/\\\\}"; v="${v//\"/\\\"}"; v="${v//\$/\$\$}"; printf '"%s"' "$v" ;;
    *) printf "'%s'" "$1" ;;
  esac
}
setenv() {  # KEY VALUE: replace the KEY= line (or its commented example) in .env, or append it
  K="$1" V="$2" awk 'BEGIN { k = ENVIRON["K"]; v = ENVIRON["V"]; done = 0 }
    !done && ($0 ~ "^" k "=" || $0 ~ "^# ?" k "=") { print k "=" v; done = 1; next }
    { print }
    END { if (!done) print k "=" v }' .env > .env.tmp && mv .env.tmp .env
}
json_str() {  # a JSON string literal
  local s="$1"; s="${s//\\/\\\\}"; s="${s//\"/\\\"}"; s="${s//$'\n'/\\n}"; s="${s//$'\r'/\\r}"; s="${s//$'\t'/\\t}"; printf '"%s"' "$s"
}

# ---- Docker and Compose v2 ----
check_docker() {
  step "Docker" "Docker"
  if ! command -v docker >/dev/null; then
    if [ "$OS" = Darwin ]; then
      die "Docker is not installed. Install Docker Desktop (https://docs.docker.com/desktop/setup/install/mac-install/), start it and run this installer again." \
          "Docker no está instalado. Instala Docker Desktop (https://docs.docker.com/desktop/setup/install/mac-install/), ábrelo y vuelve a ejecutar este instalador."
    elif [ "$WSL" = 1 ]; then
      die "Docker is not available in this WSL distribution. Install Docker Desktop on Windows, enable Settings > Resources > WSL integration for this distribution and run this installer again (or use install.ps1 from PowerShell)." \
          "Docker no está disponible en esta distribución de WSL. Instala Docker Desktop en Windows, activa Settings > Resources > WSL integration para esta distribución y vuelve a ejecutar este instalador (o usa install.ps1 desde PowerShell)."
    fi
    say "Docker is not installed. It can be installed now with Docker's official script (get.docker.com), which needs sudo." \
        "Docker no está instalado. Se puede instalar ahora con el script oficial de Docker (get.docker.com), que necesita sudo."
    if [ "$INSTALL_DOCKER" = 1 ] || { [ "$TTY" = 1 ] && yesno "Install Docker now?" "¿Instalar Docker ahora?" y; }; then
      curl -fsSL https://get.docker.com | $SUDO sh
      if [ -n "$SUDO" ]; then $SUDO usermod -aG docker "$(id -un)" || true; fi
    else
      die "Install Docker (https://docs.docker.com/engine/install/) and run this installer again, or add --install-docker." \
          "Instala Docker (https://docs.docker.com/engine/install/) y vuelve a ejecutar este instalador, o añade --install-docker."
    fi
  fi
  local out; out="$(docker info 2>&1 || true)"
  if ! docker info >/dev/null 2>&1; then
    if [ "$OS" = Darwin ]; then
      say "Docker Desktop is not running: starting it..." "Docker Desktop no está en marcha: arrancándolo..."
      open -a Docker 2>/dev/null || true
      local i=0; while ! docker info >/dev/null 2>&1; do [ "$i" -ge 60 ] && die "Docker Desktop did not start: open it and run this installer again." "Docker Desktop no ha arrancado: ábrelo y vuelve a ejecutar este instalador."; sleep 2; i=$((i + 1)); done
    elif [ -n "$SUDO" ] && case "$out" in *"ermission denied"*) true ;; *) false ;; esac; then
      DOCKER="sudo docker"
      say "Your user cannot use Docker without sudo yet (log out and in again after being added to the docker group): using sudo for now." \
          "Tu usuario aún no puede usar Docker sin sudo (cierra la sesión y vuelve a entrar tras añadirlo al grupo docker): se usa sudo por ahora."
      $DOCKER info >/dev/null 2>&1 || die "Docker does not answer, even with sudo." "Docker no responde, ni siquiera con sudo."
    elif [ "$WSL" = 1 ]; then
      die "Docker does not answer: start Docker Desktop on Windows and check its WSL integration for this distribution." "Docker no responde: arranca Docker Desktop en Windows y revisa su integración con WSL para esta distribución."
    else
      say "The Docker service is not running: starting it..." "El servicio de Docker no está en marcha: arrancándolo..."
      $SUDO systemctl start docker 2>/dev/null || true
      docker info >/dev/null 2>&1 || { $DOCKER info >/dev/null 2>&1 || DOCKER="$SUDO docker"; }
      $DOCKER info >/dev/null 2>&1 || die "Docker does not answer: check 'systemctl status docker'." "Docker no responde: revisa 'systemctl status docker'."
    fi
  fi
  if ! $DOCKER compose version >/dev/null 2>&1; then
    if [ "$OS" = Darwin ]; then die "Docker Compose v2 is missing: update Docker Desktop." "Falta Docker Compose v2: actualiza Docker Desktop."; fi
    die "Docker Compose v2 is missing: install the docker-compose-plugin package (https://docs.docker.com/compose/install/linux/) or reinstall Docker with get.docker.com." \
        "Falta Docker Compose v2: instala el paquete docker-compose-plugin (https://docs.docker.com/compose/install/linux/) o reinstala Docker con get.docker.com."
  fi
  say "$($DOCKER --version) · $($DOCKER compose version --short 2>/dev/null || $DOCKER compose version)" "$($DOCKER --version) · $($DOCKER compose version --short 2>/dev/null || $DOCKER compose version)"
}

# ---- release files ----
fetch() {  # release asset name, destination
  if [ -n "$FROM" ]; then
    local src="$FROM/$1"; [ -f "$src" ] || [ "$1" != env.example ] || src="$FROM/.env.example"
    cp "$src" "$2"; return
  fi
  local url="https://github.com/$REPO/releases/download/v$VERSION/$1"
  [ -n "$VERSION" ] && [ "$VERSION" != latest ] || url="https://github.com/$REPO/releases/latest/download/$1"
  curl -fsSL --retry 3 --max-time 120 "$url" -o "$2"
}

# ---- an existing install: offer update.sh instead ----
existing_install() {
  step "Existing installation" "Instalación existente"
  say "MimirSynth is already installed in $DIR." "MimirSynth ya está instalado en $DIR."
  if [ "$OS" = Darwin ]; then  # update.sh needs GNU tools (flock, GNU sed and stat)
    say "To upgrade it: back up, then run 'docker compose pull && docker compose up -d' in that folder (see Upgrading in docs/INSTALL.md)." \
        "Para actualizarlo: haz una copia de seguridad y ejecuta 'docker compose pull && docker compose up -d' en esa carpeta (ver Actualizar en docs/es/INSTALL.md)."
    exit 0
  fi
  [ -f update.sh ] || { fetch update.sh update.sh && chmod +x update.sh; } || die "could not download update.sh" "no se pudo descargar update.sh"
  local run=0
  if [ "$UPGRADE" = 1 ]; then run=1
  elif [ "$TTY" = 1 ] && yesno "Upgrade it now with update.sh (backup, update and check)?" "¿Actualizarlo ahora con update.sh (copia de seguridad, actualización y comprobación)?" y; then run=1; fi
  if [ "$run" = 1 ]; then
    local lang_env="${LANG:-}"; [ "$L" = es ] && lang_env="es_ES.UTF-8"
    if [ "$DOCKER" = docker ]; then LANG="$lang_env" ./update.sh --yes; else sudo env LANG="$lang_env" ./update.sh --yes; fi
  else
    say "Nothing was changed. To upgrade later: cd $DIR && ./update.sh   (./update.sh --check only reports)" \
        "No se ha cambiado nada. Para actualizar más tarde: cd $DIR && ./update.sh   (./update.sh --check solo informa)"
  fi
  exit 0
}

# ---- questions ----
ask_graph() {
  step "Graph database" "Base de datos de grafos"
  if [ -z "$GRAPH" ]; then
    say "  1) local: a FalkorDB started next to MimirSynth (recommended if you are starting)" "  1) local: un FalkorDB que se arranca junto a MimirSynth (recomendado si empiezas)"
    say "  2) existing: a FalkorDB or Neo4j server you already run" "  2) existente: un servidor FalkorDB o Neo4j que ya tienes"
    ask "Choose" "Elige" 1
    case "$REPLY" in 2|e|existing|existente) GRAPH=existing ;; *) GRAPH=local ;; esac
  fi
  case "$GRAPH" in local|existing) ;; *) die "--graph must be local or existing" "--graph debe ser local o existing" ;; esac
  [ "$GRAPH" = existing ] || return 0
  while :; do
    if [ -z "$GTYPE" ]; then ask "Type: falkordb or neo4j" "Tipo: falkordb o neo4j" falkordb; GTYPE="$REPLY"; fi
    case "$GTYPE" in falkordb|neo4j) ;; *) [ "$TTY" = 1 ] || die "--graph-type must be falkordb or neo4j" "--graph-type debe ser falkordb o neo4j"; GTYPE=""; continue ;; esac
    if [ -z "$GHOST" ]; then ask "Host (name or IP address)" "Host (nombre o dirección IP)" ""; GHOST="$REPLY"; fi
    [ -n "$GHOST" ] || { [ "$TTY" = 1 ] || die "--graph-host is required with --graph existing" "--graph-host es obligatorio con --graph existing"; continue; }
    local dport=6379; [ "$GTYPE" = neo4j ] && dport=7687
    if [ -z "$GPORT" ]; then ask "Port" "Puerto" "$dport"; GPORT="$REPLY"; fi
    case "$GPORT" in ""|*[!0-9]*) [ "$TTY" = 1 ] || die "--graph-port must be a number" "--graph-port debe ser un número"; GPORT=""; continue ;; esac
    if [ "$TTY" = 1 ] && [ -z "$GUSER" ]; then
      if [ "$GTYPE" = neo4j ]; then ask "User" "Usuario" neo4j; else ask "User (empty if it has none)" "Usuario (vacío si no tiene)" ""; fi
      GUSER="$REPLY"
    fi
    [ "$GTYPE" != neo4j ] || [ -n "$GUSER" ] || GUSER=neo4j
    if [ "$TTY" = 1 ] && [ -z "$GPASS" ]; then ask_secret "Password (empty if it has none)" "Contraseña (vacía si no tiene)"; GPASS="$REPLY"; fi
    if [ "$GTYPE" = neo4j ] && [ "$TTY" = 1 ] && [ -z "$GDB" ]; then ask "Database (empty: the server's default)" "Base de datos (vacío: la predeterminada del servidor)" ""; GDB="$REPLY"; fi
    say "Checking that $GHOST:$GPORT answers..." "Comprobando que $GHOST:$GPORT responde..."
    if tcp_check "$GHOST" "$GPORT"; then say "It answers." "Responde."; break; fi
    warn "nothing answers at $GHOST:$GPORT" "nada responde en $GHOST:$GPORT"
    if [ "$SKIP_GRAPH_CHECK" = 1 ]; then break; fi
    [ "$TTY" = 1 ] || die "check the address, or add --skip-graph-check" "revisa la dirección, o añade --skip-graph-check"
    if yesno "Enter the values again?" "¿Volver a introducir los datos?" y; then GTYPE=""; GHOST=""; GPORT=""; GUSER=""; GPASS=""; GDB=""; continue; fi
    yesno "Continue anyway?" "¿Continuar de todos modos?" n || die "cancelled" "cancelado"
    break
  done
  # Inside the container, localhost is the container itself: the host is host.docker.internal (the compose file maps it on Linux).
  CHOST="$GHOST"
  case "$GHOST" in localhost|127.0.0.1|::1)
    CHOST="host.docker.internal"
    say "MimirSynth will reach it as host.docker.internal. On Linux the server must listen on an address the containers reach, not only on 127.0.0.1." \
        "MimirSynth llegará a él como host.docker.internal. En Linux el servidor debe escuchar en una dirección que alcancen los contenedores, no solo en 127.0.0.1." ;;
  esac
}

ask_ollama() {
  step "Embeddings" "Embeddings"
  local host_ollama=0
  if curl -fsS --max-time 2 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then host_ollama=1; fi
  if [ -z "$OLLAMA" ]; then
    if [ "$host_ollama" = 1 ]; then
      say "Ollama is already running on this computer: MimirSynth will use it (http://host.docker.internal:11434/v1)." \
          "Ollama ya está en marcha en este ordenador: MimirSynth lo usará (http://host.docker.internal:11434/v1)."
      if yesno "Start a bundled Ollama anyway?" "¿Arrancar de todos modos un Ollama incluido?" n; then OLLAMA=1; else OLLAMA=0; fi
    else
      say "MimirSynth needs an embedding model to search its memory. A bundled Ollama runs it on this computer's CPU (the image is a download of about 3.5 GB, the model about 300 MB). Without it, configure a provider in the setup wizard." \
          "MimirSynth necesita un modelo de embeddings para buscar en su memoria. Un Ollama incluido lo ejecuta en la CPU de este ordenador (la imagen es una descarga de unos 3,5 GB, el modelo unos 300 MB). Sin él, configura un proveedor en el asistente."
      if [ "$TTY" = 1 ] && yesno "Start a bundled Ollama?" "¿Arrancar un Ollama incluido?" y; then OLLAMA=1; else OLLAMA=0; fi
    fi
  fi
  if [ "$OLLAMA" = 0 ] && [ "$host_ollama" = 1 ]; then
    curl -fsS --max-time 2 http://127.0.0.1:11434/api/tags 2>/dev/null | grep -q "\"$EMBED_MODEL" || \
      warn "the Ollama on this computer does not have $EMBED_MODEL: run 'ollama pull $EMBED_MODEL'" "el Ollama de este ordenador no tiene $EMBED_MODEL: ejecuta 'ollama pull $EMBED_MODEL'"
    if [ "$OS" = Linux ] && [ "$WSL" = 0 ]; then
      say "On Linux, Ollama must listen on all interfaces for the container to reach it (OLLAMA_HOST=0.0.0.0): see Preparing Ollama in docs/INSTALL.md." \
          "En Linux, Ollama debe escuchar en todas las interfaces para que el contenedor llegue a él (OLLAMA_HOST=0.0.0.0): ver Preparar Ollama en docs/es/INSTALL.md."
    fi
  fi
}

pick_port() {
  if [ -n "$PORT" ]; then
    port_busy "$PORT" && die "port $PORT is in use: choose another with --port" "el puerto $PORT está en uso: elige otro con --port"
    return 0
  fi
  PORT=8000
  while port_busy "$PORT"; do PORT=$((PORT + 1)); [ "$PORT" -lt 8100 ] || die "no free port between 8000 and 8099: use --port" "no hay ningún puerto libre entre 8000 y 8099: usa --port"; done
  [ "$PORT" = 8000 ] || say "Port 8000 is in use: MimirSynth will use $PORT." "El puerto 8000 está en uso: MimirSynth usará el $PORT."
}

write_config() {
  step "Configuration" "Configuración"
  if [ -z "$VERSION" ]; then
    if [ -n "$FROM" ]; then VERSION=latest
    else
      VERSION="$(curl -fsS --max-time 15 "https://api.github.com/repos/$REPO/releases/latest" 2>/dev/null | sed -n 's/.*"tag_name": *"\([^"]*\)".*/\1/p' | head -1 || true)"
      VERSION="$(norm "${VERSION:-latest}")"
    fi
  else VERSION="$(norm "$VERSION")"; fi
  fetch docker-compose.yml docker-compose.yml || die "could not download docker-compose.yml of version $VERSION" "no se pudo descargar el docker-compose.yml de la versión $VERSION"
  (umask 077; fetch env.example .env) || die "could not download env.example of version $VERSION" "no se pudo descargar el env.example de la versión $VERSION"
  chmod 600 .env
  if [ "$OS" != Darwin ]; then
    if fetch update.sh update.sh 2>/dev/null; then chmod +x update.sh; else rm -f update.sh; fi
  fi
  local profiles=""
  [ "$GRAPH" = local ] && profiles="bundled"
  if [ "$OLLAMA" = 1 ]; then
    if grep -qE '^  ollama:' docker-compose.yml; then profiles="${profiles:+$profiles,}ollama"
    else warn "version $VERSION has no bundled Ollama: configure embeddings in the setup wizard" "la versión $VERSION no incluye Ollama: configura los embeddings en el asistente"; OLLAMA=0; fi
  fi
  setenv POSTGRES_PASSWORD "$(gen_secret)"
  setenv MIMIRSYNTH_SESSION_SECRET "$(gen_secret)"
  setenv MIMIRSYNTH_VERSION "$VERSION"
  setenv MIMIRSYNTH_PORT "$PORT"
  setenv MIMIRSYNTH_DEFAULT_LANGUAGE "$L"
  setenv COMPOSE_PROFILES "$profiles"
  [ "$OLLAMA" = 1 ] && setenv MIMIRSYNTH_EMBEDDING_BASE_URL "http://ollama:11434/v1"
  if [ "$GRAPH" = existing ]; then
    setenv MIMIRSYNTH_GRAPH_BACKEND "$GTYPE"
    if [ "$GTYPE" = falkordb ]; then
      setenv MIMIRSYNTH_FALKOR_HOST "$(env_quote "$CHOST")"
      setenv MIMIRSYNTH_FALKOR_PORT "$GPORT"
      [ -z "$GUSER" ] || setenv MIMIRSYNTH_FALKOR_USERNAME "$(env_quote "$GUSER")"
      [ -z "$GPASS" ] || setenv MIMIRSYNTH_FALKOR_PASSWORD "$(env_quote "$GPASS")"
    else
      setenv MIMIRSYNTH_NEO4J_URI "$(env_quote "bolt://$CHOST:$GPORT")"
      setenv MIMIRSYNTH_NEO4J_USER "$(env_quote "$GUSER")"
      [ -z "$GPASS" ] || setenv MIMIRSYNTH_NEO4J_PASSWORD "$(env_quote "$GPASS")"
      [ -z "$GDB" ] || setenv MIMIRSYNTH_NEO4J_DATABASE "$(env_quote "$GDB")"
    fi
  fi
  dc config -q || die "the generated configuration is not valid (docker compose config)" "la configuración generada no es válida (docker compose config)"
  say "Version $VERSION · port $PORT · profiles: ${profiles:-none} · secrets generated in $DIR/.env" \
      "Versión $VERSION · puerto $PORT · perfiles: ${profiles:-ninguno} · secretos generados en $DIR/.env"
}

# ---- after the start ----
wait_health() {  # 0: healthy; 2: it answers, but something it needs does not; 1: no answer
  local t0=$SECONDS first503="" code
  HEALTH_BODY=""
  while [ $((SECONDS - t0)) -lt "$WAIT_SECONDS" ]; do
    code="$(curl -s -o "$TMPF" -w '%{http_code}' --max-time 5 "http://127.0.0.1:$PORT/api/health" 2>/dev/null || true)"
    HEALTH_BODY="$(cat "$TMPF" 2>/dev/null || true)"
    case "$code" in
      200) return 0 ;;
      503) [ -n "$first503" ] || first503=$SECONDS; [ $((SECONDS - first503)) -lt 60 ] || return 2 ;;
    esac
    sleep 3
  done
  [ -z "$first503" ] || return 2
  return 1
}

setup_code() {  # the first-start code from the log (the last one, if the container restarted)
  dc logs --no-log-prefix mimirsynth 2>/dev/null | awk '/FIRST START/ { f = 1; next } f && /^[[:space:]]+[A-Za-z0-9_-]+[[:space:]]*$/ { c = $1; f = 0 } END { if (c) print c }'
}

# HOOK(#358): full test of an existing graph database through the API. POST /api/admin/graph/test does not exist yet (#358): until
# it does, this answers 404 and only the TCP checks run (from this computer before writing .env, and from the container after the
# start). When #358 lands: decide how the endpoint is reachable during the first start (there is no administrator yet; this sends
# the first-start code as X-Setup-Code) and adjust the body to its schema. Returns 0 ok, 1 failed (REPLY has the answer), 3 not available.
graph_api_test() {
  local body code
  body="{\"backend\":$(json_str "$GTYPE"),\"host\":$(json_str "$CHOST"),\"port\":${GPORT:-0},\"user\":$(json_str "$GUSER"),\"password\":$(json_str "$GPASS"),\"database\":$(json_str "$GDB")}"
  code="$(printf '%s' "$body" | curl -s -o "$TMPF" -w '%{http_code}' --max-time 30 -X POST -H 'Content-Type: application/json' \
          -H "X-Setup-Code: ${SETUP_CODE:-}" --data-binary @- "http://127.0.0.1:$PORT/api/admin/graph/test" 2>/dev/null || true)"
  REPLY="$(head -c 300 "$TMPF" 2>/dev/null || true)"
  case "$code" in 2??) return 0 ;; 401|403|404|405|"") return 3 ;; *) return 1 ;; esac
}

check_graph_from_container() {
  step "Graph database" "Base de datos de grafos"
  if dc exec -T mimirsynth python -c 'import socket, sys; socket.create_connection((sys.argv[1], int(sys.argv[2])), 5)' "$CHOST" "$GPORT" >/dev/null 2>&1; then
    say "The container reaches $CHOST:$GPORT." "El contenedor llega a $CHOST:$GPORT."
  else
    warn "the container does not reach $CHOST:$GPORT: check the address, the server's listen address and the firewall, then change .env and run 'docker compose up -d'" \
         "el contenedor no llega a $CHOST:$GPORT: revisa la dirección, la dirección en la que escucha el servidor y el cortafuegos, cambia .env y ejecuta 'docker compose up -d'"
  fi
  local rc=0; graph_api_test || rc=$?
  case "$rc" in
    0) say "Connection test passed." "La prueba de conexión ha pasado." ;;
    1) warn "the connection test failed: $REPLY" "la prueba de conexión ha fallado: $REPLY" ;;
    *) say "The full connection test (credentials, version, permissions) runs in the setup wizard." "La prueba completa de conexión (credenciales, versión, permisos) se hace en el asistente." ;;
  esac
}

open_browser() {
  [ "$BROWSER" = 1 ] || return 0
  if [ "$OS" = Darwin ]; then open "$1" >/dev/null 2>&1 || true
  elif [ "$WSL" = 1 ]; then { command -v wslview >/dev/null && wslview "$1"; } >/dev/null 2>&1 || cmd.exe /c start "" "$1" >/dev/null 2>&1 || true
  elif [ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ] && command -v xdg-open >/dev/null; then xdg-open "$1" >/dev/null 2>&1 & fi
}

# ================================================================================================================================
# Everything runs from main, called on the last line: a download cut short (curl | bash) runs nothing instead of half a script.
main() {
parse_args "$@"
setup_lang
setup_tty
trap 'say "The installer stopped (line $LINENO). Nothing was removed: fix the cause and run it again." "El instalador se ha detenido (línea $LINENO). No se ha borrado nada: corrige la causa y vuelve a ejecutarlo." >&2' ERR
say "MimirSynth installer" "Instalador de MimirSynth"
command -v curl >/dev/null || die "curl is required" "hace falta curl"
if [ -n "$FROM" ]; then FROM="$(cd "$FROM" && pwd)"; fi
check_docker

if [ -z "$DIR" ]; then
  if [ -f docker-compose.yml ] && [ -f .env ] && grep -q mimirsynth docker-compose.yml; then DIR="$PWD"; else DIR="$HOME/mimirsynth"; fi
fi
mkdir -p "$DIR"; DIR="$(cd "$DIR" && pwd)"; cd "$DIR"
TMPF="$(mktemp)"; trap 'rm -f "$TMPF"' EXIT

if [ -f docker-compose.yml ] && [ -f .env ]; then
  if [ -n "$(dc ps -aq mimirsynth 2>/dev/null || true)" ]; then existing_install; fi
  step "Configuration" "Configuración"
  say "$DIR already has a configuration that has not been started: using it as it is." "$DIR ya tiene una configuración que no se ha arrancado: se usa tal cual."
  PORT="$(envget MIMIRSYNTH_PORT .env)"; PORT="${PORT:-8000}"
  case ",$(envget COMPOSE_PROFILES .env)," in *,ollama,*) OLLAMA=1 ;; *) OLLAMA=0 ;; esac
  if [ -n "$(envget MIMIRSYNTH_NEO4J_URI .env)" ] || [ "$(envget MIMIRSYNTH_FALKOR_HOST .env)" != falkordb ]; then GRAPH=existing; else GRAPH=local; fi
  GTYPE="$(envget MIMIRSYNTH_GRAPH_BACKEND .env)"; GTYPE="${GTYPE:-falkordb}"
  if [ "$GTYPE" = neo4j ]; then
    CHOST="$(envget MIMIRSYNTH_NEO4J_URI .env)"; CHOST="${CHOST#*://}"; GPORT="${CHOST##*:}"; CHOST="${CHOST%:*}"
  else
    CHOST="$(envget MIMIRSYNTH_FALKOR_HOST .env)"; GPORT="$(envget MIMIRSYNTH_FALKOR_PORT .env)"
  fi
  GHOST="$CHOST"
elif [ -f docker-compose.yml ] || [ -f .env ]; then
  die "$DIR has only one of docker-compose.yml and .env: finish or remove that installation, or choose another folder with --dir" \
      "$DIR solo tiene uno de docker-compose.yml y .env: termina o borra esa instalación, o elige otra carpeta con --dir"
else
  say "It will be installed in $DIR." "Se instalará en $DIR."
  ask_graph
  ask_ollama
  pick_port
  write_config
fi

if [ "$START" = 0 ]; then
  say "Configuration written. To start it: cd $DIR && docker compose up -d   (or run this installer again)" \
      "Configuración escrita. Para arrancarla: cd $DIR && docker compose up -d   (o vuelve a ejecutar este instalador)"
  exit 0
fi

step "Start" "Arranque"
say "Downloading the images and starting the services (the first time takes a few minutes)..." "Descargando las imágenes y arrancando los servicios (la primera vez tarda unos minutos)..."
dc up -d

if [ "$OLLAMA" = 1 ]; then
  step "Embedding model" "Modelo de embeddings"
  i=0; until dc exec -T ollama ollama list >/dev/null 2>&1; do i=$((i + 1)); [ "$i" -lt 60 ] || break; sleep 2; done
  if dc exec -T ollama ollama pull "$EMBED_MODEL"; then say "$EMBED_MODEL is ready." "$EMBED_MODEL está listo."
  else warn "could not download $EMBED_MODEL: run 'docker compose exec ollama ollama pull $EMBED_MODEL' in $DIR" "no se pudo descargar $EMBED_MODEL: ejecuta 'docker compose exec ollama ollama pull $EMBED_MODEL' en $DIR"; fi
fi

step "Waiting for MimirSynth" "Esperando a MimirSynth"
rc=0; wait_health || rc=$?
case "$rc" in
  0) say "It answers and reaches its databases." "Responde y llega a sus bases de datos." ;;
  2) warn "it answers, but does not reach everything it needs: $HEALTH_BODY" "responde, pero no llega a todo lo que necesita: $HEALTH_BODY" ;;
  *) dc logs --tail 30 mimirsynth >&2 || true
     die "it did not answer within ${WAIT_SECONDS}s: see 'docker compose logs mimirsynth' in $DIR" "no ha respondido en ${WAIT_SECONDS}s: mira 'docker compose logs mimirsynth' en $DIR" ;;
esac

SETUP_CODE=""
if curl -fsS --max-time 5 "http://127.0.0.1:$PORT/api/auth/options" 2>/dev/null | grep -q '"setup":true'; then
  i=0; until [ -n "$SETUP_CODE" ] || [ "$i" -ge 10 ]; do SETUP_CODE="$(setup_code)"; [ -n "$SETUP_CODE" ] || sleep 1; i=$((i + 1)); done
fi
if [ "$GRAPH" = existing ]; then check_graph_from_container; fi

URL="http://localhost:$PORT"
step "Ready" "Listo"
say "  Open:             $URL" "  Abre:             $URL"
if [ -n "$SETUP_CODE" ]; then
  say "  First-start code: $SETUP_CODE" "  Código de inicio: $SETUP_CODE"
  say "  In the browser, enter the code and create the administrator account; the wizard then guides you through the rest." \
      "  En el navegador, introduce el código y crea la cuenta de administrador; el asistente te guía después en el resto."
else
  say "  Sign in with your administrator account." "  Entra con tu cuenta de administrador."
fi
if [ -n "${SSH_CONNECTION:-}" ] && [ "$OS" = Linux ]; then
  ip="$(hostname -I 2>/dev/null | awk '{print $1}' || true)"
  [ -z "$ip" ] || say "  From another computer: http://$ip:$PORT (put HTTPS in front before exposing it to the Internet)" \
                      "  Desde otro ordenador: http://$ip:$PORT (pon HTTPS delante antes de exponerlo a Internet)"
fi
say "  Folder:           $DIR  (docker compose commands run here; upgrade with ./update.sh)" \
    "  Carpeta:          $DIR  (los comandos de docker compose se ejecutan aquí; actualiza con ./update.sh)"
[ "$OS" != Darwin ] || say "  update.sh is for Linux: on macOS, upgrade as described in docs/INSTALL.md." "  update.sh es para Linux: en macOS, actualiza como se explica en docs/es/INSTALL.md."
open_browser "$URL"
}

main "$@"
