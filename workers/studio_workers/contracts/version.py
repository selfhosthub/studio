# workers/studio_workers/contracts/version.py

# Workers component version, single source. Stamped by dev/version-bump-rollup.sh
# --apply; pyproject reads it as the package version; the worker sends it at
# registration and the API (which bakes this contracts tree) enforces it.
WORKERS_VERSION = "1.6.0"
