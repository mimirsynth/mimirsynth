#!/usr/bin/env bash
# What the Release workflow does with an npm plugin (#432), run in the plugin's folder. Usage: npm-release.sh [TAG [OUT]]
# - No tag (the workflow started by hand) or a pre-release tag (vX.Y.Z-rc.N): packs the plugin into folder OUT (default: the current
#   one) and publishes nothing. A release candidate is tried from that tarball, which the workflow keeps as an artifact of the run, or
#   from the repository.
# - A final tag (vX.Y.Z): publishes the plugin's version, with provenance, through npm trusted publishing (OIDC). It goes under `latest`,
#   or under `next` when the plugin's own version is a pre-release (npm refuses one under `latest`). Trusted publishing authenticates
#   `npm publish` and nothing else, so this script runs no other command that writes to npm (dist-tag, deprecate, access): without a
#   token they fail with E401. A version that is already on npm is left as it is, and the job ends in success.
set -Eeuo pipefail
tag="${1:-}"; out="${2:-.}"
name=$(node -p 'require("./package.json").name')
version=$(node -p 'require("./package.json").version')

case "$tag" in
  "") why="the workflow was started by hand" ;;
  *-*) why="$tag is a pre-release: only a final release publishes to npm" ;;
  *) why="" ;;
esac
if [ -n "$why" ]; then
  mkdir -p "$out"
  npm pack --pack-destination "$out"
  file="$out/$(printf '%s' "${name#@}" | tr / -)-$version.tgz"   # what npm pack names it: @scope/name 1.2.3 → scope-name-1.2.3.tgz
  [ -s "$file" ] || { echo "::error::npm pack did not write $file"; exit 1; }
  echo "::notice::$name@$version packed as $(basename "$file"), not published to npm ($why)"
  exit 0
fi

dist=latest
case "$version" in *-*) dist=next ;; esac
err=$(mktemp); trap 'rm -f "$err"' EXIT
if ! have=$(npm view "$name@$version" version 2>"$err"); then
  # E404: the package is not on npm at all (an unknown version of a known package answers nothing, with success)
  grep -q E404 "$err" || { cat "$err" >&2; echo "::error::could not ask npm whether $name@$version is published"; exit 1; }
  have=""
fi
if [ "$have" = "$version" ]; then
  echo "::notice::$name@$version is already on npm: nothing to publish"
  latest=$(npm view "$name" dist-tags.latest 2>/dev/null || true)
  if [ "$dist" = latest ] && [ "$latest" != "$version" ]; then
    # only a version published before #432 (by a release candidate, under `next`) can be here; the release itself is fine
    echo "::warning::$name: the dist-tag latest is on ${latest:-no version}, not $version. Trusted publishing cannot move it; someone with publish rights on the scope runs: npm dist-tag add $name@$version latest"
  fi
  exit 0
fi
npm publish --provenance --access public --tag "$dist"
echo "::notice::published $name@$version (dist-tag $dist)"
