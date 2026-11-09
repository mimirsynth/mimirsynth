#!/usr/bin/env bash
# MimirSynth installer for Linux and macOS (Docker Desktop). On Windows, use install.ps1.
#   curl -fsSL https://github.com/MimirSynth/mimirsynth/releases/latest/download/install.sh | bash
# It checks Docker, asks a few questions, writes docker-compose.yml and .env (with generated secrets), starts the stack, waits
# until it answers and opens the browser on the first-start wizard. Run it again at any time: it detects an existing install and
# offers update.sh instead. Without a terminal, or with --yes, it asks nothing and uses the flags and the defaults (see --help).
set -Eeuo pipefail

REPO="MimirSynth/mimirsynth"
RELEASE="dev"   # the release this installer belongs to: release.yml writes it here ("dev" is a copy from the repository)
EMBED_MODEL="nomic-embed-text"
WAIT_SECONDS="${WAIT_SECONDS:-300}"
DIR=""; VERSION=""; PORT=""; FROM=""; YES=0; LANG_OPT=""
GRAPH=""; GTYPE=""; GHOST=""; GPORT=""; GUSER=""; GDB=""; GTLS=""; GSCHEME=""; GPASS="${MIMIRSYNTH_GRAPH_PASSWORD:-}"; SKIP_GRAPH_CHECK=0
PROBED=0; WROTE=0  # PROBED: the existing graph database passed the full test before the start; WROTE: this run wrote the configuration
GRAPH_DOWN=0       # after the start, /api/health said the graph database does not answer
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
  --graph-tls              the existing Neo4j asks for TLS (neo4j+s://, as Neo4j Aura does)
  --graph-scheme neo4j|bolt   how to reach Neo4j: neo4j (default) routes, as a cluster such as Neo4j Aura needs, and works with a
                           single server too; bolt only connects directly to that one server. With no --graph-database, the
                           user's default database is used (on Neo4j Aura, the instance's own), and the test names it
  --skip-graph-check       go on even if the existing graph database does not answer or does not pass the connection
                           test (address, credentials, version and write permission, run before anything starts)
  --ollama | --no-ollama   start a bundled Ollama for embeddings and download nomic-embed-text (default without
                           questions: no)
  --install-docker         on Linux, install Docker with its official script if it is missing
  --upgrade                if MimirSynth is already installed in DIR, run its update.sh without asking (with --version, to
                           that release); it never goes down to the latest stable release from a newer one or a candidate
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
    --graph-tls) GTLS=1 ;;
    --graph-scheme) GSCHEME="${2:-}"; shift ;;
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
# Versions compare as SemVer 2.0 (#403): 0.15.0 > 0.15.0-rc.2 > 0.15.0-rc.1 > 0.14.0, a pre-release below its final release.
# Names such as "latest" or "ci" are not versions: nothing is compared with them.
SEMVER_RE='^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(-[0-9A-Za-z-]+(\.[0-9A-Za-z-]+)*)?(\+[0-9A-Za-z.-]+)?$'
semver() { [[ "$(norm "$1")" =~ $SEMVER_RE ]]; }
vercmp() {  # prints -1, 0 or 1 when $1 is older than, the same as or newer than $2 (both semver); what follows "+" does not count
  local a b x y i n; local -a A B
  a="$(norm "$1")"; b="$(norm "$2")"; a="${a%%+*}"; b="${b%%+*}"
  IFS=. read -r -a A <<<"${a%%-*}"; IFS=. read -r -a B <<<"${b%%-*}"
  for i in 0 1 2; do
    if [ "${A[i]}" -gt "${B[i]}" ]; then echo 1; return; elif [ "${A[i]}" -lt "${B[i]}" ]; then echo -1; return; fi
  done
  if [[ $a != *-* ]]; then if [[ $b != *-* ]]; then echo 0; else echo 1; fi; return; fi
  if [[ $b != *-* ]]; then echo -1; return; fi
  IFS=. read -r -a A <<<"${a#*-}"; IFS=. read -r -a B <<<"${b#*-}"
  n=${#A[@]}; [ "${#B[@]}" -ge "$n" ] || n=${#B[@]}
  for ((i = 0; i < n; i++)); do   # identifier by identifier: numbers as numbers and below words, words in ASCII order
    x="${A[i]}"; y="${B[i]}"; [ "$x" != "$y" ] || continue
    if [[ $x =~ ^[0-9]+$ && $y =~ ^[0-9]+$ ]]; then if [ "$x" -gt "$y" ]; then echo 1; else echo -1; fi
    elif [[ $x =~ ^[0-9]+$ ]]; then echo -1
    elif [[ $y =~ ^[0-9]+$ ]]; then echo 1
    elif [ "$(printf '%s\n%s\n' "$x" "$y" | LC_ALL=C sort | head -n 1)" = "$x" ]; then echo -1
    else echo 1; fi
    return
  done
  if [ "${#A[@]}" -gt "${#B[@]}" ]; then echo 1; elif [ "${#A[@]}" -lt "${#B[@]}" ]; then echo -1; else echo 0; fi
}
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
setenv() {  # KEY VALUE: replace the KEY= line (or its commented example) in .env, or append it; .env stays readable only by you
  (umask 077; K="$1" V="$2" awk 'BEGIN { k = ENVIRON["K"]; v = ENVIRON["V"]; done = 0 }
    !done && ($0 ~ "^" k "=" || $0 ~ "^# ?" k "=") { print k "=" v; done = 1; next }
    { print }
    END { if (!done) print k "=" v }' .env > .env.tmp) && mv .env.tmp .env && chmod 600 .env
}
json_str() {  # a JSON string literal
  local s="$1"; s="${s//\\/\\\\}"; s="${s//\"/\\\"}"; s="${s//$'\n'/\\n}"; s="${s//$'\r'/\\r}"; s="${s//$'\t'/\\t}"; printf '"%s"' "$s"
}

# ---- apt's locks (#418) ----
# Just after a machine starts, its own updates (apt-daily, unattended-upgrades) or cloud-init's packages hold apt's locks for a few
# minutes, and get.docker.com's first apt-get then fails («Unable to lock directory /var/lib/apt/lists/»). apt and dpkg take POSIX
# (fcntl) locks, which flock(1) neither sees nor waits for, and which /proc/locks lists to every user: finding them needs neither
# root nor fuser or lsof, missing from a minimal Debian or Ubuntu. The wait is at most APT_WAIT_SECONDS in all, retries included.
APT_LOCKS="/var/lib/dpkg/lock-frontend /var/lib/dpkg/lock /var/lib/apt/lists/lock /var/cache/apt/archives/lock"
APT_WAIT_SECONDS="${APT_WAIT_SECONDS:-300}"
case "$APT_WAIT_SECONDS" in ""|*[!0-9]*) APT_WAIT_SECONDS=300 ;; esac
APT_DEADLINE=""; APT_HELD=""
apt_holder() {  # 0 while one of apt's locks is held, with APT_HELD «the lock, held by the program (PID n)»; 1 when all are free
  local f di dev ino key pid what
  for f in $APT_LOCKS; do
    [ -e "$f" ] || continue
    pid=""
    if [ -r /proc/locks ]; then
      di="$(stat -c '%d %i' "$f" 2>/dev/null)" || continue
      dev="${di% *}"; ino="${di#* }"
      # /proc/locks names the file as major:minor:inode, the device split as the kernel does; by its inode alone when no device
      # matches (a btrfs subvolume reports another device). Waiters ("->") hold nothing.
      key="$(printf '%02x:%02x:%s' $(( (dev >> 8) & 0xfff )) $(( (dev & 0xff) | ((dev >> 12) & 0xfff00) )) "$ino")"
      pid="$(awk -v k="$key" -v i="$ino" '$2 == "POSIX" || $2 == "OFDLCK" {
               if ($6 == k) { exact = $5; exit }
               split($6, a, ":"); if (a[3] == i && loose == "") loose = $5 }
             END { print (exact != "" ? exact : loose) }' /proc/locks 2>/dev/null || true)"
    elif command -v fuser >/dev/null 2>&1; then  # without /proc/locks: whoever has the file open (sudo -n: never a password prompt here)
      pid="$(${SUDO:+$SUDO -n} fuser "$f" 2>/dev/null | awk '{ print $1 }' || true)"
    fi
    [ -n "$pid" ] || continue
    what=""
    if [ "$pid" -gt 0 ] 2>/dev/null; then
      what="$(tr -s '\000-\037' ' ' <"/proc/$pid/cmdline" 2>/dev/null | cut -c1-60 || true)"; what="${what% }"   # one line
      [ -n "$what" ] || what="$(cat "/proc/$pid/comm" 2>/dev/null || true)"
    fi
    if [ -z "$what" ]; then
      if [ "$L" = es ]; then APT_HELD="$f, retenido por otro proceso"; else APT_HELD="$f, held by another process"; fi
    elif [ "$L" = es ]; then APT_HELD="$f, retenido por $what (PID $pid)"
    else APT_HELD="$f, held by $what (PID $pid)"; fi
    return 0
  done
  return 1
}
apt_wait() {  # until apt's locks have been free for a few seconds: 0; 1 once the APT_WAIT_SECONDS are spent (APT_HELD says why)
  command -v dpkg >/dev/null 2>&1 || return 0   # not a Debian or Ubuntu: get.docker.com uses another package manager
  [ -n "$APT_DEADLINE" ] || APT_DEADLINE=$((SECONDS + APT_WAIT_SECONDS))
  local free=0 told="" waited
  # free three times in a row, two seconds apart: apt-daily, unattended-upgrades and cloud-init run apt more than once
  while [ "$free" -lt 3 ]; do
    if apt_holder; then
      free=0; waited=$((SECONDS + APT_WAIT_SECONDS - APT_DEADLINE))
      if [ -z "$told" ]; then
        say "Waiting for apt, which another program is using: $APT_HELD. Just after a machine starts, its own updates (apt-daily, unattended-upgrades) or cloud-init usually hold it for a few minutes. Waiting up to $((APT_DEADLINE - SECONDS))s..." \
            "Esperando a apt, que está usando otro programa: $APT_HELD. Justo después de arrancar una máquina, sus propias actualizaciones (apt-daily, unattended-upgrades) o cloud-init suelen tenerlo unos minutos. Se espera hasta $((APT_DEADLINE - SECONDS)) s..."
        told=$SECONDS
      elif [ $((SECONDS - told)) -ge 30 ]; then
        say "Still waiting for apt (${waited}s): $APT_HELD" "Se sigue esperando a apt (${waited} s): $APT_HELD"
        told=$SECONDS
      fi
      [ "$SECONDS" -lt "$APT_DEADLINE" ] || return 1
    else
      free=$((free + 1))
    fi
    [ "$free" -ge 3 ] || sleep 2
  done
  [ -z "$told" ] || say "apt is free again." "apt vuelve a estar libre."
}

