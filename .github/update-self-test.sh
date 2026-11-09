#!/usr/bin/env bash
# CI (#413): update.sh brings itself up to date, install.sh --upgrade gives an existing install the current update.sh, and the
# backups. Against a stand-in `docker` (the database, the images and the running application, as in update-version-test.sh) and a
# stand-in `curl` that serves the releases from a local folder ($FAKE/releases/vX.Y.Z/FILE) and plays GitHub's API. The scripts
# themselves, their downloads, checksums, backups and .env changes run for real in throwaway folders.
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FAKE="$(mktemp -d)"; export FAKE
trap 'rm -rf "$FAKE"' EXIT
mkdir -p "$FAKE/bin" "$FAKE/releases"

cat > "$FAKE/bin/docker" <<'EOF'
#!/bin/sh
echo "${MIMIRSYNTH_VERSION:--} $*" >> "$FAKE/docker.log"
case "$*" in
  *"select version_num"*) echo "${FAKE_DB:-0058}" ;;
  *pg_dump*) head -c 4096 /dev/urandom ;;
  *"ps -aq mimirsynth"*) echo 0123456789ab ;;   # the application's container exists: an installation
  *" pull "*) ;;
  *" up -d "*) if [ "${FAKE_UP:-ok}" = ok ]; then v="$(sed -n 's/^MIMIRSYNTH_VERSION=//p' .env)"; echo "${v%%-*}" > "$FAKE/running"; fi ;;
esac
exit 0
EOF
cat > "$FAKE/bin/curl" <<'EOF'
#!/bin/sh
out=""; url=""
while [ $# -gt 0 ]; do case "$1" in -o) out="$2"; shift ;; -*) ;; *) url="$1" ;; esac; shift; done
echo "$url" >> "$FAKE/curl.log"
[ -z "$out" ] || exec > "$out"
case "$url" in
  */api/config) [ -s "$FAKE/running" ] || exit 7; printf '{"name":"MimirSynth","version":"%s"}' "$(cat "$FAKE/running")" ;;
  */api/health) [ -s "$FAKE/running" ] || exit 7; echo '{"status":"ok"}' ;;
  */releases/latest) printf '{\n  "tag_name": "v%s",\n  "prerelease": false\n}\n' "$FAKE_LATEST" ;;
  *"/releases?per_page="*) echo "[]" ;;
  */releases/download/*) f="$FAKE/releases/${url#*/releases/download/}"; [ -f "$f" ] || exit 22; cat "$f" ;;
  *) exit 22 ;;
esac
EOF
chmod +x "$FAKE/bin/docker" "$FAKE/bin/curl"
export PATH="$FAKE/bin:$PATH" LANG=C.UTF-8 LC_ALL='' WAIT_SECONDS=4

