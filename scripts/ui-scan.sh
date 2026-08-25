#!/usr/bin/env bash
# =============================================================================
# ui-scan.sh -- design-system snapshot of cbshome's frontend.
#
# The deployed frontend container is a static nginx image (no node, no source),
# so the scan cannot run inside it. But the frontend SOURCE already lives on the
# host in the managed checkout that `cbshome update` keeps in sync with GitHub:
#   /opt/cbshome/repo/frontend
#
# So we do NOT clone and do NOT touch the running stack. We run a throwaway
# node container over that existing checkout: it copies the source in (the host
# copy is never modified), installs deps, runs the extractor, and writes
# observed.yaml back to the host. The container is discarded on exit.
#
# RUN ON THE SERVER, AS ROOT, with extractor.mjs next to this script:
#   ./ui-scan.sh
#
# To snapshot newer code, run `cbshome update` first (your normal flow), then this.
# OUTPUT: ./ui-scan-out/observed.yaml
# =============================================================================
set -euo pipefail

INSTALL_BASE="/opt/cbshome"
REPO_DIR="${INSTALL_BASE}/repo"
FE_SRC="${REPO_DIR}/frontend"     # managed checkout, kept in sync by cbshome update
REPO="aivis-one/cbshome"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXTRACTOR="${SCRIPT_DIR}/extractor.mjs"
OUT_DIR="$(pwd)/ui-scan-out"

[ -f "$EXTRACTOR" ] || { echo "ERROR: extractor.mjs not found next to this script ($EXTRACTOR)" >&2; exit 1; }
[ -d "$FE_SRC/src" ] || { echo "ERROR: frontend source not found at $FE_SRC/src" >&2; exit 1; }
command -v docker >/dev/null 2>&1 || { echo "ERROR: docker is not available" >&2; exit 1; }
mkdir -p "$OUT_DIR"

# Provenance only: which branch/commit the managed checkout is on.
REF="$(git -C "$REPO_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)"
[ "$REF" = "HEAD" ] && REF="$(git -C "$REPO_DIR" rev-parse --short HEAD 2>/dev/null || echo unknown)"

# Pick the tsconfig that actually declares path aliases (Vite splits these into
# tsconfig.app.json while tsconfig.json only holds project references).
TSCONFIG="tsconfig.json"
for c in tsconfig.app.json tsconfig.json; do
  if [ -f "$FE_SRC/$c" ] && grep -q '"paths"' "$FE_SRC/$c"; then TSCONFIG="$c"; break; fi
done

echo ">> scanning ${REPO}@${REF} from ${FE_SRC} (tsconfig: ${TSCONFIG}) ..."

docker run --rm \
  -v "$FE_SRC":/srcro:ro \
  -v "$EXTRACTOR":/extractor.mjs:ro \
  -v "$OUT_DIR":/out \
  -e REPO="$REPO" -e REF="$REF" -e TSCONFIG="$TSCONFIG" \
  node:22-slim bash -euc '
    # Work on a copy so the host checkout is never modified.
    mkdir -p /build
    cp -a /srcro/. /build/
    rm -rf /build/node_modules /build/dist
    cd /build
    cp /extractor.mjs ./__ui_extractor.mjs

    echo ">> installing frontend deps ..."
    npm install --no-audit --no-fund --silent

    # Extractor-only deps (typescript, vue and the @vue compilers come from the
    # project itself via the install above).
    echo ">> installing extractor deps ..."
    npm install --no-save --no-audit --no-fund --silent vue-component-meta@^2 js-yaml@^4

    echo ">> extracting ..."
    node ./__ui_extractor.mjs . /out/observed.yaml --repo "$REPO" --ref "$REF" --tsconfig "$TSCONFIG"
  '

echo ">> done -> ${OUT_DIR}/observed.yaml"