# Docker's official script, after apt's locks are free. Its apt-get calls wait for dpkg's lock themselves for the rest of the time
# (DPkg::Lock::Timeout, through APT_CONFIG, which apt reads before its own configuration); apt-get update has no such wait for the
# lists lock, so a run that fails on an apt lock (a program that took it in the meantime) waits again and tries again, twice at most.
install_docker() {
  local tmp try=1 left
  apt_wait || apt_gave_up
  tmp="$(mktemp -d)"
  if ! curl -fsSL --retry 3 --max-time 120 https://get.docker.com -o "$tmp/get-docker.sh"; then
    rm -rf "$tmp"
    die "could not download Docker's installation script (https://get.docker.com)" "no se pudo descargar el script de instalación de Docker (https://get.docker.com)"
  fi
  while :; do
    left=60; [ -z "$APT_DEADLINE" ] || [ $((APT_DEADLINE - SECONDS)) -le 60 ] || left=$((APT_DEADLINE - SECONDS))
    printf 'DPkg::Lock::Timeout "%s";\n' "$left" >"$tmp/apt.conf"
    if $SUDO env APT_CONFIG="$tmp/apt.conf" sh "$tmp/get-docker.sh" </dev/null 2>&1 | tee "$tmp/log"; then break; fi
    if [ "$try" -lt 3 ] && grep -qE '^E: .*(/var/lib/dpkg/lock|/var/lib/apt/lists/|/var/cache/apt/archives/lock)' "$tmp/log"; then
      try=$((try + 1))
      warn "another program took apt's lock while Docker was being installed: waiting for it and trying again ($try/3)" \
           "otro programa ha tomado el bloqueo de apt mientras se instalaba Docker: se espera y se vuelve a intentar ($try/3)"
      apt_wait && continue
      rm -rf "$tmp"; apt_gave_up
    fi
    rm -rf "$tmp"
    die "Docker's installation script (get.docker.com) failed: see its output above. Docker was not installed and this installer wrote nothing yet: fix the cause and run it again." \
        "El script de instalación de Docker (get.docker.com) ha fallado: mira su salida más arriba. No se ha instalado Docker y este instalador aún no ha escrito nada: corrige la causa y vuelve a ejecutarlo."
  done
  rm -rf "$tmp"
}
apt_gave_up() {
  die "apt is still in use after ${APT_WAIT_SECONDS}s ($APT_HELD), so Docker was not installed and this installer wrote nothing yet. When that program ends, run the installer again; to wait longer, set APT_WAIT_SECONDS (e.g. curl ... | APT_WAIT_SECONDS=900 bash)." \
      "apt sigue en uso tras ${APT_WAIT_SECONDS} s ($APT_HELD), así que no se ha instalado Docker y este instalador aún no ha escrito nada. Cuando ese programa termine, vuelve a ejecutar el instalador; para esperar más, define APT_WAIT_SECONDS (p. ej. curl ... | APT_WAIT_SECONDS=900 bash)."
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
      install_docker
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
# It always gets the update.sh of this installer's release (#413), checked against that release's SHA256SUMS: it used to be
# downloaded only when missing, so a fixed update.sh never reached an existing install. Never an older one than the update.sh
# already there or than the installed version: update.sh then brings itself up to the release it updates to.
refresh_updater() {
  local rel="$RELEASE" floor new sums want got url
  if [ -n "$FROM" ]; then fetch update.sh update.sh && chmod +x update.sh && return 0; die "could not copy update.sh from $FROM" "no se pudo copiar update.sh de $FROM"; fi
  semver "$rel" || rel="$VERSION"
  semver "$rel" || rel="$(curl -fsS --max-time 15 "https://api.github.com/repos/$REPO/releases/latest" 2>/dev/null | sed -n 's/.*"tag_name": *"\([^"]*\)".*/\1/p' | head -1 || true)"
  rel="$(norm "$rel")"
  if ! semver "$rel"; then
    [ -f update.sh ] || die "could not find the latest release to download update.sh (no network?)" "no se pudo saber la última versión para descargar update.sh (¿sin red?)"
    warn "could not find the latest release: keeping the update.sh already there" "no se pudo saber la última versión: se mantiene el update.sh que ya hay"
    return 0
  fi
  if [ -f update.sh ]; then
    for floor in "$(envget MIMIRSYNTH_VERSION .env)" "$(sed -n 's/^RELEASE="\([^"]*\)".*/\1/p' update.sh | head -1)"; do
      if semver "$floor" && [ "$(vercmp "$rel" "$floor")" = -1 ]; then
        say "update.sh: the one already there is kept, newer than release $rel's (it brings itself up to date when it runs)." \
            "update.sh: se mantiene el que ya hay, más reciente que el de la versión $rel (se pone al día solo al ejecutarse)."
        return 0
      fi
    done
  fi
  url="https://github.com/$REPO/releases/download/v$rel"
  if ! new="$(mktemp ./.update.sh.XXXXXX 2>/dev/null)"; then
    [ -f update.sh ] || die "cannot write update.sh in $DIR" "no se puede escribir update.sh en $DIR"
    warn "cannot write in $DIR: keeping the update.sh already there" "no se puede escribir en $DIR: se mantiene el update.sh que ya hay"
    return 0
  fi
  sums="$(mktemp)"
  if curl -fsSL --retry 3 --max-time 120 "$url/update.sh" -o "$new" && curl -fsSL --retry 3 --max-time 60 "$url/SHA256SUMS" -o "$sums"; then
    want="$(awk '$2 == "update.sh" || $2 == "*update.sh" { print $1; exit }' "$sums")"; got="$(sha256sum "$new" | cut -d' ' -f1)"
    if [ -n "$want" ] && [ "$want" = "$got" ]; then
      rm -f "$sums"; chmod 755 "$new"; mv -f "$new" update.sh
      say "update.sh: the one of release $rel (checked against its SHA256SUMS)." "update.sh: el de la versión $rel (comprobado con su SHA256SUMS)."
      return 0
    fi
    warn "the update.sh of release $rel does not match its SHA256SUMS: it was NOT used" "el update.sh de la versión $rel no coincide con su SHA256SUMS: NO se ha usado"
  else
    warn "could not download the update.sh of release $rel" "no se pudo descargar el update.sh de la versión $rel"
  fi
  rm -f "$new" "$sums"
  [ -f update.sh ] || die "could not download update.sh" "no se pudo descargar update.sh"
  say "Keeping the update.sh already there." "Se mantiene el update.sh que ya hay."
}
existing_install() {
  step "Existing installation" "Instalación existente"
  say "MimirSynth is already installed in $DIR." "MimirSynth ya está instalado en $DIR."
  if [ "$OS" = Darwin ]; then  # update.sh needs GNU tools (flock, GNU sed and stat)
    say "To upgrade it: back up, then run 'docker compose pull && docker compose up -d' in that folder (see Upgrading in docs/INSTALL.md)." \
        "Para actualizarlo: haz una copia de seguridad y ejecuta 'docker compose pull && docker compose up -d' en esa carpeta (ver Actualizar en docs/es/INSTALL.md)."
    exit 0
  fi
  refresh_updater
  local run=0
  if [ "$UPGRADE" = 1 ]; then run=1
  elif [ "$TTY" = 1 ] && yesno "Upgrade it now with update.sh (backup, update and check)?" "¿Actualizarlo ahora con update.sh (copia de seguridad, actualización y comprobación)?" y; then run=1; fi
  if [ "$run" = 1 ]; then
    local lang_env="${LANG:-}"; [ "$L" = es ] && lang_env="es_ES.UTF-8"
    local args=(--yes); [ -z "$VERSION" ] || args+=(--version "$VERSION")   # update.sh decides; it never goes down on its own (#403)
    if [ "$DOCKER" = docker ]; then LANG="$lang_env" ./update.sh "${args[@]}"; else sudo env LANG="$lang_env" ./update.sh "${args[@]}"; fi
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
    if [ "$GTYPE" = neo4j ] && [ "$TTY" = 1 ] && [ -z "$GDB" ]; then
      ask "Database (empty: the user's default, which the test finds; on Neo4j Aura, the instance's own)" \
          "Base de datos (vacío: la predeterminada del usuario, que la prueba encuentra; en Neo4j Aura, la de la instancia)" ""; GDB="$REPLY"
    fi
    if [ "$GTYPE" = neo4j ] && [ -z "$GTLS" ]; then
      if yesno "Does it ask for TLS (neo4j+s://, as Neo4j Aura does)?" "¿Pide TLS (neo4j+s://, como Neo4j Aura)?" n; then GTLS=1; else GTLS=0; fi
    fi
    case "${GSCHEME:-neo4j}" in neo4j|bolt) ;; *) die "--graph-scheme must be neo4j or bolt" "--graph-scheme debe ser neo4j o bolt" ;; esac
    # The environment has no TLS setting for FalkorDB: that connection is saved in Administration > Graph database instead.
    [ "$GTYPE" != falkordb ] || [ "${GTLS:-0}" = 0 ] || die "a FalkorDB with TLS is configured in Administration > Graph database: install with --graph local and change it there" \
      "un FalkorDB con TLS se configura en Administración > Base de datos de grafos: instala con --graph local y cámbialo allí"
    say "Checking that $GHOST:$GPORT answers..." "Comprobando que $GHOST:$GPORT responde..."
    if tcp_check "$GHOST" "$GPORT"; then say "It answers." "Responde."; break; fi
    warn "nothing answers at $GHOST:$GPORT" "nada responde en $GHOST:$GPORT"
    if [ "$SKIP_GRAPH_CHECK" = 1 ]; then break; fi
    [ "$TTY" = 1 ] || die "check the address, or add --skip-graph-check" "revisa la dirección, o añade --skip-graph-check"
    if yesno "Enter the values again?" "¿Volver a introducir los datos?" y; then GTYPE=""; GHOST=""; GPORT=""; GUSER=""; GPASS=""; GDB=""; GTLS=""; GSCHEME=""; continue; fi
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
  WROTE=1
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
  write_graph_env
  dc config -q || die "the generated configuration is not valid (docker compose config)" "la configuración generada no es válida (docker compose config)"
  say "Version $VERSION · port $PORT · profiles: ${profiles:-none} · secrets generated in $DIR/.env" \
      "Versión $VERSION · puerto $PORT · perfiles: ${profiles:-ninguno} · secretos generados en $DIR/.env"
}

# ---- an existing graph database ----
GRAPH_KEYS="MIMIRSYNTH_GRAPH_BACKEND MIMIRSYNTH_FALKOR_HOST MIMIRSYNTH_FALKOR_PORT MIMIRSYNTH_FALKOR_USERNAME MIMIRSYNTH_FALKOR_PASSWORD
MIMIRSYNTH_NEO4J_URI MIMIRSYNTH_NEO4J_USER MIMIRSYNTH_NEO4J_PASSWORD MIMIRSYNTH_NEO4J_DATABASE"
unsetenv() {  # KEY: back to its commented example in .env, without the value
  (umask 077; K="$1" awk 'BEGIN { k = ENVIRON["K"] } $0 ~ "^" k "=" { print "# " k "="; next } { print }' .env > .env.tmp) && mv .env.tmp .env && chmod 600 .env
}
# The URI the test before the start tries and .env gets, the same string for both (#408): the routing scheme (neo4j://, neo4j+s://),
# which a cluster such as Neo4j Aura needs and a single server accepts too, unless --graph-scheme bolt asks for a direct connection.
neo4j_uri() {
  local scheme="${GSCHEME:-neo4j}"
  if [ "${GTLS:-0}" = 1 ]; then scheme="$scheme+s"; fi
  printf '%s://%s:%s' "$scheme" "$CHOST" "$GPORT"
}
# The environment wins over Administration > Graph database when it is set (#358): an existing database the installer was told about
# goes in .env, read-only in the interface. A local install writes none of these, so the interface can change it.
write_graph_env() {
  local k; for k in $GRAPH_KEYS; do unsetenv "$k"; done
  [ "$GRAPH" = existing ] || return 0
  setenv MIMIRSYNTH_GRAPH_BACKEND "$GTYPE"
  if [ "$GTYPE" = falkordb ]; then
    setenv MIMIRSYNTH_FALKOR_HOST "$(env_quote "$CHOST")"
    setenv MIMIRSYNTH_FALKOR_PORT "$GPORT"
    [ -z "$GUSER" ] || setenv MIMIRSYNTH_FALKOR_USERNAME "$(env_quote "$GUSER")"
    [ -z "$GPASS" ] || setenv MIMIRSYNTH_FALKOR_PASSWORD "$(env_quote "$GPASS")"
  else
    setenv MIMIRSYNTH_NEO4J_URI "$(env_quote "$(neo4j_uri)")"
    setenv MIMIRSYNTH_NEO4J_USER "$(env_quote "$GUSER")"
    [ -z "$GPASS" ] || setenv MIMIRSYNTH_NEO4J_PASSWORD "$(env_quote "$GPASS")"
    [ -z "$GDB" ] || setenv MIMIRSYNTH_NEO4J_DATABASE "$(env_quote "$GDB")"
  fi
}

# The full test, before anything starts: graphconn.probe, the same steps as POST /api/admin/graph/test (address, TLS, credentials,
# version, write permission and what the database holds), in a throwaway container of the release's own image (plain `docker run`,
# so it creates no volume or network of the project), which reaches the server as MimirSynth will. The connection goes in on stdin
# (base64 JSON, the endpoint's body), never on a command line. Exit status 3: a release without graphconn (before #358); 4: the test
# itself could not run. It prints «server version|database|graphs» or the cause; install.ps1 asks for JSON instead (ASCII only, so no
# console code page can garble the cause). Shared with install.ps1 (CI compares them): no double quotes.
PROBE_PY="import base64,json,logging,os,sys,importlib.util as u;logging.disable(50);sys.excepthook=lambda t,v,b:(print(ascii(v)),sys.stdout.flush(),os._exit(4));u.find_spec('mimirsynth.graphconn') or sys.exit(3);from mimirsynth.graphconn import probe;from mimirsynth.graphdb import Connection;b=json.loads(base64.b64decode(sys.stdin.buffer.read()));r=probe(Connection(b['backend'],b['host'],int(b.get('port') or 0),b.get('user') or '',b.get('password') or '',bool(b.get('tls')),b.get('database') or '',b.get('uri') or ''),sys.argv[1]);s=r['server'] or {};a=[' '.join(str(x) for x in (s.get('server'),s.get('version')) if x),str(s.get('database') or ''),str(len(r['graphs']))] if r['ok'] else [r['error']['message']];print(json.dumps(a) if sys.argv[2:]==['json'] else '|'.join(a));sys.exit(0 if r['ok'] else 1)"
graph_probe() {  # 0 passed (REPLY: «server version|database|graphs»), 1 failed (REPLY: the cause, in the user's language), 3 not available
  local body out img uri="" rc=0
  [ "$GTYPE" != neo4j ] || uri="$(neo4j_uri)"
  body="{\"backend\":$(json_str "$GTYPE"),\"host\":$(json_str "$CHOST"),\"port\":${GPORT:-0},\"user\":$(json_str "$GUSER"),\"password\":$(json_str "$GPASS"),\"tls\":$([ "${GTLS:-0}" = 1 ] && echo true || echo false),\"database\":$(json_str "$GDB"),\"uri\":$(json_str "$uri")}"
  img="$(dc config --images mimirsynth 2>/dev/null | grep -m 1 "/mimirsynth:" || true)"  # it lists postgres too, in no fixed order
  img="${img:-ghcr.io/mimirsynth/mimirsynth:$VERSION}"
  out="$(printf '%s' "$body" | base64 | tr -d '\n' | $DOCKER run --rm -i --add-host host.docker.internal:host-gateway --read-only --tmpfs /tmp \
           --cap-drop ALL --security-opt no-new-privileges "$img" python -c "$PROBE_PY" "$L")" || rc=$?
  REPLY="$(printf '%s' "$out" | tail -n 1)"
  case "$rc" in
    0|1|3) return "$rc" ;;
    *) warn "could not run the connection test in a container (exit status $rc): $REPLY" "no se ha podido ejecutar la prueba de conexión en un contenedor (código $rc): $REPLY"; return 3 ;;
  esac
}