# A published release: the repository's scripts with its version written in (.github/stamp-release.sh, as release.yml does) and
# their SHA256SUMS. $2 = bad: a SHA256SUMS whose line for update.sh does not match.
release() {
  local r="$FAKE/releases/v$1"; mkdir -p "$r"
  cp "$ROOT/update.sh" "$ROOT/install.sh" "$ROOT/install.ps1" "$r/"
  bash "$ROOT/.github/stamp-release.sh" "$1" "$r" >/dev/null
  (cd "$r" && sha256sum update.sh install.sh install.ps1 > SHA256SUMS)
  if [ "${2:-}" = bad ]; then sed -i 's/^[0-9a-f]\{8\}/00000000/' "$r/SHA256SUMS"; fi
}
# An update.sh as installed by an older release: the repository's, stamped $1 (or with no RELEASE line at all, as before #413, when
# $1 is "legacy"), saying «OLD UPDATER» when it starts, so that the output tells which update.sh ran. "published": the rc.3 release's.
old_updater() {
  local hello='/^set -Eeuo pipefail/a echo "OLD UPDATER"'
  case "$1" in
    published) cat "$FAKE/releases/v0.15.0-rc.3/update.sh" ;;
    legacy) sed -e '/^RELEASE=/d' -e "$hello" "$ROOT/update.sh" ;;
    *) sed -e "s/^RELEASE=\"dev\"/RELEASE=\"$1\"/" -e "$hello" "$ROOT/update.sh" ;;
  esac
}
# A fresh installation folder with that update.sh: configured version $2, running $3 ("" = the application does not answer)
install_() {
  D="$FAKE/$1"; mkdir -p "$D"
  printf 'services: {}\n' > "$D/docker-compose.yml"
  printf 'MIMIRSYNTH_PORT=8000\nMIMIRSYNTH_VERSION=%s\n' "$2" > "$D/.env"; cp "$D/.env" "$FAKE/env.before"
  old_updater "${4:-0.15.0-rc.2}" > "$D/update.sh"; chmod +x "$D/update.sh"; cp "$D/update.sh" "$FAKE/updater.before"
  printf '%s' "$3" > "$FAKE/running"; : > "$FAKE/docker.log"; : > "$FAKE/curl.log"
}
run() {  # the installation's own update.sh, as people run it: its output in $FAKE/out, its exit code in $rc
  echo "-- $(basename "$D"): ./update.sh $*"
  rc=0; (cd "$D" && ./update.sh "$@") > "$FAKE/out" 2>&1 || rc=$?
  sed 's/^/   | /' "$FAKE/out"
}
fail()      { echo "FAIL ($D): $*"; exit 1; }
expect()    { grep -qF -- "$1" "$FAKE/out" || fail "the output does not say «$1»"; }
expect_no() { if grep -qF -- "$1" "$FAKE/out"; then fail "the output says «$1»"; fi; }
rc_is()     { [ "$rc" = "$1" ] || fail "exit code $rc, expected $1"; }
says_n()    { [ "$(grep -cF -- "$1" "$FAKE/out")" = "$2" ] || fail "«$1» is not said $2 time(s)"; }
fetched_n() { [ "$(grep -c "/releases/download/v$1/update.sh$" "$FAKE/curl.log")" = "$2" ] || fail "the update.sh of $1 was not downloaded $2 time(s)"; }
updater_is() { cmp -s "$D/update.sh" "$1" || fail "update.sh is not $1"; }
no_temp()   { local t; for t in "$D"/.update.sh.*; do [ ! -e "$t" ] || fail "a temporary update.sh was left behind: $t"; done; }
good_backup() {  # a backup of a working 0.15.0-rc.1, as update.sh writes it
  mkdir -p "$D/backup"; printf 'services: {}\n' > "$D/backup/docker-compose.yml"; cp "$D/.env" "$D/backup/env"
  head -c 2048 /dev/urandom | gzip > "$D/backup/mimirsynth.sql.gz"
  printf 'version=%s\nconfigured=%s\ndate=2026-11-01T10:00:00+00:00\nalembic=0058\nstate=answering\n' "${1-0.15.0}" "${2-0.15.0-rc.1}" > "$D/backup/INFO"
  rm -rf "$FAKE/backup.before"; cp -a "$D/backup" "$FAKE/backup.before"
}
backup_kept() { diff -r "$FAKE/backup.before" "$D/backup" >/dev/null || fail "the backup of the working instance was changed"; }

export FAKE_LATEST=0.14.0
release 0.15.0-rc.3

# ---- 1. update.sh brings itself up to date ----
# An older update.sh takes the target release's, checked against its SHA256SUMS, runs it with the same arguments, and only once
install_ self-update 0.15.0-rc.2 0.15.0
run --yes --version 0.15.0-rc.3
rc_is 0; updater_is "$FAKE/releases/v0.15.0-rc.3/update.sh"; no_temp
expect "update.sh replaced by the one of release 0.15.0-rc.3 (checked against its SHA256SUMS): running it again."
says_n "OLD UPDATER" 1; says_n "update.sh replaced" 1; fetched_n 0.15.0-rc.3 1   # the new one does not replace itself again
expect "Updated to 0.15.0-rc.3."
grep -qx 'MIMIRSYNTH_VERSION=0.15.0-rc.3' "$D/.env" || fail ".env does not say 0.15.0-rc.3"
grep -qx 'version=0.15.0' "$D/backup/INFO" && grep -qx 'state=answering' "$D/backup/INFO" || fail "the backup's INFO lacks the version or the state"
[ -x "$D/update.sh" ] || fail "update.sh is no longer executable"
# ... the same from the latest release for --check, which then reports with the new update.sh
FAKE_LATEST=0.15.0-rc.3 install_ self-update-check 0.15.0-rc.2 0.15.0
FAKE_LATEST=0.15.0-rc.3 run --check
rc_is 0; updater_is "$FAKE/releases/v0.15.0-rc.3/update.sh"; says_n "OLD UPDATER" 1; fetched_n 0.15.0-rc.3 1; expect "target: 0.15.0-rc.3"
# ... and from a copy of the repository's update.sh, which does not know which release it is
install_ self-update-dev 0.15.0-rc.1 0.15.0 dev
run --yes --version 0.15.0-rc.3
rc_is 0; updater_is "$FAKE/releases/v0.15.0-rc.3/update.sh"; says_n "OLD UPDATER" 1; expect "Updated to 0.15.0-rc.3."

