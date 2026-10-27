#!/usr/bin/env bash
# MimirSynth updater: backup -> update -> verify. Run it from the folder with your docker-compose.yml and .env (or set MIMIRSYNTH_DIR).
#   ./update.sh                  update to the latest stable release
#   ./update.sh --version 0.7.1  update (or go) to a specific version; release candidates such as 0.7.1-rc.1 work too
#   ./update.sh --check          only say what is running and what is the latest release
#   ./update.sh --rollback       go back to the previous version using the backup (add --with-db to restore the database too)
# Every run keeps ONE backup (./backup): the previous one is replaced only after the new one has been written and checked.
# Options: --no-files (skip the documents volume), --update-compose / --keep-compose, --force, --yes, --backup-dir DIR.
set -Eeuo pipefail

REPO="MimirSynth/mimirsynth"
DIR="${MIMIRSYNTH_DIR:-$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)}"
BACKUP_DIR="${BACKUP_DIR:-$DIR/backup}"
WAIT_SECONDS="${WAIT_SECONDS:-180}"
MODE=update; TARGET=""; FORCE=0; YES=0; FILES=1; COMPOSE_MODE=auto; WITH_DB=0

case "${LC_ALL:-${LANG:-}}" in es*) L=es ;; *) L=en ;; esac
say()  { if [ "$L" = es ]; then printf '%s\n' "$2"; else printf '%s\n' "$1"; fi; }
step() { printf '\n== '; say "$@"; }
warn() { { printf 'WARN: '; say "$@"; } >&2; }
die()  { { printf 'ERROR: '; say "$@"; } >&2; exit 1; }

while [ $# -gt 0 ]; do
  case "$1" in
    --check) MODE=check ;;
    --rollback) MODE=rollback ;;
    --with-db) WITH_DB=1 ;;
    --version) TARGET="${2:-}"; shift ;;
    --force) FORCE=1 ;;
    --yes|-y) YES=1 ;;
    --no-files) FILES=0 ;;
    --update-compose) COMPOSE_MODE=update ;;
    --keep-compose) COMPOSE_MODE=keep ;;
    --backup-dir) BACKUP_DIR="${2:-}"; shift ;;
    -h|--help) sed -n '2,10p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) die "unknown option: $1" "opción desconocida: $1" ;;
  esac
  shift
done

cd "$DIR"
[ -f docker-compose.yml ] && [ -f .env ] || die "docker-compose.yml and .env not found in $DIR" "no hay docker-compose.yml y .env en $DIR"
command -v docker >/dev/null && docker compose version >/dev/null 2>&1 || die "Docker with Compose v2 is required" "hace falta Docker con Compose v2"
command -v curl >/dev/null || die "curl is required" "hace falta curl"
exec 9>"$DIR/.update.lock"; flock -n 9 || die "another update is running" "ya hay otra actualización en marcha"

