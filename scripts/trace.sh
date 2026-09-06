#!/usr/bin/env bash
# Requirements trace with OpenFastTrace: fails when a requirement in docs/requirements.md has no [impl->req~...] tag.
set -euo pipefail
cd "$(dirname "$0")/.."
VERSION=4.9.0
SHA256=d4ed42503ae066f51d55c3aad7c6e4b16acb80365921951ef5a065a4dc3d94f3
JAR="${OFT_JAR:-${XDG_CACHE_HOME:-$HOME/.cache}/openfasttrace-$VERSION.jar}"
if [ ! -f "$JAR" ]; then
  mkdir -p "$(dirname "$JAR")"
  curl -sSL -o "$JAR" "https://github.com/itsallcode/openfasttrace/releases/download/$VERSION/openfasttrace-$VERSION.jar"
fi
echo "$SHA256  $JAR" | sha256sum -c --quiet
# ponytail: OFT's tag importer knows no .css; the stylesheet is fed through a .c-named symlink so its /* [impl->...] */ tags count
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
ln -s "$PWD/site/style.css" "$tmp/style.css.c"
java -jar "$JAR" trace -o plain "$@" docs site scripts "$tmp"
