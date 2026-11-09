#!/usr/bin/env bash
# MimirSynth updater: backup -> update -> verify. Run it from the folder with your docker-compose.yml and .env (or set MIMIRSYNTH_DIR).
#   ./update.sh                  update to the latest stable release; never down to it, from a newer version or release candidate
#   ./update.sh --version 0.7.1  update (or go) to a specific version; release candidates such as 0.7.1-rc.1 work too. An older one is
#                                refused when its application does not know the database's revision (--force goes anyway)
#   ./update.sh --check          only say what is running, what is the latest release and what ./update.sh would do
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
    -h|--help) sed -n '2,9p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
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
# The same for the optional OCR service (#135): it is updated with the application when its container exists here.
OCR=""
if [ -n "$(docker compose --profile ocr ps -aq ocr 2>/dev/null)" ]; then DC="$DC --profile ocr"; OCR="ocr"; fi
envget() { local v; v=$(grep -E "^$1=" .env | tail -1 | cut -d= -f2- || true); v="${v%\"}"; v="${v#\"}"; printf '%s' "${v:-$2}"; }
norm()   { printf '%s' "${1#v}"; }
base()   { local v; v="$(norm "$1")"; printf '%s' "${v%%-*}"; }
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
hsize() { numfmt --to=iec "$(stat -c %s "$1")" 2>/dev/null || stat -c %s "$1"; }
PORT="$(envget MIMIRSYNTH_PORT 8000)"
api()    { curl -fsS --max-time 5 "http://127.0.0.1:$PORT$1"; }
running_version() { api /api/config 2>/dev/null | sed -n 's/.*"version":"\([^"]*\)".*/\1/p' || true; }
latest_tag() { curl -fsS --max-time 15 "https://api.github.com/repos/$REPO/releases/latest" | sed -n 's/.*"tag_name": *"\([^"]*\)".*/\1/p' | head -1; }
release_tags() { curl -fsS --max-time 15 "https://api.github.com/repos/$REPO/releases?per_page=50" | sed -n 's/.*"tag_name": *"\([^"]*\)".*/\1/p'; }
newer_in_line() {  # $1 a pre-release: the newest release of its line (the same X.Y.Z) above it, or nothing
  local best="" t
  for t in $(release_tags 2>/dev/null || true); do
    t="$(norm "$t")"; semver "$t" && [ "$(base "$t")" = "$(base "$1")" ] && [ "$(vercmp "$t" "$1")" = 1 ] || continue
    if [ -z "$best" ] || [ "$(vercmp "$t" "$best")" = 1 ]; then best="$t"; fi
  done
  printf '%s' "$best"
}
asset()  { curl -fsSL --max-time 30 "https://github.com/$REPO/releases/download/v$(norm "$1")/docker-compose.yml"; }
db_version() { $DC exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "select version_num from alembic_version"' 2>/dev/null | tr -d '[:space:]' || true; }
# The database revisions an image knows, one per line, read from its migrations in a throwaway container (#403)
REVS_PY='import importlib.util as u,pathlib,re
for f in (pathlib.Path(u.find_spec("mimirsynth").submodule_search_locations[0])/"migrations"/"versions").glob("*.py"):
  m=re.search(r"^revision\s*(?::[^=]*)?=\s*[\x27\"]([^\x27\"]+)",f.read_text(),re.M)
  m and print(m.group(1))'
image_revisions() { MIMIRSYNTH_VERSION="$1" $DC run --rm --no-deps -T --entrypoint python mimirsynth -c "$REVS_PY" 2>/dev/null || true; }
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
# What is installed, as precisely as it is known: /api/config says 0.15.0 for 0.15.0-rc.1, the configured version names the candidate
inst=""
if semver "$cur_cfg" && { [ -z "$cur_run" ] || [ "$cur_run" = "$(base "$cur_cfg")" ]; }; then inst="$(norm "$cur_cfg")"
elif semver "$cur_run"; then inst="$(norm "$cur_run")"; fi
step "Version" "Versión"
if [ -z "$TARGET" ]; then
  TARGET="$(latest_tag || true)"
  [ -n "$TARGET" ] || die "could not find the latest release (no network?): use --version" "no se pudo saber la última versión (¿sin red?): usa --version"
  TARGET="$(norm "$TARGET")"
  # Without --version it never goes down (#403): from a version newer than the latest stable release there is nothing to do
  if [ -n "$inst" ] && semver "$TARGET" && [ "$(vercmp "$inst" "$TARGET")" = 1 ]; then
    say "Running: ${cur_run:-not responding} · configured: $cur_cfg · latest stable release: $TARGET" "En marcha: ${cur_run:-no responde} · configurada: $cur_cfg · última versión estable: $TARGET"
    say "$inst is newer than the latest stable release ($TARGET): nothing to do. Use --version to choose another one." \
        "$inst es más reciente que la última versión estable ($TARGET): no hay nada que hacer. Usa --version para elegir otra."
    if [[ $inst == *-* ]]; then
      nxt="$(newer_in_line "$inst")"
      [ -z "$nxt" ] || say "A newer release of the $(base "$inst") line is out: ./update.sh --version $nxt" "Hay una versión más reciente de la línea $(base "$inst"): ./update.sh --version $nxt"
    fi
    exit 0
  fi
fi
TARGET="$(norm "$TARGET")"
say "Running: ${cur_run:-not responding} · configured: $cur_cfg · target: $TARGET" "En marcha: ${cur_run:-no responde} · configurada: $cur_cfg · objetivo: $TARGET"
dirn=""; [ -z "$inst" ] || ! semver "$TARGET" || dirn="$(vercmp "$TARGET" "$inst")"
if [ "$dirn" = -1 ]; then
  say "$TARGET is older than $inst: going down only if its application knows the database's revision (or with --force)." \
      "$TARGET es anterior a $inst: solo se baja si su aplicación conoce la revisión de la base de datos (o con --force)."
fi
if [ "$MODE" = check ]; then exit 0; fi
if [ "$FORCE" != 1 ] && [ -n "$cur_run" ] && [ "$cur_run" = "$(base "$TARGET")" ] && [ "$cur_cfg" = "$TARGET" ]; then say "Already up to date." "Ya está actualizado."; exit 0; fi
[ -n "$cur_run" ] || warn "the application is not answering now: the backup only covers what the database holds" "la aplicación no responde ahora: la copia solo cubre lo que haya en la base de datos"

step "Download" "Descarga"
newc="$(mktemp)"; trap 'rm -f "$newc"' EXIT
have_new=0; [ "$COMPOSE_MODE" != keep ] && asset "$TARGET" > "$newc" 2>/dev/null && [ -s "$newc" ] && have_new=1
say "Pulling the image..." "Descargando la imagen..."
# first, so that a wrong version or no network aborts BEFORE touching the backup that is already there
MIMIRSYNTH_VERSION="$TARGET" $DC pull mimirsynth $OCR || die "could not pull $TARGET: nothing was changed, the existing backup is intact" "no se pudo descargar $TARGET: no se ha cambiado nada, la copia que había sigue intacta"

# Going down (#403): an application older than the database's revision does not start, so it is checked with the image just pulled
if [ "$dirn" = -1 ]; then
  if [ "$FORCE" = 1 ]; then warn "going down to $TARGET with --force: the database's revision is not checked" "se baja a $TARGET con --force: no se comprueba la revisión de la base de datos"
  else
    rev="$(db_version)"; revs="$(image_revisions "$TARGET")"
    if [ -n "$rev" ] && printf '%s\n' "$revs" | grep -qxF "$rev"; then
      say "$TARGET knows this database (revision $rev)." "$TARGET conoce esta base de datos (revisión $rev)."
    else
      if [ -n "$rev" ] && [ -n "$revs" ]; then
        say "$TARGET does not know this database's revision ($rev): its application would not start. Nothing was changed." \
            "$TARGET no conoce la revisión de esta base de datos ($rev): su aplicación no arrancaría. No se ha cambiado nada."
      else
        say "Could not check whether $TARGET knows this database's revision (${rev:-unknown}). Nothing was changed." \
            "No se pudo comprobar si $TARGET conoce la revisión de esta base de datos (${rev:-desconocida}). No se ha cambiado nada."
      fi
      bk="$(sed -n 's/^configured=//p' "$BACKUP_DIR/INFO" 2>/dev/null || true)"
      if [ -n "$bk" ] && [ "$(norm "$bk")" = "$TARGET" ]; then
        say "The backup in $BACKUP_DIR is of $TARGET: ./update.sh --rollback --with-db goes back to it with its database (whatever was written since is lost)." \
            "La copia de $BACKUP_DIR es de $TARGET: ./update.sh --rollback --with-db vuelve a ella con su base de datos (lo escrito desde entonces se pierde)."
      else
        say "An older version needs the database of its time: ./update.sh --rollback --with-db restores the one in $BACKUP_DIR, when that backup is of the version you want." \
            "Una versión anterior necesita la base de datos de su momento: ./update.sh --rollback --with-db restaura la de $BACKUP_DIR, si esa copia es de la versión que quieres."
      fi
      die "not going down to $TARGET (--force goes anyway)" "no se baja a $TARGET (--force lo hace igualmente)"
    fi
  fi
fi

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
$DC up -d mimirsynth $OCR
if verify "$TARGET"; then
  say "Updated to $TARGET. Backup of the previous state: $BACKUP_DIR" "Actualizado a $TARGET. Copia del estado anterior: $BACKUP_DIR"
else
  say "The update to $TARGET did not verify. To go back: ./update.sh --rollback  (add --with-db to restore the database too)" "La actualización a $TARGET no se ha verificado. Para volver atrás: ./update.sh --rollback  (añade --with-db para restaurar también la base de datos)"
  exit 1
fi
