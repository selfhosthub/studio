#!/usr/bin/env bash
# scripts/codeql-scan.sh — run CodeQL security-extended locally on python (api/)
# and javascript (ui/), using the shared config in .github/codeql/.
#
# Databases go to /tmp; SARIF to /tmp; both are gitignored/dockerignored anyway.
# Exits non-zero if the parser flags any error-severity finding.
#
# Requires: codeql CLI on PATH. Skips gracefully if not installed.
#   brew install --cask codeql
#
# Usage:
#   scripts/codeql-scan.sh            # both languages
#   scripts/codeql-scan.sh python     # one language
#   scripts/codeql-scan.sh javascript

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
cd "$REPO_DIR"

CONFIG=".github/codeql/config.yml"
PARSER="scripts/parse-codeql-sarif.py"

if ! command -v codeql >/dev/null 2>&1; then
    echo "▸ codeql CLI not installed — skipping scan (brew install --cask codeql)"
    exit 0
fi
[[ -f "$CONFIG" ]] || { echo "✗ missing $CONFIG" >&2; exit 1; }
[[ -f "$PARSER" ]] || { echo "✗ missing $PARSER" >&2; exit 1; }

# Suite per language; both use security-extended to match the GitHub workflow.
declare -A SUITE=(
    [python]="codeql/python-queries:codeql-suites/python-security-extended.qls"
    [javascript]="codeql/javascript-queries:codeql-suites/javascript-security-extended.qls"
)

LANGS=("$@")
[[ ${#LANGS[@]} -eq 0 ]] && LANGS=(python javascript)

echo "▸ Downloading query packs (no-op if cached)"
codeql pack download codeql/python-queries codeql/javascript-queries >/dev/null

rc=0
for lang in "${LANGS[@]}"; do
    [[ -n "${SUITE[$lang]:-}" ]] || { echo "✗ unknown language: $lang" >&2; exit 1; }
    db="/tmp/codeql-${lang}-db"
    sarif="/tmp/${lang}.sarif"

    echo "▸ [$lang] creating database"
    codeql database create "$db" --language="$lang" --source-root=. \
        --codescanning-config="$CONFIG" --threads=0 --overwrite >/dev/null

    echo "▸ [$lang] analyzing (security-extended)"
    codeql database analyze "$db" "${SUITE[$lang]}" --threads=0 \
        --format=sarif-latest --output="$sarif" >/dev/null

    # Parser exits 1 on any error-severity finding; keep going, remember failure.
    python3 "$PARSER" "$sarif" "$lang" "$CONFIG" || rc=1

    rm -rf "$db"
done

exit $rc
