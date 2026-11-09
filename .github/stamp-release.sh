#!/usr/bin/env bash
# Writes the release's version into update.sh, install.sh and install.ps1 of folder DIR (default: the current one) before release.yml
# publishes them (#413). With it, update.sh never takes an older release's update.sh for itself, and the installers know which
# update.sh to give an existing installation. In the repository they say "dev". Usage: stamp-release.sh VERSION [DIR]
set -Eeuo pipefail
v="${1#v}"; dir="${2:-.}"
[[ "$v" =~ ^[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.-]+)?$ ]] || { echo "not a version: $v" >&2; exit 1; }
for f in update.sh install.sh; do
  [ "$(grep -c '^RELEASE="dev"' "$dir/$f")" = 1 ] || { echo "$f: no single RELEASE=\"dev\" line" >&2; exit 1; }
  sed -i "s/^RELEASE=\"dev\"/RELEASE=\"$v\"/" "$dir/$f"
done
[ "$(grep -c '^\$Release = "dev"' "$dir/install.ps1")" = 1 ] || { echo 'install.ps1: no single $Release = "dev" line' >&2; exit 1; }
sed -i "s/^\\\$Release = \"dev\"/\$Release = \"$v\"/" "$dir/install.ps1"
grep -q "^RELEASE=\"$v\"" "$dir/update.sh" && grep -q "^RELEASE=\"$v\"" "$dir/install.sh" && grep -q "^\\\$Release = \"$v\"" "$dir/install.ps1" \
  || { echo "the version was not written" >&2; exit 1; }
echo "update.sh, install.sh and install.ps1 say $v"
