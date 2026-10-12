#!/usr/bin/env bash
# Build the FAIRSCAPE Studio demo image from the sibling checkouts.
#
#   deploy/build-image.sh [TAG]        # default tag: fairscape-studio:local
#
# Each repo goes in as `git archive` of the ref named below — committed code
# only, never a checkout's uncommitted edits. The nf-fairscape plugin is taken
# from ~/.nextflow/plugins, where `make install` in nf-fairscape puts it.
set -euo pipefail
TAG=${1:-fairscape-studio:local}
HERE=$(cd "$(dirname "$0")" && pwd)
STUDIO=$(dirname "$HERE")
ROOT=${FAIRSCAPE_REPOS:-$(dirname "$STUDIO")}
PLUGIN=${NF_FAIRSCAPE_PLUGIN:-$HOME/.nextflow/plugins/nf-fairscape-0.2.0}

# repo  ref (HEAD = whatever is checked out)
REPOS="
fairscape_models HEAD
fairscape_conversion HEAD
fairscape_artifacts HEAD
AIreadiness-grader HEAD
snakemake-report-plugin-fairscape HEAD
rocrate_studio HEAD
"

CTX=$(mktemp -d)
trap 'rm -rf "$CTX"' EXIT
mkdir -p "$CTX/src" "$CTX/plugins"
while read -r repo ref; do
  [ -z "$repo" ] && continue
  dir=$( [ "$repo" = rocrate_studio ] && echo "$STUDIO" || echo "$ROOT/$repo" )
  mkdir -p "$CTX/src/$repo"
  git -C "$dir" archive "$ref" | tar -x -C "$CTX/src/$repo"
  echo "$repo $(git -C "$dir" rev-parse --abbrev-ref HEAD)@$(git -C "$dir" rev-parse --short "$ref")"
done <<< "$REPOS"
cp -r "$PLUGIN" "$CTX/plugins/"
cp "$HERE/Dockerfile" "$CTX/"

docker build -t "$TAG" "$CTX"