abandon() {  # removes what this run wrote, so that running the installer again starts from the questions
  [ "$WROTE" = 1 ] || return 0
  rm -f docker-compose.yml .env .env.tmp update.sh
}

test_graph() {
  step "Graph database: connection test" "Base de datos de grafos: prueba de conexión"
  while :; do
    say "Testing $GTYPE at $CHOST:$GPORT from a MimirSynth container: credentials, version and write permission (the first time, the image is downloaded)..." \
        "Probando $GTYPE en $CHOST:$GPORT desde un contenedor de MimirSynth: credenciales, versión y permiso de escritura (la primera vez se descarga la imagen)..."
    local rc=0; graph_probe || rc=$?
    case "$rc" in
      0) PROBED=1
         local srv db n den="" des=""
         IFS='|' read -r srv db n <<<"$REPLY"
         if [ -n "$db" ] && [ -z "$GDB" ]; then den=", database «$db» (the user's default)"; des=", base de datos «$db» (la predeterminada del usuario)"
         elif [ -n "$db" ]; then den=", database «$db»"; des=", base de datos «$db»"; fi
         say "Connection test passed: $srv$den, $n graph(s) or partition(s) found." \
             "La prueba de conexión ha pasado: $srv$des, $n grafo(s) o partición(es) encontrados."
         return 0 ;;
      3) say "This release cannot test it before the start: it is tested once MimirSynth answers." \
             "Esta versión no puede probarla antes del arranque: se prueba cuando MimirSynth responda."
         return 0 ;;
    esac
    warn "the connection test failed: $REPLY" "la prueba de conexión ha fallado: $REPLY"
    if [ "$SKIP_GRAPH_CHECK" = 1 ]; then return 0; fi
    if [ "$TTY" = 1 ]; then
      if yesno "Enter the values again?" "¿Volver a introducir los datos?" y; then
        GTYPE=""; GHOST=""; GPORT=""; GUSER=""; GPASS=""; GDB=""; GTLS=""; GSCHEME=""
        ask_graph; write_graph_env; continue
      fi
      if yesno "Install anyway?" "¿Instalar de todos modos?" n; then return 0; fi
    fi
    abandon
    die "the graph database does not pass the connection test, so nothing was installed: fix the cause, or add --skip-graph-check" \
        "la base de datos de grafos no pasa la prueba de conexión, así que no se ha instalado nada: corrige la causa, o añade --skip-graph-check"
  done
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

