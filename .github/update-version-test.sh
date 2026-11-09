#!/usr/bin/env bash
# CI (#403): which version update.sh goes to, against a stand-in `docker` and `curl`. The stand-ins play the database (its alembic
# revision), the images (the revisions each one knows), the running application (it answers with the version the .env names once
# `up` has run) and GitHub (the latest stable release and the list of releases). Everything else that update.sh does, the backup
# included, runs for real in a throwaway folder.
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FAKE="$(mktemp -d)"; export FAKE
trap 'rm -rf "$FAKE"' EXIT
mkdir -p "$FAKE/bin"

# ---- SemVer: the cases install.ps1 also checks ----
norm() { printf '%s' "${1#v}"; }
eval "$(sed -n '/^SEMVER_RE=/,/^}/p' "$ROOT/update.sh")"
n=0
while read -r a b want; do
  case "$a" in ''|'#'*) continue ;; esac
  got="$(vercmp "$a" "$b")"; [ "$got" = "$want" ] || { echo "vercmp $a $b = $got, expected $want"; exit 1; }
  semver "$a" || { echo "$a should be a version"; exit 1; }
  n=$((n + 1))
done < "$ROOT/.github/semver-cases.txt"
for v in latest ci 0.15 0.15.0.1 01.2.3 0.15.0-; do if semver "$v"; then echo "$v should not be a version"; exit 1; fi; done
echo "ok: $n SemVer comparisons"

# ---- the stand-ins ----
cat > "$FAKE/bin/docker" <<'EOF'
#!/bin/sh
echo "${MIMIRSYNTH_VERSION:--} $*" >> "$FAKE/docker.log"
case "$*" in
  *"select version_num"*) echo "$FAKE_DB" ;;
  *pg_dump*) head -c 4096 /dev/urandom ;;
  *" pull "*) [ "${FAKE_PULL:-ok}" = ok ] ;;
  *" run "*"--entrypoint python"*) for r in $FAKE_REVS; do echo "$r"; done ;;   # what the image of $MIMIRSYNTH_VERSION knows
  *" up -d "*) v="$(sed -n 's/^MIMIRSYNTH_VERSION=//p' .env)"; echo "${v%%-*}" > "$FAKE/running" ;;
esac
exit 0
EOF
cat > "$FAKE/bin/curl" <<'EOF'
#!/bin/sh
for url; do :; done   # the URL is the last argument
case "$url" in
  */api/config) [ -s "$FAKE/running" ] || exit 7; printf '{"name":"MimirSynth","version":"%s"}' "$(cat "$FAKE/running")" ;;
  */api/health) [ -s "$FAKE/running" ] || exit 7; echo '{"status":"ok"}' ;;
  */releases/latest) printf '{\n  "tag_name": "v%s",\n  "prerelease": false\n}\n' "$FAKE_LATEST" ;;
  *"/releases?per_page="*) echo "["; for t in $FAKE_TAGS; do printf '  {\n    "tag_name": "v%s",\n' "$t"; done; echo "]" ;;
  *) exit 22 ;;   # the release files: none, so the compose file is kept
esac
EOF
chmod +x "$FAKE/bin/docker" "$FAKE/bin/curl"
export PATH="$FAKE/bin:$PATH" LANG=C.UTF-8 LC_ALL='' WAIT_SECONDS=9

# case NAME CONFIGURED RUNNING [update.sh options...]: a fresh installation folder, then update.sh; its output in $FAKE/out, its exit code in $rc
case_() {
  local name="$1" cfg="$2" run="$3"; shift 3
  D="$FAKE/$name"; mkdir -p "$D"
  printf 'services: {}\n' > "$D/docker-compose.yml"
  printf 'MIMIRSYNTH_PORT=8000\nMIMIRSYNTH_VERSION=%s\n' "$cfg" > "$D/.env"; cp "$D/.env" "$FAKE/env.before"
  printf '%s' "$run" > "$FAKE/running"; : > "$FAKE/docker.log"
  echo "-- $name: configured $cfg, running ${run:-nothing}, latest stable $FAKE_LATEST: update.sh $*"
  rc=0; MIMIRSYNTH_DIR="$D" "$ROOT/update.sh" "$@" > "$FAKE/out" 2>&1 || rc=$?
  sed 's/^/   | /' "$FAKE/out"
}
expect()    { grep -qF -- "$1" "$FAKE/out" || { echo "FAIL ($D): the output does not say «$1»"; exit 1; }; }
expect_no() { if grep -qF -- "$1" "$FAKE/out"; then echo "FAIL ($D): the output says «$1»"; exit 1; fi; }
rc_is()     { [ "$rc" = "$1" ] || { echo "FAIL ($D): exit code $rc, expected $1"; exit 1; }; }
untouched() {
  cmp -s "$D/.env" "$FAKE/env.before" || { echo "FAIL ($D): .env was changed"; exit 1; }
  [ ! -e "$D/backup" ] || { echo "FAIL ($D): a backup was made"; exit 1; }
  if grep -qE ' (pull|up) ' "$FAKE/docker.log"; then echo "FAIL ($D): it pulled or started something"; exit 1; fi
}
went_to()   {
  rc_is 0; expect "Updated to $1."
  grep -qx "MIMIRSYNTH_VERSION=$1" "$D/.env" || { echo "FAIL ($D): .env does not say $1"; exit 1; }
  grep -q "^$1 compose pull mimirsynth" "$FAKE/docker.log" || { echo "FAIL ($D): $1 was not pulled"; exit 1; }
  grep -qx "configured=$2" "$D/backup/INFO" || { echo "FAIL ($D): the backup is not of $2"; exit 1; }
}