# The bundled-FalkorDB profile is only added when that container exists here (or COMPOSE_PROFILES is set): with an external FalkorDB,
# naming the profile would create an empty, unused graphdata volume.
DC="docker compose"
if [ -n "$(docker compose --profile bundled ps -aq falkordb 2>/dev/null)" ]; then DC="docker compose --profile bundled"; fi
envget() { local v; v=$(grep -E "^$1=" .env | tail -1 | cut -d= -f2- || true); v="${v%\"}"; v="${v#\"}"; printf '%s' "${v:-$2}"; }
norm()   { printf '%s' "${1#v}"; }
base()   { local v; v="$(norm "$1")"; printf '%s' "${v%%-*}"; }
hsize() { numfmt --to=iec "$(stat -c %s "$1")" 2>/dev/null || stat -c %s "$1"; }
PORT="$(envget MIMIRSYNTH_PORT 8000)"
api()    { curl -fsS --max-time 5 "http://127.0.0.1:$PORT$1"; }
running_version() { api /api/config 2>/dev/null | sed -n 's/.*"version":"\([^"]*\)".*/\1/p' || true; }
latest_tag() { curl -fsS --max-time 15 "https://api.github.com/repos/$REPO/releases/latest" | sed -n 's/.*"tag_name": *"\([^"]*\)".*/\1/p' | head -1; }
asset()  { curl -fsSL --max-time 30 "https://github.com/$REPO/releases/download/v$(norm "$1")/docker-compose.yml"; }
db_version() { $DC exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "select version_num from alembic_version"' 2>/dev/null | tr -d '[:space:]' || true; }
set_env_version() { if grep -qE '^MIMIRSYNTH_VERSION=' .env; then sed -i "s|^MIMIRSYNTH_VERSION=.*|MIMIRSYNTH_VERSION=$1|" .env; else printf '\nMIMIRSYNTH_VERSION=%s\n' "$1" >> .env; fi; }

backup() {
  step "Backup" "Copia de seguridad"
  local tmp="$DIR/.backup.new"; rm -rf "$tmp"; (umask 077; mkdir -p "$tmp")
  trap 'rm -rf "$tmp"' ERR
  $DC exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' | gzip > "$tmp/mimirsynth.sql.gz"
  gzip -t "$tmp/mimirsynth.sql.gz" && [ "$(stat -c %s "$tmp/mimirsynth.sql.gz")" -gt 1024 ] || die "the database dump is empty or corrupt" "el volcado de la base de datos está vacío o dañado"
  say "PostgreSQL: $(hsize "$tmp/mimirsynth.sql.gz")" "PostgreSQL: $(hsize "$tmp/mimirsynth.sql.gz")"
  cp docker-compose.yml "$tmp/docker-compose.yml"; cp .env "$tmp/env"
  if [ "$FILES" = 1 ] && $DC exec -T mimirsynth tar -czf - -C /data/documents . > "$tmp/docstore.tar.gz" 2>/dev/null && [ -s "$tmp/docstore.tar.gz" ]; then
    say "Documents volume: $(hsize "$tmp/docstore.tar.gz")" "Volumen de documentos: $(hsize "$tmp/docstore.tar.gz")"
  else
    rm -f "$tmp/docstore.tar.gz"; [ "$FILES" = 1 ] && warn "documents volume not saved (empty, or the container is not running)" "volumen de documentos no guardado (vacío, o el contenedor no está en marcha)"
  fi
  if $DC ps --services --status running 2>/dev/null | grep -qx falkordb; then
    if $DC exec -T falkordb redis-cli SAVE >/dev/null 2>&1 && $DC cp falkordb:/var/lib/falkordb/data/dump.rdb "$tmp/falkordb-dump.rdb" >/dev/null 2>&1; then
      say "FalkorDB (bundled): $(hsize "$tmp/falkordb-dump.rdb")" "FalkorDB (incluido): $(hsize "$tmp/falkordb-dump.rdb")"
    else warn "could not save the bundled FalkorDB" "no se pudo guardar el FalkorDB incluido"; fi
  else
    warn "FalkorDB is external: it is NOT part of this backup" "FalkorDB es externo: NO forma parte de esta copia"
  fi
  printf 'version=%s\nconfigured=%s\ndate=%s\nalembic=%s\n' "$(running_version)" "$(envget MIMIRSYNTH_VERSION latest)" "$(date -Is)" "$(db_version)" > "$tmp/INFO"
  trap - ERR
  rm -rf "$BACKUP_DIR"; mv "$tmp" "$BACKUP_DIR"   # the previous backup goes away only now, with the new one already complete
  say "Saved in $BACKUP_DIR (the previous backup was replaced)" "Guardada en $BACKUP_DIR (la copia anterior se ha sustituido)"
}

verify() {  # $1 = expected version
  step "Verification" "Comprobación"
  local want ok=0 t0=$SECONDS v; want="$(base "$1")"
  while [ $((SECONDS - t0)) -lt "$WAIT_SECONDS" ]; do
    v="$(running_version)"
    if [ "$v" = "$want" ] && api /api/health >/dev/null 2>&1; then ok=1; break; fi
    sleep 3
  done
  [ "$ok" = 1 ] || { say "It did not answer with version $want within ${WAIT_SECONDS}s (it says: '${v:-nothing}')" "No respondió con la versión $want en ${WAIT_SECONDS}s (responde: '${v:-nada}')"; return 1; }
  local cid hs; cid="$($DC ps -q mimirsynth)"; hs="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$cid" 2>/dev/null || echo ?)"
  say "Version: $v · health: $hs · database revision: $(db_version)" "Versión: $v · salud: $hs · revisión de la base de datos: $(db_version)"
  local errs; errs="$($DC logs --since 5m mimirsynth 2>&1 | grep -ciE 'traceback|critical' || true)"
  [ "${errs:-0}" -eq 0 ] || warn "$errs error lines in the last 5 minutes of the log: check them" "$errs líneas de error en los últimos 5 minutos del log: revísalas"
  return 0
}

