#!/usr/bin/env bash
# scripts/release.sh — cut a new image release for studio.
#
# Bumps VERSION, commits + pushes, tags vX.Y.Z, and creates a GitHub release.
# The tag push triggers .github/workflows/release-images.yml, which builds the
# 9 images on amd64 (+arm64 where applicable) and pushes them to GHCR.
#
# This script does NOT build images locally. For fast single-arch local builds
# during development, use studio-app/scripts/build-all-images.sh.
#
# Usage:
#   scripts/release.sh patch                      # 1.0.0 → 1.0.1
#   scripts/release.sh minor                      # 1.0.0 → 1.1.0
#   scripts/release.sh major                      # 1.0.0 → 2.0.0
#   scripts/release.sh 1.2.3                      # explicit
#   scripts/release.sh patch --message "Hotfix"
#   scripts/release.sh minor --notes-from CHANGELOG_NEXT.md
#   scripts/release.sh patch --dry-run
#   scripts/release.sh 1.0.0 --force              # re-cut existing tag
#
# Requirements:
#   - clean working tree
#   - on main branch
#   - gh CLI authenticated with push access

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
cd "$REPO_DIR"

# ----- args -----

BUMP_ARG="${1:-}"
NOTES_FROM=""
MESSAGE=""
DRY_RUN=0
FORCE=0

shift  # drop <bump>
while [[ $# -gt 0 ]]; do
    case "$1" in
        --notes-from) NOTES_FROM="${2:-}"; shift 2 ;;
        --message)    MESSAGE="${2:-}"; shift 2 ;;
        --dry-run)    DRY_RUN=1; shift ;;
        --force)      FORCE=1; shift ;;
        *)            echo "Unknown arg: $1" >&2; exit 1 ;;
    esac
done

if [[ -z "$BUMP_ARG" ]]; then
    cat >&2 <<EOF
Usage: $0 <bump> [--notes-from path] [--message text] [--dry-run] [--force]

<bump> is one of:
  patch                          1.0.0 → 1.0.1   (bug fix, no behavior change)
  minor                          1.0.0 → 1.1.0   (new feature, backwards-compatible)
  major                          1.0.0 → 2.0.0   (breaking change)
  X.Y.Z                          explicit version

Examples:
  $0 patch
  $0 minor --message "Add comfyui worker queue split"
  $0 patch --notes-from CHANGELOG_NEXT.md
  $0 patch --dry-run
  $0 1.0.0 --force --message "Re-cut release"

--force deletes an existing tag + GitHub release before re-creating them.
Operators who already pulled the previous images will have stale copies.

Notes (priority order):
  1. --message <text>            inline string
  2. --notes-from <path>          read from file
  3. CHANGELOG_NEXT.md            default if it exists
  4. (nothing)                    error — release notes are required
EOF
    exit 1
fi