export FAKE_DB=0058 FAKE_REVS="" FAKE_PULL=ok

# A release candidate newer than the latest stable release: nothing to do, and the same verdict from --check (the bug of #403)
export FAKE_LATEST=0.14.0 FAKE_TAGS="0.15.0-rc.1 0.14.0 0.14.0-rc.2 0.14.0-rc.1"
case_ rc-to-older-stable 0.15.0-rc.1 0.15.0 --yes
rc_is 0; untouched
expect "0.15.0-rc.1 is newer than the latest stable release (0.14.0): nothing to do. Use --version to choose another one."
expect_no "target: 0.14.0"; expect_no "A newer release"
case_ rc-to-older-stable-check 0.15.0-rc.1 0.15.0 --check
rc_is 0; untouched; expect "0.15.0-rc.1 is newer than the latest stable release (0.14.0): nothing to do."
case_ rc-not-answering 0.15.0-rc.1 "" --yes
rc_is 0; untouched; expect "0.15.0-rc.1 is newer than the latest stable release (0.14.0): nothing to do."
case_ latest-running-newer latest 0.15.0 --yes
rc_is 0; untouched; expect "0.15.0 is newer than the latest stable release (0.14.0): nothing to do."

# ... and a newer candidate of the same line is offered, not installed
export FAKE_TAGS="0.15.0-rc.2 0.15.0-rc.1 0.14.0 0.16.0-rc.1"
case_ rc-offers-next-rc 0.15.0-rc.1 0.15.0 --yes
rc_is 0; untouched; expect "A newer release of the 0.15.0 line is out: ./update.sh --version 0.15.0-rc.2"

# A release candidate to its final release, and a stable release to a newer one
export FAKE_LATEST=0.15.0 FAKE_TAGS="0.15.0 0.15.0-rc.1 0.14.0"
case_ rc-to-its-final 0.15.0-rc.1 0.15.0 --check
rc_is 0; untouched; expect "target: 0.15.0"; expect_no "nothing to do"
case_ rc-to-its-final 0.15.0-rc.1 0.15.0 --yes
went_to 0.15.0 0.15.0-rc.1; expect_no "older than"
export FAKE_LATEST=0.15.0
case_ stable-to-newer 0.14.0 0.14.0 --yes
went_to 0.15.0 0.14.0
case_ up-to-date 0.15.0 0.15.0 --yes
rc_is 0; untouched; expect "Already up to date."
case_ rc-to-next-rc 0.15.0-rc.1 0.15.0 --yes --version 0.15.0-rc.2
went_to 0.15.0-rc.2 0.15.0-rc.1

# An explicit older version whose application does not know the database: refused before anything changes, unless --force
export FAKE_REVS="0056 0057"
case_ down-check 0.15.0-rc.1 0.15.0 --check --version 0.14.0
rc_is 0; untouched; expect "0.14.0 is older than 0.15.0-rc.1"
case_ down-refused 0.15.0-rc.1 0.15.0 --yes --version 0.14.0
rc_is 1; expect "0.14.0 does not know this database's revision (0058): its application would not start. Nothing was changed."
expect "./update.sh --rollback --with-db"; expect "not going down to 0.14.0 (--force goes anyway)"
cmp -s "$D/.env" "$FAKE/env.before" && [ ! -e "$D/backup" ] || { echo "FAIL ($D): something was changed"; exit 1; }
if grep -qE ' up ' "$FAKE/docker.log"; then echo "FAIL ($D): it started something"; exit 1; fi
case_ down-forced 0.15.0-rc.1 0.15.0 --yes --version 0.14.0 --force
went_to 0.14.0 0.15.0-rc.1; expect "going down to 0.14.0 with --force"
# with a backup of that very version, the refusal points to it
mkdir -p "$FAKE/down-backup/backup"; printf 'version=0.14.0\nconfigured=0.14.0\n' > "$FAKE/down-backup/backup/INFO"
case_ down-backup 0.15.0-rc.1 0.15.0 --yes --version 0.14.0
rc_is 1; expect "The backup in $D/backup is of 0.14.0: ./update.sh --rollback --with-db goes back to it with its database"
# the database's revision cannot be read: refused too
FAKE_DB="" case_ down-unknown 0.15.0-rc.1 0.15.0 --yes --version 0.14.0
rc_is 1; expect "Could not check whether 0.14.0 knows this database's revision (unknown)."

# An older version that knows the database (no migration in between) goes ahead
export FAKE_REVS="0057 0058"
case_ down-known 0.14.1 0.14.1 --yes --version 0.14.0
went_to 0.14.0 0.14.1; expect "0.14.0 knows this database (revision 0058)."

# In Spanish
export FAKE_LATEST=0.14.0 FAKE_TAGS="0.15.0-rc.1 0.14.0"
LANG=es_ES.UTF-8 case_ rc-es 0.15.0-rc.1 0.15.0 --yes
rc_is 0; untouched; expect "0.15.0-rc.1 es más reciente que la última versión estable (0.14.0): no hay nada que hacer. Usa --version para elegir otra."
echo "ok: update.sh"