# The same full test through the API (#358), of the connection in force (no body: the one in .env, with its password), for when it
# did not run before the start. While there is no administrator the endpoint takes the first-start code as X-Setup-Code. It answers
# 200 with "ok" true or false and, when false, the cause in "message"; a release without it answers 404. Returns 0 ok, 1 failed (REPLY
# has the cause), 3 not available.
graph_api_test() {
  local code
  code="$(curl -s -o "$TMPF" -w '%{http_code}' --max-time 30 -X POST -H "Accept-Language: $L" \
          -H "X-Setup-Code: ${SETUP_CODE:-}" "http://127.0.0.1:$PORT/api/admin/graph/test" 2>/dev/null || true)"
  REPLY="$(head -c 4000 "$TMPF" 2>/dev/null || true)"
  case "$code" in
    2??)
      # the answer's own "ok", its first key: every step that passed has an "ok":true of its own (#408)
      case "$REPLY" in '{"ok":true'*) return 0 ;; esac
      REPLY="$(printf '%s' "$REPLY" | sed -n 's/.*"message":"\([^"]*\)".*/\1/p')"; REPLY="${REPLY:-?}"
      return 1 ;;
    401|403|404|405|"") return 3 ;;
    *) REPLY="$(printf '%s' "$REPLY" | head -c 300)"; return 1 ;;
  esac
}