if [[ -f VERSION ]]; then
    CURRENT_VERSION="$(tr -d '[:space:]' < VERSION)"
    if ! [[ "$CURRENT_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        echo "✗ VERSION file has unexpected shape: $CURRENT_VERSION" >&2
        exit 1
    fi
    IFS=. read -r CUR_MAJ CUR_MIN CUR_PAT <<< "$CURRENT_VERSION"
else
    CURRENT_VERSION=""
fi

case "$BUMP_ARG" in
    patch|minor|major)
        if [[ -z "$CURRENT_VERSION" ]]; then
            echo "✗ no VERSION file yet — pass an explicit X.Y.Z for the first release" >&2
            exit 1
        fi
        case "$BUMP_ARG" in
            patch) VERSION="${CUR_MAJ}.${CUR_MIN}.$((CUR_PAT + 1))" ;;
            minor) VERSION="${CUR_MAJ}.$((CUR_MIN + 1)).0" ;;
            major) VERSION="$((CUR_MAJ + 1)).0.0" ;;
        esac
        ;;
    *)
        if [[ "$BUMP_ARG" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
            VERSION="$BUMP_ARG"
        else
            echo "✗ <bump> must be patch, minor, major, or X.Y.Z (got: $BUMP_ARG)" >&2
            exit 1
        fi
        ;;
esac

TAG="v$VERSION"

# ----- helpers -----

red()    { printf '\033[31m%s\033[0m\n' "$*"; }
green()  { printf '\033[32m%s\033[0m\n' "$*"; }
yellow() { printf '\033[33m%s\033[0m\n' "$*"; }
dim()    { printf '\033[2m%s\033[0m\n' "$*"; }

step()  { printf '\n\033[36m▸\033[0m %s\n' "$*"; }
ok()    { printf '  \033[32m✓\033[0m %s\n' "$*"; }
fatal() { printf '  \033[31m✗\033[0m %s\n' "$*" >&2; exit 1; }

run() {
    if [[ "$DRY_RUN" == "1" ]]; then
        dim "    [dry-run] $*"
    else
        "$@"
    fi
}

# ----- preflight -----

step "Preflight"

command -v gh >/dev/null || fatal "gh CLI not installed"
gh auth status >/dev/null 2>&1 || fatal "gh CLI not authenticated — run 'gh auth login'"
ok "gh CLI authed"

ok "current version: ${CURRENT_VERSION:-(none — first release)}"
ok "new version:     $VERSION  ($BUMP_ARG)"

if [[ -n "$CURRENT_VERSION" && "$CURRENT_VERSION" == "$VERSION" && "$FORCE" == "0" ]]; then
    fatal "VERSION is already $VERSION — nothing to bump (use --force to re-release)"
fi

if ! git diff --quiet || ! git diff --cached --quiet; then
    fatal "working tree has uncommitted changes — commit or stash first"
fi
UNTRACKED="$(git ls-files --others --exclude-standard)"
if [[ -n "$UNTRACKED" ]]; then
    red "  ✗ untracked files present — commit or .gitignore them before releasing:" >&2
    echo "$UNTRACKED" | sed 's/^/      /' >&2
    exit 1
fi
ok "working tree clean"

BRANCH="$(git rev-parse --abbrev-ref HEAD)"
if [[ "$BRANCH" != "main" ]]; then
    fatal "must be on main branch (currently on: $BRANCH)"
fi
ok "on main"

TAG_EXISTS_LOCAL=0
TAG_EXISTS_REMOTE=0
RELEASE_EXISTS=0
if git rev-parse "$TAG" >/dev/null 2>&1; then TAG_EXISTS_LOCAL=1; fi
if git ls-remote --tags origin "refs/tags/$TAG" | grep -q "$TAG"; then TAG_EXISTS_REMOTE=1; fi
if gh release view "$TAG" >/dev/null 2>&1; then RELEASE_EXISTS=1; fi

if [[ "$FORCE" == "0" ]]; then
    [[ "$TAG_EXISTS_LOCAL" == "1" ]]  && fatal "tag $TAG already exists locally — re-run with --force to replace"
    [[ "$TAG_EXISTS_REMOTE" == "1" ]] && fatal "tag $TAG already exists on origin — re-run with --force to replace"
    [[ "$RELEASE_EXISTS" == "1" ]]    && fatal "release $TAG already published — re-run with --force to replace"
    ok "tag $TAG is free"
else
    ok "force-replace mode (existing tag/release will be deleted)"
fi

if [[ -n "$MESSAGE" ]]; then
    NOTES_SOURCE="--message"
    NOTES_BODY="$MESSAGE"
elif [[ -n "$NOTES_FROM" ]]; then
    [[ -f "$NOTES_FROM" ]] || fatal "notes file not found: $NOTES_FROM"
    NOTES_SOURCE="$NOTES_FROM"
    NOTES_BODY="$(cat "$NOTES_FROM")"
elif [[ -f CHANGELOG_NEXT.md ]]; then
    NOTES_SOURCE="CHANGELOG_NEXT.md"
    NOTES_BODY="$(cat CHANGELOG_NEXT.md)"
else
    fatal "no release notes — pass --message, --notes-from, or create CHANGELOG_NEXT.md"
fi
ok "notes from: $NOTES_SOURCE"

# ----- nuke existing release/tag if --force -----

if [[ "$FORCE" == "1" ]]; then
    step "Deleting existing $TAG (force mode)"
    if [[ "$RELEASE_EXISTS" == "1" ]]; then
        run gh release delete "$TAG" --yes --cleanup-tag
        ok "deleted GitHub release $TAG"
    elif [[ "$TAG_EXISTS_REMOTE" == "1" ]]; then
        run git push origin ":refs/tags/$TAG"
        ok "deleted remote tag $TAG"
    fi
    if [[ "$TAG_EXISTS_LOCAL" == "1" ]]; then
        run git tag -d "$TAG"
        ok "deleted local tag $TAG"
    fi
    if [[ "$CURRENT_VERSION" == "$VERSION" ]]; then
        ok "VERSION unchanged — skipping bump commit"
        SKIP_VERSION_COMMIT=1
    fi
fi

SKIP_VERSION_COMMIT="${SKIP_VERSION_COMMIT:-0}"

# ----- bump VERSION -----

step "Bumping VERSION → $VERSION"
if [[ "$DRY_RUN" == "1" ]]; then
    dim "    [dry-run] echo $VERSION > VERSION"
else
    echo "$VERSION" > VERSION
fi
ok "VERSION written"

# ----- commit + push -----

if [[ "$SKIP_VERSION_COMMIT" == "1" ]]; then
    step "Skipping commit (VERSION unchanged in --force mode)"
else
    step "Committing + pushing"
    run git add VERSION
    run git commit -m "Release v$VERSION"
    run git push origin main
    ok "committed and pushed"
fi

# ----- tag -----

step "Tagging $TAG"
run git tag -a "$TAG" -m "$TAG"
run git push origin "$TAG"
ok "tagged and pushed — CI will build images now"

# ----- create release -----

step "Creating GitHub release $TAG"

INSTALL_SNIPPET=$(cat <<EOF

## Images

All 9 images published to GHCR with tags \`:${VERSION}\` and \`:latest\`.

\`\`\`sh
docker pull ghcr.io/selfhosthub/studio-api:${VERSION}
docker pull ghcr.io/selfhosthub/studio-ui:${VERSION}
docker pull ghcr.io/selfhosthub/studio-worker-general:${VERSION}
docker pull ghcr.io/selfhosthub/studio-worker-transfer:${VERSION}
docker pull ghcr.io/selfhosthub/studio-worker-video:${VERSION}
docker pull ghcr.io/selfhosthub/studio-worker-comfyui:${VERSION}
docker pull ghcr.io/selfhosthub/studio-worker-audio:${VERSION}
docker pull ghcr.io/selfhosthub/studio-core:${VERSION}
docker pull ghcr.io/selfhosthub/studio-full:${VERSION}
\`\`\`

Operators normally pull these via \`studio-console\` rather than directly.
EOF
)
FULL_NOTES="${NOTES_BODY}${INSTALL_SNIPPET}"

if [[ "$DRY_RUN" == "1" ]]; then
    dim "    [dry-run] gh release create $TAG --title $TAG --notes <body>"
    echo
    yellow "── dry-run notes preview ──"
    echo "$FULL_NOTES"
    ok "release would be published (dry-run)"
else
    gh release create "$TAG" --title "$TAG" --notes "$FULL_NOTES"
    ok "release published"
fi

# ----- post-release housekeeping -----

if [[ -f CHANGELOG_NEXT.md && "$NOTES_SOURCE" == "CHANGELOG_NEXT.md" ]]; then
    step "Clearing CHANGELOG_NEXT.md"
    if [[ "$DRY_RUN" == "0" ]]; then
        : > CHANGELOG_NEXT.md
        git add CHANGELOG_NEXT.md
        git commit -m "Reset CHANGELOG_NEXT after v$VERSION"
        git push origin main
    fi
    ok "cleared and pushed"
fi

echo
if [[ "$DRY_RUN" == "1" ]]; then
    yellow "✓ dry-run complete — nothing was changed"
    echo
    echo "    Re-run without --dry-run to release v$VERSION."
else
    green "✓ v$VERSION released"
    echo
    echo "    https://github.com/selfhosthub/studio/releases/tag/$TAG"
    echo
    echo "    CI is now building images. Watch progress:"
    echo "    gh run watch"
fi
echo