# A wrong checksum: the script is not replaced, it says so and goes on with the update.sh it has
release 0.15.0-rc.4 bad
install_ bad-checksum 0.15.0-rc.2 0.15.0
run --yes --version 0.15.0-rc.4
rc_is 0; updater_is "$FAKE/updater.before"; no_temp
expect "the update.sh of release 0.15.0-rc.4 does not match its SHA256SUMS: it was NOT used, going on with this one"
says_n "OLD UPDATER" 1; expect "Updated to 0.15.0-rc.4."
# A release without the files (no network, or a wrong version): the same
install_ no-download 0.15.0-rc.2 0.15.0
run --check --version 0.15.0-rc.9
rc_is 0; updater_is "$FAKE/updater.before"; no_temp; expect "could not download the update.sh of release 0.15.0-rc.9: going on with this one"

# Never an older release's update.sh: not when going down with --version, nor for the latest stable release below a candidate
install_ older-target 0.15.0-rc.3 0.15.0 0.15.0-rc.3
run --check --version 0.15.0-rc.2
rc_is 0; updater_is "$FAKE/updater.before"; fetched_n 0.15.0-rc.2 0; expect "0.15.0-rc.2 is older than 0.15.0-rc.3"
release 0.15.0-rc.5
install_ older-than-itself 0.15.0-rc.2 0.15.0 0.15.0-rc.9   # an update.sh newer than the target release
run --check --version 0.15.0-rc.5
rc_is 0; updater_is "$FAKE/updater.before"; fetched_n 0.15.0-rc.5 0
install_ latest-below-rc 0.15.0-rc.1 0.15.0
run --yes
rc_is 0; updater_is "$FAKE/updater.before"; fetched_n 0.14.0 0; expect "nothing to do"
install_ opt-out 0.15.0-rc.2 0.15.0
run --check --version 0.15.0-rc.3 --no-self-update
rc_is 0; updater_is "$FAKE/updater.before"; fetched_n 0.15.0-rc.3 0
echo "ok: update.sh brings itself up to date"

# ---- 2. install.sh --upgrade gives an existing installation the update.sh of its own release ----
installer() {  # the published install.sh of release $1, run against the installation folder
  echo "-- $(basename "$D"): install.sh of $1 $*"
  local i="$FAKE/releases/v$1/install.sh"; shift
  rc=0; bash "$i" --dir "$D" "$@" > "$FAKE/out" 2>&1 || rc=$?
  sed 's/^/   | /' "$FAKE/out"
}
install_ installer-upgrade 0.15.0-rc.1 0.15.0 legacy   # the case of #413: an rc.1 install, the rc.3 installer, 0.14.0 the latest stable
installer 0.15.0-rc.3 --upgrade --yes
rc_is 0; updater_is "$FAKE/releases/v0.15.0-rc.3/update.sh"; no_temp
expect "update.sh: the one of release 0.15.0-rc.3 (checked against its SHA256SUMS)."
expect_no "OLD UPDATER"; expect "0.15.0-rc.1 is newer than the latest stable release (0.14.0): nothing to do."
cmp -s "$D/.env" "$FAKE/env.before" || fail ".env was changed"
install_ installer-keeps-newer 0.15.0-rc.1 0.15.0 0.16.0
installer 0.15.0-rc.3 --upgrade --yes
rc_is 0; updater_is "$FAKE/updater.before"; expect "update.sh: the one already there is kept, newer than release 0.15.0-rc.3's"
install_ installer-older-than-installed 0.15.0-rc.5 0.15.0 legacy
installer 0.15.0-rc.3 --yes
rc_is 0; updater_is "$FAKE/updater.before"; expect "update.sh: the one already there is kept"
install_ installer-bad-checksum 0.15.0-rc.1 0.15.0 legacy
installer 0.15.0-rc.4 --yes
rc_is 0; updater_is "$FAKE/updater.before"; no_temp; expect "the update.sh of release 0.15.0-rc.4 does not match its SHA256SUMS: it was NOT used"
echo "ok: install.sh gives the current update.sh"

