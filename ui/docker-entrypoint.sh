#!/bin/sh
# ui/docker-entrypoint.sh
#
# Generate /app/public/__env.js so the browser can read runtime config.
# NEXT_PUBLIC_* vars are inlined at build time by Next.js, which means
# the Docker image would be tied to a single API URL.  This script runs
# at container start and writes the actual values into a JS file that
# the client loads before React hydrates.

cat > /app/public/__env.js <<EOF
window.__ENV = {
  NEXT_PUBLIC_API_URL: "${NEXT_PUBLIC_API_URL}",
  NEXT_PUBLIC_WS_URL: "${NEXT_PUBLIC_WS_URL}"
};
EOF

exec "$@"