health_graph_ok() {  # /api/health says the instance reaches its graph database (a few tries: the backend connects on demand)
  local i
  for i in 1 2 3; do
    curl -s -o "$TMPF" --max-time 10 "http://127.0.0.1:$PORT/api/health" 2>/dev/null || true
    HEALTH_BODY="$(cat "$TMPF" 2>/dev/null || true)"
    case "$HEALTH_BODY" in *'"graph":true'*) return 0 ;; esac
    [ "$i" = 3 ] || sleep 3
  done
  return 1
}

# Returns 1 when the running instance cannot use the existing graph database: the container does not reach it, the test through the
# API fails, or /api/health said the graph does not answer and still says so after a test that passes.
check_graph_from_container() {
  step "Graph database" "Base de datos de grafos"
  local bad=0
  if dc exec -T mimirsynth python -c 'import socket, sys; socket.create_connection((sys.argv[1], int(sys.argv[2])), 5)' "$CHOST" "$GPORT" >/dev/null 2>&1; then
    say "The container reaches $CHOST:$GPORT." "El contenedor llega a $CHOST:$GPORT."
  else
    warn "the container does not reach $CHOST:$GPORT: check the address, the server's listen address and the firewall" \
         "el contenedor no llega a $CHOST:$GPORT: revisa la dirección, la dirección en la que escucha el servidor y el cortafuegos"
    bad=1
  fi
  local rc=0; graph_api_test || rc=$?
  case "$rc" in
    0) say "Connection test passed." "La prueba de conexión ha pasado."; bad=0
       if [ "$GRAPH_DOWN" = 1 ] && ! health_graph_ok; then
         warn "the connection test passes, but MimirSynth still does not reach the graph database: $HEALTH_BODY" \
              "la prueba de conexión pasa, pero MimirSynth sigue sin llegar a la base de datos de grafos: $HEALTH_BODY"
         bad=1
       fi ;;
    1) warn "the connection test failed: $REPLY" "la prueba de conexión ha fallado: $REPLY"; bad=1 ;;
    *) say "The full connection test (credentials, version, permissions) runs in the setup wizard." "La prueba completa de conexión (credenciales, versión, permisos) se hace en el asistente."
       [ "$GRAPH_DOWN" = 0 ] || bad=1 ;;
  esac
  return "$bad"
}