# ---- 3. backups ----
# An update while the application does not answer leaves the backup of the working instance as it was, and writes its own beside it
export FAKE_LATEST=0.15.0-rc.3
install_ down 0.15.0-rc.1 "" published; good_backup
FAKE_UP=fail run --yes --version 0.15.0-rc.3
rc_is 1; backup_kept
expect "the application is not answering now"
expect "The backup of the last working instance is kept: $D/backup (version 0.15.0, 2026-11-01T10:00:00+00:00)."
expect "To go back to $D/backup (0.15.0, 2026-11-01T10:00:00+00:00): ./update.sh --rollback"
failed=("$D"/backup.failed-*); [ "${#failed[@]}" = 1 ] && [ -d "${failed[0]}" ] || fail "no single backup.failed-* folder"
grep -qx 'version=0.15.0' "${failed[0]}/INFO" && grep -qx 'state=not-answering' "${failed[0]}/INFO" || fail "the failed backup's INFO lacks the version or the state"
first="${failed[0]}"
# ... a second failed run keeps it so too, and only the newest failed backup
FAKE_UP=fail run --yes --version 0.15.0-rc.3
rc_is 1; backup_kept
failed=("$D"/backup.failed-*); [ "${#failed[@]}" = 1 ] && [ "${failed[0]}" != "$first" ] || fail "the older failed backup was not replaced by the newer one"
# ... and --rollback still goes back to the backup of the working instance
printf '%s' "" > "$FAKE/running"; : > "$FAKE/docker.log"
run --rollback --yes
rc_is 0; expect "Back on 0.15.0-rc.1."; grep -qx 'MIMIRSYNTH_VERSION=0.15.0-rc.1' "$D/.env" || fail ".env is not the backup's"
# With no backup of a working instance, it says that there is nothing to go back to
install_ down-no-backup 0.15.0-rc.1 "" published
FAKE_UP=fail run --yes --version 0.15.0-rc.3
rc_is 1; [ ! -e "$D/backup" ] || fail "a failed state was saved as the backup --rollback uses"
expect "there is no backup of a working instance in $D/backup: --rollback will have nothing to go back to"
expect "there is no backup of a working instance to go back to"

# A backup with no version (made while the application did not answer, by an update.sh before #413) is refused before anything changes
install_ rollback-no-version 0.14.0 "" 0.15.0-rc.3; good_backup "" 0.14.0; sed -i '/^state=/d' "$D/backup/INFO"
run --rollback --yes --with-db
rc_is 1; expect "it is not a valid point to go back to. Nothing was changed."; expect "not going back to that backup"
cmp -s "$D/.env" "$FAKE/env.before" || fail ".env was changed"
[ ! -e "$D/.env.rolledback" ] || fail "the rollback began"
if grep -qE ' (stop|up -d|exec -T postgres)' "$FAKE/docker.log"; then fail "it stopped, started or restored something"; fi
# ... and so is one written beside the good one, if --backup-dir points at it
install_ rollback-failed-dir 0.15.0-rc.1 "" 0.15.0-rc.3; good_backup 0.15.0; sed -i 's/^state=.*/state=not-answering/' "$D/backup/INFO"
run --rollback --yes
rc_is 1; expect "it is not a valid point to go back to. Nothing was changed."
# In Spanish
install_ rollback-es 0.14.0 "" 0.15.0-rc.3; good_backup "" 0.14.0
LANG=es_ES.UTF-8 run --rollback --yes
rc_is 1; expect "no es un punto válido al que volver. No se ha cambiado nada."
echo "ok: backups"

# ---- 4. the release writes its version into the scripts, once each ----
grep -qx 'RELEASE="0.15.0-rc.3"   # .*' "$FAKE/releases/v0.15.0-rc.3/update.sh" || { echo "FAIL: update.sh is not stamped"; exit 1; }
grep -q '^RELEASE="0.15.0-rc.3"' "$FAKE/releases/v0.15.0-rc.3/install.sh" || { echo "FAIL: install.sh is not stamped"; exit 1; }
grep -q '^\$Release = "0.15.0-rc.3"' "$FAKE/releases/v0.15.0-rc.3/install.ps1" || { echo "FAIL: install.ps1 is not stamped"; exit 1; }
if bash "$ROOT/.github/stamp-release.sh" "0.15.0-rc.3" "$FAKE/releases/v0.15.0-rc.3" 2>/dev/null; then echo "FAIL: stamped twice"; exit 1; fi
if bash "$ROOT/.github/stamp-release.sh" latest "$FAKE/releases/v0.15.0-rc.5" 2>/dev/null; then echo "FAIL: stamped with a non-version"; exit 1; fi
echo "ok: update.sh"