if [ "$MODE" = rollback ]; then
  step "Rollback" "Vuelta atrás"
  [ -f "$BACKUP_DIR/INFO" ] || die "there is no backup in $BACKUP_DIR" "no hay copia en $BACKUP_DIR"
  prev="$(sed -n 's/^configured=//p' "$BACKUP_DIR/INFO")"
  say "Backup of $(sed -n 's/^date=//p' "$BACKUP_DIR/INFO") (version $(sed -n 's/^version=//p' "$BACKUP_DIR/INFO"), database revision $(sed -n 's/^alembic=//p' "$BACKUP_DIR/INFO"))." "Copia del $(sed -n 's/^date=//p' "$BACKUP_DIR/INFO") (versión $(sed -n 's/^version=//p' "$BACKUP_DIR/INFO"), revisión de la base de datos $(sed -n 's/^alembic=//p' "$BACKUP_DIR/INFO"))."
  [ "$WITH_DB" = 1 ] && say "The database will be RESTORED from that backup: whatever was written since is lost." "La base de datos se RESTAURARÁ desde esa copia: lo escrito desde entonces se pierde."
  if [ "$YES" != 1 ]; then
    [ -t 0 ] || die "confirm with --yes" "confirma con --yes"
    read -r -p "Continue? [y/N] " a; case "$a" in y|Y|s|S) ;; *) die "cancelled" "cancelado" ;; esac
  fi
  cp docker-compose.yml docker-compose.yml.rolledback; cp .env .env.rolledback
  cp "$BACKUP_DIR/docker-compose.yml" docker-compose.yml; cp "$BACKUP_DIR/env" .env; chmod 600 .env
  if [ "$WITH_DB" = 1 ]; then
    $DC stop mimirsynth
    $DC exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d postgres -c "DROP DATABASE IF EXISTS \"$POSTGRES_DB\" WITH (FORCE)" -c "CREATE DATABASE \"$POSTGRES_DB\""'
    gunzip -c "$BACKUP_DIR/mimirsynth.sql.gz" | $DC exec -T postgres sh -c 'psql -q -U "$POSTGRES_USER" -d "$POSTGRES_DB"' >/dev/null
    say "Database restored." "Base de datos restaurada."
  fi
  $DC up -d mimirsynth
  verify "$(sed -n 's/^version=//p' "$BACKUP_DIR/INFO")" || die "the previous version does not answer: check 'docker compose logs mimirsynth'" "la versión anterior no responde: revisa 'docker compose logs mimirsynth'"
  say "Back on ${prev:-the previous version}. The failed files are kept as *.rolledback." "De vuelta en ${prev:-la versión anterior}. Los ficheros de la versión fallida quedan como *.rolledback."
  exit 0
fi

# ---- update / check ----
cur_cfg="$(envget MIMIRSYNTH_VERSION latest)"; cur_run="$(running_version)"
[ -n "$TARGET" ] || TARGET="$(latest_tag)" || true
[ -n "$TARGET" ] || die "could not find the latest release (no network?): use --version" "no se pudo saber la última versión (¿sin red?): usa --version"
TARGET="$(norm "$TARGET")"
step "Version" "Versión"
say "Running: ${cur_run:-not responding} · configured: $cur_cfg · target: $TARGET" "En marcha: ${cur_run:-no responde} · configurada: $cur_cfg · objetivo: $TARGET"
if [ "$MODE" = check ]; then exit 0; fi
if [ "$FORCE" != 1 ] && [ -n "$cur_run" ] && [ "$cur_run" = "$(base "$TARGET")" ] && [ "$cur_cfg" = "$TARGET" ]; then say "Already up to date." "Ya está actualizado."; exit 0; fi
[ -n "$cur_run" ] || warn "the application is not answering now: the backup only covers what the database holds" "la aplicación no responde ahora: la copia solo cubre lo que haya en la base de datos"

step "Download" "Descarga"
newc="$(mktemp)"; trap 'rm -f "$newc"' EXIT
have_new=0; [ "$COMPOSE_MODE" != keep ] && asset "$TARGET" > "$newc" 2>/dev/null && [ -s "$newc" ] && have_new=1
say "Pulling the image..." "Descargando la imagen..."
# first, so that a wrong version or no network aborts BEFORE touching the backup that is already there
MIMIRSYNTH_VERSION="$TARGET" $DC pull mimirsynth || die "could not pull $TARGET: nothing was changed, the existing backup is intact" "no se pudo descargar $TARGET: no se ha cambiado nada, la copia que había sigue intacta"

backup

step "Update" "Actualización"
if [ "$have_new" = 1 ]; then
  if cmp -s "$newc" docker-compose.yml; then say "docker-compose.yml: same as the release." "docker-compose.yml: igual que el de la versión."
  else
    adopt=0
    if [ "$COMPOSE_MODE" = update ]; then adopt=1
    elif [ "$cur_cfg" != latest ] && asset "$cur_cfg" 2>/dev/null | cmp -s - docker-compose.yml; then adopt=1; fi   # the current file is the unmodified one of the running release
    if [ "$adopt" = 1 ]; then cp "$newc" docker-compose.yml; say "docker-compose.yml updated to the one of release $TARGET (the old one is in the backup)." "docker-compose.yml actualizado al de la versión $TARGET (el anterior está en la copia)."
    else warn "your docker-compose.yml differs from the release's, so it was NOT replaced (use --update-compose to adopt the new one)" "tu docker-compose.yml difiere del de la versión, así que NO se ha reemplazado (usa --update-compose para adoptar el nuevo)"; fi
  fi
fi
set_env_version "$TARGET"
$DC up -d mimirsynth
if verify "$TARGET"; then
  say "Updated to $TARGET. Backup of the previous state: $BACKUP_DIR" "Actualizado a $TARGET. Copia del estado anterior: $BACKUP_DIR"
else
  say "The update to $TARGET did not verify. To go back: ./update.sh --rollback  (add --with-db to restore the database too)" "La actualización a $TARGET no se ha verificado. Para volver atrás: ./update.sh --rollback  (añade --with-db para restaurar también la base de datos)"
  exit 1
fi