# MimirSynth is running, but without its graph database nothing works: the run fails (#408), unless --skip-graph-check.
graph_unusable() {
  if [ "$SKIP_GRAPH_CHECK" = 1 ]; then
    warn "MimirSynth is running, but cannot use the graph database until the connection works: fix it in .env and run 'docker compose up -d' in $DIR" \
         "MimirSynth está en marcha, pero no puede usar la base de datos de grafos hasta que la conexión funcione: corrígela en .env y ejecuta 'docker compose up -d' en $DIR"
    return 0
  fi
  die "MimirSynth is running in $DIR, but cannot use the graph database until the connection works: fix it in .env (MIMIRSYNTH_NEO4J_* or MIMIRSYNTH_FALKOR_*) and run 'docker compose up -d' there (or add --skip-graph-check)" \
      "MimirSynth está en marcha en $DIR, pero no puede usar la base de datos de grafos hasta que la conexión funcione: corrígela en .env (MIMIRSYNTH_NEO4J_* o MIMIRSYNTH_FALKOR_*) y ejecuta allí 'docker compose up -d' (o añade --skip-graph-check)"
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
  CHOST="$(envget MIMIRSYNTH_FALKOR_HOST .env)"  # a local install does not write it
  if [ -n "$(envget MIMIRSYNTH_NEO4J_URI .env)" ] || { [ -n "$CHOST" ] && [ "$CHOST" != falkordb ]; }; then GRAPH=existing; else GRAPH=local; fi
  GTYPE="$(envget MIMIRSYNTH_GRAPH_BACKEND .env)"; GTYPE="${GTYPE:-falkordb}"
  if [ "$GTYPE" = neo4j ]; then
    CHOST="$(envget MIMIRSYNTH_NEO4J_URI .env)"; CHOST="${CHOST#*://}"; GPORT="${CHOST##*:}"; CHOST="${CHOST%:*}"
    GPORT="${GPORT:-7687}"; case "$GPORT" in *[!0-9]*) GPORT=7687 ;; esac
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
  if [ "$GRAPH" = existing ]; then test_graph; fi
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
  2) warn "it answers, but does not reach everything it needs: $HEALTH_BODY" "responde, pero no llega a todo lo que necesita: $HEALTH_BODY"
     case "$HEALTH_BODY" in *'"graph":false'*) GRAPH_DOWN=1 ;; esac ;;
  *) dc logs --tail 30 mimirsynth >&2 || true
     die "it did not answer within ${WAIT_SECONDS}s: see 'docker compose logs mimirsynth' in $DIR" "no ha respondido en ${WAIT_SECONDS}s: mira 'docker compose logs mimirsynth' en $DIR" ;;
esac

SETUP_CODE=""
if curl -fsS --max-time 5 "http://127.0.0.1:$PORT/api/auth/options" 2>/dev/null | grep -q '"setup":true'; then
  i=0; until [ -n "$SETUP_CODE" ] || [ "$i" -ge 10 ]; do SETUP_CODE="$(setup_code)"; [ -n "$SETUP_CODE" ] || sleep 1; i=$((i + 1)); done
fi
if [ "$GRAPH" = existing ] && { [ "$PROBED" = 0 ] || [ "$GRAPH_DOWN" = 1 ]; }; then check_graph_from_container || graph_unusable; fi

URL="http://localhost:$PORT"
# The setup wizard (#361) is at /configuracion. Its API answers 401 without a session; a release without it serves the web app on any
# path (200), and there /configuracion would be a page that does not exist once the administrator signs in.
case "$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "http://127.0.0.1:$PORT/api/setup" 2>/dev/null || true)" in
  401|403) URL="$URL/configuracion" ;;
esac
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
