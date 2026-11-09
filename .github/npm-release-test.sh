#!/usr/bin/env bash
# CI (#432): what .github/npm-release.sh does with a plugin on each kind of release, against a stand-in `npm` that plays the registry
# (the versions it has, its dist-tag latest, or an error) and logs every command. A release candidate or a run by hand only packs; a
# final release publishes a new version under `latest` with provenance, and a version npm already has ends in success with nothing
# published. No command that trusted publishing does not cover (dist-tag, deprecate, access) is ever run.
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FAKE="$(mktemp -d)"; export FAKE
trap 'rm -rf "$FAKE"' EXIT
mkdir -p "$FAKE/bin" "$FAKE/pkg"

cat > "$FAKE/bin/npm" <<'EOF'
#!/bin/sh
echo "$*" >> "$FAKE/npm.log"
case "$1" in
  pack)   # npm pack --pack-destination DIR
    f=$(node -p 'const p = require("./package.json"); p.name.slice(1).replace("/", "-") + "-" + p.version + ".tgz"')
    echo "tarball" > "$3/$f"; echo "$f" ;;
  view)   # npm view NAME@VERSION version | npm view NAME dist-tags.latest
    [ -z "${FAKE_ERROR:-}" ] || { echo "npm error code $FAKE_ERROR" >&2; exit 1; }
    [ -n "$FAKE_PUBLISHED" ] || { echo "npm error code E404" >&2; exit 1; }   # the package is not on npm at all
    case "$3" in
      version) v="${2##*@}"; for p in $FAKE_PUBLISHED; do [ "$p" != "$v" ] || echo "$v"; done ;;
      dist-tags.latest) echo "$FAKE_LATEST" ;;
    esac ;;
  publish) ;;
  *) echo "unexpected: npm $*" >&2; exit 3 ;;
esac
EOF
chmod +x "$FAKE/bin/npm"
export PATH="$FAKE/bin:$PATH"

# case NAME TAG VERSION: the plugin at VERSION, then npm-release.sh TAG; its output in $FAKE/out, its exit code in $rc
case_() {
  local name="$1" tag="$2" version="$3"
  printf '{"name": "@mimirsynth/opencode", "version": "%s"}\n' "$version" > "$FAKE/pkg/package.json"
  rm -rf "$FAKE/tgz"; : > "$FAKE/npm.log"
  echo "-- $name: tag ${tag:-none}, plugin $version, npm has ${FAKE_PUBLISHED:-nothing} (latest ${FAKE_LATEST:--})${FAKE_ERROR:+, npm answers $FAKE_ERROR}"
  rc=0; (cd "$FAKE/pkg" && bash "$ROOT/.github/npm-release.sh" "$tag" "$FAKE/tgz") > "$FAKE/out" 2>&1 || rc=$?
  sed 's/^/   | /' "$FAKE/out"
  if grep -Eq '^(dist-tag|deprecate|access|owner|unpublish)' "$FAKE/npm.log"; then echo "ran an npm command trusted publishing does not cover"; exit 1; fi
}
fail() { echo "FAIL: $*"; echo "npm log:"; cat "$FAKE/npm.log"; exit 1; }
packed_only() {   # VERSION: the tarball was written and nothing was published
  [ "$rc" = 0 ] || fail "exit code $rc"
  [ -s "$FAKE/tgz/mimirsynth-opencode-$1.tgz" ] || fail "no tarball"
  ! grep -q '^publish' "$FAKE/npm.log" || fail "published"
  grep -q "not published to npm" "$FAKE/out" || fail "does not say it was not published"
}

FAKE_PUBLISHED="0.1.1 0.1.2 0.1.3" FAKE_LATEST=0.1.3
export FAKE_PUBLISHED FAKE_LATEST FAKE_ERROR=""

case_ rc v0.16.0-rc.1 0.1.4
packed_only 0.1.4
! grep -q '^view' "$FAKE/npm.log" || fail "a release candidate does not need to ask npm"

case_ by-hand "" 0.1.4
packed_only 0.1.4

case_ final-new v0.16.0 0.1.4
[ "$rc" = 0 ] || fail "exit code $rc"
grep -qx 'publish --provenance --access public --tag latest' "$FAKE/npm.log" || fail "not published under latest with provenance"
grep -q "published @mimirsynth/opencode@0.1.4 (dist-tag latest)" "$FAKE/out" || fail "does not say what it published"

case_ final-already-published v0.16.0 0.1.3
[ "$rc" = 0 ] || fail "a version already on npm must end in success, got $rc"
! grep -q '^publish' "$FAKE/npm.log" || fail "published again"
grep -q "already on npm: nothing to publish" "$FAKE/out" || fail "does not say there was nothing to publish"
! grep -q '::warning::' "$FAKE/out" || fail "warned although latest is on it"

# v0.15.0: 0.1.3 published by a release candidate under `next`, `latest` still on 0.1.1. Green, with a warning, and nothing moved.
FAKE_LATEST=0.1.1 case_ final-already-published-latest-behind v0.15.0 0.1.3
[ "$rc" = 0 ] || fail "exit code $rc"
! grep -q '^publish' "$FAKE/npm.log" || fail "published again"
grep -q '::warning::.*latest is on 0.1.1, not 0.1.3' "$FAKE/out" || fail "no warning that latest is behind"

FAKE_PUBLISHED="" case_ final-first-publish v0.16.0 0.1.0
[ "$rc" = 0 ] || fail "exit code $rc"
grep -qx 'publish --provenance --access public --tag latest' "$FAKE/npm.log" || fail "the first version was not published"

case_ final-plugin-prerelease v0.16.0 0.2.0-beta.1
[ "$rc" = 0 ] || fail "exit code $rc"
grep -qx 'publish --provenance --access public --tag next' "$FAKE/npm.log" || fail "a pre-release plugin version goes under next"

FAKE_ERROR=E500 case_ final-registry-down v0.16.0 0.1.4
[ "$rc" != 0 ] || fail "an unanswered npm view must fail"
! grep -q '^publish' "$FAKE/npm.log" || fail "published without knowing"

# the workflow runs this script and no npm command of its own that writes to the registry
grep -q 'bash ../../.github/npm-release.sh' "$ROOT/.github/workflows/release.yml" || { echo "release.yml does not run npm-release.sh"; exit 1; }
if grep -v '^\s*#' "$ROOT/.github/workflows/release.yml" | grep -Eq 'npm (publish|dist-tag|deprecate|access)'; then
  echo "release.yml runs npm publish or dist-tag itself: that belongs in npm-release.sh"; exit 1
fi
echo "ok: npm-release.sh packs a release candidate, publishes a final release once, and never runs npm dist-tag"
