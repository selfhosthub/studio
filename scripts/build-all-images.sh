#!/usr/bin/env bash
# scripts/build-all-images.sh — build all 9 studio images locally for pre-release testing.
#
# Single-arch (host platform) builds that mirror the CI matrix in
# .github/workflows/release-images.yml. Run this before scripts/release.sh to
# confirm every image builds cleanly; it does NOT push. CI does the real
# multi-arch build + push to GHCR on tag.
#
# Usage:
#   scripts/build-all-images.sh                 # tag with VERSION file contents
#   scripts/build-all-images.sh 1.2.3           # explicit tag
#   scripts/build-all-images.sh --only api,ui   # build a subset
#   scripts/build-all-images.sh --no-cache      # force a clean rebuild
#   JOBS=4 scripts/build-all-images.sh          # cap concurrent builds (default: nproc)

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
cd "$REPO_DIR"

REGISTRY="ghcr.io/selfhosthub"

# ----- args -----

VERSION=""
ONLY=""
NO_CACHE=""
JOBS="${JOBS:-$(command -v nproc >/dev/null && nproc || sysctl -n hw.ncpu)}"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --only)     ONLY="${2:-}"; shift 2 ;;
        --no-cache) NO_CACHE="--no-cache"; shift ;;
        -*)         echo "Unknown arg: $1" >&2; exit 1 ;;
        *)          VERSION="$1"; shift ;;
    esac
done

[[ -z "$VERSION" ]] && VERSION="$(cat VERSION)"

# name|context|dockerfile|contracts  — mirrors the CI build matrix.
# contracts=1 passes --build-context contracts=workers/studio_workers/contracts
# (a named build context, not an image); the Dockerfile's `COPY --from=contracts`
# needs it. Worker images carry contracts inside the package tree.
IMAGES=(
    "studio-api|api|api/Dockerfile|1"
    "studio-ui|ui|ui/Dockerfile|0"
    "studio-worker-general|workers|workers/studio_workers/engines/general/Dockerfile|0"
    "studio-worker-transfer|workers|workers/studio_workers/engines/transfer/Dockerfile|0"
    "studio-worker-video|workers|workers/studio_workers/engines/video/Dockerfile|0"
    "studio-worker-comfyui|workers|workers/studio_workers/engines/comfyui/Dockerfile|0"
    "studio-worker-audio|workers|workers/studio_workers/engines/audio/Dockerfile|0"
    "studio-core|.|Dockerfile|0"
    "studio-full|.|Dockerfile.full|0"
)

# Combined images bake in the release version + the pinned console version.
# CI passes STUDIO_VERSION (the release tag) and STUDIO_CONSOLE_VERSION (from
# versions.json); both ARGs have no default and fail the build if empty.
CONSOLE_VERSION="$(grep -oE '"studio_console"[^,}]*' versions.json | grep -oE '[0-9]+\.[0-9]+\.[0-9]+')"
COMBINED_ARGS="--build-arg STUDIO_VERSION=$VERSION --build-arg STUDIO_CONSOLE_VERSION=$CONSOLE_VERSION"
declare -A BUILD_ARGS=(
    [studio-core]="$COMBINED_ARGS"
    [studio-full]="$COMBINED_ARGS"
)

# ----- build -----

LOG_DIR="$(mktemp -d -t studio-build-XXXXXX)"
echo "Building up to $JOBS image(s) in parallel — logs in $LOG_DIR"
echo

build_one() {
    local name="$1" context="$2" dockerfile="$3" contracts="$4"
    local log="$LOG_DIR/$name.log"

    local ctx_arg=""
    [[ "$contracts" == "1" ]] && ctx_arg="--build-context contracts=workers/studio_workers/contracts"

    echo "==> Building $REGISTRY/$name:$VERSION"
    # shellcheck disable=SC2086
    if docker build $NO_CACHE $ctx_arg ${BUILD_ARGS[$name]:-} \
        -t "$REGISTRY/$name:$VERSION" \
        -f "$dockerfile" "$context" >"$log" 2>&1; then
        echo "    ok   $name"
    else
        echo "    FAIL $name (see $log)"
        return 1
    fi
}

pids=()
status=0
for entry in "${IMAGES[@]}"; do
    IFS='|' read -r name context dockerfile contracts <<< "$entry"

    if [[ -n "$ONLY" ]]; then
        short="${name#studio-}"
        [[ ",$ONLY," == *",$short,"* || ",$ONLY," == *",$name,"* ]] || continue
    fi

    build_one "$name" "$context" "$dockerfile" "$contracts" &
    pids+=($!)

    # Throttle: wait for a slot when at the concurrency cap.
    while [[ "$(jobs -rp | wc -l)" -ge "$JOBS" ]]; do wait -n; done
done

# Reap remaining jobs, capturing any failure.
built=()
i=0
for entry in "${IMAGES[@]}"; do
    IFS='|' read -r name _ _ _ <<< "$entry"
    if [[ -n "$ONLY" ]]; then
        short="${name#studio-}"
        [[ ",$ONLY," == *",$short,"* || ",$ONLY," == *",$name,"* ]] || continue
    fi
    if wait "${pids[$i]}"; then built+=("$name"); else status=1; fi
    i=$((i + 1))
done

echo
if [[ $status -eq 0 ]]; then
    echo "Built ${#built[@]} image(s) at tag $VERSION:"
    printf '  %s\n' "${built[@]}"
else
    echo "Some builds FAILED — logs in $LOG_DIR"
fi

exit $status