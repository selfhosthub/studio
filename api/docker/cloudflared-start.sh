#!/bin/bash
# api/docker/cloudflared-start.sh
# Launch cloudflared with the token from /workspace/.env. Read fresh on
# every program start so studio-console's CF wizard can write the token
# and `supervisorctl start cloudflared` picks it up without a supervisord
# restart.
#
# supervisord's %(ENV_X)s interpolation happens at conf-load time and
# can't be re-evaluated after token-write, hence this wrapper.
set -euo pipefail

WORKSPACE_ENV="/workspace/.env"

if [ ! -f "$WORKSPACE_ENV" ]; then
    echo "FATAL: $WORKSPACE_ENV not found - cloudflared cannot read its token." >&2
    exit 1
fi

TOKEN="$(grep -E '^CLOUDFLARE_TUNNEL_TOKEN=' "$WORKSPACE_ENV" | head -1 | cut -d= -f2- | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//")"

if [ -z "$TOKEN" ]; then
    echo "FATAL: CLOUDFLARE_TUNNEL_TOKEN not set in $WORKSPACE_ENV." >&2
    echo "       Run studio-console → Cloudflare → Setup to configure the tunnel." >&2
    exit 1
fi

exec cloudflared tunnel --no-autoupdate run --token "$TOKEN"
